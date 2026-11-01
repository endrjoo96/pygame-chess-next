import copy
import random
from dataclasses import dataclass
from enum import Enum

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import POS, id_to_xy, xy_to_id
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState, RuneTrap
from processors.movement_processor import process_possible_basic_moves
from utils.run_config import GAME_SEED, RUN_MODE, RunMode


class GameActionType(Enum):
    MOVE = "move"
    PROMOTE = "promote"
    TELEPORT = "teleport"
    RETURN_TO_START = "return_to_start"
    APPLY_PASSIVE = "apply_passive"
    APPLY_BUFF = "apply_buff"
    RESURRECT = "resurrect"
    PLACE_RUNE = "place_rune"
    TREBUCHET = "trebuchet"
    RECRUIT_PAWN = "recruit_pawn"


@dataclass(frozen=True)
class GameAction:
    """Jedna kompletna decyzja domenowa, niezależna od sekwencji kliknięć UI."""

    action_type: GameActionType
    source: int
    destination: int = 0
    card_index: int = -1
    captured_color: COLOR = COLOR.EMPTY
    captured_index: int = -1
    secondary_source: int = 0

    @staticmethod
    def _format_position(position):
        if position in range(1, 65):
            return POS(position).name
        return "invalid({})".format(position)

    def __str__(self):
        fields = [
            "type={}".format(self.action_type.value),
            "source={}".format(self._format_position(self.source)),
        ]
        if self.destination:
            fields.append(
                "destination={}".format(self._format_position(self.destination)))
        if self.card_index >= 0:
            fields.append("card_index={}".format(self.card_index))
        if self.captured_color != COLOR.EMPTY or self.captured_index >= 0:
            fields.extend((
                "captured_color={}".format(self.captured_color.value),
                "captured_index={}".format(self.captured_index),
            ))
        if self.secondary_source:
            fields.append(
                "secondary_source={}".format(
                    self._format_position(self.secondary_source)))
        return "GameAction({})".format(", ".join(fields))


class GameRules:
    """Mutowalne reguły przejścia stanu, niezależne od interfejsu gry."""

    @classmethod
    def apply_action(
        cls,
        state: GameState,
        action: GameAction,
        *,
        advance_board_card_clock: bool = True,
    ) -> GameState:
        """Stosuje akcję, opcjonalnie aktualizując zegar kart planszowych."""
        rng = None
        if advance_board_card_clock:
            rng = random.Random(GAME_SEED if GAME_SEED is not None else 0)
            rng.setstate(state.random_state)

        state.selected_piece_position = action.source
        state.selected_card = (
            (state.current_turn, action.card_index)
            if action.card_index >= 0 else None
        )

        if action.action_type not in (
            GameActionType.MOVE,
            GameActionType.APPLY_BUFF,
        ):
            state.en_passant_target = None
            state.en_passant_targets = []

        if action.action_type == GameActionType.MOVE:
            if cls._trigger_rune_on_route(
                state, action.source, action.destination
            ):
                state.en_passant_target = None
                state.en_passant_targets = []
                cls._consume_selected_card_use(state)
                cls._finish_piece_move(
                    state, False, rng, advance_board_card_clock)
            else:
                target = state.pieces_locations[action.destination]
                if target.exists() and not cls._is_rook_tower_throw_selected(state):
                    cls._capture_piece(state, target)
                else:
                    captured_position = cls.en_passant_capture_position(
                        state, action.source, action.destination)
                    if captured_position is not None:
                        captured_pawn = state.pieces_locations[captured_position]
                        cls._capture_piece(state, captured_pawn)
                        state.pieces_locations[captured_position] = Piece()
                cls._move_piece(
                    state, action.destination, rng, advance_board_card_clock)
        elif action.action_type in (
            GameActionType.APPLY_PASSIVE,
            GameActionType.APPLY_BUFF,
        ):
            enchantment = state.get_cards_for(state.current_turn)[action.card_index]
            cls._apply_selected_piece_enchantment(
                state,
                action.source,
                enchantment,
                ends_turn=action.action_type == GameActionType.APPLY_PASSIVE,
            )
        elif action.action_type == GameActionType.PROMOTE:
            cls._promote_piece(state, action.source)
        elif action.action_type == GameActionType.TELEPORT:
            source_piece = state.pieces_locations[action.source]
            destination_piece = state.pieces_locations[action.destination]
            source_piece.set_has_moved()
            destination_piece.set_has_moved()
            state.pieces_locations[action.source] = destination_piece
            state.pieces_locations[action.destination] = source_piece
            cls._discard_selected_card(state)
            state.selected_card = None
            state.selected_piece_position = 0
            cls._end_turn(state)
        elif action.action_type == GameActionType.RETURN_TO_START:
            if cls._trigger_rune_on_route(
                state, action.source, action.destination
            ):
                cls._consume_selected_card_use(state)
                cls._finish_piece_move(
                    state, False, rng, advance_board_card_clock)
            else:
                cls._move_piece(
                    state, action.destination, rng, advance_board_card_clock)
        elif action.action_type == GameActionType.RESURRECT:
            piece = state.get_captured_for(action.captured_color).pop(action.captured_index)
            state.pieces_locations[action.destination] = piece
            trapped = cls._trigger_rune_on_route(
                state, action.destination, action.destination)
            cls._discard_selected_card(state)
            state.selected_card = None
            if not trapped:
                cls._collect_board_card(state, action.destination, state.current_turn)
            state.selected_captured_piece = None
            state.resurrection_moves = []
            state.selected_piece_position = 0
            cls._end_turn(state)
        elif action.action_type == GameActionType.PLACE_RUNE:
            card = state.get_cards_for(state.current_turn)[action.card_index]
            state.rune_traps.append(RuneTrap(
                action.destination,
                state.current_turn,
                card,
                state.turns_started[state.current_turn],
            ))
            cls._discard_selected_card(state)
            state.selected_card = None
            state.selected_piece_position = 0
            cls._end_turn(state)
        elif action.action_type == GameActionType.TREBUCHET:
            cls._fire_trebuchet(
                state, action.source, action.secondary_source, action.destination,
                rng, advance_board_card_clock)
        elif action.action_type == GameActionType.RECRUIT_PAWN:
            cls._recruit_pawn(state, action.destination, rng, advance_board_card_clock)

        if rng is not None:
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
    def _apply_selected_piece_enchantment(
        cls, state, position, enchantment, *, ends_turn,
    ):
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
        if ends_turn:
            cls._end_turn(state)

    @classmethod
    def _fire_trebuchet(
        cls, state, rook_position, pawn_position, destination, rng,
        advance_board_card_clock,
    ):
        rook = state.pieces_locations[rook_position]
        pawn = state.pieces_locations[pawn_position]
        color = state.current_turn
        _, _, _, card = cls._get_used_card(state, color)
        collected_card = False
        if not cls._trigger_rune_on_route(state, pawn_position, destination):
            state.pieces_locations[pawn_position] = Piece()
            state.pieces_locations[destination] = pawn
            pawn.set_has_moved()
            collected_card = cls._collect_board_card(state, destination, color)

        rook.set_stunned_for_turns(1)
        rook.add_stun_effect(card, 1)
        cls._consume_selected_card_use(state)
        cls._finish_piece_move(
            state, collected_card, rng, advance_board_card_clock)

    @classmethod
    def _recruit_pawn(cls, state, destination, rng, advance_board_card_clock):
        color = state.current_turn
        home_row = 0 if color == COLOR.WHITE else 7
        x, y = id_to_xy(destination)
        if y != home_row or state.pieces_locations[destination].exists():
            raise ValueError("A recruited pawn must be placed on an empty home-rank square")
        state.pieces_locations[destination] = Piece(color, PIECE_TYPE.PAWN)
        cls._consume_selected_card_use(state)
        cls._finish_piece_move(
            state, False, rng, advance_board_card_clock)

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
        ending_color = state.current_turn
        for trap in state.rune_traps:
            if (
                trap.owner == ending_color
                and trap.placed_on_turn < state.turns_started[ending_color]
            ):
                trap.remaining_owner_turns -= 1
        state.rune_traps = [
            trap for trap in state.rune_traps
            if trap.remaining_owner_turns > 0
        ]
        state.current_turn = COLOR.BLACK if state.current_turn == COLOR.WHITE else COLOR.WHITE
        state.turns_started[state.current_turn] += 1
        cls._apply_ready_passive_enchantments(state, state.current_turn)

    @staticmethod
    def _consume_selected_card_use(state):
        if state.selected_card is None:
            return
        color, card_index = state.selected_card
        card_deck = state.get_cards_for(color)
        if 0 <= card_index < len(card_deck):
            card = card_deck[card_index]
            if card.consume_use() == 0:
                card_deck.pop(card_index)
        state.selected_card = None

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
        piece.set_has_moved()
        piece.clear_effects()
        captured = (
            state.captured_black
            if piece.get_color() == COLOR.WHITE else state.captured_white
        )
        captured.append(piece)

    @classmethod
    def _move_piece(cls, state, destination, rng, advance_board_card_clock):
        source_position = state.selected_piece_position
        if source_position <= 0:
            return

        moving_color = state.current_turn
        piece = state.pieces_locations[source_position]
        officer_followers = cls._officer_follower_positions(
            state, source_position, piece)
        en_passant_target = cls._en_passant_target_after_pawn_move(
            piece, moving_color, source_position, destination)
        state.en_passant_target = None
        state.en_passant_targets = []
        first_double_move = (
            cls._selected_card_is_double_move(state) and state.double_move_step == 0
        )
        if state.double_move_step == 0:
            cls._advance_stun_effects(state, moving_color)

        _, card_index, card_deck, used_card = cls._get_used_card(state, moving_color)
        castling_rook_positions = (
            cls.castling_rook_positions(state, source_position, destination)
            if used_card is None and state.double_move_step == 0 else None
        )
        collected_rook_card = False
        if castling_rook_positions is not None:
            rook_source, rook_destination = castling_rook_positions
            if not cls._trigger_rune_on_route(
                state, rook_source, rook_destination
            ):
                rook = state.pieces_locations[rook_source]
                state.pieces_locations[rook_source] = Piece()
                state.pieces_locations[rook_destination] = rook
                rook.set_has_moved()
                collected_rook_card = cls._collect_board_card(
                    state, rook_destination, moving_color)

        if (
            used_card is not None
            and used_card.get_card_type() == EnchantmentCardType.ROOK_TOWER_THROW
        ):
            cls._capture_rook_throw_route(state, source_position, destination)

        state.pieces_locations[source_position] = Piece()
        state.pieces_locations[destination] = piece
        piece.set_has_moved()
        collected_board_card = (
            cls._collect_board_card(state, destination, moving_color)
            or collected_rook_card
        )
        followers_collected_card, follower_en_passant_targets = (
            cls._move_officer_followers(
                state, source_position, destination, piece, officer_followers)
        )
        collected_board_card = followers_collected_card or collected_board_card
        if en_passant_target is not None:
            follower_en_passant_targets.insert(0, en_passant_target)

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

        cls._finish_piece_move(
            state, collected_board_card, rng, advance_board_card_clock)
        state.en_passant_targets = list(dict.fromkeys(follower_en_passant_targets))
        state.en_passant_target = (
            state.en_passant_targets[0] if state.en_passant_targets else None
        )

    @staticmethod
    def _officer_follower_positions(state, officer_position, officer):
        if (
            officer.get_type() != PIECE_TYPE.PAWN
            or not any(
                enchantment.get_card_type() == EnchantmentCardType.PAWN_OFFICER
                for enchantment in officer.get_passive_enchantments()
            )
        ):
            return ()

        officers = [
            (position, piece)
            for position, piece in state.pieces_locations.items()
            if piece.exists()
            and piece.get_color() == officer.get_color()
            and piece.get_type() == PIECE_TYPE.PAWN
            and any(
                enchantment.get_card_type() == EnchantmentCardType.PAWN_OFFICER
                for enchantment in piece.get_passive_enchantments()
            )
        ]
        officer_x, officer_y = id_to_xy(officer_position)
        return tuple(
            position
            for position, piece in state.pieces_locations.items()
            if position != officer_position
            and piece.exists()
            and piece.get_color() == officer.get_color()
            and piece.get_type() == PIECE_TYPE.PAWN
            and max(
                abs(id_to_xy(position)[0] - officer_x),
                abs(id_to_xy(position)[1] - officer_y),
            ) == 1
            and min(
                officers,
                key=lambda candidate: (
                    max(
                        abs(id_to_xy(position)[0] - id_to_xy(candidate[0])[0]),
                        abs(id_to_xy(position)[1] - id_to_xy(candidate[0])[1]),
                    ),
                    candidate[0],
                ),
                default=(None, None),
            )[0] == officer_position
        )

    @classmethod
    def _move_officer_followers(
        cls, state, officer_source, officer_destination, officer, follower_positions,
    ):
        if not follower_positions:
            return False, []

        source_x, source_y = id_to_xy(officer_source)
        destination_x, destination_y = id_to_xy(officer_destination)
        delta_x = destination_x - source_x
        delta_y = destination_y - source_y
        officer_effects = officer.get_passive_enchantments()
        collected_board_card = False
        en_passant_targets = []

        for follower_source in sorted(follower_positions):
            follower = state.pieces_locations[follower_source]
            if (
                not follower.exists()
                or follower.get_type() != PIECE_TYPE.PAWN
                or follower.get_color() != state.current_turn
                or not follower.can_receive_enchantment()
            ):
                continue

            follower_x, follower_y = id_to_xy(follower_source)
            target_x = follower_x + delta_x
            target_y = follower_y + delta_y
            if not (0 <= target_x < 8 and 0 <= target_y < 8):
                continue
            follower_destination = xy_to_id(target_x, target_y)

            effective_follower = copy.deepcopy(follower)
            effective_follower.remove_passive_enchantments()
            for enchantment in officer_effects:
                effective_follower.set_enchantment(enchantment)
            legal_moves = process_possible_basic_moves(
                effective_follower,
                (follower_x, follower_y),
                state.pieces_locations,
            )
            if [target_x, target_y] not in legal_moves:
                continue

            if cls._trigger_rune_on_route(
                state, follower_source, follower_destination
            ):
                continue

            target_piece = state.pieces_locations[follower_destination]
            if target_piece.exists():
                cls._capture_piece(state, target_piece)
            en_passant_target = cls._en_passant_target_after_pawn_move(
                follower, state.current_turn, follower_source, follower_destination)
            state.pieces_locations[follower_source] = Piece()
            state.pieces_locations[follower_destination] = follower
            follower.set_has_moved()
            if en_passant_target is not None:
                en_passant_targets.append(en_passant_target)
            collected_board_card = (
                cls._collect_board_card(
                    state, follower_destination, state.current_turn)
                or collected_board_card
            )

        return collected_board_card, en_passant_targets

    @classmethod
    def _trigger_rune_on_route(cls, state, source, destination):
        piece = state.pieces_locations[source]
        source_x, source_y = id_to_xy(source)
        destination_x, destination_y = id_to_xy(destination)
        delta_x = destination_x - source_x
        delta_y = destination_y - source_y

        if source == destination:
            route = (destination,)
        elif piece.get_type() == PIECE_TYPE.KNIGHT:
            route = (destination,)
        elif (
            delta_x == 0
            or delta_y == 0
            or abs(delta_x) == abs(delta_y)
        ):
            step_x = (delta_x > 0) - (delta_x < 0)
            step_y = (delta_y > 0) - (delta_y < 0)
            route = tuple(
                xy_to_id(source_x + step_x * step, source_y + step_y * step)
                for step in range(1, max(abs(delta_x), abs(delta_y)) + 1)
            )
        else:
            route = (destination,)

        for position in route:
            trap = next(
                (trap for trap in state.rune_traps if trap.position == position),
                None,
            )
            if trap is None:
                continue
            state.rune_traps.remove(trap)
            cls._capture_piece(state, piece)
            state.pieces_locations[source] = Piece()
            return True
        return False

    @staticmethod
    def _en_passant_target_after_pawn_move(
        piece, moving_color, source_position, destination,
    ):
        if piece.get_type() != PIECE_TYPE.PAWN or piece.has_moved():
            return None
        source_x, source_y = id_to_xy(source_position)
        destination_x, destination_y = id_to_xy(destination)
        starting_row = 1 if moving_color == COLOR.WHITE else 6
        direction = 1 if moving_color == COLOR.WHITE else -1
        if (
            source_x != destination_x
            or source_y != starting_row
            or destination_y != source_y + 2 * direction
        ):
            return None
        return xy_to_id(source_x, source_y + direction)

    @staticmethod
    def en_passant_capture_position(state, source, destination):
        if destination not in GameRules._en_passant_targets(state):
            return None
        if not (1 <= source <= 64 and 1 <= destination <= 64):
            return None
        piece = state.pieces_locations[source]
        if (
            not piece.exists()
            or piece.get_color() != state.current_turn
            or piece.get_type() != PIECE_TYPE.PAWN
            or state.pieces_locations[destination].exists()
        ):
            return None

        source_x, source_y = id_to_xy(source)
        destination_x, destination_y = id_to_xy(destination)
        direction = 1 if state.current_turn == COLOR.WHITE else -1
        if (
            abs(destination_x - source_x) != 1
            or destination_y != source_y + direction
        ):
            return None

        captured_position = xy_to_id(destination_x, source_y)
        captured_piece = state.pieces_locations[captured_position]
        if (
            not captured_piece.exists()
            or captured_piece.get_type() != PIECE_TYPE.PAWN
            or captured_piece.get_color() == state.current_turn
        ):
            return None
        return captured_position

    @staticmethod
    def _en_passant_targets(state):
        targets = getattr(state, "en_passant_targets", ())
        if targets:
            return tuple(targets)
        target = state.en_passant_target
        return () if target is None else (target,)

    @staticmethod
    def castling_rook_positions(state, source, destination):
        king = state.pieces_locations.get(source)
        if (
            king is None
            or not king.exists()
            or king.get_type() != PIECE_TYPE.KING
            or king.get_color() != state.current_turn
            or king.has_moved()
        ):
            return None

        home_row = 0 if state.current_turn == COLOR.WHITE else 7
        if (
            source != xy_to_id(4, home_row)
            or king.get_starting_position() != source
        ):
            return None
        if destination == xy_to_id(6, home_row):
            rook_source_x, rook_destination_x = 7, 5
            path = (5, 6)
        elif destination == xy_to_id(2, home_row):
            rook_source_x, rook_destination_x = 0, 3
            path = (1, 2, 3)
        else:
            return None

        rook_source = xy_to_id(rook_source_x, home_row)
        rook_destination = xy_to_id(rook_destination_x, home_row)
        rook = state.pieces_locations[rook_source]
        if (
            not rook.exists()
            or rook.get_color() != state.current_turn
            or rook.get_type() != PIECE_TYPE.ROOK
            or rook.has_moved()
            or rook.get_starting_position() != rook_source
        ):
            return None
        if any(
            state.pieces_locations[xy_to_id(x, home_row)].exists()
            for x in path
        ):
            return None
        return rook_source, rook_destination

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
        board_cards = GameRules._board_cards(state)
        collected = next(
            (card for card in board_cards if card[0] == destination),
            None,
        )
        if collected is None:
            return False
        GameRules._add_card_for(state, moving_color, collected[1])
        board_cards.remove(collected)
        GameRules._set_board_cards(state, board_cards)
        return True

    @staticmethod
    def _board_cards(state):
        if state.board_cards:
            return state.board_cards
        if state.board_card_available and state.board_enchantment is not None:
            return [(state.board_card_position, state.board_enchantment)]
        return []

    @staticmethod
    def _set_board_cards(state, board_cards):
        state.board_cards = board_cards
        state.board_card_available = bool(board_cards)
        if board_cards:
            state.board_card_position, state.board_enchantment = board_cards[0]
        else:
            state.board_enchantment = None

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
    def _finish_piece_move(
        cls, state, collected_board_card, rng, advance_board_card_clock,
    ):
        cls._end_turn(state)
        if advance_board_card_clock:
            if collected_board_card and state.pending_board_card_delay is None:
                cls._schedule_next_board_card(state, rng)
            cls._advance_board_card_clock(state, rng)

        state.selected_piece_position = 0
        state.selected_card = None
        state.selected_captured_piece = None
        state.double_move_step = 0
        state.double_move_collected_board_card = False

    @classmethod
    def _schedule_next_board_card(cls, state, rng):
        state.pending_board_card_delay = (
            0 if RUN_MODE is RunMode.DEBUG else rng.randint(1, 5)
        )
        if state.pending_board_card_delay == 0:
            cls._place_next_board_card(state, rng)

    @classmethod
    def _advance_board_card_clock(cls, state, rng):
        """Zmniejsza licznik i wykłada kolejną kartę po zebraniu poprzedniej."""
        if state.pending_board_card_delay is None:
            return
        if state.pending_board_card_delay > 0:
            state.pending_board_card_delay -= 1
        if state.pending_board_card_delay == 0:
            cls._place_next_board_card(state, rng)

    @staticmethod
    def _place_next_board_card(state, rng):
        existing_cards = GameRules._board_cards(state)
        occupied_card_positions = {position for position, _ in existing_cards}
        empty_positions = [
            position for position in range(1, 65)
            if not state.pieces_locations[position].exists()
            and position not in occupied_card_positions
            and all(trap.position != position for trap in state.rune_traps)
        ]
        if not empty_positions:
            return
        existing_cards.append((
            rng.choice(empty_positions),
            EnchantmentCardType.create_random(rng),
        ))
        GameRules._set_board_cards(state, existing_cards)
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
