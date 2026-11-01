import os
import random
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import (
    ChessAI,
    SearchConfig,
    WorkerPoolInitializationCancelled,
    _RootEvaluation,
    _evaluate_root_action,
)
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from logic.search_cache import Bound, CacheEntry
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
        cache_size_callback=None, node_progress_callback=None,
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
        cache_size_callback=None, node_progress_callback=None,
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

    def counted_destinations_for(piece, source, locations, enchantment=None):
        calls.append((source, enchantment))
        return original_destinations_for(
            piece, source, locations, enchantment)

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


def test_ponder_worker_count_uses_ceiling_and_respects_task_count():
    ai = ChessAI(max_workers=9, ponder_cpu_percent=50)

    assert ai._ponder_worker_count_for_tasks(100) == 5
    assert ai._ponder_worker_count_for_tasks(3) == 3
    assert ChessAI(
        max_workers=9, ponder_cpu_percent=0
    )._ponder_worker_count_for_tasks(100) == 0


def test_ponder_stops_when_cache_reaches_its_limit(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args):
            future = Future()
            try:
                future.set_result(function(*args))
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

    def apply_generated_action(search_state, action):
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
        cache_size_callback=None, node_progress_callback=None,
    ):
        entry = CacheEntry(
            ("pondered", search_state.cache_key()),
            depth,
            action,
            float(depth),
            Bound.EXACT,
        )
        return _RootEvaluation(float(depth), 1, (entry,))

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

    assert result.completed_depth == 2
    assert result.root_branches == 1
    assert result.stopped_reason == "cache-full"
    assert len(ai._cache) == 2
    assert all(entry.root_scope_ids for entry in ai._cache.snapshot(2))
    assert not ai._worker_search_cancel_event.is_set()
    assert not ai._ponder_active


def test_ponder_extends_retained_cache_as_each_root_action_finishes(monkeypatch):
    class ImmediateExecutor:
        def submit(self, function, *args):
            future = Future()
            try:
                future.set_result(function(*args))
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
    ai._states_after_player_turn = lambda _state, _event: (
        first_root, second_root)

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
        cache_size_callback=None, node_progress_callback=None,
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


def test_ponder_reports_live_nodes_and_completed_depth(monkeypatch):
    import logic.chess_ai as chess_ai

    class ImmediateExecutor:
        def submit(self, function, *args):
            future = Future()
            try:
                future.set_result(function(*args))
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
    cache_entry_values = [0]
    node_values = [0]
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

    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    action = GameAction(GameActionType.MOVE, 1, 2)
    observed_progress = []
    monkeypatch.setattr(
        ai, "_states_after_player_turn", lambda _state, _event: (state,))
    monkeypatch.setattr(
        ai, "_order_actions", lambda _state, actions: actions)
    monkeypatch.setattr(
        GameSimulation, "available_actions", lambda _state: [action])

    def evaluate_root_action(
        _state, _action, _depth, _config, _deadline, _cache_snapshot,
        cache_size_callback=None, node_progress_callback=None,
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
    assert observed_progress == [("pondering", 1, 0, 128)]
    assert ai.search_progress_stats() == ("idle", 0, 1, 128)


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
        assert len({worker.pid for worker in prepared_workers}) == 2
        assert [worker.cache_entries for worker in prepared_workers] == [0, 0]
        assert [worker.visited_nodes for worker in prepared_workers] == [0, 0]
        ai.choose_action(observation)
        assert ai._worker_pool is worker_pool
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
    assert [worker.state for worker in ai.worker_stats()] == ["busy"]
    ai._set_local_worker_busy(False)

    disabled_cache = ChessAI(
        SearchConfig(cache_enabled=False, cache_max_entries=2),
        max_workers=1,
    )
    assert disabled_cache.cache_stats() == (False, 0, 2, 0)


def test_local_worker_cache_size_is_visible_during_search(monkeypatch):
    ai = ChessAI(
        SearchConfig(time_limit_seconds=5, max_depth=1),
        max_workers=1,
        ponder_cpu_percent=0,
    )
    observed_cache_sizes = []

    def evaluate_root_action(
        state, action, depth, config, deadline, snapshot,
        cache_size_callback=None, node_progress_callback=None,
    ):
        cache_size_callback(7)
        node_progress_callback(128)
        worker = ai.worker_stats()[0]
        observed_cache_sizes.append((
            worker.state,
            worker.cache_entries,
            worker.visited_nodes,
            ai.search_progress_stats(),
        ))
        return _RootEvaluation(0.0, 128)

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)

    ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))

    assert observed_cache_sizes
    assert all(
        value[:3] == ("busy", 7, 128)
        for value in observed_cache_sizes
    )
    assert observed_cache_sizes[0][3] == ("searching", 1, 0, 128)
    assert all(
        phase == "searching"
        and current_depth == 1
        and completed_depth == 0
        and visited_nodes >= 128
        for phase, current_depth, completed_depth, visited_nodes
        in (value[3] for value in observed_cache_sizes)
    )
    assert ai.worker_stats()[0].cache_entries == 0
    assert ai.worker_stats()[0].visited_nodes == 0
    phase, current_depth, completed_depth, visited_nodes = (
        ai.search_progress_stats())
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

    def wait_during_search(_worker, _state, _depth, _alpha, _beta):
        _worker._nodes = 17
        _worker._node_progress_callback(17)
        entered_search.set()
        assert release_search.wait(timeout=2)
        return 0.0

    monkeypatch.setattr(ChessAI, "_search", wait_during_search)
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
    assert [depth for _, depth in parallel_progress] == [0, 1, 2]
    assert [depth for _, depth in serial_progress] == [0, 1, 2]
    assert parallel_result.visited_nodes == serial_result.visited_nodes
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
