import random
from dataclasses import dataclass
from enum import Enum
from typing import List

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import id_to_xy, xy_to_id
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState
from models.starting_positions import pieces_starting_positions_map
from processors.movement_processor import process_possible_basic_moves


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


class _SimulationCards:
    def __init__(self, state):
        self.white_cards = state.white_cards
        self.black_cards = state.black_cards

    def get_cards_for(self, color):
        return self.white_cards if color == COLOR.WHITE else self.black_cards

    def add_card_for(self, color, card):
        deck = self.get_cards_for(color)
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


class _SimulationCaptures:
    def __init__(self, state):
        self.captured_white = state.captured_white
        self.captured_black = state.captured_black

    def get_captured_white(self):
        return self.captured_white

    def get_captured_black(self):
        return self.captured_black

    def capture_piece(self, piece):
        piece.clear_effects()
        captured = self.captured_black if piece.get_color() == COLOR.WHITE else self.captured_white
        captured.append(piece)

    def release_captured_piece(self, color, index):
        captured = self.captured_white if color == COLOR.WHITE else self.captured_black
        return captured.pop(index)


class GameSimulation:
    """Generuje akcje i symuluje je na kopiach stanu przez współdzielone reguły gry."""

    MOVEMENT_CARDS = {
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD,
        EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD,
        EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION,
        EnchantmentCardType.ROOK_JUMP_ALLIES,
        EnchantmentCardType.QUEEN_JUMP_ALLIES,
        EnchantmentCardType.ROOK_TOWER_THROW,
    }

    @staticmethod
    def destinations_for(piece, source, pieces_locations, enchantment=None):
        """Zwraca ruchy używane wspólnie przez interfejs i generator akcji."""
        return process_possible_basic_moves(
            piece, id_to_xy(source), pieces_locations, enchantment)

    @classmethod
    def available_actions(cls, state: GameState) -> List[GameAction]:
        """Zwraca legalne akcje dla gracza na ruchu, z użyciem kart i bez nich."""
        if state.get_winner() is not None:
            return []

        actions = []
        current_color = state.current_turn
        cards = state.get_cards_for(current_color)
        in_double_move = state.double_move_step > 0
        selected_double_card = -1
        if in_double_move:
            if (
                state.selected_card is None
                or state.selected_card[0] != current_color
                or not 0 <= state.selected_card[1] < len(cards)
                or cards[state.selected_card[1]].get_card_type()
                != EnchantmentCardType.PIECE_DOUBLE_MOVE
            ):
                return []
            selected_double_card = state.selected_card[1]

        for source, piece in state.pieces_locations.items():
            if not piece.exists() or piece.get_color() != current_color:
                continue
            if in_double_move and source != state.selected_piece_position:
                continue
            can_move = piece.can_receive_enchantment()
            if can_move:
                for destination in cls.destinations_for(
                    piece, source, state.pieces_locations
                ):
                    actions.append(GameAction(
                        GameActionType.MOVE,
                        source,
                        xy_to_id(*destination),
                        selected_double_card,
                    ))

            if in_double_move:
                continue

            for card_index, card in enumerate(cards):
                card_type = card.get_card_type()
                required_type = card.get_required_piece_type()
                if required_type not in (PIECE_TYPE.EMPTY, piece.get_type()):
                    continue

                if card_type in cls.MOVEMENT_CARDS:
                    if not can_move:
                        continue
                    for destination in cls.destinations_for(
                        piece, source, state.pieces_locations, card
                    ):
                        actions.append(GameAction(
                            GameActionType.MOVE,
                            source,
                            xy_to_id(*destination),
                            card_index,
                        ))
                elif card.is_passive() and can_move:
                    actions.append(GameAction(
                        GameActionType.APPLY_PASSIVE,
                        source,
                        card_index=card_index,
                    ))
                elif card_type.promoted_piece_type is not None:
                    if piece.get_promotion_stun_turns_to(card_type.promoted_piece_type):
                        actions.append(GameAction(
                            GameActionType.PROMOTE,
                            source,
                            card_index=card_index,
                        ))
                elif card_type == EnchantmentCardType.PIECE_TELEPORT:
                    for destination, target in state.pieces_locations.items():
                        if destination != source and target.exists():
                            actions.append(GameAction(
                                GameActionType.TELEPORT,
                                source,
                                destination,
                                card_index,
                            ))
                elif card_type == EnchantmentCardType.RETURN_TO_START:
                    if not can_move:
                        continue
                    for destination in cls._return_targets(state, source):
                        actions.append(GameAction(
                            GameActionType.RETURN_TO_START,
                            source,
                            destination,
                            card_index,
                        ))
                elif card_type == EnchantmentCardType.PIECE_DOUBLE_MOVE:
                    if not can_move:
                        continue
                    for destination in cls.destinations_for(
                        piece, source, state.pieces_locations
                    ):
                        actions.append(GameAction(
                            GameActionType.MOVE,
                            source,
                            xy_to_id(*destination),
                            card_index,
                        ))
                elif card.allows_captured_piece_selection():
                    actions.extend(cls._resurrection_actions(
                        state, source, card_index, card_type.resurrected_piece_type))

        return actions

    @staticmethod
    def _return_targets(state, source):
        selected_piece = state.pieces_locations[source]
        origin = selected_piece.get_starting_position()
        original_piece = next(
            (
                piece for starting_position, piece in pieces_starting_positions_map.items()
                if starting_position.value == origin
            ),
            None,
        )
        if original_piece is None:
            return []
        return [
            starting_position.value
            for starting_position, starting_piece in pieces_starting_positions_map.items()
            if starting_position.value != source
            and starting_piece.get_color() == original_piece.get_color()
            and starting_piece.get_type() == original_piece.get_type()
            and not state.pieces_locations[starting_position.value].exists()
        ]

    @staticmethod
    def _resurrection_actions(state, source, card_index, piece_type):
        color = state.current_turn
        king_position = next(
            (
                position for position, piece in state.pieces_locations.items()
                if piece.exists() and piece.get_color() == color
                and piece.get_type() == PIECE_TYPE.KING and piece.can_receive_enchantment()
            ),
            None,
        )
        if king_position is None:
            return []

        captured_color = COLOR.BLACK if color == COLOR.WHITE else COLOR.WHITE
        captured = state.get_captured_for(captured_color)
        matching_pieces = [
            (index, piece) for index, piece in enumerate(captured)
            if piece.get_color() == color and piece.get_type() == piece_type
        ]
        king_x, king_y = id_to_xy(king_position)
        actions = []
        for captured_index, _ in matching_pieces:
            for y in range(max(0, king_y - 1), min(7, king_y + 1) + 1):
                for x in range(max(0, king_x - 1), min(7, king_x + 1) + 1):
                    destination = xy_to_id(x, y)
                    if (x, y) != (king_x, king_y) and not state.pieces_locations[destination].exists():
                        actions.append(GameAction(
                            GameActionType.RESURRECT,
                            source,
                            destination,
                            card_index,
                            captured_color,
                            captured_index,
                        ))
        return actions

    @classmethod
    def apply(cls, state: GameState, action: GameAction) -> GameState:
        """Zastosowuje legalną akcję na kopii stanu i pozostawia wejście nietknięte."""
        if action not in cls.available_actions(state):
            raise ValueError("The action is not legal in the supplied game state")

        result = state.clone()
        game = cls._make_simulation_game(result)
        game.selected_piece_position = action.source
        game.selected_card = (
            (result.current_turn, action.card_index)
            if action.card_index >= 0 else None
        )

        if action.action_type == GameActionType.MOVE:
            destination_piece = game.pieces_locations[action.destination]
            game.moves = [id_to_xy(action.destination)]
            if destination_piece.exists():
                game.capture_piece(action.destination)
            else:
                game.move_piece(action.destination)
        elif action.action_type == GameActionType.APPLY_PASSIVE:
            enchantment = game.cards_processor.get_cards_for(game.current_turn)[action.card_index]
            game._GameLogicLoop__apply_selected_passive_enchantment(
                action.source, game.pieces_locations[action.source], enchantment)
        elif action.action_type == GameActionType.PROMOTE:
            game._GameLogicLoop__handle_piece_upgrade(game.pieces_locations[action.source])
        elif action.action_type == GameActionType.TELEPORT:
            game._GameLogicLoop__handle_piece_teleport(
                action.destination, game.pieces_locations[action.destination])
        elif action.action_type == GameActionType.RETURN_TO_START:
            game._GameLogicLoop__handle_return_to_start_click(
                action.destination, game.pieces_locations[action.destination])
        elif action.action_type == GameActionType.RESURRECT:
            game.selected_captured_piece = (action.captured_color, action.captured_index)
            game.resurrection_moves = [action.destination]
            game._GameLogicLoop__resurrect_selected_piece(action.destination)

        result = GameState.from_game(game)
        result.random_state = game.rng.getstate()
        return result

    @staticmethod
    def _make_simulation_game(state):
        """Buduje lekką fasadę logiki gry bez inicjalizowania ekranu i zasobów."""
        from logic.stage.game_logic_loop import GameLogicLoop

        game = GameLogicLoop.__new__(GameLogicLoop)
        game.current_turn = state.current_turn
        game.turns_started = state.turns_started
        game.pieces_locations = state.pieces_locations
        game.cards_processor = _SimulationCards(state)
        game.capture_processor = _SimulationCaptures(state)
        game.board_card_available = state.board_card_available
        game.board_card_position = state.board_card_position
        game.board_enchantment = state.board_enchantment
        game.pending_board_card_delay = state.pending_board_card_delay
        game.selected_card = state.selected_card
        game.selected_piece_position = state.selected_piece_position
        game.selected_captured_piece = state.selected_captured_piece
        game.double_move_step = state.double_move_step
        game.double_move_collected_board_card = state.double_move_collected_board_card
        game.resurrection_moves = state.resurrection_moves
        game.moves = []
        game.rng = random.Random()
        game.rng.setstate(state.random_state)
        return game
