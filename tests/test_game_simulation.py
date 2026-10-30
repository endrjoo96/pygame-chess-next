import random

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState
from logic.game_simulation import GameActionType, GameSimulation


@pytest.fixture
def empty_state():
    return GameState(
        pieces_locations={position: Piece() for position in range(1, 65)},
        current_turn=COLOR.WHITE,
        turns_started={COLOR.WHITE: 1, COLOR.BLACK: 0},
        white_cards=[],
        black_cards=[],
        captured_white=[],
        captured_black=[],
        board_card_available=False,
        board_card_position=36,
        board_enchantment=None,
        pending_board_card_delay=None,
        random_state=random.getstate(),
    )


def test_available_actions_and_simulation_share_board_move_rules(empty_state):
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    empty_state.pieces_locations[1] = rook
    empty_state.pieces_locations[3] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    empty_state.pieces_locations[4] = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)

    actions = GameSimulation.available_actions(empty_state)

    assert GameActionType.MOVE in {action.action_type for action in actions}
    assert any(action.source == 1 and action.destination == 3 for action in actions)
    assert not any(action.source == 1 and action.destination in (4, 5) for action in actions)

    capture = next(
        action for action in actions
        if action.source == 1 and action.destination == 3
    )
    result = GameSimulation.apply(empty_state, capture)

    assert result.pieces_locations[3].get_type() == PIECE_TYPE.ROOK
    assert not result.pieces_locations[1].exists()
    assert [piece.get_type() for piece in result.captured_white] == [PIECE_TYPE.PAWN]
    assert empty_state.pieces_locations[1] is rook
    assert empty_state.pieces_locations[3].get_type() == PIECE_TYPE.PAWN
    assert empty_state.captured_white == []


def test_card_movement_action_consumes_card_and_preserves_input_state(empty_state):
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    empty_state.pieces_locations[9] = pawn
    empty_state.white_cards.append(
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(uses=1)
    )

    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.MOVE
        and action.source == 9
        and action.destination == 25
        and action.card_index == 0
    )
    result = GameSimulation.apply(empty_state, action)

    assert result.pieces_locations[25].get_type() == PIECE_TYPE.PAWN
    assert result.pieces_locations[25] is not pawn
    assert result.white_cards == []
    assert empty_state.pieces_locations[9] is pawn
    assert len(empty_state.white_cards) == 1
    assert empty_state.white_cards[0].get_remaining_uses() == 1


def test_passive_card_simulation_applies_detonation_without_mutating_source(empty_state):
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    enemy = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)
    empty_state.pieces_locations[28] = pawn
    empty_state.pieces_locations[29] = enemy
    empty_state.white_cards.append(EnchantmentCardType.PAWN_DETONATION.create())

    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.APPLY_PASSIVE and action.source == 28
    )
    result = GameSimulation.apply(empty_state, action)

    assert not result.pieces_locations[28].exists()
    assert not result.pieces_locations[29].exists()
    assert [piece.get_type() for piece in result.captured_white] == [PIECE_TYPE.KNIGHT]
    assert result.white_cards == []
    assert empty_state.pieces_locations[28] is pawn
    assert empty_state.pieces_locations[29] is enemy
    assert len(empty_state.white_cards) == 1


def test_teleport_action_swaps_pieces_on_a_copy(empty_state):
    knight = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)
    bishop = Piece(COLOR.BLACK, PIECE_TYPE.BISHOP)
    empty_state.pieces_locations[1] = knight
    empty_state.pieces_locations[2] = bishop
    empty_state.white_cards.append(EnchantmentCardType.PIECE_TELEPORT.create())

    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.TELEPORT
        and action.source == 1
        and action.destination == 2
    )
    result = GameSimulation.apply(empty_state, action)

    assert result.pieces_locations[1].get_type() == PIECE_TYPE.BISHOP
    assert result.pieces_locations[2].get_type() == PIECE_TYPE.KNIGHT
    assert result.white_cards == []
    assert empty_state.pieces_locations[1] is knight
    assert empty_state.pieces_locations[2] is bishop


def test_promotion_action_applies_upgrade_stun_and_consumes_card(empty_state):
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    empty_state.pieces_locations[9] = pawn
    empty_state.white_cards.append(
        EnchantmentCardType.PAWN_UPGRADE_TO_QUEEN.create()
    )
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.PROMOTE
        and action.source == 9
        and action.card_index == 0
    )

    result = GameSimulation.apply(empty_state, action)

    assert result.pieces_locations[9].get_type() == PIECE_TYPE.QUEEN
    assert result.pieces_locations[9].is_stunned()
    assert result.white_cards == []
    assert empty_state.pieces_locations[9] is pawn


def test_return_to_start_action_moves_piece_to_an_empty_matching_start_square(empty_state):
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK, starting_position=1)
    empty_state.pieces_locations[17] = rook
    empty_state.white_cards.append(EnchantmentCardType.RETURN_TO_START.create(uses=1))
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.RETURN_TO_START
        and action.source == 17
        and action.destination == 1
    )

    result = GameSimulation.apply(empty_state, action)

    assert result.pieces_locations[1].get_type() == PIECE_TYPE.ROOK
    assert not result.pieces_locations[17].exists()
    assert result.white_cards == []
    assert empty_state.pieces_locations[17] is rook


def test_resurrection_action_restores_matching_captured_piece(empty_state):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    empty_state.captured_black.append(pawn)
    empty_state.white_cards.append(EnchantmentCardType.KING_PAWN_RESURRECTION.create())
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.RESURRECT and action.destination == 2
    )

    result = GameSimulation.apply(empty_state, action)

    assert result.pieces_locations[2].get_type() == PIECE_TYPE.PAWN
    assert result.captured_black == []
    assert result.white_cards == []
    assert empty_state.captured_black == [pawn]
    assert empty_state.pieces_locations[2].get_type() == PIECE_TYPE.EMPTY


def test_double_move_keeps_same_player_to_move_until_second_step(empty_state):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    empty_state.white_cards.append(EnchantmentCardType.PIECE_DOUBLE_MOVE.create(uses=1))
    first_action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.MOVE
        and action.source == 1
        and action.destination == 2
        and action.card_index == 0
    )

    after_first = GameSimulation.apply(empty_state, first_action)

    assert after_first.current_turn == COLOR.WHITE
    assert after_first.double_move_step == 1
    assert after_first.selected_piece_position == 2
    second_action = next(
        action for action in GameSimulation.available_actions(after_first)
        if action.source == 2 and action.destination == 3
    )

    after_second = GameSimulation.apply(after_first, second_action)

    assert after_second.current_turn == COLOR.BLACK
    assert after_second.double_move_step == 0
    assert after_second.pieces_locations[3].get_type() == PIECE_TYPE.ROOK
    assert after_second.white_cards == []
    assert after_first.pieces_locations[2].get_type() == PIECE_TYPE.ROOK


def test_rejecting_unavailable_action_does_not_change_state(empty_state):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    illegal = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == 1
    )
    illegal = type(illegal)(
        illegal.action_type, illegal.source, destination=65,
        card_index=illegal.card_index,
    )

    with pytest.raises(ValueError, match="not legal"):
        GameSimulation.apply(empty_state, illegal)

    assert empty_state.pieces_locations[1].get_type() == PIECE_TYPE.ROOK
    assert 65 not in empty_state.pieces_locations


@pytest.mark.parametrize(
    ("capture_list", "king_color", "winner"),
    [
        ("captured_white", COLOR.BLACK, COLOR.WHITE),
        ("captured_black", COLOR.WHITE, COLOR.BLACK),
    ],
)
def test_state_detects_winner_from_captured_king(
    empty_state, capture_list, king_color, winner
):
    getattr(empty_state, capture_list).append(Piece(king_color, PIECE_TYPE.KING))

    assert empty_state.get_winner() == winner
    assert GameSimulation.available_actions(empty_state) == []
