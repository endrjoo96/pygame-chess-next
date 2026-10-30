import random
from dataclasses import dataclass
from enum import Enum

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import id_to_xy, xy_to_id
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState
from processors.movement_processor import process_possible_basic_moves
from utils.run_config import GAME_SEED, RUN_MODE, RunMode


class GameActionType(Enum):
    MOVE = "move"
    PROMOTE = "promote"
    TELEPORT = "teleport"
    RETURN_TO_START = "return_to_start"
    APPLY_PASSIVE = "apply_passive"
    RESURRECT = "resurrect"


@dataclass(frozen=True)
class GameAction:
    """Jedna kompletna decyzja domenowa, niezależna od sekwencji kliknięć UI."""

    action_type: GameActionType
    source: int
    destination: int = 0
    card_index: int = -1
    captured_color: COLOR = COLOR.EMPTY
    captured_index: int = -1


class GameRules:
    """Mutowalne reguły przejścia stanu, niezależne od interfejsu gry."""

    @classmethod
    def apply_action(cls, state: GameState, action: GameAction) -> GameState:
        """Zastosowuje legalną akcję do stanu przekazanego przez wywołującego."""
        rng = random.Random(GAME_SEED if GAME_SEED is not None else 0)
        rng.setstate(state.random_state)
        state.selected_piece_position = action.source
        state.selected_card = (
            (state.current_turn, action.card_index)
            if action.card_index >= 0 else None
        )

        if action.action_type == GameActionType.MOVE:
            target = state.pieces_locations[action.destination]
            if target.exists() and not cls._is_rook_tower_throw_selected(state):
                cls._capture_piece(state, target)
            cls._move_piece(state, action.destination, rng)
        elif action.action_type == GameActionType.APPLY_PASSIVE:
            enchantment = state.get_cards_for(state.current_turn)[action.card_index]
            cls._apply_selected_passive(state, action.source, enchantment)
        elif action.action_type == GameActionType.PROMOTE:
            cls._promote_piece(state, action.source)
        elif action.action_type == GameActionType.TELEPORT:
            state.pieces_locations[action.source], state.pieces_locations[action.destination] = (
                state.pieces_locations[action.destination],
                state.pieces_locations[action.source],
            )
            cls._discard_selected_card(state)
            state.selected_card = None
            state.selected_piece_position = 0
            cls._end_turn(state)
        elif action.action_type == GameActionType.RETURN_TO_START:
            cls._move_piece(state, action.destination, rng)
        elif action.action_type == GameActionType.RESURRECT:
            piece = state.get_captured_for(action.captured_color).pop(action.captured_index)
            state.pieces_locations[action.destination] = piece
            cls._discard_selected_card(state)
            state.selected_card = None
            state.selected_captured_piece = None
            state.resurrection_moves = []
            state.selected_piece_position = 0
            cls._end_turn(state)

        state.random_state = rng.getstate()
        return state

    @staticmethod
    def _discard_selected_card(state):
        card_color, card_index = state.selected_card
        state.get_cards_for(card_color).pop(card_index)

    @classmethod
    def _promote_piece(cls, state, position):
        card = state.get_cards_for(state.current_turn)[state.selected_card[1]]
        piece = state.pieces_locations[position]
        piece.promote_to(card.get_card_type().promoted_piece_type)
        stun_turns = card.get_rate_stun_after_use()
        piece.set_stunned_for_turns(stun_turns)
        piece.add_stun_effect(card, stun_turns)
        cls._discard_selected_card(state)
        state.selected_card = None
        state.selected_piece_position = 0
        cls._end_turn(state)

    @classmethod
    def _apply_selected_passive(cls, state, position, enchantment):
        delay = enchantment.get_rate_delay_before_use()
        if delay > 0:
            piece = state.pieces_locations[position]
            piece.add_delayed_enchantment(
                enchantment, state.turns_started[state.current_turn] + delay)
        else:
            cls._apply_passive_enchantment(state, position, enchantment)

        cls._discard_selected_card(state)
        state.selected_card = None
        state.selected_captured_piece = None
        state.selected_piece_position = 0
        cls._end_turn(state)

    @staticmethod
    def _apply_passive_enchantment(state, position, enchantment):
        if enchantment.get_card_type() in (
            EnchantmentCardType.PAWN_DETONATION,
            EnchantmentCardType.PAWN_DETONATION_DELAYED_1,
            EnchantmentCardType.PAWN_DETONATION_DELAYED_2,
        ):
            GameRules._detonate_pawn(state, position)
        else:
            state.pieces_locations[position].set_enchantment(enchantment)

    @staticmethod
    def _detonate_pawn(state, position):
        x, y = id_to_xy(position)
        for target_y in range(max(0, y - 1), min(7, y + 1) + 1):
            for target_x in range(max(0, x - 1), min(7, x + 1) + 1):
                if target_x == x and target_y == y:
                    continue
                target_position = xy_to_id(target_x, target_y)
                target_piece = state.pieces_locations[target_position]
                if target_piece.exists():
                    GameRules._capture_piece(state, target_piece)
                    state.pieces_locations[target_position] = Piece()

        state.pieces_locations[position] = Piece()
        state.selected_piece_position = 0

    @classmethod
    def _end_turn(cls, state):
        state.current_turn = COLOR.BLACK if state.current_turn == COLOR.WHITE else COLOR.WHITE
        state.turns_started[state.current_turn] += 1
        cls._apply_ready_passive_enchantments(state, state.current_turn)

    @classmethod
    def _apply_ready_passive_enchantments(cls, state, color):
        turn = state.turns_started[color]
        for position, piece in state.pieces_locations.items():
            if not piece.exists() or piece.get_color() != color:
                continue
            for enchantment in piece.get_delayed_enchantments_ready_at(turn):
                if not piece.exists():
                    break
                cls._apply_passive_enchantment(state, position, enchantment)

    @staticmethod
    def _capture_piece(state, piece):
        piece.clear_effects()
        captured = (
            state.captured_black
            if piece.get_color() == COLOR.WHITE else state.captured_white
        )
        captured.append(piece)

    @classmethod
    def _move_piece(cls, state, destination, rng):
        source_position = state.selected_piece_position
        if source_position <= 0:
            return

        moving_color = state.current_turn
        first_double_move = (
            cls._selected_card_is_double_move(state) and state.double_move_step == 0
        )
        if state.double_move_step == 0:
            cls._advance_stun_effects(state, moving_color)

        _, card_index, card_deck, used_card = cls._get_used_card(state, moving_color)
        piece = state.pieces_locations[source_position]
        if (
            used_card is not None
            and used_card.get_card_type() == EnchantmentCardType.ROOK_TOWER_THROW
        ):
            cls._capture_rook_throw_route(state, source_position, destination)

        state.pieces_locations[source_position] = Piece()
        state.pieces_locations[destination] = piece
        collected_board_card = cls._collect_board_card(state, destination, moving_color)

        if not first_double_move and used_card is not None and used_card.consume_use() == 0:
            card_deck.pop(card_index)
        cls._apply_move_stun(piece, used_card)

        collected_board_card = (
            collected_board_card or state.double_move_collected_board_card
        )
        if first_double_move and cls._continue_double_move(
            state, piece, destination, used_card, card_deck, card_index,
            collected_board_card,
        ):
            return

        cls._finish_piece_move(state, collected_board_card, rng)

    @staticmethod
    def _get_used_card(state, moving_color):
        if state.selected_card is None or state.selected_card[0] != moving_color:
            return None, None, None, None
        card_color, card_index = state.selected_card
        card_deck = state.get_cards_for(card_color)
        if not 0 <= card_index < len(card_deck):
            return card_color, card_index, card_deck, None
        return card_color, card_index, card_deck, card_deck[card_index]

    @classmethod
    def _capture_rook_throw_route(cls, state, source_position, destination):
        source_x, source_y = id_to_xy(source_position)
        destination_x, destination_y = id_to_xy(destination)
        step_x = (destination_x > source_x) - (destination_x < source_x)
        step_y = (destination_y > source_y) - (destination_y < source_y)
        target_x, target_y = source_x + step_x, source_y + step_y
        while (target_x, target_y) != (destination_x, destination_y):
            target_position = xy_to_id(target_x, target_y)
            target_piece = state.pieces_locations[target_position]
            if target_piece.exists():
                cls._capture_piece(state, target_piece)
                state.pieces_locations[target_position] = Piece()
            target_x += step_x
            target_y += step_y

        target_piece = state.pieces_locations[destination]
        if target_piece.exists():
            cls._capture_piece(state, target_piece)

    @staticmethod
    def _collect_board_card(state, destination, moving_color):
        collected = (
            state.board_card_available
            and destination == state.board_card_position
        )
        if collected:
            GameRules._add_card_for(
                state, moving_color, state.board_enchantment)
            state.board_card_available = False
        return collected

    @staticmethod
    def _add_card_for(state, color, card):
        deck = state.get_cards_for(color)
        if card.is_reusable():
            matching_card = next(
                (
                    existing for existing in deck
                    if existing.get_card_type() == card.get_card_type()
                    and existing.is_reusable()
                ),
                None,
            )
            if matching_card is not None:
                matching_card.add_uses(card.get_remaining_uses())
                return True
        if len(deck) >= 8:
            return False
        deck.append(card)
        return True

    @staticmethod
    def _apply_move_stun(piece, used_card):
        passive_enchantments = piece.get_passive_enchantments()
        stun_turns = (
            used_card.get_rate_stun_after_use()
            if used_card is not None
            else sum(
                enchantment.get_rate_stun_after_use()
                for enchantment in passive_enchantments
            )
        )
        if stun_turns <= 0:
            return

        piece.set_stunned_for_turns(stun_turns)
        stun_enchantments = (
            [used_card]
            if used_card is not None and used_card.get_rate_stun_after_use() > 0
            else passive_enchantments
        )
        for enchantment in stun_enchantments:
            if enchantment.get_rate_stun_after_use() > 0:
                piece.add_stun_effect(enchantment, stun_turns)

    @classmethod
    def _continue_double_move(
        cls, state, piece, destination, used_card, card_deck, card_index,
        collected_board_card,
    ):
        state.double_move_step = 1
        state.double_move_collected_board_card = collected_board_card
        state.selected_piece_position = destination
        moves = process_possible_basic_moves(
            piece, id_to_xy(destination), state.pieces_locations)
        if moves:
            return True
        if used_card is not None and used_card.consume_use() == 0:
            card_deck.pop(card_index)
        return False

    @classmethod
    def _finish_piece_move(cls, state, collected_board_card, rng):
        cls._end_turn(state)
        if collected_board_card and state.pending_board_card_delay is None:
            cls._schedule_next_board_card(state, rng)
        elif (
            state.pending_board_card_delay is not None
            and state.pending_board_card_delay > 0
        ):
            state.pending_board_card_delay -= 1
        if (
            state.pending_board_card_delay == 0
            and not state.board_card_available
        ):
            cls._place_next_board_card(state, rng)

        state.selected_piece_position = 0
        state.selected_card = None
        state.selected_captured_piece = None
        state.double_move_step = 0
        state.double_move_collected_board_card = False

    @classmethod
    def _schedule_next_board_card(cls, state, rng):
        state.board_card_available = False
        state.pending_board_card_delay = (
            0 if RUN_MODE is RunMode.DEBUG else rng.randint(1, 5)
        )
        if state.pending_board_card_delay == 0:
            cls._place_next_board_card(state, rng)

    @staticmethod
    def _place_next_board_card(state, rng):
        empty_positions = [
            position for position in range(1, 65)
            if not state.pieces_locations[position].exists()
        ]
        state.board_card_position = rng.choice(empty_positions)
        state.board_enchantment = EnchantmentCardType.create_random(rng)
        state.board_card_available = True
        state.pending_board_card_delay = (
            0 if RUN_MODE is RunMode.DEBUG else rng.randint(1, 5)
        )

    @staticmethod
    def _advance_stun_effects(state, color):
        for piece in state.pieces_locations.values():
            if piece.exists() and piece.get_color() == color:
                piece.advance_stun_effects()

    @staticmethod
    def _selected_card_is_double_move(state):
        if state.selected_card is None or state.selected_card[0] != state.current_turn:
            return False
        card_color, card_index = state.selected_card
        deck = state.get_cards_for(card_color)
        return (
            0 <= card_index < len(deck)
            and deck[card_index].get_card_type() == EnchantmentCardType.PIECE_DOUBLE_MOVE
        )

    @classmethod
    def _is_rook_tower_throw_selected(cls, state):
        if state.selected_card is None or state.selected_card[0] != state.current_turn:
            return False
        _, _, _, card = cls._get_used_card(state, state.current_turn)
        return (
            card is not None
            and card.get_card_type() == EnchantmentCardType.ROOK_TOWER_THROW
        )
