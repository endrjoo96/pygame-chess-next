import os
import random

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import ChessAI, SearchConfig
from logic.game_simulation import GameSimulation
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState
from utils.run_config import (
    AI_SEARCH_CPU_PERCENT,
    AI_SEARCH_MAX_DEPTH,
    AI_SEARCH_TIME_LIMIT_SECONDS,
)


def make_black_to_move_state():
    return GameState(
        pieces_locations={position: Piece() for position in range(1, 65)},
        current_turn=COLOR.BLACK,
        turns_started={COLOR.WHITE: 1, COLOR.BLACK: 1},
        white_cards=[],
        black_cards=[],
        captured_white=[],
        captured_black=[],
        board_card_available=False,
        board_card_position=36,
        board_enchantment=None,
        pending_board_card_delay=None,
        random_state=random.Random(23).getstate(),
    )


def test_ai_finds_immediate_king_capture():
    state = make_black_to_move_state()
    state.pieces_locations[1] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[2] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=1, hidden_hand_samples=1),
        max_workers=1,
    )
    progress = []

    decision = ai.choose_action(
        observation,
        random.Random(5),
        progress_callback=lambda action, depth: progress.append((action, depth)),
    )

    assert decision.action is not None
    result = GameSimulation.apply(state, decision.action)
    assert result.get_winner() == COLOR.BLACK
    assert decision.completed_depth == 1
    assert [depth for _, depth in progress] == [0, 1]


def test_ai_returns_a_legal_fallback_when_search_budget_expires():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=1e-12, max_depth=4, hidden_hand_samples=1),
        max_workers=1,
    )

    decision = ai.choose_action(observation, random.Random(5))

    assert decision.action in GameSimulation.available_actions(state)
    assert decision.completed_depth == 0


def test_ai_default_sampling_is_reproducible_from_observation_seed():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.white_cards = [
        EnchantmentCardType.PAWN_SWORDSMAN.create(),
        EnchantmentCardType.PIECE_TELEPORT.create(),
    ]
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=1, hidden_hand_samples=2),
        max_workers=1,
    )

    first = ai.choose_action(observation)
    second = ai.choose_action(observation)

    assert first.action == second.action
    assert first.score == second.score
    assert first.completed_depth == second.completed_depth


def test_ai_only_accepts_black_to_move_observations():
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI()

    with pytest.raises(ValueError, match="not the AI player's turn"):
        ai.choose_action(observation)


def test_default_search_limits_match_run_properties():
    assert SearchConfig().time_limit_seconds == AI_SEARCH_TIME_LIMIT_SECONDS
    assert SearchConfig().max_depth == AI_SEARCH_MAX_DEPTH
    assert ChessAI().max_workers >= 1


@pytest.mark.parametrize(
    ("cpu_percent", "expected_workers"),
    [(1, 1), (12, 1), (50, 4), (99, 7), (100, 8)],
)
def test_cpu_percentage_limits_workers_with_floor_rounding(
    monkeypatch, cpu_percent, expected_workers
):
    monkeypatch.setattr("logic.chess_ai.os.cpu_count", lambda: 8)

    ai = ChessAI(cpu_percent=cpu_percent)

    assert ai.max_workers == expected_workers


def test_explicit_worker_count_overrides_cpu_percentage():
    assert ChessAI(max_workers=3, cpu_percent=1).max_workers == 3


def test_worker_count_is_capped_by_available_search_tasks():
    assert ChessAI(max_workers=8)._worker_count_for_tasks(3) == 3


@pytest.mark.parametrize("cpu_percent", [0, 101])
def test_ai_rejects_cpu_percentage_outside_supported_range(cpu_percent):
    with pytest.raises(ValueError, match="CPU usage percentage"):
        ChessAI(cpu_percent=cpu_percent)


def test_configured_cpu_percent_is_used_by_default():
    assert ChessAI().max_workers == max(
        1, (os.cpu_count() or 1) * AI_SEARCH_CPU_PERCENT // 100)


def test_parallel_search_matches_serial_search_and_reports_completed_depths():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    config = SearchConfig(
        time_limit_seconds=15,
        max_depth=2,
        hidden_hand_samples=2,
    )
    serial_progress = []
    parallel_progress = []

    serial_result = ChessAI(config, max_workers=1).choose_action(
        observation,
        random.Random(17),
        progress_callback=lambda action, depth: serial_progress.append(
            (action, depth)),
    )
    parallel_result = ChessAI(config, max_workers=2).choose_action(
        observation,
        random.Random(17),
        progress_callback=lambda action, depth: parallel_progress.append(
            (action, depth)),
    )

    assert parallel_result.action == serial_result.action
    assert parallel_result.score == pytest.approx(serial_result.score)
    assert parallel_result.completed_depth == serial_result.completed_depth == 2
    assert [depth for _, depth in parallel_progress] == [0, 1, 2]
    assert [depth for _, depth in serial_progress] == [0, 1, 2]
    assert parallel_result.visited_nodes == serial_result.visited_nodes


def test_evaluation_prefers_a_piece_not_under_immediate_attack():
    exposed = make_black_to_move_state()
    exposed.current_turn = COLOR.WHITE
    exposed.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    exposed.pieces_locations[9] = Piece(COLOR.BLACK, PIECE_TYPE.BISHOP)
    safe = exposed.clone()
    safe.pieces_locations[9] = Piece()
    safe.pieces_locations[10] = Piece(COLOR.BLACK, PIECE_TYPE.BISHOP)

    assert ChessAI.evaluate(safe) > ChessAI.evaluate(exposed)


def test_evaluation_prioritizes_king_safety_over_a_safe_square():
    exposed = make_black_to_move_state()
    exposed.current_turn = COLOR.WHITE
    exposed.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    exposed.pieces_locations[9] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    safe = exposed.clone()
    safe.pieces_locations[9] = Piece()
    safe.pieces_locations[10] = Piece(COLOR.BLACK, PIECE_TYPE.KING)

    assert ChessAI.evaluate(safe) > ChessAI.evaluate(exposed)


def test_evaluation_rewards_developing_a_minor_piece_toward_the_center():
    state = make_black_to_move_state()
    undeveloped = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT, starting_position=58)
    developed = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT, starting_position=58)
    state.pieces_locations[58] = undeveloped
    undeveloped_score = ChessAI.evaluate(state)

    state.pieces_locations[58] = Piece()
    state.pieces_locations[44] = developed

    assert ChessAI.evaluate(state) > undeveloped_score


def test_evaluation_values_access_to_a_visible_board_card():
    state = make_black_to_move_state()
    state.pieces_locations[36] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.board_card_available = True
    state.board_card_position = 37
    state.board_enchantment = EnchantmentCardType.PIECE_TELEPORT.create()
    close_opportunity = ChessAI.evaluate(state)

    state.board_card_position = 64

    assert close_opportunity > ChessAI.evaluate(state)


def test_ai_prefers_a_safe_board_card_over_a_small_capture():
    state = make_black_to_move_state()
    state.pieces_locations[28] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[29] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    state.board_card_available = True
    state.board_card_position = 20
    state.board_enchantment = EnchantmentCardType.PIECE_TELEPORT.create()
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=1, hidden_hand_samples=1),
        max_workers=1,
    )

    decision = ai.choose_action(observation, random.Random(5))

    assert decision.action is not None
    assert decision.action.destination == state.board_card_position
