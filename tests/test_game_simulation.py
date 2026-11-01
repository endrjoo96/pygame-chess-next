import builtins
import random

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import POS
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState

_TEST_RANDOM_SEED = 123456789011


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
        random_state=random.Random(_TEST_RANDOM_SEED).getstate(),
    )


def add_castling_pieces(state, color):
    home_rank = 1 if color == COLOR.WHITE else 8
    king_position = POS["E{}".format(home_rank)].value
    rook_positions = (
        POS["A{}".format(home_rank)].value,
        POS["H{}".format(home_rank)].value,
    )
    state.pieces_locations[king_position] = Piece(
        color, PIECE_TYPE.KING, king_position)
    for rook_position in rook_positions:
        state.pieces_locations[rook_position] = Piece(
            color, PIECE_TYPE.ROOK, rook_position)
    return king_position, rook_positions


def test_game_action_log_string_uses_chess_square_names():
    action = GameAction(GameActionType.MOVE, source=13, destination=45)

    assert str(action) == "GameAction(type=move, source=E2, destination=E6)"


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


def test_double_move_actions_reuse_basic_destinations(empty_state, monkeypatch):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    empty_state.white_cards.append(
        EnchantmentCardType.PIECE_DOUBLE_MOVE.create())
    calls = []
    original_destinations_for = GameSimulation.destinations_for

    def counted_destinations_for(piece, source, locations, enchantment=None):
        calls.append((source, enchantment))
        return original_destinations_for(piece, source, locations, enchantment)

    monkeypatch.setattr(
        GameSimulation,
        "destinations_for",
        staticmethod(counted_destinations_for),
    )

    actions = GameSimulation.available_actions(empty_state)

    assert sum(source == 1 for source, _ in calls) == 1
    assert any(action.source == 1 and action.card_index == -1 for action in actions)
    assert any(action.source == 1 and action.card_index == 0 for action in actions)


def test_game_state_clone_isolates_piece_effects_and_preserves_card_aliases(
    empty_state,
):
    card = EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(uses=2)
    piece = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    piece.set_enchantment(card)
    piece.add_delayed_enchantment(card, 2)
    piece.set_stunned_for_turns(2)
    piece.add_stun_effect(card, 2)
    empty_state.pieces_locations[9] = piece
    empty_state.white_cards.append(card)

    cloned_state = empty_state.clone()
    cloned_piece = cloned_state.pieces_locations[9]
    cloned_card = cloned_state.white_cards[0]
    cloned_effects = cloned_piece.get_effects(0)

    assert cloned_effects[0][0] is cloned_card
    assert cloned_effects[1][0] is cloned_card
    assert cloned_effects[2][0] is cloned_card
    assert cloned_state.random_state is empty_state.random_state
    assert cloned_state.turns_started is not empty_state.turns_started

    cloned_card.consume_use()
    assert cloned_card.get_remaining_uses() == 1
    assert card.get_remaining_uses() == 2
    assert cloned_piece.get_delayed_enchantments_ready_at(2) == [cloned_card]
    assert len(cloned_piece.get_effects(0)) == 2
    assert len(piece.get_effects(0)) == 3


def test_generated_action_fast_path_matches_validated_apply(empty_state):
    empty_state.pieces_locations[1] = Piece(
        COLOR.WHITE, PIECE_TYPE.ROOK, starting_position=1)
    empty_state.pieces_locations[9] = Piece(
        COLOR.BLACK, PIECE_TYPE.PAWN, starting_position=9)
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == 1 and action.destination == 9
    )

    validated = GameSimulation.apply(empty_state, action)
    generated = GameSimulation._apply_generated_action(empty_state, action)

    assert validated.current_turn == generated.current_turn
    assert validated.turns_started == generated.turns_started
    assert validated.random_state == generated.random_state
    assert validated.get_captured_for(COLOR.WHITE)[0].get_type() == (
        generated.get_captured_for(COLOR.WHITE)[0].get_type()
    )
    assert {
        position: (piece.get_color(), piece.get_type())
        for position, piece in validated.pieces_locations.items()
    } == {
        position: (piece.get_color(), piece.get_type())
        for position, piece in generated.pieces_locations.items()
    }
    assert empty_state.pieces_locations[1].get_type() == PIECE_TYPE.ROOK
    assert empty_state.pieces_locations[9].get_type() == PIECE_TYPE.PAWN


def test_generated_action_fast_path_does_not_regenerate_legal_actions(
    empty_state, monkeypatch
):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    action = GameSimulation.available_actions(empty_state)[0]

    def unexpected_validation(cls, state):
        pytest.fail("The generated-action fast path must not validate again")

    monkeypatch.setattr(
        GameSimulation, "available_actions", classmethod(unexpected_validation))

    result = GameSimulation._apply_generated_action(empty_state, action)

    assert result.pieces_locations[action.destination].get_color() == COLOR.WHITE


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


def test_resurrection_collects_board_card_after_consuming_resurrection_card(
    empty_state,
):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    empty_state.captured_black.append(Piece(COLOR.WHITE, PIECE_TYPE.PAWN))
    empty_state.white_cards = [
        EnchantmentCardType.PAWN_SWORDSMAN.create()
        for _ in range(7)
    ] + [EnchantmentCardType.KING_PAWN_RESURRECTION.create()]
    board_card = EnchantmentCardType.PIECE_TELEPORT.create()
    empty_state.board_cards = [(2, board_card)]
    empty_state.board_card_available = True
    empty_state.board_card_position = 2
    empty_state.board_enchantment = board_card
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.RESURRECT
        and action.destination == 2
    )

    result = GameSimulation.apply(empty_state, action)

    assert len(result.white_cards) == 8
    assert result.white_cards[-1].get_card_type() == (
        EnchantmentCardType.PIECE_TELEPORT)
    assert result.board_cards == []
    assert empty_state.white_cards[-1].get_card_type() == (
        EnchantmentCardType.KING_PAWN_RESURRECTION)
    assert empty_state.board_cards == [(2, board_card)]


def test_board_card_is_destroyed_when_hand_cannot_accept_it(empty_state):
    empty_state.pieces_locations[1] = Piece(
        COLOR.WHITE, PIECE_TYPE.ROOK, starting_position=1)
    empty_state.white_cards = [
        EnchantmentCardType.PAWN_SWORDSMAN.create()
        for _ in range(8)
    ]
    board_card = EnchantmentCardType.PIECE_TELEPORT.create()
    empty_state.board_cards = [(2, board_card)]
    empty_state.board_card_available = True
    empty_state.board_card_position = 2
    empty_state.board_enchantment = board_card
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.MOVE
        and action.source == 1
        and action.destination == 2
        and action.card_index == -1
    )

    result = GameSimulation.apply(empty_state, action)

    assert len(result.white_cards) == 8
    assert result.board_cards == []
    assert not result.board_card_available
    assert result.board_enchantment is None
    assert all(
        card.get_card_type() != EnchantmentCardType.PIECE_TELEPORT
        for card in result.white_cards
    )


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
        ("captured_black", COLOR.WHITE, COLOR.BLACK),
        ("captured_white", COLOR.BLACK, COLOR.WHITE),
    ],
)
def test_state_detects_winner_from_captured_king(
    empty_state, capture_list, king_color, winner
):
    getattr(empty_state, capture_list).append(Piece(king_color, PIECE_TYPE.KING))

    assert empty_state.get_winner() == winner
    assert GameSimulation.available_actions(empty_state) == []


def test_apply_does_not_import_game_logic_loop(empty_state, monkeypatch):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == 1 and action.destination == 2
    )
    original_import = builtins.__import__

    def reject_game_logic_loop(name, *args, **kwargs):
        if name == "logic.stage.game_logic_loop":
            raise AssertionError("simulation attempted to import GameLogicLoop")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_game_logic_loop)

    result = GameSimulation.apply(empty_state, action)

    assert result.pieces_locations[2].get_type() == PIECE_TYPE.ROOK
    assert empty_state.pieces_locations[1].get_type() == PIECE_TYPE.ROOK


def test_rook_tower_throw_captures_every_piece_on_route(empty_state):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    empty_state.pieces_locations[3] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    empty_state.pieces_locations[5] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)
    empty_state.white_cards.append(EnchantmentCardType.ROOK_TOWER_THROW.create())
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.MOVE
        and action.source == 1
        and action.destination == 8
        and action.card_index == 0
    )

    result = GameSimulation.apply(empty_state, action)

    assert result.pieces_locations[8].get_type() == PIECE_TYPE.ROOK
    assert not result.pieces_locations[3].exists()
    assert not result.pieces_locations[5].exists()
    assert [piece.get_type() for piece in result.captured_black] == [PIECE_TYPE.PAWN]
    assert [piece.get_type() for piece in result.captured_white] == [PIECE_TYPE.KNIGHT]
    assert result.white_cards == []
    assert empty_state.pieces_locations[3].get_type() == PIECE_TYPE.PAWN
    assert empty_state.pieces_locations[5].get_type() == PIECE_TYPE.KNIGHT


def test_delayed_passive_activates_at_players_next_turn(empty_state):
    empty_state.pieces_locations[28] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    empty_state.pieces_locations[29] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)
    empty_state.pieces_locations[1] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    empty_state.white_cards.append(
        EnchantmentCardType.PAWN_DETONATION_DELAYED_1.create()
    )
    passive_action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.action_type == GameActionType.APPLY_PASSIVE and action.source == 28
    )

    after_apply = GameSimulation.apply(empty_state, passive_action)
    black_move = next(
        action for action in GameSimulation.available_actions(after_apply)
        if action.source == 1 and action.destination == 2
    )
    after_black_move = GameSimulation.apply(after_apply, black_move)

    assert after_black_move.current_turn == COLOR.WHITE
    assert not after_black_move.pieces_locations[28].exists()
    assert not after_black_move.pieces_locations[29].exists()
    assert [piece.get_type() for piece in after_black_move.captured_white] == [
        PIECE_TYPE.KNIGHT
    ]
    assert empty_state.pieces_locations[28].get_type() == PIECE_TYPE.PAWN
    assert empty_state.pieces_locations[29].get_type() == PIECE_TYPE.KNIGHT


@pytest.mark.parametrize("pending_delay", [None, 1])
def test_collecting_current_board_card_does_not_spawn_a_future_card(
    empty_state, pending_delay,
):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    empty_state.board_card_available = True
    empty_state.board_card_position = 2
    empty_state.board_enchantment = EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(
        uses=2
    )
    empty_state.pending_board_card_delay = pending_delay
    initial_random_state = empty_state.random_state
    action = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == 1 and action.destination == 2
    )

    result = GameSimulation.apply(empty_state, action)

    assert not result.board_card_available
    assert result.board_cards == []
    assert result.board_enchantment is None
    assert result.pending_board_card_delay == pending_delay
    assert result.random_state == initial_random_state
    assert len(result.white_cards) == 1
    assert result.white_cards[0].get_card_type() == (
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD)
    assert empty_state.board_card_available
    assert empty_state.board_card_position == 2
    assert empty_state.white_cards == []


def test_board_card_countdown_does_not_advance_in_simulation(empty_state):
    empty_state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    empty_state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    empty_state.board_card_available = True
    empty_state.board_card_position = 17
    empty_state.board_enchantment = EnchantmentCardType.PIECE_TELEPORT.create()
    empty_state.pending_board_card_delay = 1
    empty_state.board_cards = [
        (17, empty_state.board_enchantment),
    ]

    white_move = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == 1 and action.destination == 9
    )
    after_white_move = GameSimulation.apply(empty_state, white_move)

    assert after_white_move.board_card_available
    assert after_white_move.pending_board_card_delay == 1
    assert [position for position, _ in after_white_move.board_cards] == [17]

    black_move = next(
        action for action in GameSimulation.available_actions(after_white_move)
        if action.source == 57 and action.destination == 58
    )
    after_black_move = GameSimulation.apply(after_white_move, black_move)
    assert after_black_move.board_card_available
    assert after_black_move.pending_board_card_delay == 1
    assert [position for position, _ in after_black_move.board_cards] == [17]


@pytest.mark.parametrize(
    (
        "moving_color", "pawn_source", "pawn_destination",
        "capturer_source", "en_passant_destination", "captured_position",
    ),
    [
        (COLOR.WHITE, POS.E2, POS.E4, POS.D4, POS.E3, POS.E4),
        (COLOR.BLACK, POS.E7, POS.E5, POS.D5, POS.E6, POS.E5),
    ],
)
def test_pawn_can_capture_en_passant_after_a_double_step(
    empty_state,
    moving_color,
    pawn_source,
    pawn_destination,
    capturer_source,
    en_passant_destination,
    captured_position,
):
    empty_state.current_turn = moving_color
    moving_pawn = Piece(
        moving_color, PIECE_TYPE.PAWN, pawn_source.value)
    capturing_color = (
        COLOR.BLACK if moving_color == COLOR.WHITE else COLOR.WHITE)
    capturing_pawn = Piece(
        capturing_color, PIECE_TYPE.PAWN, capturer_source.value)
    capturing_pawn.set_has_moved()
    empty_state.pieces_locations[pawn_source.value] = moving_pawn
    empty_state.pieces_locations[capturer_source.value] = capturing_pawn

    double_step = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == pawn_source.value
        and action.destination == pawn_destination.value
        and action.card_index == -1
    )
    after_double_step = GameSimulation.apply(empty_state, double_step)

    assert after_double_step.en_passant_target == (
        POS.E3.value if moving_color == COLOR.WHITE else POS.E6.value
    )
    en_passant = next(
        action for action in GameSimulation.available_actions(after_double_step)
        if action.source == capturer_source.value
        and action.destination == en_passant_destination.value
        and action.card_index == -1
    )
    result = GameSimulation.apply(after_double_step, en_passant)

    assert result.pieces_locations[en_passant_destination.value].get_type() == (
        PIECE_TYPE.PAWN)
    assert not result.pieces_locations[captured_position.value].exists()
    assert result.get_captured_for(capturing_color)[0].get_type() == (
        PIECE_TYPE.PAWN)
    assert result.en_passant_target is None
    assert empty_state.en_passant_target is None
    assert empty_state.pieces_locations[pawn_source.value] is moving_pawn


def test_en_passant_right_expires_after_any_opponent_move(empty_state):
    empty_state.pieces_locations[POS.E2.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.PAWN, POS.E2.value)
    empty_state.pieces_locations[POS.D4.value] = Piece(
        COLOR.BLACK, PIECE_TYPE.PAWN, POS.D7.value)
    empty_state.pieces_locations[POS.D4.value].set_has_moved()

    white_double_step = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == POS.E2.value
        and action.destination == POS.E4.value
    )
    after_white_move = GameSimulation.apply(empty_state, white_double_step)
    black_move = next(
        action for action in GameSimulation.available_actions(after_white_move)
        if action.source == POS.D4.value
        and action.destination == POS.D3.value
    )

    result = GameSimulation.apply(after_white_move, black_move)

    assert result.en_passant_target is None
    assert not any(
        action.source == POS.D4.value
        and action.destination == POS.E3.value
        for action in GameSimulation.available_actions(result)
    )


def test_moved_pawn_cannot_double_step_from_its_starting_rank(empty_state):
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN, POS.E2.value)
    pawn.set_has_moved()
    empty_state.pieces_locations[POS.E2.value] = pawn

    assert not any(
        action.source == POS.E2.value
        and action.destination == POS.E4.value
        for action in GameSimulation.available_actions(empty_state)
    )


def test_state_cache_key_distinguishes_en_passant_and_castling_rights(
    empty_state,
):
    king_position, (queenside_rook, _) = add_castling_pieces(
        empty_state, COLOR.WHITE)
    original_key = empty_state.cache_key()
    moved_rook_state = empty_state.clone()
    moved_rook_state.pieces_locations[queenside_rook].set_has_moved()
    en_passant_state = empty_state.clone()
    en_passant_state.en_passant_target = POS.E3.value

    assert moved_rook_state.cache_key() != original_key
    assert en_passant_state.cache_key() != original_key
    assert empty_state.pieces_locations[king_position].has_moved() is False


@pytest.mark.parametrize(
    ("color", "castle_destination", "rook_destination", "rook_source"),
    [
        (COLOR.WHITE, POS.G1, POS.F1, POS.H1),
        (COLOR.WHITE, POS.C1, POS.D1, POS.A1),
        (COLOR.BLACK, POS.G8, POS.F8, POS.H8),
        (COLOR.BLACK, POS.C8, POS.D8, POS.A8),
    ],
)
def test_castling_moves_king_and_rook_and_consumes_rights(
    empty_state, color, castle_destination, rook_destination, rook_source,
):
    empty_state.current_turn = color
    king_position, _ = add_castling_pieces(empty_state, color)

    castle = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == king_position
        and action.destination == castle_destination.value
        and action.card_index == -1
    )
    result = GameSimulation.apply(empty_state, castle)

    assert result.pieces_locations[castle_destination.value].get_type() == (
        PIECE_TYPE.KING)
    assert result.pieces_locations[rook_destination.value].get_type() == (
        PIECE_TYPE.ROOK)
    assert not result.pieces_locations[king_position].exists()
    assert not result.pieces_locations[rook_source.value].exists()
    assert result.pieces_locations[castle_destination.value].has_moved()
    assert result.pieces_locations[rook_destination.value].has_moved()
    assert empty_state.pieces_locations[king_position].get_type() == (
        PIECE_TYPE.KING)
    assert empty_state.pieces_locations[rook_source.value].get_type() == (
        PIECE_TYPE.ROOK)


@pytest.mark.parametrize(
    ("attacker_position", "attacker_type", "castle_destination"),
    [
        (POS.E8, PIECE_TYPE.ROOK, POS.C1),
        (POS.F8, PIECE_TYPE.ROOK, POS.G1),
        (POS.G8, PIECE_TYPE.ROOK, POS.G1),
        (POS.H2, PIECE_TYPE.PAWN, POS.G1),
    ],
)
def test_castling_is_allowed_regardless_of_attacked_king_squares(
    empty_state, attacker_position, attacker_type, castle_destination,
):
    king_position, _ = add_castling_pieces(empty_state, COLOR.WHITE)
    empty_state.pieces_locations[attacker_position.value] = Piece(
        COLOR.BLACK, attacker_type, attacker_position.value)

    castle_destinations = {
        action.destination for action in GameSimulation.available_actions(
            empty_state)
        if action.source == king_position
    }

    assert castle_destination.value in castle_destinations


@pytest.mark.parametrize(
    ("blocking_piece", "forbidden_destination", "available_destination"),
    [
        (POS.F1, POS.G1, POS.C1),
        (POS.B1, POS.C1, POS.G1),
    ],
)
def test_castling_requires_every_square_between_king_and_rook_to_be_empty(
    empty_state, blocking_piece, forbidden_destination, available_destination,
):
    king_position, _ = add_castling_pieces(empty_state, COLOR.WHITE)
    empty_state.pieces_locations[blocking_piece.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.KNIGHT, blocking_piece.value)

    castle_destinations = {
        action.destination for action in GameSimulation.available_actions(
            empty_state)
        if action.source == king_position
    }

    assert forbidden_destination.value not in castle_destinations
    assert available_destination.value in castle_destinations


def test_castling_right_is_lost_after_king_moves_away_and_back(empty_state):
    king_position, (queenside_rook, kingside_rook) = add_castling_pieces(
        empty_state, COLOR.WHITE)
    empty_state.pieces_locations[POS.A8.value] = Piece(
        COLOR.BLACK, PIECE_TYPE.KNIGHT, POS.A8.value)
    king_move = next(
        action for action in GameSimulation.available_actions(empty_state)
        if action.source == king_position and action.destination == POS.E2.value
    )
    after_king_move = GameSimulation.apply(empty_state, king_move)
    black_move = next(
        action for action in GameSimulation.available_actions(after_king_move)
        if action.source == POS.A8.value and action.destination == POS.B6.value
    )
    after_black_move = GameSimulation.apply(after_king_move, black_move)
    king_return = next(
        action for action in GameSimulation.available_actions(after_black_move)
        if action.source == POS.E2.value and action.destination == king_position
    )
    returned = GameSimulation.apply(after_black_move, king_return)
    black_return_move = next(
        action for action in GameSimulation.available_actions(returned)
        if action.source == POS.B6.value and action.destination == POS.C4.value
    )
    returned = GameSimulation.apply(returned, black_return_move)

    assert returned.pieces_locations[king_position].has_moved()
    assert not any(
        action.source == king_position
        and action.destination in (POS.C1.value, POS.G1.value)
        for action in GameSimulation.available_actions(returned)
    )


def test_castling_right_is_lost_after_rook_moves_away_and_back(empty_state):
    king_position, (_, kingside_rook) = add_castling_pieces(
        empty_state, COLOR.WHITE)
    empty_state.pieces_locations[POS.A8.value] = Piece(
        COLOR.BLACK, PIECE_TYPE.KNIGHT, POS.A8.value)
    rook_move = next(
        action for action in GameSimulation.available_actions(empty_state)
            if action.source == kingside_rook
        and action.destination == POS.H2.value
    )
    after_rook_move = GameSimulation.apply(empty_state, rook_move)
    black_move = next(
        action for action in GameSimulation.available_actions(after_rook_move)
        if action.source == POS.A8.value and action.destination == POS.B6.value
    )
    after_black_move = GameSimulation.apply(after_rook_move, black_move)
    rook_return = next(
        action for action in GameSimulation.available_actions(after_black_move)
        if action.source == POS.H2.value
        and action.destination == kingside_rook
    )
    returned = GameSimulation.apply(after_black_move, rook_return)
    black_return_move = next(
        action for action in GameSimulation.available_actions(returned)
        if action.source == POS.B6.value and action.destination == POS.C4.value
    )
    returned = GameSimulation.apply(returned, black_return_move)

    castle_destinations = {
        action.destination for action in GameSimulation.available_actions(
            returned)
        if action.source == king_position
    }

    assert returned.pieces_locations[kingside_rook].has_moved()
    assert POS.G1.value not in castle_destinations
    assert POS.C1.value in castle_destinations
