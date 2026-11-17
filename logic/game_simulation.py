from typing import List

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import id_to_xy, xy_to_id
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState
from models.starting_positions import pieces_starting_positions_map
from logic.game_rules import GameAction, GameActionType, GameRules
from processors.bitboard_move_generator import BoardBitboards
from processors.movement_processor import process_possible_basic_moves
from utils.logging import log_error


class GameSimulation:
    """Generuje akcje i symuluje je na kopiach stanu przez współdzielone reguły gry."""

    MOVEMENT_CARDS = {
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD,
        EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION,
        EnchantmentCardType.ROOK_JUMP_ALLIES,
        EnchantmentCardType.QUEEN_JUMP_ALLIES,
        EnchantmentCardType.ROOK_TOWER_THROW,
    }
    TREBUCHET_RANGE = 5
    PAWN_PROMOTION_TYPES = GameRules.PAWN_PROMOTION_TYPES

    @classmethod
    def _append_move_actions(
        cls, actions, piece, source, destination, card_index=-1,
    ):
        promotion_rank = 7 if piece.get_color() == COLOR.WHITE else 0
        promotion_types = (
            cls.PAWN_PROMOTION_TYPES
            if (
                piece.get_type() == PIECE_TYPE.PAWN
                and id_to_xy(destination)[1] == promotion_rank
            )
            else (None,)
        )
        for promotion_type in promotion_types:
            actions.append(GameAction(
                GameActionType.MOVE,
                source,
                destination,
                card_index,
                promotion_type=promotion_type,
            ))

    @staticmethod
    def destinations_for(
        piece, source, pieces_locations, enchantment=None, occupancy=None
    ):
        """Zwraca ruchy używane wspólnie przez interfejs i generator akcji."""
        return process_possible_basic_moves(
            piece, id_to_xy(source), pieces_locations, enchantment, occupancy)

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

        unavailable = set()
        if any(
            card.get_card_type() in (
                EnchantmentCardType.KNIGHT_RUNIC_TRAP,
                EnchantmentCardType.RECRUIT_PAWN,
            )
            for card in cards
        ):
            unavailable = {
                position for position, _ in GameRules._board_cards(state)
            }
            unavailable.update(trap.position for trap in state.rune_traps)

        white_occupancy = 0
        black_occupancy = 0
        occupied = 0
        moving_pieces = []
        for source, piece in state.pieces_locations.items():
            if not piece.exists():
                continue
            bit = 1 << (source - 1)
            occupied |= bit
            piece_color = piece.get_color()
            if piece_color == COLOR.WHITE:
                white_occupancy |= bit
            elif piece_color == COLOR.BLACK:
                black_occupancy |= bit
            if (
                piece_color == current_color
                and (not in_double_move or source == state.selected_piece_position)
            ):
                moving_pieces.append((source, piece))
        occupancy = BoardBitboards(
            white_occupancy, black_occupancy, occupied)

        for source, piece in moving_pieces:
            can_move = piece.can_receive_enchantment()
            basic_destinations = (
                cls.destinations_for(
                    piece, source, state.pieces_locations, occupancy=occupancy)
                if can_move else ()
            )
            if basic_destinations:
                for destination in basic_destinations:
                    cls._append_move_actions(
                        actions,
                        piece,
                        source,
                        xy_to_id(*destination),
                        selected_double_card,
                    )

            if in_double_move:
                continue
            if can_move:
                for destination in cls.special_move_destinations(state, source):
                    actions.append(GameAction(
                        GameActionType.MOVE,
                        source,
                        destination,
                    ))

            for card_index, card in enumerate(cards):
                card_type = card.get_card_type()
                required_type = card.get_required_piece_type()
                if required_type not in (PIECE_TYPE.EMPTY, piece.get_type()):
                    continue

                if card_type == EnchantmentCardType.KNIGHT_RUNIC_TRAP:
                    if not can_move:
                        continue
                    x, y = id_to_xy(source)
                    for target_y in range(max(0, y - 1), min(7, y + 1) + 1):
                        for target_x in range(max(0, x - 1), min(7, x + 1) + 1):
                            if (target_x, target_y) == (x, y):
                                continue
                            destination = xy_to_id(target_x, target_y)
                            if (
                                not state.pieces_locations[destination].exists()
                                and destination not in unavailable
                            ):
                                actions.append(GameAction(
                                    GameActionType.PLACE_RUNE,
                                    source,
                                    destination,
                                    card_index,
                                ))
                elif card_type == EnchantmentCardType.ROOK_TREBUCHET:
                    if not can_move:
                        continue
                    rook_x, rook_y = id_to_xy(source)
                    for pawn_position, target in state.pieces_locations.items():
                        if (
                            not target.exists()
                            or target.get_type() != PIECE_TYPE.PAWN
                            or max(
                                abs(id_to_xy(pawn_position)[0] - rook_x),
                                abs(id_to_xy(pawn_position)[1] - rook_y),
                            ) != 1
                        ):
                            continue
                        for target_y in range(
                            max(0, rook_y - cls.TREBUCHET_RANGE),
                            min(7, rook_y + cls.TREBUCHET_RANGE) + 1,
                        ):
                            for target_x in range(
                                max(0, rook_x - cls.TREBUCHET_RANGE),
                                min(7, rook_x + cls.TREBUCHET_RANGE) + 1,
                            ):
                                destination = xy_to_id(target_x, target_y)
                                if not state.pieces_locations[destination].exists():
                                    actions.append(GameAction(
                                        GameActionType.TREBUCHET,
                                        source,
                                        destination,
                                        card_index,
                                        secondary_source=pawn_position,
                                    ))
                elif card_type in cls.MOVEMENT_CARDS:
                    if not can_move:
                        continue
                    for destination in cls.destinations_for(
                        piece,
                        source,
                        state.pieces_locations,
                        card,
                        occupancy,
                    ):
                        cls._append_move_actions(
                            actions,
                            piece,
                            source,
                            xy_to_id(*destination),
                            card_index,
                        )
                elif card.is_passive() and can_move:
                    action_type = (
                        GameActionType.APPLY_BUFF
                        if card.is_buff()
                        else GameActionType.APPLY_PASSIVE
                    )
                    actions.append(GameAction(
                        action_type,
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
                    for destination in basic_destinations:
                        cls._append_move_actions(
                            actions,
                            piece,
                            source,
                            xy_to_id(*destination),
                            card_index,
                        )
                elif card.allows_captured_piece_selection():
                    actions.extend(cls._resurrection_actions(
                        state, source, card_index, card_type.resurrected_piece_type))

        if not in_double_move:
            home_row = 0 if current_color == COLOR.WHITE else 7
            for card_index, card in enumerate(cards):
                if card.get_card_type() != EnchantmentCardType.RECRUIT_PAWN:
                    continue
                for x in range(8):
                    destination = xy_to_id(x, home_row)
                    if (
                        not state.pieces_locations[destination].exists()
                        and destination not in unavailable
                    ):
                        actions.append(GameAction(
                            GameActionType.RECRUIT_PAWN,
                            0,
                            destination,
                            card_index,
                        ))

        return actions

    @classmethod
    def special_move_destinations(cls, state, source):
        """Zwraca pola bicia w przelocie i roszady dla zwykłego ruchu."""
        if state.double_move_step > 0 or not 1 <= source <= 64:
            return ()
        piece = state.pieces_locations[source]
        if (
            not piece.exists()
            or piece.get_color() != state.current_turn
            or not piece.can_receive_enchantment()
        ):
            return ()

        destinations = []
        for en_passant_target in GameRules._en_passant_targets(state):
            en_passant_capture = GameRules.en_passant_capture_position(
                state, source, en_passant_target)
            if en_passant_capture is not None:
                destinations.append(en_passant_target)

        if piece.get_type() != PIECE_TYPE.KING:
            return tuple(destinations)

        for destination in cls._castling_destinations(state, source):
            destinations.append(destination)
        return tuple(destinations)

    @classmethod
    def _castling_destinations(cls, state, source):
        home_row = 0 if state.current_turn == COLOR.WHITE else 7
        destinations = []
        for destination_x in (6, 2):
            destination = xy_to_id(destination_x, home_row)
            rook_positions = GameRules.castling_rook_positions(
                state, source, destination)
            if rook_positions is None:
                continue
            destinations.append(destination)
        return tuple(destinations)

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
    def apply(
        cls,
        state: GameState,
        action: GameAction,
        *,
        advance_board_card_clock: bool = False,
    ) -> GameState:
        """Stosuje akcję na kopii; domyślnie nie przewiduje przyszłych kart planszowych."""
        if action not in cls.available_actions(state):
            log_error(
                "Rejected illegal simulated action {} for {}".format(
                    action, state.current_turn.value)
            )
            raise ValueError("The action is not legal in the supplied game state")

        return cls._apply_generated_action(
            state, action, advance_board_card_clock=advance_board_card_clock)

    @classmethod
    def _apply_generated_action(
        cls,
        state: GameState,
        action: GameAction,
        *,
        advance_board_card_clock: bool = False,
    ) -> GameState:
        """Stosuje akcję wygenerowaną dla niezmienionego stanu bez ponownej walidacji."""
        return GameRules.apply_action(
            state.clone(),
            action,
            advance_board_card_clock=advance_board_card_clock,
        )
