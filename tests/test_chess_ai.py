import os
import random
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from threading import Event, Lock

import pytest

from benchmarks import benchmark_move_generation as benchmark
from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import POS
from logic.chess_ai import (
    ChessAI,
    SearchConfig,
    WorkerPoolInitializationCancelled,
    _RootEvaluation,
    _evaluate_root_action,
    _expand_ponder_white_action,
)
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from logic.opening_book import opening_hints
from logic.search_cache import Bound, CacheEntry
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState, RuneTrap
from utils.logging import log_info
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


@pytest.mark.parametrize(
    "seed,plies,position,expected_score,expected_threat",
    [
        (20261116, 13, "ordinary", 0.1425, 0.1925),
        (20261116, 13, "cards", 2.7425, 0.1925),
        (20261116, 13, "complex", 5.14, 2.5025),
        (20261117, 5, "ordinary", 1.475, 1.43),
        (20261117, 5, "cards", 4.1, 1.43),
        (20261117, 5, "complex", 6.17875, 3.665),
    ],
)
def test_evaluation_characterization_for_seeded_card_positions(
    seed, plies, position, expected_score, expected_threat,
):
    state = benchmark.make_seeded_position(seed, plies)
    if position == "cards":
        state = benchmark.make_card_position(state)
    elif position == "complex":
        state = benchmark.make_complex_card_position(state)
    original_key = state.cache_key()

    assert ChessAI.evaluate(state) == pytest.approx(
        expected_score, abs=1e-12, rel=0)
    assert ChessAI._threat_score(state) == pytest.approx(
        expected_threat, abs=1e-12, rel=0)
    assert state.cache_key() == original_key


def test_attack_map_deduplicates_rook_throw_and_respects_stun():
    state = make_black_to_move_state()
    state.pieces_locations[1] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[28] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[2] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    state.pieces_locations[3] = Piece(COLOR.WHITE, PIECE_TYPE.QUEEN)
    state.pieces_locations[4] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    state.pieces_locations[64] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.black_cards = [
        EnchantmentCardType.ROOK_TOWER_THROW.create(),
        EnchantmentCardType.ROOK_TOWER_THROW.create(),
    ]

    attacks = ChessAI._attack_map(state)

    assert attacks[COLOR.BLACK][4] == {1, 28}
    assert attacks[COLOR.BLACK][3] == {1}
    assert attacks[COLOR.BLACK][5] == {1}
    assert ChessAI._threat_score(state) == pytest.approx(46.125)
    state.pieces_locations[28].set_stunned_for_turns(2)
    assert ChessAI._attack_map(state)[COLOR.BLACK][4] == {1}
    assert ChessAI._threat_score(state) == pytest.approx(37.125)


def test_ai_finds_immediate_king_capture():
    state = make_black_to_move_state()
    state.pieces_locations[1] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[2] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=1),
        max_workers=1,
    )
    progress = []

    decision = ai.choose_action(
        observation,
        progress_callback=lambda action, depth: progress.append((action, depth)),
    )

    assert decision.action is not None
    result = GameSimulation.apply(state, decision.action)
    assert result.get_winner() == COLOR.BLACK
    assert decision.completed_depth == 1
    assert [depth for _, depth in progress] == [0, 1]


def test_white_prioritizes_valuable_captures_when_ordering_moves():
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    state.pieces_locations[3] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    state.pieces_locations[8] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[64] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    actions = GameSimulation.available_actions(state)
    capture = next(
        action for action in actions
        if action.source == 1 and action.destination == 3
    )

    ordered = ChessAI(max_workers=1)._order_actions(state, actions)

    assert ordered[0] == capture


def test_white_prioritizes_an_immediate_king_capture():
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    state.pieces_locations[3] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[64] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    actions = GameSimulation.available_actions(state)
    king_capture = next(
        action for action in actions
        if action.source == 1 and action.destination == 3
    )

    ordered = ChessAI(max_workers=1)._order_actions(state, actions)

    assert ordered[0] == king_capture


def test_opening_book_skips_position_key_after_its_covered_range(monkeypatch):
    state = make_black_to_move_state()
    state.turns_started = {COLOR.WHITE: 3, COLOR.BLACK: 2}

    def unexpected_position_key(_state):
        pytest.fail("Opening positions outside the book range need no key")

    monkeypatch.setattr(
        "logic.opening_book._position_key", unexpected_position_key)

    assert opening_hints(state) == ()


def test_ai_returns_a_legal_fallback_when_search_budget_expires():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=1e-12, max_depth=4),
        max_workers=1,
    )

    decision = ai.choose_action(observation)

    assert decision.action in GameSimulation.available_actions(state)
    assert decision.completed_depth == 0


def test_ai_returns_best_known_move_after_an_incomplete_iteration(monkeypatch):
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(SearchConfig(time_limit_seconds=2, max_depth=2), max_workers=1)
    initial_actions = ai._order_actions(
        state, GameSimulation.available_actions(state))
    shallow_candidate = initial_actions[0]
    deep_candidate = initial_actions[-1]

    def evaluate_root_action(
        search_state, action, depth, config, deadline, snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        if depth == 1:
            if action == shallow_candidate:
                return _RootEvaluation(15.0, 1)
            if action == deep_candidate:
                return _RootEvaluation(20.0, 1)
            return _RootEvaluation(0.0, 1)
        if action == deep_candidate:
            return _RootEvaluation(-10.0, 1)
        return _RootEvaluation(None, 1)

    monkeypatch.setattr("logic.chess_ai._evaluate_root_action", evaluate_root_action)

    decision = ai.choose_action(observation)

    assert decision.action == shallow_candidate
    assert decision.score == 15.0
    assert decision.completed_depth == 1


def test_root_search_passes_alpha_and_excludes_bound_only_candidates(monkeypatch):
    state = make_black_to_move_state()
    observation = GameObservation.from_state(state, COLOR.BLACK)
    actions = [
        GameAction(GameActionType.MOVE, 1, destination)
        for destination in (2, 3, 4)
    ]
    evaluated_alphas = []
    monkeypatch.setattr(
        GameSimulation, "available_actions", lambda _state: actions)
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action", lambda search_state, _action: search_state)
    monkeypatch.setattr(ChessAI, "_order_actions", lambda _self, _state, moves: moves)
    monkeypatch.setattr(ChessAI, "evaluate", staticmethod(lambda _state: 0.0))

    def evaluate_root_action(
        _state, action, _depth, _config, _deadline, _snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        evaluated_alphas.append(root_alpha)
        if action == actions[0]:
            return _RootEvaluation(5.0, 1)
        if action == actions[1]:
            return _RootEvaluation(
                4.0, 1, bound=Bound.UPPER, reliable=True)
        return _RootEvaluation(6.0, 1)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)
    candidate_updates = []

    result = ChessAI(
        SearchConfig(max_depth=1, cache_enabled=False), max_workers=1
    ).choose_action(
        observation,
        candidate_callback=lambda action, depth, score: candidate_updates.append(
            (action, depth, score)),
    )

    assert evaluated_alphas == [-float("inf"), 5.0, 5.0]
    assert result.action == actions[2]
    assert (actions[1], 1, 4.0) not in candidate_updates


def test_root_fail_low_discards_a_shallower_score_for_that_action(monkeypatch):
    state = make_black_to_move_state()
    observation = GameObservation.from_state(state, COLOR.BLACK)
    actions = [
        GameAction(GameActionType.MOVE, 1, destination)
        for destination in (2, 3, 4)
    ]
    monkeypatch.setattr(
        GameSimulation, "available_actions", lambda _state: actions)
    monkeypatch.setattr(
        GameSimulation,
        "_apply_generated_action",
        lambda search_state, _action: search_state,
    )
    monkeypatch.setattr(
        ChessAI, "_order_actions", lambda _self, _state, moves: list(moves))
    monkeypatch.setattr(
        ChessAI, "evaluate", staticmethod(lambda _state: 0.0))

    def evaluate_root_action(
        _state, action, depth, _config, _deadline, _snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        if depth == 1:
            return _RootEvaluation(10.0 - actions.index(action), 1)
        if action == actions[1]:
            return _RootEvaluation(
                -6.0, 1, bound=Bound.UPPER, reliable=True)
        return _RootEvaluation(
            -5.0 if action == actions[0] else -3.0, 1)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)

    result = ChessAI(
        SearchConfig(max_depth=2, cache_enabled=False), max_workers=1
    ).choose_action(observation)

    assert result.action == actions[2]
    assert result.score == -3.0
    assert result.completed_depth == 2


def test_ai_search_is_reproducible_for_the_same_observation():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.white_cards = [
        EnchantmentCardType.PAWN_SWORDSMAN.create(),
        EnchantmentCardType.PIECE_TELEPORT.create(),
    ]
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=1),
        max_workers=1,
    )

    first = ai.choose_action(observation)
    second = ai.choose_action(observation)

    assert first.action == second.action
    assert first.score == second.score
    assert first.completed_depth == second.completed_depth


def test_ai_passes_the_opponents_exact_cards_to_root_simulations(monkeypatch):
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.white_cards = [EnchantmentCardType.PAWN_SWORDSMAN.create()]
    observation = GameObservation.from_state(state, COLOR.BLACK)
    searched_states = []

    def evaluate_root_action(
        search_state, action, depth, config, deadline, snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        searched_states.append(search_state)
        return _RootEvaluation(0.0, 1)

    monkeypatch.setattr("logic.chess_ai._evaluate_root_action", evaluate_root_action)
    ai = ChessAI(SearchConfig(time_limit_seconds=2, max_depth=1), max_workers=1)

    result = ai.choose_action(observation)

    assert result.completed_depth == 1
    assert searched_states
    assert all(
        search_state.white_cards[0].get_card_type()
        == EnchantmentCardType.PAWN_SWORDSMAN
        for search_state in searched_states
    )


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


@pytest.mark.parametrize("debug_enabled", [True, False])
def test_ai_logs_search_metrics_only_when_debug_is_enabled(
    monkeypatch, debug_enabled
):
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    messages = []
    monkeypatch.setattr(
        "logic.chess_ai.is_enabled",
        lambda level: debug_enabled and level == "DEBUG",
    )
    monkeypatch.setattr("logic.chess_ai.log_debug", messages.append)

    decision = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=1),
        max_workers=1,
    ).choose_action(observation)

    metrics = [
        message for message in messages
        if message.startswith("AI search metrics:")
    ]
    assert decision.action is not None
    assert len(metrics) == int(debug_enabled)
    if debug_enabled:
        assert "workers=1" in metrics[0]
        assert "max_depth=1" in metrics[0]
        assert "completed_depth=1" in metrics[0]
        assert "elapsed=" in metrics[0]
        assert "nodes=" in metrics[0]
        assert "nodes_per_second=" in metrics[0]


def test_evaluation_reuses_basic_destinations_for_threat_assessment(monkeypatch):
    state = make_black_to_move_state()
    state.pieces_locations[1] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[9] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[64] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    calls = []
    original_destinations_for = GameSimulation.destinations_for

    def counted_destinations_for(
        piece, source, locations, enchantment=None, occupancy=None
    ):
        calls.append((source, enchantment))
        return original_destinations_for(
            piece, source, locations, enchantment, occupancy)

    monkeypatch.setattr(
        GameSimulation,
        "destinations_for",
        staticmethod(counted_destinations_for),
    )

    ChessAI.evaluate(state)

    eligible_sources = [
        position
        for position, piece in state.pieces_locations.items()
        if piece.exists() and piece.can_receive_enchantment()
    ]
    assert [source for source, enchantment in calls] == eligible_sources
    assert all(enchantment is None for _, enchantment in calls)


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


@pytest.mark.parametrize(
    ("max_depth", "pondered_depth", "expected_seconds"),
    [
        (5, None, 10.0),
        (5, 1, 10.0),
        (5, 3, 6.0),
        (5, 5, 2.0),
        (5, 8, 2.0),
        (1, 1, 10.0),
    ],
)
def test_search_time_budget_scales_with_ponder_depth(
    max_depth, pondered_depth, expected_seconds,
):
    ai = ChessAI(
        SearchConfig(time_limit_seconds=10, max_depth=max_depth),
        max_workers=1,
    )

    assert ai._search_time_limit_for_depth(pondered_depth) == pytest.approx(
        expected_seconds)


def test_search_uses_ponder_depth_for_current_state_and_logs_budget(monkeypatch):
    import logic.chess_ai as chess_ai

    state = make_black_to_move_state()
    action = GameAction(GameActionType.MOVE, 1, 2)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=10, max_depth=5),
        max_workers=1,
    )
    ai._ponder_completed_depths[state.cache_key()] = 3
    log_messages = []
    monkeypatch.setattr(chess_ai.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(chess_ai, "log_info", log_messages.append)
    monkeypatch.setattr(
        GameSimulation, "available_actions", lambda _state: [action])
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action",
        lambda search_state, _action: search_state.clone())
    monkeypatch.setattr(
        chess_ai,
        "_evaluate_root_action",
        lambda *args, **kwargs: _RootEvaluation(0.0, 1),
    )

    ai.choose_action(observation)

    assert ai._deadline == pytest.approx(106.0)
    assert log_messages[0] == (
        "AI search time budget: allocated=6.000s, configured=10.000s, "
        "ponder_depth=3, max_depth=5, fallback=False"
    )
    assert state.cache_key() not in ai._ponder_completed_depths


def test_ponder_worker_count_uses_ceiling_and_respects_task_count():
    ai = ChessAI(max_workers=9, ponder_cpu_percent=50)

    assert ai._ponder_worker_count_for_tasks(100) == 5
    assert ai._ponder_worker_count_for_tasks(3) == 3
    assert ChessAI(
        max_workers=9, ponder_cpu_percent=0
    )._ponder_worker_count_for_tasks(100) == 0


def test_ponder_stops_when_cache_reaches_its_limit(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    white_action = GameAction(GameActionType.MOVE, 1, 2)
    second_white_action = GameAction(GameActionType.MOVE, 2, 3)
    black_action = GameAction(GameActionType.MOVE, 3, 4)

    def available_actions(search_state):
        if search_state.current_turn == COLOR.BLACK:
            return [black_action]
        if search_state.double_move_step:
            return [second_white_action]
        return [white_action]

    def apply_generated_action(
        search_state, action, advance_board_card_clock=False,
    ):
        child = search_state.clone()
        if search_state.current_turn == COLOR.WHITE and not search_state.double_move_step:
            child.current_turn = COLOR.WHITE
            child.double_move_step = 1
        else:
            child.current_turn = COLOR.BLACK
            child.double_move_step = 0
        return child

    def evaluate_root_action(
        search_state, action, depth, config, deadline, cache_snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        ponder_root_keys.append(search_state.cache_key())
        entry = CacheEntry(
            ("pondered", search_state.cache_key()),
            depth,
            action,
            float(depth),
            Bound.EXACT,
        )
        return _RootEvaluation(float(depth), 1, (entry,))

    ponder_root_keys = []
    monkeypatch.setattr(GameSimulation, "available_actions", available_actions)
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action", apply_generated_action)
    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)
    ai = ChessAI(
        SearchConfig(max_depth=3, cache_max_entries=2),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None

    result = ai.ponder(state, Event())
    progress = ai.search_progress_stats()

    assert result.completed_depth == 2
    assert result.root_branches == 1
    assert result.stopped_reason == "cache-full"
    assert ai._ponder_completed_depths[ponder_root_keys[0]] == 2
    assert progress[11] == (("a1-b1", 1.0, 2),)
    assert len(ai._cache) == 2
    assert all(entry.root_scope_ids for entry in ai._cache.snapshot(2))
    assert not ai._worker_search_cancel_event.is_set()
    assert not ai._ponder_active


def test_ponder_white_expansion_matches_state_after_board_card_clock(monkeypatch):
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    state.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    state.pending_board_card_delay = 1
    white_action = GameAction(GameActionType.MOVE, 9, 17)
    monkeypatch.setattr(
        GameSimulation,
        "available_actions",
        lambda current_state: (
            [white_action] if current_state.current_turn == COLOR.WHITE else []
        ),
    )
    monkeypatch.setattr("logic.chess_ai._WORKER_SEARCH_CANCEL_EVENT", None)

    actual_state = GameSimulation.apply(
        state, white_action, advance_board_card_clock=True)
    pondered_roots = _expand_ponder_white_action(state, white_action)

    assert len(pondered_roots) == 1
    assert actual_state.random_state != state.random_state
    assert pondered_roots[0].cache_key() == actual_state.cache_key()


def test_ponder_reports_top_five_dangerous_white_moves(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=1, cache_max_entries=16),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    white_actions = tuple(
        GameAction(GameActionType.MOVE, source, source + 8)
        for source in range(1, 7)
    )
    scores = (3.0, -2.0, 0.5, 6.0, -1.0, 1.0, -3.0)
    reply_scores = (8.0, -2.0, 0.5, -4.0, -1.0, 2.0, -3.0)
    roots = {}
    for action_index, action in enumerate(white_actions):
        branch_indexes = (0, 6) if action_index == 0 else (action_index,)
        roots[action] = []
        for branch_index in branch_indexes:
            root = state.clone()
            root.current_turn = COLOR.BLACK
            root.selected_piece_position = branch_index
            roots[action].append(root)
        roots[action] = tuple(roots[action])
    black_action = GameAction(GameActionType.MOVE, 3, 4)
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, action: roots[action],
    )
    monkeypatch.setattr(
        GameSimulation,
        "available_actions",
        lambda current_state: (
            list(white_actions)
            if current_state.current_turn == COLOR.WHITE
            else [black_action]
        ),
    )
    monkeypatch.setattr(ai, "_order_actions", lambda _state, actions: actions)
    monkeypatch.setattr(
        ai, "evaluate",
        lambda current_state: scores[current_state.selected_piece_position],
    )
    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action",
        lambda root, *_args, **_kwargs: _RootEvaluation(
            reply_scores[root.selected_piece_position],
            1,
        ),
    )

    ai.ponder(state, Event())

    assert ai.search_progress_stats()[11] == (
        ("d1-d2", -4.0, 2),
        ("a1-a2", -3.0, 2),
        ("b1-b2", -2.0, 2),
        ("e1-e2", -1.0, 2),
        ("c1-c2", 0.5, 2),
    )


def test_ponder_dangerous_moves_use_score_after_black_reply(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=2, cache_max_entries=3),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    white_actions = (
        GameAction(GameActionType.MOVE, 1, 2),
        GameAction(GameActionType.MOVE, 2, 3),
    )
    roots = {}
    for action_index, action in enumerate(white_actions):
        root = state.clone()
        root.current_turn = COLOR.BLACK
        root.selected_piece_position = action_index
        roots[action] = root
    black_action = GameAction(GameActionType.MOVE, 3, 4)
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, action: (roots[action],),
    )
    monkeypatch.setattr(
        GameSimulation,
        "available_actions",
        lambda current_state: (
            list(white_actions)
            if current_state.current_turn == COLOR.WHITE
            else [black_action]
        ),
    )
    monkeypatch.setattr(ai, "_order_actions", lambda _state, actions: actions)
    monkeypatch.setattr(
        ai, "evaluate",
        lambda root: 4.0 if root.selected_piece_position == 0 else -2.0,
    )

    def evaluate_root_action(
        root, action, depth, *_args, **_kwargs,
    ):
        score = -1.0 if root.selected_piece_position == 0 else -5.0
        entry = CacheEntry(
            ("pondered", root.selected_piece_position, depth),
            depth,
            action,
            score,
            Bound.EXACT,
        )
        return _RootEvaluation(score, 1, (entry,))

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)

    result = ai.ponder(state, Event())

    assert result.stopped_reason == "cache-full"
    assert ai.search_progress_stats()[11] == (
        ("b1-c1", -5.0, 2),
        ("a1-b1", -1.0, 2),
    )


def test_ponder_scores_white_move_that_leaves_black_without_actions(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=2, cache_max_entries=16),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    white_actions = (
        GameAction(GameActionType.MOVE, 1, 2),
        GameAction(GameActionType.MOVE, 2, 3),
    )
    roots = {}
    for action_index in range(2):
        root = state.clone()
        root.current_turn = COLOR.BLACK
        root.selected_piece_position = action_index
        roots[white_actions[action_index]] = root
    black_action = GameAction(GameActionType.MOVE, 3, 4)
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, action: (roots[action],),
    )
    monkeypatch.setattr(
        GameSimulation,
        "available_actions",
        lambda current_state: (
            list(white_actions)
            if current_state.current_turn == COLOR.WHITE
            else (
                [] if current_state.selected_piece_position == 0
                else [black_action]
            )
        ),
    )
    monkeypatch.setattr(ai, "_order_actions", lambda _state, actions: actions)
    monkeypatch.setattr(
        ai,
        "evaluate",
        lambda current_state: (
            -100_000.0
            if current_state.selected_piece_position == 0 else 0.0
        ),
    )
    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action",
        lambda *_args, **_kwargs: _RootEvaluation(1.0, 1),
    )

    ai.ponder(state, Event())

    assert ai.search_progress_stats()[11] == (
        ("a1-b1", -100_000.0, 1),
        ("b1-c1", 1.0, 2),
    )


def test_ponder_extends_retained_cache_as_each_root_action_finishes(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=1, cache_max_entries=8),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None

    ponder_state = make_black_to_move_state()
    ponder_state.current_turn = COLOR.WHITE
    first_root = ponder_state.clone()
    first_root.current_turn = COLOR.BLACK
    second_root = first_root.clone()
    second_root.selected_piece_position = 2
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, _action: (first_root, second_root),
    )

    retained_entry = CacheEntry(
        ("retained-branch",), 3, None, 1.0, Bound.EXACT)
    ai._cache.put(retained_entry)
    observed_cache_sizes = []
    action = GameAction(GameActionType.MOVE, 3, 4)
    monkeypatch.setattr(
        GameSimulation, "available_actions", lambda _state: [action])
    monkeypatch.setattr(ai, "_order_actions", lambda _state, actions: actions)

    def evaluate_root_action(
        state, action, depth, _config, _deadline, _cache_snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        observed_cache_sizes.append(len(ai._cache))
        entry = CacheEntry(
            ("pondered", state.cache_key()), depth, action, float(depth),
            Bound.EXACT)
        return _RootEvaluation(float(depth), 1, (entry,))

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)

    result = ai.ponder(ponder_state, Event())

    assert result.completed_depth == 1
    assert observed_cache_sizes == [1, 2]
    assert ai._cache.get(retained_entry.key, retained_entry.depth) == retained_entry
    assert len(ai._cache) == 3
    assert ai.cache_diagnostics() == (True, 3, 8, 0, 3)


def test_ponder_shares_alpha_sequentially_within_each_branch(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=1, cache_max_entries=16),
        max_workers=2,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    ponder_state = make_black_to_move_state()
    ponder_state.current_turn = COLOR.WHITE
    first_root = ponder_state.clone()
    first_root.current_turn = COLOR.BLACK
    first_root.selected_piece_position = 1
    second_root = first_root.clone()
    second_root.selected_piece_position = 2
    first_actions = [
        GameAction(GameActionType.MOVE, 1, 2),
        GameAction(GameActionType.MOVE, 1, 3),
    ]
    second_actions = [
        GameAction(GameActionType.MOVE, 2, 3),
        GameAction(GameActionType.MOVE, 2, 4),
    ]
    actions_by_root = {1: first_actions, 2: second_actions}
    observed = []
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, _action: (first_root, second_root),
    )

    def available_actions(root):
        if root.current_turn == COLOR.WHITE:
            return [GameAction(GameActionType.MOVE, 1, 2)]
        return actions_by_root[root.selected_piece_position]

    monkeypatch.setattr(
        GameSimulation, "available_actions", available_actions)
    monkeypatch.setattr(
        ai, "_order_actions", lambda _root, actions: list(actions))

    def evaluate_root_action(
        root, action, _depth, _config, _deadline, _snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        root_index = root.selected_piece_position
        observed.append((root_index, action, root_alpha))
        if action == first_actions[0]:
            score = 10.0
        elif action == first_actions[1]:
            score = 9.0
        elif action == second_actions[0]:
            score = 20.0
        else:
            score = 22.0
        bound = (
            Bound.UPPER
            if action == first_actions[1] else Bound.EXACT
        )
        entry = CacheEntry(
            ("ponder-branch-child", root_index, action.destination),
            1,
            None,
            score,
            Bound.EXACT,
        )
        return _RootEvaluation(
            score, 1, (entry,), bound=bound, reliable=True)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)

    result = ai.ponder(ponder_state, Event())

    assert result.completed_depth == 1
    assert observed == [
        (1, first_actions[0], -float("inf")),
        (2, second_actions[0], -float("inf")),
        (1, first_actions[1], 10.0),
        (2, second_actions[1], 20.0),
    ]
    assert len(ai._cache) == 4
    for root, actions in (
        (first_root, first_actions), (second_root, second_actions)
    ):
        for action in actions:
            scope_id = ai._cache.scope_id_for(root.cache_key(), action)
            entry = ai._cache.get(
                ("ponder-branch-child", root.selected_piece_position,
                 action.destination),
                1,
            )
            assert entry.root_scope_ids == frozenset((scope_id,))


def test_ponder_prioritizes_best_white_positions_without_pruning(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=1, cache_max_entries=16),
        max_workers=2,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None

    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    white_actions = [
        GameAction(GameActionType.MOVE, 1, 2),
        GameAction(GameActionType.MOVE, 1, 3),
    ]
    roots = {}
    for position in (5, 6):
        root = state.clone()
        root.current_turn = COLOR.BLACK
        root.selected_piece_position = position
        roots[position] = root
    black_actions = {
        5: [
            GameAction(GameActionType.MOVE, 5, 7),
            GameAction(GameActionType.MOVE, 5, 8),
        ],
        6: [
            GameAction(GameActionType.MOVE, 6, 7),
            GameAction(GameActionType.MOVE, 6, 8),
        ],
    }
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, action: (
            roots[5] if action == white_actions[0] else roots[6],
        ),
    )
    monkeypatch.setattr(
        GameSimulation,
        "available_actions",
        lambda current_state: (
            white_actions
            if current_state.current_turn == COLOR.WHITE
            else black_actions[current_state.selected_piece_position]
        ),
    )
    monkeypatch.setattr(ai, "_order_actions", lambda _state, actions: actions)
    monkeypatch.setattr(
        ai,
        "evaluate",
        lambda root: {5: 10.0, 6: -10.0}[root.selected_piece_position],
    )
    evaluated = []

    def evaluate_root_action(
        root, action, _depth, _config, _deadline, _snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        evaluated.append((root.selected_piece_position, action))
        return _RootEvaluation(0.0, 1)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)

    result = ai.ponder(state, Event())

    assert result.completed_depth == 1
    assert evaluated == [
        (6, black_actions[6][0]),
        (5, black_actions[5][0]),
        (6, black_actions[6][1]),
        (5, black_actions[5][1]),
    ]


def test_ponder_deepens_priority_branch_to_limit_before_next_branch(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=2, cache_max_entries=32),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None

    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    white_action = GameAction(GameActionType.MOVE, 1, 2)
    roots = {}
    for position in (5, 6):
        root = state.clone()
        root.current_turn = COLOR.BLACK
        root.selected_piece_position = position
        roots[position] = root
    black_actions = {
        5: [
            GameAction(GameActionType.MOVE, 5, 7),
            GameAction(GameActionType.MOVE, 5, 8),
        ],
        6: [
            GameAction(GameActionType.MOVE, 6, 7),
            GameAction(GameActionType.MOVE, 6, 8),
        ],
    }
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, _action: (roots[5], roots[6]),
    )
    monkeypatch.setattr(
        GameSimulation,
        "available_actions",
        lambda current_state: (
            [white_action]
            if current_state.current_turn == COLOR.WHITE
            else black_actions[current_state.selected_piece_position]
        ),
    )
    monkeypatch.setattr(ai, "_order_actions", lambda _state, actions: actions)
    monkeypatch.setattr(
        ai,
        "evaluate",
        lambda root: {5: 10.0, 6: -10.0}[root.selected_piece_position],
    )
    evaluated = []

    def evaluate_root_action(
        root, action, depth, _config, _deadline, _snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        evaluated.append((root.selected_piece_position, depth, action))
        return _RootEvaluation(0.0, 1)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)

    result = ai.ponder(state, Event())

    assert result.max_branch_depth == 2
    assert result.root_branches == 2
    assert evaluated == [
        (6, 1, black_actions[6][0]),
        (6, 1, black_actions[6][1]),
        (6, 2, black_actions[6][0]),
        (6, 2, black_actions[6][1]),
        (5, 1, black_actions[5][0]),
        (5, 1, black_actions[5][1]),
        (5, 2, black_actions[5][0]),
        (5, 2, black_actions[5][1]),
    ]
    assert ai.search_progress_stats()[11] == (("a1-b1", 0.0, 2),)
    assert ai.search_progress_stats()[9:] == (
        ((2, 2),),
        2,
        (("a1-b1", 0.0, 2),),
    )


def test_ponder_dispatches_search_before_all_expansions_finish(monkeypatch):
    import logic.chess_ai as chess_ai

    white_actions = [
        GameAction(GameActionType.MOVE, 1, 2),
        GameAction(GameActionType.MOVE, 1, 3),
    ]
    black_action = GameAction(GameActionType.MOVE, 3, 4)
    ponder_state = make_black_to_move_state()
    ponder_state.current_turn = COLOR.WHITE
    first_root = ponder_state.clone()
    first_root.current_turn = COLOR.BLACK
    first_root.selected_piece_position = 1
    second_root = first_root.clone()
    second_root.selected_piece_position = 2

    class DynamicExecutor:
        def __init__(self):
            self.expansion_future = None
            self.search_started_early = False
            self.task_kinds = []

        def submit(self, function, *args, **kwargs):
            future = Future()
            if function is expand_action:
                self.task_kinds.append("expand")
                if args[1] == white_actions[0]:
                    future.set_result((first_root,))
                else:
                    self.expansion_future = future
            elif function is evaluate_action:
                self.task_kinds.append("search")
                if not self.expansion_future.done():
                    self.search_started_early = True
                    self.expansion_future.set_result((second_root,))
                future.set_result(_RootEvaluation(0.0, 1))
            else:
                raise AssertionError("Unexpected pondering task")
            return future

    def expand_action(_state, _action):
        raise AssertionError("The executor controls expansion results")

    def evaluate_action(*_args, **_kwargs):
        raise AssertionError("The executor controls search results")

    ai = ChessAI(
        SearchConfig(max_depth=1, cache_max_entries=16),
        max_workers=2,
        ponder_cpu_percent=100,
    )
    executor = DynamicExecutor()
    ai._worker_pool = executor
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    monkeypatch.setattr(chess_ai, "_expand_ponder_white_action", expand_action)
    monkeypatch.setattr(chess_ai, "_evaluate_root_action", evaluate_action)
    monkeypatch.setattr(
        GameSimulation,
        "available_actions",
        lambda state: white_actions if state.current_turn == COLOR.WHITE
        else [black_action],
    )
    monkeypatch.setattr(ai, "_order_actions", lambda _state, actions: actions)

    result = ai.ponder(ponder_state, Event())

    assert result.completed_depth == 1
    assert result.root_branches == 2
    assert executor.search_started_early
    assert executor.task_kinds == ["expand", "expand", "search", "search"]


def test_ponder_reuses_each_root_key_and_action_group_across_depths(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=3, cache_max_entries=16),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    ponder_state = make_black_to_move_state()
    ponder_state.current_turn = COLOR.WHITE
    root_state = ponder_state.clone()
    root_state.current_turn = COLOR.BLACK
    key_calls = []
    original_cache_key = root_state.cache_key

    def counted_cache_key():
        key_calls.append(True)
        return original_cache_key()

    root_state.cache_key = counted_cache_key
    action = GameAction(GameActionType.MOVE, 1, 2)
    available_action_calls = []
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, _action: (root_state,),
    )

    def available_actions(search_state):
        if search_state.current_turn == COLOR.WHITE:
            return [action]
        available_action_calls.append(True)
        return [action]

    monkeypatch.setattr(
        GameSimulation, "available_actions", available_actions)
    monkeypatch.setattr(
        ai, "_order_actions", lambda _state, actions: list(actions))
    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action",
        lambda _state, _action, depth, *_args, **_kwargs:
            _RootEvaluation(float(depth), 1),
    )

    result = ai.ponder(ponder_state, Event())

    assert result.completed_depth == 3
    assert len(key_calls) == 1
    assert len(available_action_calls) == 1


def test_ponder_generates_later_task_groups_only_when_needed(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    cancellation_event = Event()
    ai = ChessAI(
        SearchConfig(max_depth=3, cache_max_entries=16),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    ponder_state = make_black_to_move_state()
    ponder_state.current_turn = COLOR.WHITE
    first_root = ponder_state.clone()
    first_root.current_turn = COLOR.BLACK
    second_root = first_root.clone()
    second_root.selected_piece_position = 2
    action = GameAction(GameActionType.MOVE, 1, 2)
    generated_roots = []
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, _action: (first_root, second_root),
    )

    def available_actions(search_state):
        if search_state.current_turn == COLOR.WHITE:
            return [action]
        generated_roots.append(search_state)
        return [action]

    monkeypatch.setattr(
        GameSimulation, "available_actions", available_actions)
    monkeypatch.setattr(
        ai, "_order_actions", lambda _state, actions: list(actions))

    def cancel_after_first_task(*_args, **_kwargs):
        cancellation_event.set()
        return _RootEvaluation(0.0, 1)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", cancel_after_first_task)

    result = ai.ponder(ponder_state, cancellation_event)

    assert result.stopped_reason == "cancelled"
    assert generated_roots == [first_root]


def test_ponder_reports_live_nodes_and_branch_depth_progress(monkeypatch):
    import logic.chess_ai as chess_ai

    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            future = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as error:
                future.set_exception(error)
            return future

    ai = ChessAI(
        SearchConfig(max_depth=1, cache_max_entries=16),
        max_workers=1,
        ponder_cpu_percent=100,
    )
    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()
    ai.prepare_workers = lambda **kwargs: None
    status_values = [chess_ai._WORKER_IDLE]
    status_pids = [123]
    depth_values = [0]
    cache_entry_values = [0]
    node_values = [0]
    status_lock = Lock()
    ai._worker_status_values = status_values
    ai._worker_status_pids = status_pids
    ai._worker_depth_values = depth_values
    ai._worker_cache_entry_values = cache_entry_values
    ai._worker_node_values = node_values
    ai._worker_status_process_lock = status_lock
    ai._worker_pool_state = "ready"
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_VALUES", status_values)
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_PIDS", status_pids)
    monkeypatch.setattr(chess_ai, "_WORKER_DEPTH_VALUES", depth_values)
    monkeypatch.setattr(
        chess_ai, "_WORKER_CACHE_ENTRY_VALUES", cache_entry_values)
    monkeypatch.setattr(chess_ai, "_WORKER_NODE_VALUES", node_values)
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_LOCK", status_lock)
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_INDEX", 0)

    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    action = GameAction(GameActionType.MOVE, 1, 2)
    observed_progress = []
    monkeypatch.setattr(
        "logic.chess_ai._expand_ponder_white_action",
        lambda _state, _action: (state,),
    )
    monkeypatch.setattr(
        ai, "_order_actions", lambda _state, actions: actions)
    monkeypatch.setattr(
        GameSimulation, "available_actions", lambda _state: [action])

    def evaluate_root_action(
        _state, _action, _depth, _config, _deadline, _cache_snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        node_progress_callback = (
            node_progress_callback or chess_ai._set_current_worker_visited_nodes)
        chess_ai._set_current_worker_status(chess_ai._WORKER_BUSY)
        node_progress_callback(128)
        observed_progress.append(ai.search_progress_stats())
        node_progress_callback(0)
        chess_ai._set_current_worker_status(chess_ai._WORKER_IDLE)
        return _RootEvaluation(0.0, 128)

    monkeypatch.setattr(
        chess_ai, "_evaluate_root_action", evaluate_root_action)

    result = ai.ponder(state, Event())

    assert result.visited_nodes == 128
    assert observed_progress == [
        (
            "pondering", 0, 0, 128, 1, 1, 1, 0, 1, ((0, 1),), 0,
            (),
        )
    ]
    assert ai.search_progress_stats() == (
        "idle", 0, 0, 128, 1, 1, 1, 1, 1, ((1, 1),), 1,
        (("a1-b1", 0.0, 2),),
    )


def test_pondering_is_disabled_when_ponder_percent_is_zero():
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    ai = ChessAI(max_workers=1, ponder_cpu_percent=0)

    result = ai.ponder(state)

    assert result.stopped_reason == "disabled"
    assert ai._worker_pool is None


def test_pondering_reuses_the_persistent_process_pool():
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    state.pieces_locations[64] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    ai = ChessAI(
        SearchConfig(max_depth=2, cache_max_entries=64),
        max_workers=1,
        ponder_cpu_percent=100,
    )

    try:
        first_result = ai.ponder(state)
        worker_pool = ai._worker_pool
        second_result = ai.ponder(state)

        assert worker_pool is not None
        assert ai._worker_pool is worker_pool
        assert first_result.completed_depth == 2
        assert second_result.completed_depth == 2
        assert len(ai._cache) > 0
    finally:
        ai.shutdown_worker_pool()


def test_prepared_worker_pool_reports_readiness_and_is_reused():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(SearchConfig(time_limit_seconds=5, max_depth=1), max_workers=2)
    progress = []
    worker_statuses = []

    def report_progress(ready, total):
        progress.append((
            ready,
            total,
            ai._worker_probe_started_count.value,
            time.monotonic(),
        ))
        worker_statuses.append(ai.worker_stats())

    try:
        with ThreadPoolExecutor(max_workers=1) as startup_executor:
            startup_executor.submit(
                ai.prepare_workers,
                report_progress,
                minimum_progress_interval_seconds=0.06,
            ).result()
        worker_pool = ai._worker_pool

        assert worker_pool is not None
        assert [(ready, total, started) for ready, total, started, _ in progress] == [
            (1, 2, 1),
            (2, 2, 2),
        ]
        assert any(
            worker.state == "initializing" for worker in worker_statuses[0])
        assert progress[1][3] - progress[0][3] >= 0.05
        prepared_workers = ai.worker_stats()
        assert [worker.state for worker in prepared_workers] == ["idle", "idle"]
        assert [worker.mode for worker in prepared_workers] == ["-", "-"]
        assert [worker.root for worker in prepared_workers] == ["-", "-"]
        assert len({worker.pid for worker in prepared_workers}) == 2
        assert [worker.cache_entries for worker in prepared_workers] == [0, 0]
        assert [worker.visited_nodes for worker in prepared_workers] == [0, 0]
        ai.choose_action(observation)
        assert ai._worker_pool is worker_pool
        completed_workers = ai.worker_stats()
        assert [worker.state for worker in completed_workers] == [
            "idle", "idle"]
        assert [worker.mode for worker in completed_workers] == ["-", "-"]
        assert [worker.root for worker in completed_workers] == ["-", "-"]
        ai.choose_action(observation)
        assert ai._worker_pool is worker_pool
    finally:
        ai.shutdown_worker_pool()

    assert ai._worker_pool is None
    assert [worker.state for worker in ai.worker_stats()] == [
        "not-started", "not-started"]
    ai.shutdown_worker_pool()


def test_cache_and_local_worker_diagnostics():
    ai = ChessAI(
        SearchConfig(cache_enabled=True, cache_max_entries=2),
        max_workers=1,
    )
    assert ai.cache_stats() == (True, 0, 2, 0)
    assert [(worker.state, worker.is_local) for worker in ai.worker_stats()] == [
        ("idle", True)]

    ai._cache.put(CacheEntry(("one",), 1, None, 1.0, Bound.EXACT))
    ai._cache.put(CacheEntry(("two",), 1, None, 2.0, Bound.EXACT))
    ai._cache.put(CacheEntry(("three",), 1, None, 3.0, Bound.EXACT))
    assert ai.cache_stats() == (True, 2, 2, 1)

    ai._set_local_worker_busy(True)
    local_worker = ai.worker_stats()[0]
    assert local_worker.state == "busy"
    assert local_worker.mode == "-"
    assert local_worker.root == "-"
    ai._set_local_worker_busy(False)

    disabled_cache = ChessAI(
        SearchConfig(cache_enabled=False, cache_max_entries=2),
        max_workers=1,
    )
    assert disabled_cache.cache_stats() == (False, 0, 2, 0)


def test_worker_stats_reports_active_mode_and_root(monkeypatch):
    import logic.chess_ai as chess_ai_module

    ai = ChessAI(max_workers=2)
    shared_lock = Lock()
    status_values = [chess_ai_module._WORKER_IDLE] * 2
    status_pids = [101, 202]
    mode_values = [chess_ai_module._WORKER_MODE_NONE] * 2
    root_values = [0, 0]
    depth_values = [0, 0]
    cache_entry_values = [0, 0]
    node_values = [0, 0]

    ai._worker_status_values = status_values
    ai._worker_status_pids = status_pids
    ai._worker_mode_values = mode_values
    ai._worker_root_values = root_values
    ai._worker_depth_values = depth_values
    ai._worker_cache_entry_values = cache_entry_values
    ai._worker_node_values = node_values
    ai._worker_status_process_lock = shared_lock
    monkeypatch.setattr(chess_ai_module, "_WORKER_STATUS_VALUES", status_values)
    monkeypatch.setattr(chess_ai_module, "_WORKER_MODE_VALUES", mode_values)
    monkeypatch.setattr(chess_ai_module, "_WORKER_ROOT_VALUES", root_values)
    monkeypatch.setattr(chess_ai_module, "_WORKER_DEPTH_VALUES", depth_values)
    monkeypatch.setattr(chess_ai_module, "_WORKER_STATUS_LOCK", shared_lock)
    monkeypatch.setattr(chess_ai_module, "_WORKER_STATUS_INDEX", 0)

    chess_ai_module._set_current_worker_status(
        chess_ai_module._WORKER_BUSY,
        chess_ai_module._WORKER_MODE_SEARCH,
        POS.C2.value,
        3,
    )
    worker = ai.worker_stats()[0]
    assert (
        worker.state, worker.mode, worker.root, worker.search_depth
    ) == ("busy", "search", "C2", 3)

    chess_ai_module._set_current_worker_status(
        chess_ai_module._WORKER_BUSY,
        chess_ai_module._WORKER_MODE_PREPARE,
        POS.D2.value,
    )
    worker = ai.worker_stats()[0]
    assert (worker.state, worker.mode, worker.root) == (
        "busy", "prepare", "D2")
    assert worker.search_depth is None

    chess_ai_module._set_current_worker_status(chess_ai_module._WORKER_IDLE)
    worker = ai.worker_stats()[0]
    assert (worker.state, worker.mode, worker.root) == ("idle", "-", "-")
    assert worker.search_depth is None


def test_worker_tasks_publish_and_clear_their_mode(monkeypatch):
    import logic.chess_ai as chess_ai_module

    status_calls = []
    debug_logs = []
    monkeypatch.setattr(
        "logic.chess_ai.is_enabled",
        lambda level: level == "DEBUG",
    )
    monkeypatch.setattr("logic.chess_ai.log_debug", debug_logs.append)
    monkeypatch.setattr(
        chess_ai_module,
        "_set_current_worker_status",
        lambda status, mode=0, root_position=0, search_depth=None:
            status_calls.append((status, mode, root_position, search_depth)),
    )
    monkeypatch.setattr(
        GameSimulation,
        "_apply_generated_action",
        lambda _state, _action: object(),
    )
    monkeypatch.setattr(
        ChessAI,
        "_search_with_proof",
        lambda _self, _state, _depth, _alpha, _beta, allow_lmr=True: (
            1.0, True),
    )
    search_action = GameAction(
        GameActionType.MOVE, POS.C2.value, POS.C4.value)
    _evaluate_root_action(
        object(),
        search_action,
        1,
        SearchConfig(max_depth=1),
        time.monotonic() + 1,
        cache_size_callback=lambda _size: None,
        node_progress_callback=lambda _nodes: None,
    )
    assert status_calls == [
        (
            chess_ai_module._WORKER_BUSY,
            chess_ai_module._WORKER_MODE_SEARCH,
            POS.C2.value,
            1,
        ),
        (
            chess_ai_module._WORKER_IDLE,
            chess_ai_module._WORKER_MODE_NONE,
            0,
            None,
        ),
    ]

    class BlackRoot:
        current_turn = COLOR.BLACK

        @staticmethod
        def get_winner():
            return None

    status_calls.clear()
    monkeypatch.setattr(
        GameSimulation,
        "_apply_generated_action",
        lambda _state, _action, **_kwargs: BlackRoot(),
    )
    prepare_action = GameAction(
        GameActionType.MOVE, POS.D2.value, POS.D4.value)
    roots = chess_ai_module._expand_ponder_white_action(
        object(), prepare_action)
    assert len(roots) == 1
    assert status_calls == [
        (
            chess_ai_module._WORKER_BUSY,
            chess_ai_module._WORKER_MODE_PREPARE,
            POS.D2.value,
            None,
        ),
        (
            chess_ai_module._WORKER_IDLE,
            chess_ai_module._WORKER_MODE_NONE,
            0,
            None,
        ),
    ]

    def raise_failure(_state, _action, **_kwargs):
        raise RuntimeError("worker task failed")

    status_calls.clear()
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action", raise_failure)
    with pytest.raises(RuntimeError, match="worker task failed"):
        _evaluate_root_action(
            object(),
            search_action,
            1,
            SearchConfig(max_depth=1),
            time.monotonic() + 1,
            cache_size_callback=lambda _size: None,
            node_progress_callback=lambda _nodes: None,
        )
    assert [call[0] for call in status_calls] == [
        chess_ai_module._WORKER_BUSY,
        chess_ai_module._WORKER_IDLE,
    ]

    status_calls.clear()
    with pytest.raises(RuntimeError, match="worker task failed"):
        chess_ai_module._expand_ponder_white_action(
            object(), prepare_action)
    assert [call[0] for call in status_calls] == [
        chess_ai_module._WORKER_BUSY,
        chess_ai_module._WORKER_IDLE,
    ]

    task_logs = [
        message for message in debug_logs
        if message.startswith("AI worker PID ")
    ]
    assert len(task_logs) == 8
    assert "started search task" in task_logs[0]
    assert "finished search task" in task_logs[1]
    assert "status=completed" in task_logs[1]
    assert "started ponder preparation task" in task_logs[2]
    assert "finished ponder preparation task" in task_logs[3]
    assert "status=completed" in task_logs[3]
    assert "finished search task" in task_logs[5]
    assert "status=failed" in task_logs[5]
    assert "finished ponder preparation task" in task_logs[7]
    assert "status=failed" in task_logs[7]


def test_local_worker_cache_size_is_visible_during_search(monkeypatch):
    ai = ChessAI(
        SearchConfig(time_limit_seconds=5, max_depth=1),
        max_workers=1,
        ponder_cpu_percent=0,
    )
    observed_cache_sizes = []

    def evaluate_root_action(
        state, action, depth, config, deadline, snapshot,
        cache_size_callback=None, node_progress_callback=None, root_alpha=None,
    ):
        cache_size_callback(7)
        node_progress_callback(128)
        worker = ai.worker_stats()[0]
        observed_cache_sizes.append((
            worker.state,
            worker.mode,
            worker.root,
            worker.cache_entries,
            worker.visited_nodes,
            action.source,
            ai.search_progress_stats(),
            worker.search_depth,
        ))
        return _RootEvaluation(0.0, 128)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)

    ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))

    assert observed_cache_sizes
    assert all(
        value[:5] == (
            "busy", "search", POS(value[5]).name, 7, 128)
        for value in observed_cache_sizes
    )
    assert observed_cache_sizes[0][6][:4] == ("searching", 1, 0, 128)
    assert all(value[7] == 1 for value in observed_cache_sizes)
    assert all(
        phase == "searching"
        and current_depth == 1
        and completed_depth == 0
        and visited_nodes >= 128
        for phase, current_depth, completed_depth, visited_nodes
        in (value[6][:4] for value in observed_cache_sizes)
    )
    assert ai.worker_stats()[0].cache_entries == 0
    assert ai.worker_stats()[0].visited_nodes == 0
    phase, current_depth, completed_depth, visited_nodes = (
        ai.search_progress_stats()[:4])
    assert phase == "idle"
    assert current_depth == 0
    assert completed_depth == 1
    assert visited_nodes == len(observed_cache_sizes) * 128


def test_process_worker_status_changes_while_evaluating(monkeypatch):
    import logic.chess_ai as chess_ai

    ai = ChessAI(max_workers=2)
    status_values = [chess_ai._WORKER_IDLE, chess_ai._WORKER_IDLE]
    status_pids = [123, 456]
    cache_entry_values = [0, 0]
    node_values = [0, 0]
    status_lock = Lock()
    ai._worker_status_values = status_values
    ai._worker_status_pids = status_pids
    ai._worker_cache_entry_values = cache_entry_values
    ai._worker_node_values = node_values
    ai._worker_status_process_lock = status_lock
    ai._worker_pool_state = "ready"
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_VALUES", status_values)
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_PIDS", status_pids)
    monkeypatch.setattr(
        chess_ai, "_WORKER_CACHE_ENTRY_VALUES", cache_entry_values)
    monkeypatch.setattr(chess_ai, "_WORKER_NODE_VALUES", node_values)
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_LOCK", status_lock)
    monkeypatch.setattr(chess_ai, "_WORKER_STATUS_INDEX", 0)
    entered_search = Event()
    release_search = Event()

    def wait_during_search(
        _worker, _state, _depth, _alpha, _beta, allow_lmr=True,
    ):
        _worker._nodes = 17
        _worker._node_progress_callback(17)
        entered_search.set()
        assert release_search.wait(timeout=2)
        return 0.0, True

    monkeypatch.setattr(ChessAI, "_search_with_proof", wait_during_search)
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    action = GameSimulation.available_actions(state)[0]
    config = SearchConfig(cache_enabled=True, cache_max_entries=8, max_depth=1)
    seed_entry = CacheEntry(("worker-seed",), 1, None, 0.0, Bound.EXACT)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _evaluate_root_action,
                state,
                action,
                1,
                config,
                time.monotonic() + 5,
                (seed_entry,),
            )
            assert entered_search.wait(timeout=1)
            assert [worker.state for worker in ai.worker_stats()] == [
                "busy", "idle"]
            assert [
                worker.cache_entries for worker in ai.worker_stats()
            ] == [1, 0]
            assert [
                worker.visited_nodes for worker in ai.worker_stats()
            ] == [17, 0]
            release_search.set()
            result = future.result(timeout=2)
            assert result.score == 0.0
            assert result.nodes == 17
        assert [worker.state for worker in ai.worker_stats()] == [
            "idle", "idle"]
        assert [worker.cache_entries for worker in ai.worker_stats()] == [0, 0]
        assert [worker.visited_nodes for worker in ai.worker_stats()] == [0, 0]
    finally:
        release_search.set()


def test_prepared_worker_pool_survives_search_timeout():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=1e-12, max_depth=2),
        max_workers=2,
    )

    try:
        ai.prepare_workers()
        worker_pool = ai._worker_pool
        decision = ai.choose_action(observation)

        assert decision.action in GameSimulation.available_actions(state)
        assert ai._worker_pool is worker_pool
    finally:
        ai.shutdown_worker_pool()


def test_worker_pool_preparation_honors_cancellation_before_start():
    cancellation_event = Event()
    cancellation_event.set()
    ai = ChessAI(max_workers=2)

    with pytest.raises(WorkerPoolInitializationCancelled):
        ai.prepare_workers(cancellation_event=cancellation_event)

    assert ai._worker_pool is None


def test_worker_pool_preparation_cleans_up_when_cancelled_mid_start():
    cancellation_event = Event()
    ai = ChessAI(max_workers=2)

    def cancel_after_first_worker(ready_workers, worker_count):
        if ready_workers == 1:
            cancellation_event.set()

    with pytest.raises(WorkerPoolInitializationCancelled):
        ai.prepare_workers(
            cancel_after_first_worker,
            cancellation_event,
            minimum_progress_interval_seconds=30,
        )

    assert ai._worker_pool is None


def test_expired_search_budget_does_not_wait_for_worker_startup():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=1e-12, max_depth=2),
        max_workers=2,
    )

    decision = ai.choose_action(observation)

    assert decision.action in GameSimulation.available_actions(state)
    assert ai._worker_pool is None


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
        metrics_enabled=True,
    )
    serial_progress = []
    parallel_progress = []
    parallel_candidate_updates = []
    parallel_events = []

    serial_result = ChessAI(config, max_workers=1).choose_action(
        observation,
        progress_callback=lambda action, depth: serial_progress.append(
            (action, depth)),
    )
    parallel_result = ChessAI(config, max_workers=2).choose_action(
        observation,
        progress_callback=lambda action, depth: (
            parallel_progress.append((action, depth)),
            parallel_events.append(("complete", depth)),
        ),
        candidate_callback=lambda action, depth, score: (
            parallel_candidate_updates.append((action, depth, score)),
            parallel_events.append(("candidate", depth)),
        ),
    )

    assert parallel_result.action == serial_result.action
    assert parallel_result.score == pytest.approx(serial_result.score)
    assert parallel_result.completed_depth == serial_result.completed_depth == 2
    assert serial_result.metrics is not None
    assert parallel_result.metrics is not None
    assert parallel_result.metrics.worker_count == 2
    assert parallel_result.metrics.worker_tasks > 0
    assert parallel_result.metrics.worker_task_ns > 0
    assert [depth for _, depth in parallel_progress] == [0, 1, 2]
    assert [depth for _, depth in serial_progress] == [0, 1, 2]
    assert parallel_result.visited_nodes > 0
    assert serial_result.visited_nodes > 0
    assert any(depth == 2 for _, depth, _ in parallel_candidate_updates)
    assert all(isinstance(score, float) for _, _, score in parallel_candidate_updates)
    assert parallel_events.index(("candidate", 2)) < parallel_events.index(
        ("complete", 2))


def test_candidate_callback_reports_manager_leader_not_last_completed_worker():
    actions = [
        GameAction(GameActionType.MOVE, source=1, destination=2),
        GameAction(GameActionType.MOVE, source=1, destination=3),
        GameAction(GameActionType.MOVE, source=1, destination=4),
    ]
    updates = []

    ChessAI._report_completed_candidate(
        actions,
        {2: 1.0, 0: 3.0, 1: 5.0},
        2,
        lambda action, depth, score: updates.append((action, depth, score)),
    )

    assert updates == [(actions[1], 2, 5.0)]


def test_lmr_only_reduces_late_quiet_moves_without_cards_or_active_effects():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    quiet_move = GameAction(GameActionType.MOVE, source=57, destination=49)

    assert ChessAI._should_reduce_late_move(state, quiet_move, 3, 3)
    assert not ChessAI._should_reduce_late_move(state, quiet_move, 2, 3)
    assert not ChessAI._should_reduce_late_move(state, quiet_move, 3, 2)

    card_move = GameAction(
        GameActionType.MOVE, source=57, destination=49, card_index=0)
    assert not ChessAI._should_reduce_late_move(state, card_move, 3, 3)

    state.pieces_locations[49] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    assert not ChessAI._should_reduce_late_move(state, quiet_move, 3, 3)
    state.pieces_locations[49] = Piece()

    state.board_card_available = True
    state.board_card_position = 49
    state.board_enchantment = EnchantmentCardType.PIECE_TELEPORT.create()
    assert not ChessAI._should_reduce_late_move(state, quiet_move, 3, 3)

    state.board_card_available = False
    state.board_enchantment = None
    state.pieces_locations[57].set_enchantment(
        EnchantmentCardType.ROOK_JUMP_ALLIES.create())
    assert not ChessAI._should_reduce_late_move(state, quiet_move, 3, 3)


def test_lmr_does_not_reduce_a_move_that_attacks_the_opposing_king():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[64] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    action = GameAction(GameActionType.MOVE, source=57, destination=49)
    child = GameSimulation._apply_generated_action(state, action)

    assert ChessAI._should_reduce_late_move(state, action, 3, 3)
    assert ChessAI._move_attacks_king(child, action, opposing_king_position=1)


def test_lmr_does_not_prevent_an_immediate_king_capture(monkeypatch):
    state = make_black_to_move_state()
    state.pieces_locations[1] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[2] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", True)

    decision = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=4),
        max_workers=1,
    ).choose_action(observation)

    assert decision.action is not None
    assert decision.action.destination == 2
    assert decision.action in GameSimulation.available_actions(state)


def test_lmr_preserves_sparse_search_choice_and_score(monkeypatch):
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    state.pieces_locations[64] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[8] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    config = SearchConfig(time_limit_seconds=10, max_depth=4)

    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", False)
    baseline = ChessAI(config, max_workers=1).choose_action(observation)
    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", True)
    reduced = ChessAI(config, max_workers=1).choose_action(observation)

    assert baseline.completed_depth == reduced.completed_depth == 4
    assert baseline.action == reduced.action
    assert baseline.score == pytest.approx(reduced.score)


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


@pytest.mark.parametrize("depth", [1, 4])
def test_ai_avoids_exposing_king_to_opponents_movement_card(depth):
    state = make_black_to_move_state()
    state.pieces_locations[POS.B1.value] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[POS.E1.value] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[POS.C3.value] = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)
    state.pieces_locations[POS.A8.value] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    state.white_cards = [
        EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION.create(uses=2),
    ]
    dangerous_move = next(
        action for action in GameSimulation.available_actions(state)
        if action.source == POS.B1.value
        and action.destination == POS.C2.value
        and action.card_index == -1
    )
    exposed = GameSimulation.apply(state, dangerous_move)
    capture = next(
        action for action in GameSimulation.available_actions(exposed)
        if action.source == POS.C3.value
        and action.destination == POS.C2.value
        and action.card_index == 0
    )
    assert GameSimulation.apply(exposed, capture).get_winner() == COLOR.WHITE

    ai = ChessAI(
        SearchConfig(time_limit_seconds=5, max_depth=depth),
        max_workers=1,
    )
    try:
        decision = ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))
    finally:
        ai.shutdown_worker_pool()

    assert decision.completed_depth == depth
    assert decision.action.source == POS.B1.value
    assert decision.action.destination == POS.C1.value


def test_ai_can_capture_king_using_existing_movement_effect():
    state = make_black_to_move_state()
    pawn = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    pawn.set_enchantment(EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD.create())
    state.pieces_locations[POS.D4.value] = pawn
    state.pieces_locations[POS.E5.value] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    state.pieces_locations[POS.H8.value] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    ai = ChessAI(SearchConfig(time_limit_seconds=2, max_depth=1), max_workers=1)
    try:
        decision = ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))
    finally:
        ai.shutdown_worker_pool()

    assert decision.action.source == POS.D4.value
    assert decision.action.destination == POS.E5.value
    assert GameSimulation.apply(state, decision.action).get_winner() == COLOR.BLACK


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
        SearchConfig(time_limit_seconds=2, max_depth=1),
        max_workers=1,
    )

    decision = ai.choose_action(observation)

    assert decision.action is not None
    assert decision.action.destination == state.board_card_position


def test_evaluation_values_rune_traps_and_the_new_card_types():
    state = make_black_to_move_state()
    state.pieces_locations[POS.E8.value] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[POS.E1.value] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    state.pieces_locations[POS.D4.value] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    without_trap = ChessAI.evaluate(state)

    state.rune_traps.append(RuneTrap(
        POS.D5.value,
        COLOR.BLACK,
        EnchantmentCardType.KNIGHT_RUNIC_TRAP.create(),
        placed_on_turn=1,
    ))
    with_trap = ChessAI.evaluate(state)
    state.rune_traps.clear()

    state.black_cards = [EnchantmentCardType.ROOK_TREBUCHET.create()]
    with_card = ChessAI.evaluate(state)

    assert with_trap > without_trap
    assert with_card > without_trap


def test_search_metrics_are_opt_in_and_do_not_change_the_selected_action(
    monkeypatch,
):
    state = make_black_to_move_state()
    state.pieces_locations[POS.A1.value] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    state.pieces_locations[POS.H8.value] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    config = SearchConfig(
        time_limit_seconds=1,
        max_depth=2,
        cache_enabled=False,
        metrics_enabled=False,
    )
    plain_ai = ChessAI(config, max_workers=1)
    monkeypatch.setattr(
        plain_ai,
        "_measure_search_call",
        lambda *args: pytest.fail("disabled metrics must skip timing wrappers"),
    )
    plain = plain_ai.choose_action(observation)
    measured = ChessAI(
        replace(config, metrics_enabled=True), max_workers=1
    ).choose_action(observation)

    assert plain.metrics is None
    assert measured.action == plain.action
    assert measured.score == plain.score
    assert measured.completed_depth == plain.completed_depth
    assert measured.metrics is not None
    assert measured.metrics.wall_time_ns > 0
    assert measured.metrics.root_actions == len(
        GameSimulation.available_actions(state)
    )
    assert measured.metrics.visited_nodes == measured.visited_nodes
    assert measured.metrics.action_generation_calls > 0
    assert measured.metrics.generated_actions >= measured.metrics.root_actions
    assert measured.metrics.action_application_calls > 0
    assert measured.metrics.evaluation_calls > 0
    assert measured.metrics.worker_tasks > 0
    assert measured.metrics.worker_task_ns > 0
