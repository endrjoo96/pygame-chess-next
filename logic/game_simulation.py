from typing import List

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import id_to_xy, xy_to_id
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState
from models.starting_positions import pieces_starting_positions_map
from logic.game_rules import GameAction, GameActionType, GameRules
from processors.movement_processor import process_possible_basic_moves
from utils.logging import log_error


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
            log_error(
                "Rejected illegal simulated action {} for {}".format(
                    action, state.current_turn.value)
            )
            raise ValueError("The action is not legal in the supplied game state")

        return GameRules.apply_action(state.clone(), action)
