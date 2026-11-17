import heapq
import math
import multiprocessing
import os
import sqlite3
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, fields, replace
from threading import Event, Lock
from typing import Any, Callable, Optional

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import POS, id_to_xy, xy_to_id
from logic.game_rules import GameAction, GameActionType, GameRules
from logic.game_simulation import GameSimulation
from logic.move_learning import (
    MoveLearningAccumulator,
    SearchResultAccumulator,
    MoveLearningStore,
    learning_position_key,
    default_move_learning_path,
    has_collectible_board_card,
    is_learning_position_eligible,
    is_plain_move,
    search_result_position_key,
)
from logic.opening_book import opening_hints
from logic.search_cache import Bound, CacheEntry, SearchCache
from models.ai_search_metrics import AISearchMetrics
from models.ai_search_stats import AIWorkerStats
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState
from processors.bitboard_move_generator import BoardBitboards
from utils.logging import (
    is_enabled,
    log_debug,
    log_error,
    log_info,
    log_logic,
    log_warn,
)
from utils.run_config import (
    AI_SEARCH_CACHE_ENABLED,
    AI_SEARCH_CACHE_MAX_ENTRIES,
    AI_SEARCH_LEARNING_ENABLED,
    AI_SEARCH_LEARNING_DATABASE_PATH,
    AI_SEARCH_LEARNING_MAX_FILE_SIZE,
    AI_SEARCH_LEARNING_SAVE_ENABLED,
    AI_SEARCH_LEARNING_SOFT_CUTOFF_THRESHOLD,
    AI_SEARCH_CPU_WORKERS,
    AI_SEARCH_CPU_WORKER_USAGE,
    AI_SEARCH_MAX_DEPTH,
    AI_SEARCH_METRICS_ENABLED,
    AI_SEARCH_PONDER_ENABLED,
    AI_SEARCH_PONDER_CPU_WORKERS,
    AI_SEARCH_PONDER_CPU_WORKER_USAGE,
    AI_SEARCH_TIME_LIMIT_SECONDS,
)


PIECE_VALUES = {
    PIECE_TYPE.PAWN: 1.0,
    PIECE_TYPE.KNIGHT: 3.0,
    PIECE_TYPE.BISHOP: 3.25,
    PIECE_TYPE.ROOK: 5.0,
    PIECE_TYPE.QUEEN: 9.0,
    PIECE_TYPE.KING: 0.0,
    PIECE_TYPE.EMPTY: 0.0,
}

CARD_VALUES = {
    EnchantmentCardType.KNIGHT_RUNIC_TRAP: 1.0,
    EnchantmentCardType.PAWN_OFFICER: 1.25,
    EnchantmentCardType.ROOK_TREBUCHET: 0.75,
    EnchantmentCardType.RECRUIT_PAWN: 0.75,
    EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD: 1.0,
    EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD: 1.0,
    EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION: 1.25,
    EnchantmentCardType.ROOK_JUMP_ALLIES: 1.0,
    EnchantmentCardType.QUEEN_JUMP_ALLIES: 1.75,
    EnchantmentCardType.PAWN_DETONATION: 1.0,
    EnchantmentCardType.PAWN_DETONATION_DELAYED_1: 1.0,
    EnchantmentCardType.PAWN_DETONATION_DELAYED_2: 1.0,
    EnchantmentCardType.PAWN_SWORDSMAN: 1.0,
    EnchantmentCardType.KING_PAWN_RESURRECTION: 1.5,
    EnchantmentCardType.KING_KNIGHT_RESURRECTION: 1.75,
    EnchantmentCardType.KING_BISHOP_RESURRECTION: 1.75,
    EnchantmentCardType.KING_ROOK_RESURRECTION: 2.5,
    EnchantmentCardType.KING_QUEEN_RESURRECTION: 3.5,
    EnchantmentCardType.ROOK_TOWER_THROW: 2.0,
    EnchantmentCardType.PIECE_TELEPORT: 1.5,
    EnchantmentCardType.PIECE_DOUBLE_MOVE: 2.0,
}
CARD_MOVEMENT_TYPES = GameSimulation.MOVEMENT_CARDS
_LMR_ENABLED = True
_WORKER_CACHE_LIMIT = 256
_WORKER_STARTUP_TIMEOUT_SECONDS = 60.0
_WORKER_PROBE_RELEASE_EVENT: Any = None
_WORKER_PROBE_STARTED_COUNT: Any = None
_WORKER_SEARCH_CANCEL_EVENT: Any = None
_WORKER_USAGE_LIMITER: Any = None
_WORKER_STATUS_VALUES: Any = None
_WORKER_STATUS_PIDS: Any = None
_WORKER_MODE_VALUES: Any = None
_WORKER_ROOT_VALUES: Any = None
_WORKER_DEPTH_VALUES: Any = None
_WORKER_CACHE_ENTRY_VALUES: Any = None
_WORKER_NODE_VALUES: Any = None
_WORKER_LEARNING_READ_VALUES: Any = None
_WORKER_MOVE_LEARNING_STORE: Any = None
_WORKER_STATUS_LOCK: Any = None
_WORKER_STATUS_INDEX: Optional[int] = None
_WORKER_NODE_UPDATE_INTERVAL = 128
_WORKER_STARTING = 0
_WORKER_INITIALIZING = 1
_WORKER_IDLE = 2
_WORKER_BUSY = 3
_WORKER_MODE_NONE = 0
_WORKER_MODE_SEARCH = 1
_WORKER_MODE_PREPARE = 2
_WORKER_STATUS_NAMES = {
    _WORKER_STARTING: "starting",
    _WORKER_INITIALIZING: "initializing",
    _WORKER_IDLE: "idle",
    _WORKER_BUSY: "busy",
}
_WORKER_MODE_NAMES = {
    _WORKER_MODE_NONE: "-",
    _WORKER_MODE_SEARCH: "search",
    _WORKER_MODE_PREPARE: "prepare",
}


def _root_square_notation(root_position):
    if not isinstance(root_position, int) or not 1 <= root_position <= 64:
        return "-"
    return POS(root_position).name


@dataclass(frozen=True)
class SearchConfig:
    """Limity obliczeń dla jednego wyboru ruchu."""

    time_limit_seconds: float = AI_SEARCH_TIME_LIMIT_SECONDS
    max_depth: int = AI_SEARCH_MAX_DEPTH
    cache_enabled: bool = AI_SEARCH_CACHE_ENABLED
    cache_max_entries: int = AI_SEARCH_CACHE_MAX_ENTRIES
    learning_enabled: bool = AI_SEARCH_LEARNING_ENABLED
    learning_save_enabled: bool = AI_SEARCH_LEARNING_SAVE_ENABLED
    learning_max_file_size_bytes: int = AI_SEARCH_LEARNING_MAX_FILE_SIZE
    learning_soft_cutoff_threshold: float = (
        AI_SEARCH_LEARNING_SOFT_CUTOFF_THRESHOLD)
    metrics_enabled: bool = AI_SEARCH_METRICS_ENABLED
    cpu_worker_usage: int = AI_SEARCH_CPU_WORKER_USAGE
    learning_path_eligible: bool = True

    def __post_init__(self):
        if self.time_limit_seconds <= 0:
            raise ValueError("The search time limit must be positive")
        if self.max_depth < 1:
            raise ValueError("The search depth must be at least one")
        if not isinstance(self.cache_enabled, bool):
            raise ValueError("The search cache setting must be a boolean")
        if not isinstance(self.metrics_enabled, bool):
            raise ValueError("The search metrics setting must be a boolean")
        if not isinstance(self.learning_enabled, bool):
            raise ValueError("The move-learning setting must be a boolean")
        if not isinstance(self.learning_save_enabled, bool):
            raise ValueError("The move-learning save setting must be a boolean")
        if not isinstance(self.learning_path_eligible, bool):
            raise ValueError("The move-learning path setting must be a boolean")
        if (
            not isinstance(self.learning_max_file_size_bytes, int)
            or isinstance(self.learning_max_file_size_bytes, bool)
            or self.learning_max_file_size_bytes < 16 * 1024
        ):
            raise ValueError(
                "The move-learning database limit must be at least 16 KiB")
        if (
            not isinstance(self.learning_soft_cutoff_threshold, (int, float))
            or isinstance(self.learning_soft_cutoff_threshold, bool)
            or not math.isfinite(self.learning_soft_cutoff_threshold)
        ):
            raise ValueError(
                "The move-learning soft-cutoff threshold must be finite")
        if (
            not isinstance(self.cpu_worker_usage, int)
            or isinstance(self.cpu_worker_usage, bool)
            or not 1 <= self.cpu_worker_usage <= 100
        ):
            raise ValueError("The CPU worker usage must be between 1 and 100")
        if (not isinstance(self.cache_max_entries, int)
                or isinstance(self.cache_max_entries, bool)
                or self.cache_max_entries < 1):
            raise ValueError("The search cache limit must be a positive integer")


@dataclass(frozen=True)
class SearchResult:
    action: Optional[GameAction]
    score: float
    completed_depth: int
    visited_nodes: int
    metrics: Optional[AISearchMetrics] = None
    learning_hint_used: bool = False


@dataclass(frozen=True)
class PonderResult:
    max_branch_depth: int
    root_branches: int
    visited_nodes: int
    stopped_reason: str

    @property
    def completed_depth(self):
        return self.max_branch_depth


class _SearchTimeout(Exception):
    pass


class _WorkerUsageLimiter:
    _CYCLE_SECONDS = 0.1

    def __init__(self, usage):
        self._usage = usage
        self._cycle_started = time.monotonic()

    def set_usage(self, usage):
        if self._usage != usage:
            self._usage = usage
            self._cycle_started = time.monotonic()

    def wait(self, deadline, cancellation_event):
        if self._usage >= 100:
            return
        active_seconds = self._CYCLE_SECONDS * self._usage / 100
        while True:
            if cancellation_event is not None and cancellation_event.is_set():
                raise _SearchTimeout
            now = time.monotonic()
            if now >= deadline:
                raise _SearchTimeout
            cycle_position = (now - self._cycle_started) % self._CYCLE_SECONDS
            if cycle_position < active_seconds:
                return
            delay = min(
                self._CYCLE_SECONDS - cycle_position,
                deadline - now,
            )
            if cancellation_event is None:
                time.sleep(delay)
            else:
                cancellation_event.wait(delay)


_LOCAL_WORKER_USAGE_LIMITER = _WorkerUsageLimiter(100)


class WorkerPoolInitializationCancelled(Exception):
    """Sygnalizuje anulowanie przygotowania puli workerów."""


@dataclass(frozen=True)
class _RootEvaluation:
    score: Optional[float]
    nodes: int
    entries: tuple = ()
    hits: int = 0
    score_hits: int = 0
    hints: int = 0
    bound: Optional[Bound] = Bound.EXACT
    reliable: bool = True
    metrics: Optional[AISearchMetrics] = None
    learning_updates: tuple = ()
    search_result_updates: tuple = ()


class _SearchMetricsCollector:
    def __init__(self):
        self._values = {field.name: 0 for field in fields(AISearchMetrics)}

    def add(self, name, value):
        self._values[name] += value

    def merge(self, metrics):
        if metrics is None:
            return
        for name in self._values:
            self._values[name] += getattr(metrics, name)

    def snapshot(self):
        return AISearchMetrics(**self._values)


def _log_search_metrics(metrics):
    milliseconds = lambda value: value / 1_000_000
    log_info(
        "AI search profile: nodes={}, wall={:.2f}ms, observation={:.2f}ms, "
        "generated_actions={} in {} calls ({:.2f}ms), "
        "ordered_actions={} in {} calls ({:.2f}ms), "
        "apply_calls={} ({:.2f}ms), evaluate_calls={} ({:.2f}ms), "
        "cache probes/hits/score-hits={}/{}/{}, cache key/lookup/store="
        "{:.2f}/{:.2f}/{:.2f}ms, cutoffs={}, LMR probes/researches={}/{}, "
        "workers={}, tasks={}, task-sum={:.2f}ms, startup={:.2f}ms, "
        "wait={:.2f}ms".format(
            metrics.visited_nodes,
            milliseconds(metrics.wall_time_ns),
            milliseconds(metrics.observation_ns),
            metrics.generated_actions,
            metrics.action_generation_calls,
            milliseconds(metrics.action_generation_ns),
            metrics.actions_ordered,
            metrics.action_ordering_calls,
            milliseconds(metrics.action_ordering_ns),
            metrics.action_application_calls,
            milliseconds(metrics.action_application_ns),
            metrics.evaluation_calls,
            milliseconds(metrics.evaluation_ns),
            metrics.cache_probes,
            metrics.cache_hits,
            metrics.cache_score_hits,
            milliseconds(metrics.cache_key_ns),
            milliseconds(metrics.cache_lookup_ns),
            milliseconds(metrics.cache_store_ns),
            metrics.alpha_beta_cutoffs,
            metrics.lmr_probes,
            metrics.lmr_researches,
            metrics.worker_count,
            metrics.worker_tasks,
            milliseconds(metrics.worker_task_ns),
            milliseconds(metrics.worker_pool_startup_ns),
            milliseconds(metrics.worker_wait_ns),
        )
    )


def _set_current_worker_status(
    status, mode=_WORKER_MODE_NONE, root_position=0, search_depth=None
):
    if (
        _WORKER_STATUS_VALUES is None
        or _WORKER_STATUS_LOCK is None
        or _WORKER_STATUS_INDEX is None
    ):
        return
    with _WORKER_STATUS_LOCK:
        _WORKER_STATUS_VALUES[_WORKER_STATUS_INDEX] = status
        if _WORKER_MODE_VALUES is not None:
            _WORKER_MODE_VALUES[_WORKER_STATUS_INDEX] = mode
        if _WORKER_ROOT_VALUES is not None:
            _WORKER_ROOT_VALUES[_WORKER_STATUS_INDEX] = (
                root_position
                if (
                    mode != _WORKER_MODE_NONE
                    and isinstance(root_position, int)
                    and 1 <= root_position <= 64
                )
                else 0
            )
        if _WORKER_DEPTH_VALUES is not None:
            _WORKER_DEPTH_VALUES[_WORKER_STATUS_INDEX] = (
                search_depth
                if mode == _WORKER_MODE_SEARCH
                and isinstance(search_depth, int)
                and search_depth > 0
                else 0
            )


def _set_current_worker_cache_entries(entry_count):
    if (
        _WORKER_CACHE_ENTRY_VALUES is None
        or _WORKER_STATUS_LOCK is None
        or _WORKER_STATUS_INDEX is None
    ):
        return
    with _WORKER_STATUS_LOCK:
        _WORKER_CACHE_ENTRY_VALUES[_WORKER_STATUS_INDEX] = entry_count


def _set_current_worker_visited_nodes(visited_nodes):
    if (
        _WORKER_NODE_VALUES is None
        or _WORKER_STATUS_LOCK is None
        or _WORKER_STATUS_INDEX is None
    ):
        return
    with _WORKER_STATUS_LOCK:
        _WORKER_NODE_VALUES[_WORKER_STATUS_INDEX] = visited_nodes


def _set_current_worker_learning_reading(is_reading):
    if (
        _WORKER_LEARNING_READ_VALUES is None
        or _WORKER_STATUS_LOCK is None
        or _WORKER_STATUS_INDEX is None
    ):
        return
    with _WORKER_STATUS_LOCK:
        _WORKER_LEARNING_READ_VALUES[_WORKER_STATUS_INDEX] = int(is_reading)


def _initialize_search_worker(
    ready_count, probe_started_count, probe_release_event, search_cancel_event,
    worker_status_values, worker_status_pids, worker_mode_values,
    worker_root_values, worker_depth_values, worker_cache_entry_values,
    worker_node_values, worker_learning_read_values,
    worker_status_lock, learning_enabled=False,
    learning_max_file_size_bytes=AI_SEARCH_LEARNING_MAX_FILE_SIZE,
    learning_database_path=None,
):
    global _WORKER_USAGE_LIMITER
    global _WORKER_PROBE_RELEASE_EVENT, _WORKER_PROBE_STARTED_COUNT
    global _WORKER_SEARCH_CANCEL_EVENT
    global _WORKER_STATUS_VALUES, _WORKER_STATUS_PIDS
    global _WORKER_MODE_VALUES, _WORKER_ROOT_VALUES, _WORKER_DEPTH_VALUES
    global _WORKER_CACHE_ENTRY_VALUES, _WORKER_NODE_VALUES
    global _WORKER_LEARNING_READ_VALUES
    global _WORKER_MOVE_LEARNING_STORE
    global _WORKER_STATUS_LOCK
    global _WORKER_STATUS_INDEX
    _WORKER_PROBE_RELEASE_EVENT = probe_release_event
    _WORKER_PROBE_STARTED_COUNT = probe_started_count
    _WORKER_SEARCH_CANCEL_EVENT = search_cancel_event
    _WORKER_USAGE_LIMITER = _WorkerUsageLimiter(100)
    _WORKER_STATUS_VALUES = worker_status_values
    _WORKER_STATUS_PIDS = worker_status_pids
    _WORKER_MODE_VALUES = worker_mode_values
    _WORKER_ROOT_VALUES = worker_root_values
    _WORKER_DEPTH_VALUES = worker_depth_values
    _WORKER_CACHE_ENTRY_VALUES = worker_cache_entry_values
    _WORKER_NODE_VALUES = worker_node_values
    _WORKER_LEARNING_READ_VALUES = worker_learning_read_values
    _WORKER_STATUS_LOCK = worker_status_lock
    _WORKER_MOVE_LEARNING_STORE = None
    if learning_enabled:
        try:
            _WORKER_MOVE_LEARNING_STORE = MoveLearningStore(
                learning_database_path or default_move_learning_path(
                    AI_SEARCH_LEARNING_DATABASE_PATH),
                learning_max_file_size_bytes,
                read_only=True,
            )
        except (OSError, sqlite3.Error, ValueError) as error:
            log_error(
                "Persistent move learning is unavailable in worker: {}".format(
                    error)
            )
    with _WORKER_STATUS_LOCK:
        _WORKER_STATUS_INDEX = next(
            (
                index for index, registered_pid
                in enumerate(_WORKER_STATUS_PIDS)
                if registered_pid == 0
            ),
            None,
        )
        if _WORKER_STATUS_INDEX is None:
            raise RuntimeError("No worker status slot is available")
        _WORKER_STATUS_PIDS[_WORKER_STATUS_INDEX] = os.getpid()
        _WORKER_MODE_VALUES[_WORKER_STATUS_INDEX] = _WORKER_MODE_NONE
        _WORKER_ROOT_VALUES[_WORKER_STATUS_INDEX] = 0
        _WORKER_DEPTH_VALUES[_WORKER_STATUS_INDEX] = 0
        _WORKER_CACHE_ENTRY_VALUES[_WORKER_STATUS_INDEX] = 0
        _WORKER_NODE_VALUES[_WORKER_STATUS_INDEX] = 0
        _WORKER_LEARNING_READ_VALUES[_WORKER_STATUS_INDEX] = 0
        _WORKER_STATUS_VALUES[_WORKER_STATUS_INDEX] = _WORKER_STARTING
    with ready_count.get_lock():
        ready_count.value += 1
    _set_current_worker_status(_WORKER_IDLE)


def _prewarm_search_worker():
    if (
        _WORKER_PROBE_RELEASE_EVENT is None
        or _WORKER_PROBE_STARTED_COUNT is None
    ):
        raise RuntimeError("AI worker was not initialized before its probe")
    _set_current_worker_status(_WORKER_INITIALIZING)
    try:
        with _WORKER_PROBE_STARTED_COUNT.get_lock():
            _WORKER_PROBE_STARTED_COUNT.value += 1
        _WORKER_PROBE_RELEASE_EVENT.wait()
        return os.getpid()
    finally:
        _set_current_worker_status(_WORKER_IDLE)


def _evaluate_root_action(
    state, action, depth, config, deadline, cache_snapshot=(),
    cache_size_callback=None, node_progress_callback=None,
    root_alpha=-math.inf, learning_store=None,
):
    """Ocenia jeden ruch startowy w izolowanym workerze."""
    task_started = (
        time.perf_counter_ns() if config.metrics_enabled else None
    )
    cache_size_callback = (
        cache_size_callback or _set_current_worker_cache_entries)
    node_progress_callback = (
        node_progress_callback or _set_current_worker_visited_nodes)
    _set_current_worker_cache_entries(0)
    node_progress_callback(0)
    _set_current_worker_status(
        _WORKER_BUSY, _WORKER_MODE_SEARCH, action.source, depth)
    worker_pid = os.getpid()
    task_status = "failed"
    worker = None
    if is_enabled("DEBUG"):
        log_debug(
            "AI worker PID {} started search task (depth {}): {}".format(
                worker_pid, depth, action)
        )
    root_bound = None
    reliable = False
    try:
        usage_limiter = (
            _WORKER_USAGE_LIMITER or _LOCAL_WORKER_USAGE_LIMITER
        )
        usage_limiter.set_usage(config.cpu_worker_usage)
        worker = ChessAI(
            config,
            max_workers=1,
            cpu_worker_usage=config.cpu_worker_usage,
            ponder_enabled=False,
            initialize_move_learning=False,
        )
        worker._learning_active = (
                config.learning_enabled
                and config.learning_path_eligible
                and is_learning_position_eligible(state)
                and is_plain_move(action)
        )
        worker._move_learning_store = (
            learning_store or _WORKER_MOVE_LEARNING_STORE)
        if worker._move_learning_store is not None:
            worker._move_learning_store.clear_hint_cache()
        worker._worker_usage_limiter = usage_limiter
        worker._deadline = deadline
        worker._nodes = 0
        worker._metrics = (
            _SearchMetricsCollector() if config.metrics_enabled else None
        )
        worker._node_progress_callback = node_progress_callback
        if worker._cache is not None:
            worker._cache = SearchCache(
                min(config.cache_max_entries, _WORKER_CACHE_LIMIT),
                on_size_change=cache_size_callback,
            )
            for entry in cache_snapshot:
                worker._cache.put(entry, updated=False)
        try:
            worker._check_deadline()
            child = worker._apply_generated_action_for_search(state, action)
            learning_path_eligible = (
                    worker._learning_active and is_learning_position_eligible(child)
            )
            worker._initial_learning_path_eligible = learning_path_eligible
            score, reliable = worker._search_with_proof(
                child, depth - 1, root_alpha, math.inf)
            if not reliable:
                score, reliable = worker._search_with_proof(
                    child, depth - 1, -math.inf, math.inf, allow_lmr=False)
            elif math.isfinite(root_alpha) and score == root_alpha:
                score, reliable = worker._search_with_proof(
                    child, depth - 1, -math.inf, math.inf)
                if not reliable:
                    score, reliable = worker._search_with_proof(
                        child, depth - 1, -math.inf, math.inf, allow_lmr=False)
            root_bound = (
                Bound.UPPER
                if reliable and score < root_alpha
                else Bound.EXACT if reliable else None
            )
        except _SearchTimeout:
            score = None
            reliable = False
            task_status = "timeout"
        entries = (
            worker._cache.snapshot(_WORKER_CACHE_LIMIT, touched_only=True)
            if worker._cache is not None else ()
        )
        if task_status != "timeout":
            task_status = "completed" if reliable else "incomplete"
        metrics = None
        if worker._metrics is not None:
            worker._metrics.add("worker_tasks", 1)
            if task_started is not None:
                worker._metrics.add(
                    "worker_task_ns", time.perf_counter_ns() - task_started)
            metrics = worker._metrics.snapshot()
        return _RootEvaluation(
            score, worker._nodes, entries, worker._cache_hits,
            worker._cache_score_hits, worker._cache_hints,
            root_bound, reliable, metrics,
            (
                worker._move_learning_updates.snapshot()
                if config.learning_enabled and config.learning_save_enabled
                else ()
            ),
            (
                worker._search_result_updates.snapshot()
                if (
                    config.learning_enabled
                    and config.learning_save_enabled
                    and reliable
                )
                else ()
            ))
    finally:
        if is_enabled("DEBUG"):
            log_debug(
                "AI worker PID {} finished search task "
                "(depth {}, status={}, nodes={}): {}".format(
                    worker_pid,
                    depth,
                    task_status,
                    getattr(worker, "_nodes", 0) if worker is not None else 0,
                    action,
                )
            )
        cache_size_callback(0)
        node_progress_callback(0)
        _set_current_worker_status(_WORKER_IDLE)


def _expand_ponder_white_action_with_eligibility(state, action):
    """Expand one white action into every completed white-turn root below it."""
    worker_pid = os.getpid()
    roots = []
    task_status = "failed"
    usage_limiter = (
        _WORKER_USAGE_LIMITER or _LOCAL_WORKER_USAGE_LIMITER
    )
    _set_current_worker_status(
        _WORKER_BUSY, _WORKER_MODE_PREPARE, action.source)
    if is_enabled("DEBUG"):
        log_debug(
            "AI worker PID {} started ponder preparation task: {}".format(
                worker_pid, action)
        )
    try:
        learning_path_eligible = (
                is_learning_position_eligible(state) and is_plain_move(action)
        )
        first_child = GameSimulation._apply_generated_action(
            state, action, advance_board_card_clock=True)
        frontier = [(
            first_child,
            learning_path_eligible and is_learning_position_eligible(first_child),
        )]
        while frontier:
            if (
                _WORKER_SEARCH_CANCEL_EVENT is not None
                and _WORKER_SEARCH_CANCEL_EVENT.is_set()
            ):
                break
            try:
                usage_limiter.wait(math.inf, _WORKER_SEARCH_CANCEL_EVENT)
            except _SearchTimeout:
                break
            current_state, learning_path_eligible = frontier.pop()
            if current_state.get_winner() is not None:
                continue
            if current_state.current_turn != COLOR.WHITE:
                if current_state.current_turn == COLOR.BLACK:
                    roots.append((
                        current_state,
                        learning_path_eligible
                        and is_learning_position_eligible(current_state),
                    ))
                continue
            children = []
            for next_action in GameSimulation.available_actions(current_state):
                if (
                    _WORKER_SEARCH_CANCEL_EVENT is not None
                    and _WORKER_SEARCH_CANCEL_EVENT.is_set()
                ):
                    break
                try:
                    usage_limiter.wait(math.inf, _WORKER_SEARCH_CANCEL_EVENT)
                except _SearchTimeout:
                    break
                child = GameSimulation._apply_generated_action(
                    current_state,
                    next_action,
                    advance_board_card_clock=True,
                )
                children.append((
                    child,
                    learning_path_eligible
                    and is_plain_move(next_action)
                    and is_learning_position_eligible(child),
                ))
            frontier.extend(reversed(children))
        task_status = (
            "cancelled"
            if (
                _WORKER_SEARCH_CANCEL_EVENT is not None
                and _WORKER_SEARCH_CANCEL_EVENT.is_set()
            )
            else "completed"
        )
        return tuple(roots)
    finally:
        if is_enabled("DEBUG"):
            log_debug(
                "AI worker PID {} finished ponder preparation task "
                "(status={}, roots={}): {}".format(
                    worker_pid, task_status, len(roots), action)
            )
        _set_current_worker_status(_WORKER_IDLE)


class _PonderRootStates(list):
    def __init__(self, roots):
        super().__init__(root_state for root_state, _ in roots)
        self.learning_eligibility = tuple(
            eligible for _, eligible in roots)


def _expand_ponder_white_action(state, action):
    return _PonderRootStates(
        _expand_ponder_white_action_with_eligibility(state, action))


def _expand_ponder_white_action_with_usage(state, action, worker_usage):
    usage_limiter = (
        _WORKER_USAGE_LIMITER or _LOCAL_WORKER_USAGE_LIMITER
    )
    usage_limiter.set_usage(worker_usage)
    roots = _expand_ponder_white_action(state, action)
    eligibility = getattr(roots, "learning_eligibility", None)
    if eligibility is None:
        eligibility = tuple(
            is_learning_position_eligible(root_state) and is_plain_move(action)
            for root_state in roots
        )
    return tuple(zip(roots, eligibility))


class ChessAI:
    """Wybiera akcje z perspektywy czarnych, znając ręce obu graczy."""

    def __init__(
        self,
        config: SearchConfig = SearchConfig(),
        max_workers: Optional[int] = None,
        cpu_worker_usage: Optional[int] = None,
        ponder_enabled: bool = AI_SEARCH_PONDER_ENABLED,
        ponder_workers: Optional[int] = None,
        ponder_cpu_worker_usage: int = AI_SEARCH_PONDER_CPU_WORKER_USAGE,
        initialize_move_learning: bool = True,
    ):
        if cpu_worker_usage is None:
            cpu_worker_usage = config.cpu_worker_usage
        if (
            max_workers is not None
            and (
                not isinstance(max_workers, int)
                or isinstance(max_workers, bool)
                or max_workers < 1
            )
        ):
            raise ValueError("The worker count must be at least one")
        if (
            not isinstance(cpu_worker_usage, int)
            or isinstance(cpu_worker_usage, bool)
            or not 1 <= cpu_worker_usage <= 100
        ):
            raise ValueError("The CPU worker usage must be between 1 and 100")
        if not isinstance(ponder_enabled, bool):
            raise ValueError(
                "The ponder enabled setting must be a boolean")
        if (
            ponder_workers is not None
            and (
                not isinstance(ponder_workers, int)
                or isinstance(ponder_workers, bool)
                or ponder_workers < 1
            )
        ):
            raise ValueError("The ponder worker count must be at least one")
        if (
            not isinstance(ponder_cpu_worker_usage, int)
            or isinstance(ponder_cpu_worker_usage, bool)
            or not 1 <= ponder_cpu_worker_usage <= 100
        ):
            raise ValueError(
                "The ponder CPU worker usage must be between 1 and 100")
        self.search_worker_count = (
            max_workers if max_workers is not None else AI_SEARCH_CPU_WORKERS
        )
        self.ponder_enabled = ponder_enabled
        self.ponder_worker_count = (
            ponder_workers
            if ponder_workers is not None else AI_SEARCH_PONDER_CPU_WORKERS
        )
        self.cpu_worker_usage = cpu_worker_usage
        self.ponder_cpu_worker_usage = ponder_cpu_worker_usage
        self.max_workers = max(
            self.search_worker_count,
            self.ponder_worker_count if self.ponder_enabled else 1,
        )
        global _WORKER_MOVE_LEARNING_STORE
        self.config = replace(config, cpu_worker_usage=cpu_worker_usage)
        self._learning_database_path = default_move_learning_path(
            AI_SEARCH_LEARNING_DATABASE_PATH)
        self._learning_database_size_error_reported = False
        self._move_learning_store = None
        self._learning_active = False
        self._move_learning_updates = MoveLearningAccumulator()
        self._search_result_updates = SearchResultAccumulator()
        self._last_learning_hint_actions = frozenset()
        self._root_learning_hint_actions = frozenset()
        if initialize_move_learning and self.config.learning_enabled:
            try:
                self._move_learning_store = MoveLearningStore.open_from_config(
                    self.config.learning_enabled,
                    self.config.learning_save_enabled,
                    self.config.learning_max_file_size_bytes,
                    self._learning_database_path,
                )
                self._learning_active = True
            except (OSError, sqlite3.Error, ValueError) as error:
                log_error(
                    "Persistent move learning is unavailable: {}".format(error)
                )
            _WORKER_MOVE_LEARNING_STORE = self._move_learning_store
        elif initialize_move_learning:
            _WORKER_MOVE_LEARNING_STORE = None
        elif self.config.learning_enabled:
            self._learning_active = True
        self._worker_usage_limiter = _LOCAL_WORKER_USAGE_LIMITER
        self._worker_usage_limiter.set_usage(cpu_worker_usage)
        self._deadline = 0.0
        self._nodes = 0
        self._node_progress_callback = None
        self._search_progress_lock = Lock()
        self._search_phase = "idle"
        self._current_search_depth = 0
        self._completed_search_depth = 0
        self._reported_search_nodes = 0
        self._ponder_white_actions_completed = None
        self._ponder_white_actions_total = None
        self._ponder_branches_generated = None
        self._ponder_root_actions_completed = None
        self._ponder_root_actions_discovered = None
        self._ponder_depth_counts = ()
        self._ponder_max_branch_depth = None
        self._ponder_dangerous_white_candidates = ()
        self._cache = SearchCache(config.cache_max_entries) if config.cache_enabled else None
        self._ponder_completed_depths = {}
        self._cache_lock = Lock()
        self._cache_generation = 0
        self._cache_hits = 0
        self._cache_score_hits = 0
        self._cache_hints = 0
        self._metrics = None
        self._worker_pool_lock = Lock()
        self._worker_metrics_lock = Lock()
        self._worker_pool = None
        self._worker_ready_count = None
        self._worker_probe_started_count = None
        self._worker_probe_release_event = None
        self._worker_search_cancel_event = None
        self._worker_status_values = None
        self._worker_status_pids = None
        self._worker_mode_values = None
        self._worker_root_values = None
        self._worker_depth_values = None
        self._worker_cache_entry_values = None
        self._worker_node_values = None
        self._worker_learning_read_values = None
        self._worker_status_process_lock = None
        self._worker_pool_state = "not-started"
        self._local_worker_busy = False
        self._local_worker_mode = _WORKER_MODE_NONE
        self._local_worker_root_position = 0
        self._local_worker_search_depth = None
        self._local_worker_cache_entries = 0
        self._local_worker_visited_nodes = 0
        self._local_worker_learning_reading = False
        self._ponder_state_lock = Lock()
        self._ponder_active = False

    def prepare_workers(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancellation_event: Optional[Event] = None,
        timeout_seconds: float = _WORKER_STARTUP_TIMEOUT_SECONDS,
        minimum_progress_interval_seconds: float = 0.0,
        force_pool: bool = False,
    ):
        """Uruchamia pulę procesów i czeka na gotowość każdego workera."""
        if cancellation_event is not None and cancellation_event.is_set():
            raise WorkerPoolInitializationCancelled(
                "AI worker initialization was cancelled")
        if minimum_progress_interval_seconds < 0:
            raise ValueError("The worker progress interval cannot be negative")
        if (
            self.max_workers <= 1
            and not force_pool
            and not (self.ponder_enabled and self.config.cache_enabled)
        ):
            if progress_callback is not None:
                progress_callback(1, 1)
            return

        with self._worker_pool_lock:
            if self._worker_pool is not None:
                if progress_callback is not None:
                    progress_callback(self.max_workers, self.max_workers)
                return
            if timeout_seconds <= 0:
                raise TimeoutError("No time remains to start AI search workers")

            context = multiprocessing.get_context("spawn")
            ready_count = context.Value("i", 0)
            probe_started_count = context.Value("i", 0)
            probe_release_event = context.Event()
            search_cancel_event = context.Event()
            worker_status_values = context.RawArray("i", self.max_workers)
            worker_status_pids = context.RawArray("i", self.max_workers)
            worker_mode_values = context.RawArray("i", self.max_workers)
            worker_root_values = context.RawArray("i", self.max_workers)
            worker_depth_values = context.RawArray("i", self.max_workers)
            worker_cache_entry_values = context.RawArray("i", self.max_workers)
            worker_node_values = context.RawArray("q", self.max_workers)
            worker_learning_read_values = context.RawArray(
                "i", self.max_workers)
            worker_status_lock = context.Lock()
            executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                mp_context=context,
                initializer=_initialize_search_worker,
                initargs=(
                    ready_count,
                    probe_started_count,
                    probe_release_event,
                    search_cancel_event,
                    worker_status_values,
                    worker_status_pids,
                    worker_mode_values,
                    worker_root_values,
                    worker_depth_values,
                    worker_cache_entry_values,
                    worker_node_values,
                    worker_learning_read_values,
                    worker_status_lock,
                    self._learning_active,
                    self.config.learning_max_file_size_bytes,
                    str(self._learning_database_path),
                ),
            )
            self._worker_pool = executor
            self._worker_ready_count = ready_count
            self._worker_probe_started_count = probe_started_count
            self._worker_probe_release_event = probe_release_event
            self._worker_search_cancel_event = search_cancel_event
            with self._worker_metrics_lock:
                self._worker_status_values = worker_status_values
                self._worker_status_pids = worker_status_pids
                self._worker_mode_values = worker_mode_values
                self._worker_root_values = worker_root_values
                self._worker_depth_values = worker_depth_values
                self._worker_cache_entry_values = worker_cache_entry_values
                self._worker_node_values = worker_node_values
                self._worker_learning_read_values = (
                    worker_learning_read_values)
                self._worker_status_process_lock = worker_status_lock
                self._worker_pool_state = "starting"
            warmup_futures = []
            try:
                deadline = time.monotonic() + timeout_seconds
                for worker_index in range(1, self.max_workers + 1):
                    if cancellation_event is not None and cancellation_event.is_set():
                        raise WorkerPoolInitializationCancelled(
                            "AI worker initialization was cancelled")
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Timed out waiting for AI search workers to start")

                    future = executor.submit(_prewarm_search_worker)
                    warmup_futures.append(future)
                    while (
                        ready_count.value < worker_index
                        or probe_started_count.value < worker_index
                    ):
                        if (
                            cancellation_event is not None
                            and cancellation_event.is_set()
                        ):
                            raise WorkerPoolInitializationCancelled(
                                "AI worker initialization was cancelled")
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                "Timed out waiting for AI search workers to start")
                        for warmup_future in warmup_futures:
                            if warmup_future.done():
                                warmup_future.result()
                        if cancellation_event is not None:
                            cancellation_event.wait(0.01)
                        else:
                            time.sleep(0.01)

                    if progress_callback is not None:
                        progress_callback(worker_index, self.max_workers)
                    if minimum_progress_interval_seconds:
                        if cancellation_event is not None:
                            if cancellation_event.wait(
                                minimum_progress_interval_seconds
                            ):
                                raise WorkerPoolInitializationCancelled(
                                    "AI worker initialization was cancelled")
                        else:
                            time.sleep(minimum_progress_interval_seconds)

                if cancellation_event is not None and cancellation_event.is_set():
                    raise WorkerPoolInitializationCancelled(
                        "AI worker initialization was cancelled")
                probe_release_event.set()
                worker_process_ids = [
                    future.result() for future in warmup_futures
                ]
                if len(set(worker_process_ids)) != self.max_workers:
                    raise RuntimeError(
                        "AI worker probes did not run in distinct processes")
                with self._worker_metrics_lock:
                    self._worker_pool_state = "ready"
            except Exception:
                probe_release_event.set()
                for future in warmup_futures:
                    future.cancel()
                executor.shutdown(wait=True, cancel_futures=True)
                self._clear_worker_pool(executor)
                raise

    def shutdown_worker_pool(self):
        """Zamyka pulę procesów; wielokrotne wywołanie jest bezpieczne."""
        with self._worker_pool_lock:
            executor = self._worker_pool
            # Keep synchronization handles alive until worker processes exit.
            ready_count = self._worker_ready_count
            probe_started_count = self._worker_probe_started_count
            probe_release_event = self._worker_probe_release_event
            search_cancel_event = self._worker_search_cancel_event
            worker_status_values = self._worker_status_values
            worker_status_pids = self._worker_status_pids
            worker_cache_entry_values = self._worker_cache_entry_values
            worker_node_values = self._worker_node_values
            worker_learning_read_values = self._worker_learning_read_values
            worker_status_process_lock = self._worker_status_process_lock
            self._clear_worker_pool(executor)
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    def close(self):
        """Zamyka workery i trwały magazyn wskazówek ruchów."""
        global _WORKER_MOVE_LEARNING_STORE
        self.shutdown_worker_pool()
        self._flush_move_learning_updates()
        self._flush_search_result_updates()
        if self._move_learning_store is not None:
            if _WORKER_MOVE_LEARNING_STORE is self._move_learning_store:
                _WORKER_MOVE_LEARNING_STORE = None
            self._move_learning_store.close()
            self._move_learning_store = None
        self._learning_active = False

    def _disable_move_learning(self, error):
        global _WORKER_MOVE_LEARNING_STORE
        log_error("Persistent move learning disabled: {}".format(error))
        if self._move_learning_store is not None:
            if _WORKER_MOVE_LEARNING_STORE is self._move_learning_store:
                _WORKER_MOVE_LEARNING_STORE = None
            self._move_learning_store.close()
            self._move_learning_store = None
        self._learning_active = False
        self._move_learning_updates = MoveLearningAccumulator()
        self._search_result_updates = SearchResultAccumulator()

    def learning_database_file_size(self):
        try:
            size = self._learning_database_path.stat().st_size
            self._learning_database_size_error_reported = False
            return size
        except FileNotFoundError:
            return 0
        except OSError as error:
            if not getattr(self, "_learning_database_size_error_reported", False):
                log_error(
                    "Unable to read move-learning database size: {}".format(
                        error)
                )
                self._learning_database_size_error_reported = True
            return None

    def action_has_learning_hint(self, action):
        return action in self._root_learning_hint_actions

    def _move_learning_action_scores(self, state, actions):
        store = self._move_learning_store or _WORKER_MOVE_LEARNING_STORE
        if (
            not self._learning_active
            or store is None
            or not isinstance(state, GameState)
        ):
            return {}
        is_process_worker = _WORKER_STATUS_INDEX is not None
        if is_process_worker:
            _set_current_worker_learning_reading(True)
        else:
            self._set_local_worker_learning_reading(True)
        try:
            return store.get_action_scores(state, actions)
        except (OSError, sqlite3.Error, ValueError) as error:
            self._disable_move_learning(error)
            return {}
        finally:
            if is_process_worker:
                _set_current_worker_learning_reading(False)
            else:
                self._set_local_worker_learning_reading(False)

    def _persistent_search_results(self, state, actions, position_key=None):
        store = self._move_learning_store or _WORKER_MOVE_LEARNING_STORE
        if (
            not self.config.cache_enabled
            or not self.config.learning_enabled
            or store is None
            or has_collectible_board_card(state)
        ):
            return {}
        is_process_worker = _WORKER_STATUS_INDEX is not None
        if is_process_worker:
            _set_current_worker_learning_reading(True)
        else:
            self._set_local_worker_learning_reading(True)
        try:
            return store.get_search_results(
                state, actions, state_key=position_key)
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            self._disable_move_learning(error)
            return {}
        finally:
            if is_process_worker:
                _set_current_worker_learning_reading(False)
            else:
                self._set_local_worker_learning_reading(False)

    def _persistent_search_position_key(self, state, state_cache_key):
        store = self._move_learning_store or _WORKER_MOVE_LEARNING_STORE
        if (
            state_cache_key is None
            or not self.config.learning_enabled
            or store is None
            or has_collectible_board_card(state)
        ):
            return None
        try:
            return search_result_position_key(state, state_cache_key)
        except (TypeError, ValueError) as error:
            self._disable_move_learning(error)
            return None

    def _record_search_result(
        self, state, action, depth, score, bound, position_key=None,
        kind="cutoff",
    ):
        store = self._move_learning_store or _WORKER_MOVE_LEARNING_STORE
        if (
            not self.config.cache_enabled
            or not self.config.learning_enabled
            or not self.config.learning_save_enabled
            or store is None
            or action is None
            or not isinstance(state, GameState)
            or has_collectible_board_card(state)
        ):
            return
        try:
            if position_key is None:
                position_key = search_result_position_key(state)
            if position_key is not None:
                self._search_result_updates.record(
                    position_key, action, depth, score, bound, kind)
        except (TypeError, ValueError) as error:
            log_error("Unable to record persistent search result: {}".format(
                error))

    def _record_best_search_result(
        self, state, action, depth, score, position_key=None,
    ):
        self._record_search_result(
            state,
            action,
            depth,
            score,
            Bound.EXACT,
            position_key,
            kind="best",
        )

    def _merge_search_result_updates(self, updates):
        if (
            self.config.cache_enabled
            and self.config.learning_enabled
            and self.config.learning_save_enabled
            and updates
        ):
            self._search_result_updates.merge(updates)

    def _flush_search_result_updates(self):
        updates = self._search_result_updates.snapshot()
        if not updates:
            return
        self._search_result_updates = SearchResultAccumulator()
        if (
            not self.config.cache_enabled
            or not self.config.learning_enabled
            or not self.config.learning_save_enabled
            or self._move_learning_store is None
        ):
            return
        try:
            self._move_learning_store.apply_search_result_updates(updates)
        except (OSError, sqlite3.Error, ValueError) as error:
            self._disable_move_learning(error)

    def _record_move_learning(
        self, state, action, signal, learning_path_eligible=True
    ):
        if (
            not self._learning_active
            or not self.config.learning_save_enabled
            or not learning_path_eligible
            or action is None
            or not is_plain_move(action)
            or not isinstance(state, GameState)
        ):
            return
        key = learning_position_key(state)
        if key is not None:
            self._move_learning_updates.record(key, action, signal)

    def _merge_move_learning_updates(self, updates):
        if (
            self._learning_active
            and self.config.learning_save_enabled
            and updates
        ):
            self._move_learning_updates.merge(updates)

    def _flush_move_learning_updates(self):
        updates = self._move_learning_updates.snapshot()
        if not updates:
            return
        self._move_learning_updates = MoveLearningAccumulator()
        if (
            not self._learning_active
            or not self.config.learning_save_enabled
            or self._move_learning_store is None
        ):
            return
        try:
            self._move_learning_store.apply_updates(updates)
        except (OSError, sqlite3.Error, ValueError) as error:
            self._disable_move_learning(error)

    def _clear_worker_pool(self, executor):
        if self._worker_pool is executor:
            self._worker_pool = None
            self._worker_ready_count = None
            self._worker_probe_started_count = None
            self._worker_probe_release_event = None
            self._worker_search_cancel_event = None
            with self._worker_metrics_lock:
                self._worker_status_values = None
                self._worker_status_pids = None
                self._worker_cache_entry_values = None
                self._worker_node_values = None
                self._worker_learning_read_values = None
                self._worker_status_process_lock = None
                self._worker_pool_state = "not-started"

    def _discard_worker_pool(self, executor):
        with self._worker_pool_lock:
            if self._worker_pool is not executor:
                return
            # Keep synchronization handles alive until worker processes exit.
            ready_count = self._worker_ready_count
            probe_started_count = self._worker_probe_started_count
            probe_release_event = self._worker_probe_release_event
            search_cancel_event = self._worker_search_cancel_event
            worker_status_values = self._worker_status_values
            worker_status_pids = self._worker_status_pids
            worker_cache_entry_values = self._worker_cache_entry_values
            worker_node_values = self._worker_node_values
            worker_learning_read_values = self._worker_learning_read_values
            worker_status_process_lock = self._worker_status_process_lock
            self._clear_worker_pool(executor)
        executor.shutdown(wait=True, cancel_futures=True)

    def clear_search_cache(self):
        with self._cache_lock:
            self._cache_generation += 1
            self._ponder_completed_depths.clear()
            if self._cache is not None:
                self._cache = SearchCache(self.config.cache_max_entries)

    def search_cache_generation(self):
        with self._cache_lock:
            return self._cache_generation

    def cache_stats(self):
        return self.cache_diagnostics()[:4]

    def cache_diagnostics(self):
        with self._cache_lock:
            cache = self._cache
            if cache is None:
                return False, 0, self.config.cache_max_entries, 0, None
            return (
                True,
                len(cache),
                cache.max_entries,
                cache.evictions,
                cache.deepest_entry_depth,
            )

    def search_progress_stats(self, workers=None):
        if workers is None:
            workers = self.worker_stats()
        active_worker_nodes = sum(worker.visited_nodes or 0 for worker in workers)
        with self._search_progress_lock:
            phase = self._search_phase
            current_depth = self._current_search_depth
            completed_depth = self._completed_search_depth
            self._reported_search_nodes = max(
                self._reported_search_nodes,
                self._nodes + active_worker_nodes,
            )
            reported_nodes = self._reported_search_nodes
            ponder_progress = (
                self._ponder_white_actions_completed,
                self._ponder_white_actions_total,
                self._ponder_branches_generated,
                self._ponder_root_actions_completed,
                self._ponder_root_actions_discovered,
                self._ponder_depth_counts,
                self._ponder_max_branch_depth,
                self._ponder_dangerous_white_candidates,
            )
        return (
            phase,
            current_depth,
            completed_depth,
            reported_nodes,
            *ponder_progress,
        )

    def _begin_search_progress(self, phase):
        with self._search_progress_lock:
            self._search_phase = phase
            self._current_search_depth = 0
            self._completed_search_depth = 0
            self._nodes = 0
            self._reported_search_nodes = 0
            self._ponder_white_actions_completed = None
            self._ponder_white_actions_total = None
            self._ponder_branches_generated = None
            self._ponder_root_actions_completed = None
            self._ponder_root_actions_discovered = None
            self._ponder_depth_counts = ()
            self._ponder_max_branch_depth = None
            self._ponder_dangerous_white_candidates = ()

    def _set_current_search_depth(self, depth):
        with self._search_progress_lock:
            self._current_search_depth = depth
            if self._search_phase == "pondering":
                self._ponder_root_actions_completed = 0
                self._ponder_root_actions_discovered = 0
                self._ponder_depth_counts = ()
                self._ponder_max_branch_depth = 0

    def _set_dangerous_white_candidates(self, candidates):
        formatted_candidates = []
        for action, score, depth in candidates:
            if not math.isfinite(score):
                continue
            source = GameAction._format_position(action.source).lower()
            destination = (
                GameAction._format_position(action.destination).lower()
                if action.destination else "-"
            )
            move = "{}-{}".format(source, destination)
            if action.action_type != GameActionType.MOVE:
                move = "{} {}".format(action.action_type.value, move)
            formatted_candidates.append((move, score, depth))
            if len(formatted_candidates) == 5:
                break
        with self._search_progress_lock:
            if self._search_phase == "pondering":
                self._ponder_dangerous_white_candidates = tuple(
                    formatted_candidates)

    def _set_ponder_depth_progress(self, branch_depths):
        depth_counts = {}
        for depth in branch_depths:
            depth_counts[depth] = depth_counts.get(depth, 0) + 1
        with self._search_progress_lock:
            if self._search_phase != "pondering":
                return
            self._ponder_depth_counts = tuple(sorted(depth_counts.items()))
            self._ponder_max_branch_depth = max(depth_counts, default=0)

    def _begin_ponder_progress(self, white_actions_total):
        with self._search_progress_lock:
            self._ponder_white_actions_completed = 0
            self._ponder_white_actions_total = white_actions_total
            self._ponder_branches_generated = 0
            self._ponder_root_actions_completed = 0
            self._ponder_root_actions_discovered = 0
            self._ponder_dangerous_white_candidates = ()

    def _record_ponder_progress(
        self,
        white_actions_completed=0,
        branches_generated=0,
        root_actions_completed=0,
        root_actions_discovered=0,
    ):
        with self._search_progress_lock:
            if self._search_phase != "pondering":
                return
            self._ponder_white_actions_completed += white_actions_completed
            self._ponder_branches_generated += branches_generated
            self._ponder_root_actions_completed += root_actions_completed
            self._ponder_root_actions_discovered += root_actions_discovered

    def _set_completed_search_depth(self, depth):
        with self._search_progress_lock:
            self._completed_search_depth = depth

    def _add_completed_nodes(self, node_count):
        with self._search_progress_lock:
            self._nodes += node_count

    def _finish_search_progress(self):
        with self._search_progress_lock:
            self._search_phase = "idle"
            self._current_search_depth = 0

    def worker_stats(self):
        with self._worker_metrics_lock:
            status_values = self._worker_status_values
            status_pids = self._worker_status_pids
            mode_values = self._worker_mode_values
            root_values = self._worker_root_values
            depth_values = self._worker_depth_values
            cache_entry_values = self._worker_cache_entry_values
            node_values = self._worker_node_values
            learning_read_values = self._worker_learning_read_values
            process_lock = self._worker_status_process_lock
            pool_state = self._worker_pool_state
            local_worker_busy = self._local_worker_busy
            local_worker_mode = self._local_worker_mode
            local_worker_root_position = self._local_worker_root_position
            local_worker_search_depth = self._local_worker_search_depth
            local_worker_cache_entries = self._local_worker_cache_entries
            local_worker_visited_nodes = self._local_worker_visited_nodes
            local_worker_learning_reading = (
                self._local_worker_learning_reading)

        if status_values is None or status_pids is None or process_lock is None:
            if self.max_workers == 1:
                return (
                    AIWorkerStats(
                        1,
                        "busy" if local_worker_busy else "idle",
                        is_local=True,
                        cache_entries=local_worker_cache_entries,
                        visited_nodes=local_worker_visited_nodes,
                        mode=_WORKER_MODE_NAMES.get(
                            local_worker_mode, "-"),
                        root=_root_square_notation(
                            local_worker_root_position)
                        if local_worker_busy else "-",
                        search_depth=(
                            local_worker_search_depth
                            if local_worker_busy
                            and local_worker_mode == _WORKER_MODE_SEARCH
                            else None
                        ),
                        learning_database_reading=(
                            local_worker_learning_reading),
                    ),
                )
            status = "starting" if pool_state == "starting" else "not-started"
            workers = tuple(
                AIWorkerStats(worker_id, status)
                for worker_id in range(1, self.max_workers + 1)
            )
            if local_worker_busy or local_worker_learning_reading:
                workers += (
                    AIWorkerStats(
                        self.max_workers + 1,
                        "busy",
                        is_local=True,
                        cache_entries=local_worker_cache_entries,
                        visited_nodes=local_worker_visited_nodes,
                        mode=_WORKER_MODE_NAMES.get(
                            local_worker_mode, "-"),
                        root=_root_square_notation(
                            local_worker_root_position),
                        search_depth=(
                            local_worker_search_depth
                            if local_worker_mode == _WORKER_MODE_SEARCH
                            else None
                        ),
                        learning_database_reading=(
                            local_worker_learning_reading),
                    ),
                )
            return workers

        with process_lock:
            process_states = tuple(
                (
                    status_values[index],
                    status_pids[index],
                    (
                        cache_entry_values[index]
                        if cache_entry_values is not None else None
                    ),
                    node_values[index] if node_values is not None else None,
                    (
                        mode_values[index]
                        if mode_values is not None else _WORKER_MODE_NONE
                    ),
                    root_values[index] if root_values is not None else 0,
                    depth_values[index] if depth_values is not None else 0,
                    (
                        bool(learning_read_values[index])
                        if learning_read_values is not None else False
                    ),
                )
                for index in range(self.max_workers)
            )

        workers = []
        for index, (
            status_code, worker_pid, cache_entries, visited_nodes,
            mode_code, root_position, search_depth, learning_database_reading,
        ) in enumerate(
            process_states
        ):
            if worker_pid == 0:
                status = "starting" if pool_state == "starting" else "not-started"
                worker_pid = None
                mode_code = _WORKER_MODE_NONE
                root_position = 0
                search_depth = 0
            else:
                status = _WORKER_STATUS_NAMES.get(status_code, "unknown")
            workers.append(AIWorkerStats(
                index + 1, status, worker_pid,
                cache_entries=cache_entries,
                visited_nodes=visited_nodes,
                mode=_WORKER_MODE_NAMES.get(mode_code, "-"),
                root=_root_square_notation(root_position),
                search_depth=(
                    search_depth
                    if mode_code == _WORKER_MODE_SEARCH and search_depth > 0
                    else None
                ),
                learning_database_reading=learning_database_reading,
            ))
        if local_worker_busy or local_worker_learning_reading:
            workers.append(
                AIWorkerStats(
                    len(workers) + 1,
                    "busy",
                    is_local=True,
                    cache_entries=local_worker_cache_entries,
                    visited_nodes=local_worker_visited_nodes,
                    mode=_WORKER_MODE_NAMES.get(local_worker_mode, "-"),
                    root=_root_square_notation(local_worker_root_position),
                    search_depth=(
                        local_worker_search_depth
                        if local_worker_mode == _WORKER_MODE_SEARCH
                        else None
                    ),
                    learning_database_reading=(
                        local_worker_learning_reading),
                ))
        return tuple(workers)

    def _set_local_worker_busy(
        self, is_busy, mode=_WORKER_MODE_NONE, root_position=0,
        search_depth=None,
    ):
        with self._worker_metrics_lock:
            self._local_worker_busy = is_busy
            self._local_worker_mode = mode if is_busy else _WORKER_MODE_NONE
            self._local_worker_root_position = (
                root_position if is_busy else 0)
            self._local_worker_search_depth = (
                search_depth
                if is_busy
                and mode == _WORKER_MODE_SEARCH
                and isinstance(search_depth, int)
                and search_depth > 0
                else None
            )
            if not is_busy:
                self._local_worker_cache_entries = 0
                self._local_worker_visited_nodes = 0

    def _set_local_worker_cache_entries(self, entry_count):
        with self._worker_metrics_lock:
            self._local_worker_cache_entries = entry_count

    def _set_local_worker_visited_nodes(self, visited_nodes):
        with self._worker_metrics_lock:
            self._local_worker_visited_nodes = visited_nodes

    def _set_local_worker_learning_reading(self, is_reading):
        with self._worker_metrics_lock:
            self._local_worker_learning_reading = is_reading

    def choose_action(
        self,
        observation: GameObservation,
        progress_callback: Optional[Callable[[GameAction, int], None]] = None,
        candidate_callback: Optional[
            Callable[[GameAction, int, float], None]
        ] = None,
        cache_generation: Optional[int] = None,
    ) -> SearchResult:
        """Szuka w pełnym stanie i zwraca najlepiej ocenionego dotąd kandydata."""
        if observation.own_color != COLOR.BLACK:
            raise ValueError("ChessAI is configured to play as black")
        if observation.current_turn != COLOR.BLACK:
            raise ValueError("It is not the AI player's turn")

        self._root_learning_hint_actions = frozenset()
        self._metrics = (
            _SearchMetricsCollector() if self.config.metrics_enabled else None
        )
        metrics_started = self._metric_start()
        state_started = self._metric_start()
        state = observation.to_state()
        self._metric_finish("observation_ns", state_started)
        root_actions = self._available_actions_for_search(state)
        if self._metrics is not None:
            self._metrics.add("root_actions", len(root_actions))
        if not root_actions:
            log_info("AI search found no legal actions")
            score = self._evaluate_for_search(state)
            self._metric_finish("wall_time_ns", metrics_started)
            metrics = self._metrics.snapshot() if self._metrics is not None else None
            if metrics is not None:
                _log_search_metrics(metrics)
            return SearchResult(None, score, 0, 0, metrics)
        key_started = self._metric_start()
        root_key = state.cache_key() if self._cache is not None else None
        self._metric_finish("cache_key_ns", key_started)

        search_started = time.monotonic()
        pondered_depth = None
        with self._cache_lock:
            if cache_generation is None:
                cache_generation = self._cache_generation
            if (
                root_key is not None
                and cache_generation == self._cache_generation
            ):
                pondered_depth = self._ponder_completed_depths.pop(
                    root_key, None)
            hint = (
                self._cache.best_move(state.cache_key())
                if self._cache is not None
                and cache_generation == self._cache_generation else None
            )
        time_limit_seconds = self._search_time_limit_for_depth(pondered_depth)
        self._deadline = search_started + time_limit_seconds
        log_info(
            "AI search time budget: allocated={:.3f}s, configured={:.3f}s, "
            "ponder_depth={}, max_depth={}, fallback={}".format(
                time_limit_seconds,
                self.config.time_limit_seconds,
                pondered_depth if pondered_depth is not None else "none",
                self.config.max_depth,
                pondered_depth is None,
            )
        )
        self._begin_search_progress("searching")
        self._cache_hits = self._cache_score_hits = self._cache_hints = 0
        ordered_actions = self._order_actions_for_search(
            state, root_actions, is_learning_position_eligible(state))
        self._root_learning_hint_actions = self._last_learning_hint_actions
        persistent_root_key = self._persistent_search_position_key(
            state, root_key)
        persistent_root_results = self._persistent_search_results(
            state, ordered_actions, persistent_root_key)
        action_order = {
            action: index for index, action in enumerate(ordered_actions)
        }
        ordered_actions = self._order_actions_with_persistent_results(
            state,
            ordered_actions,
            persistent_root_results,
            self.config.max_depth,
        )
        if hint in ordered_actions:
            ordered_actions.remove(hint)
            ordered_actions.insert(0, hint)
            self._cache_hints += 1
            if self._metrics is not None:
                self._metrics.add("cache_hints", 1)
        best_action = ordered_actions[0]
        best_score = self._evaluate_for_search(
            self._apply_generated_action_for_search(state, best_action))
        best_known_scores = {best_action: (best_score, 0)}
        completed_depth = 0
        if progress_callback is not None:
            progress_callback(best_action, completed_depth)
        if candidate_callback is not None:
            candidate_callback(best_action, completed_depth, best_score)

        worker_count = self._worker_count_for_tasks(len(ordered_actions))
        if self._metrics is not None:
            self._metrics.add("worker_count", worker_count)
        log_info(
            "AI search started: {} root actions, max_depth={}, time_limit={:.2f}s, "
            "workers={}".format(
                len(ordered_actions),
                self.config.max_depth,
                self.config.time_limit_seconds,
                worker_count,
            )
        )
        interrupted = False
        if worker_count > 1 and self._worker_pool is None:
            startup_time_remaining = self._deadline - time.monotonic()
            if startup_time_remaining <= 0:
                interrupted = True
            else:
                try:
                    startup_started = self._metric_start()
                    self.prepare_workers(timeout_seconds=startup_time_remaining)
                    self._metric_finish("worker_pool_startup_ns", startup_started)
                except TimeoutError:
                    self._metric_finish(
                        "worker_pool_startup_ns", startup_started)
                    if time.monotonic() >= self._deadline:
                        interrupted = True
                    else:
                        self._finish_search_progress()
                        raise
                except Exception:
                    self._finish_search_progress()
                    raise
        executor = (
            self._worker_pool
            if worker_count > 1 and not interrupted else None
        )
        try:
            for depth in range(1, self.config.max_depth + 1):
                if time.monotonic() >= self._deadline:
                    interrupted = True
                    break
                self._set_current_search_depth(depth)
                log_logic("AI search started depth {}".format(depth))
                with self._cache_lock:
                    snapshot = (
                        self._cache.snapshot(_WORKER_CACHE_LIMIT)
                        if self._cache is not None
                        and self._cache_generation == cache_generation else ()
                    )
                iteration_cache = (
                    SearchCache(self.config.cache_max_entries)
                    if self.config.cache_enabled else None
                )
                completed_scores = {}
                outcomes = {}
                precompleted_root_actions = set()
                next_merge = 0
                root_alpha = -math.inf
                finished_root_actions = 0
                iteration_search_result_updates = []
                exact_root_results = {
                    action: result
                    for action, records in persistent_root_results.items()
                    for result in records
                    if (
                        result.depth == depth
                        and result.kind == "best"
                        and result.bound == Bound.EXACT.value
                    )
                }
                bad_root_actions = {
                    action
                    for action, records in persistent_root_results.items()
                    if any(
                        self._is_persistently_soft_cutoff(state, result)
                        for result in self._search_results_at_depth(
                            records, depth)
                    )
                }
                has_recommended_root_action = any(
                    action not in bad_root_actions
                    for action in ordered_actions
                )
                fallback_root_action = None
                if (
                    not has_recommended_root_action
                    and bad_root_actions
                    and len(bad_root_actions) == len(ordered_actions)
                ):
                    fallback_root_action = max(
                        bad_root_actions,
                        key=lambda action: self._mover_relative_score(
                            state,
                            max(
                                (
                                    result.score
                                    for result
                                    in self._search_results_at_depth(
                                        persistent_root_results[action], depth)
                                    if self._is_persistently_soft_cutoff(
                                        state, result)
                                ),
                                key=lambda score: self._mover_relative_score(
                                    state, score),
                            ),
                        ),
                    )
                    for action, records in persistent_root_results.items():
                        if action == fallback_root_action:
                            continue
                        cutoff_exact = next(
                            (
                                result
                                for result in self._search_results_at_depth(
                                    records, depth)
                                if result.kind == "cutoff"
                                and result.bound == Bound.EXACT.value
                                and self._is_persistently_soft_cutoff(
                                    state, result)
                            ),
                            None,
                        )
                        if cutoff_exact is not None:
                            exact_root_results[action] = cutoff_exact
                root_alpha = max(
                    (
                        result.score
                        for action, result in exact_root_results.items()
                        if action != fallback_root_action
                    ),
                    default=-math.inf,
                )

                def record_result(index, result):
                    nonlocal next_merge, root_alpha, finished_root_actions
                    self._add_completed_nodes(result.nodes)
                    if self._metrics is not None:
                        self._metrics.merge(result.metrics)
                    self._merge_move_learning_updates(
                        getattr(result, "learning_updates", ()))
                    iteration_search_result_updates.extend(
                        getattr(result, "search_result_updates", ()))
                    self._cache_hits += result.hits
                    self._cache_score_hits += result.score_hits
                    self._cache_hints += result.hints
                    outcomes[index] = result
                    while next_merge in outcomes:
                        merge_index = next_merge
                        completed = outcomes.pop(next_merge)
                        if iteration_cache is not None:
                            scoped_entries = self._entries_for_root_scope(
                                root_key,
                                ordered_actions[merge_index],
                                completed.entries,
                                cache_generation,
                            )
                            for entry in scoped_entries:
                                iteration_cache.put(entry)
                        next_merge += 1
                        if completed.score is None:
                            continue
                        finished_root_actions += 1
                        if (
                            completed.bound == Bound.UPPER
                            and completed.reliable
                            and completed.score < root_alpha
                        ):
                            best_known_scores.pop(
                                ordered_actions[merge_index], None)
                            continue
                        if (
                            completed.bound != Bound.EXACT
                            or not completed.reliable
                        ):
                            raise RuntimeError(
                                "Root action search returned an unverified score")
                        if is_enabled("DEBUG"):
                            log_debug(
                                "AI root action at depth {}: {} => {:.2f} "
                                "({} nodes)".format(
                                    depth,
                                    ordered_actions[merge_index],
                                    completed.score,
                                    completed.nodes,
                                )
                            )
                        completed_scores[merge_index] = completed.score
                        best_known_scores[
                            ordered_actions[merge_index]
                        ] = (completed.score, depth)
                        root_alpha = max(root_alpha, completed.score)
                        previous_leader = self._candidate_leader_index(
                            completed_scores)
                        self._report_completed_candidate(
                            ordered_actions, completed_scores, depth,
                            candidate_callback, previous_leader)

                for action_index, action in enumerate(ordered_actions):
                    cached_result = exact_root_results.get(action)
                    if action != fallback_root_action and cached_result is not None:
                        precompleted_root_actions.add(action_index)
                        best_known_scores[action] = (
                            cached_result.score, depth)
                        self._cache_score_hits += 1
                        if self._metrics is not None:
                            self._metrics.add("cache_score_hits", 1)
                        record_result(action_index, _RootEvaluation(
                            cached_result.score,
                            0,
                            bound=Bound.EXACT,
                            reliable=True,
                        ))
                        continue
                    if action == fallback_root_action:
                        continue
                    cached_soft_cutoff = next(
                        (
                            result for result
                            in self._search_results_at_depth(
                                persistent_root_results.get(action, ()), depth)
                            if result.kind == "cutoff"
                            and result.bound == Bound.EXACT.value
                            and self._is_persistently_soft_cutoff(
                                state, result)
                        ),
                        None,
                    )
                    if (
                        cached_soft_cutoff is not None
                        and self._mover_relative_score(state, root_alpha)
                            >= self.config.learning_soft_cutoff_threshold
                    ):
                        precompleted_root_actions.add(action_index)
                        self._cache_score_hits += 1
                        if self._metrics is not None:
                            self._metrics.add("cache_score_hits", 1)
                        record_result(action_index, _RootEvaluation(
                            cached_soft_cutoff.score,
                            0,
                            bound=Bound.UPPER,
                            reliable=True,
                        ))
                        continue
                    cached_upper_bound = next(
                        (
                            result for result
                            in self._search_results_at_depth(
                                persistent_root_results.get(action, ()), depth)
                            if result.bound == Bound.UPPER.value
                            and result.kind == "cutoff"
                            and result.score < root_alpha
                        ),
                        None,
                    )
                    if cached_upper_bound is not None:
                        precompleted_root_actions.add(action_index)
                        self._cache_score_hits += 1
                        if self._metrics is not None:
                            self._metrics.add("cache_score_hits", 1)
                        record_result(action_index, _RootEvaluation(
                            cached_upper_bound.score,
                            0,
                            bound=Bound.UPPER,
                            reliable=True,
                        ))

                if executor is None:
                    for action_index, action in enumerate(ordered_actions):
                        if action_index in precompleted_root_actions:
                            continue
                        self._set_local_worker_busy(
                            True, _WORKER_MODE_SEARCH, action.source, depth)
                        try:
                            result = _evaluate_root_action(
                                state, action, depth, self.config, self._deadline,
                                snapshot, self._set_local_worker_cache_entries,
                                self._set_local_worker_visited_nodes,
                                root_alpha=root_alpha)
                        except Exception as error:
                            log_error(
                                "AI root task failed for {} at depth {}: {}".format(
                                    action, depth, error)
                            )
                            raise
                        finally:
                            self._set_local_worker_busy(False)
                        record_result(action_index, result)
                        if result.score is None:
                            interrupted = True
                            break
                else:
                    pending = {}
                    next_action = 0
                    while time.monotonic() < self._deadline:
                        while (
                            next_action < len(ordered_actions)
                            and next_action in precompleted_root_actions
                        ):
                            next_action += 1
                        while (
                            next_action < len(ordered_actions)
                            and len(pending) < worker_count
                            and next_action < next_merge + worker_count
                        ):
                            future = executor.submit(
                                _evaluate_root_action, state, ordered_actions[next_action],
                                depth, self.config, self._deadline, snapshot,
                                root_alpha=root_alpha)
                            pending[future] = next_action
                            next_action += 1
                        if not pending:
                            break
                        remaining = max(0.0, self._deadline - time.monotonic())
                        wait_started = self._metric_start()
                        done, _ = wait(
                            set(pending),
                            timeout=min(0.05, remaining),
                            return_when=FIRST_COMPLETED,
                        )
                        self._metric_finish("worker_wait_ns", wait_started)
                        for future in sorted(done, key=pending.get):
                            task_index = pending.pop(future)
                            try:
                                result = future.result()
                            except Exception as error:
                                log_error(
                                    "AI worker failed for {} at depth {}: {}".format(
                                        ordered_actions[task_index], depth, error)
                                )
                                raise
                            record_result(task_index, result)
                            if result.score is None:
                                interrupted = True
                        if interrupted:
                            break

                    if pending:
                        interrupted = True
                        for future in pending:
                            future.cancel()
                        for future, task_index in sorted(
                            pending.items(), key=lambda item: item[1]
                        ):
                            if not future.cancelled():
                                try:
                                    result = future.result()
                                except Exception as error:
                                    log_error(
                                        "AI worker failed for {} at depth {}: {}".format(
                                            ordered_actions[task_index],
                                            depth,
                                            error,
                                        )
                                    )
                                    raise
                                record_result(task_index, result)

                if iteration_cache is not None:
                    for index in sorted(outcomes):
                        scoped_entries = self._entries_for_root_scope(
                            root_key,
                            ordered_actions[index],
                            outcomes[index].entries,
                            cache_generation,
                        )
                        for entry in scoped_entries:
                            iteration_cache.put(entry)
                    with self._cache_lock:
                        if self._cache_generation == cache_generation:
                            for entry in iteration_cache.snapshot(self.config.cache_max_entries):
                                self._cache.put(entry)
                if finished_root_actions != len(ordered_actions):
                    interrupted = True
                    break
                self._merge_search_result_updates(
                    iteration_search_result_updates)
                depth_scores = [
                    (completed_scores[index], action)
                    for index, action in enumerate(ordered_actions)
                    if index in completed_scores
                ]

                best_score, best_action = max(
                    depth_scores,
                    key=lambda item: (item[0], -action_order[item[1]]))
                self._record_best_search_result(
                    state,
                    best_action,
                    depth,
                    best_score,
                    persistent_root_key,
                )
                for action_index, action in enumerate(ordered_actions):
                    if action == best_action:
                        continue
                    result = outcomes.get(action_index)
                    if (
                        result is None
                        or result.score is None
                        or not result.reliable
                        or result.bound is None
                    ):
                        continue
                    if (
                        result.bound != Bound.EXACT
                        or self._mover_relative_score(state, result.score)
                        < self.config.learning_soft_cutoff_threshold
                    ):
                        self._record_search_result(
                            state,
                            action,
                            depth,
                            result.score,
                            result.bound,
                            persistent_root_key,
                            kind="cutoff",
                        )
                if depth == 1:
                    self._record_move_learning(
                        state, best_action, "preferred")
                    _, worst_action = min(
                        depth_scores,
                        key=lambda item: (item[0], action_order[item[1]]))
                    if worst_action != best_action:
                        self._record_move_learning(
                            state, worst_action, "worst")
                completed_depth = depth
                self._set_completed_search_depth(completed_depth)
                log_logic(
                    "AI search completed depth {}: best action={}, score={:+.2f}".format(
                        depth, best_action, best_score)
                )
                if progress_callback is not None:
                    progress_callback(best_action, completed_depth)
                if candidate_callback is not None:
                    candidate_callback(best_action, completed_depth, best_score)
                ordered_exact_actions = [
                    action
                    for _, action in sorted(
                        depth_scores,
                        key=lambda item: (item[0], -action_order[item[1]]),
                        reverse=True)
                ]
                exact_actions = set(ordered_exact_actions)
                ordered_actions = ordered_exact_actions + [
                    action for action in ordered_actions
                    if action not in exact_actions
                ]
        except Exception:
            if executor is not None:
                self._discard_worker_pool(executor)
            raise
        finally:
            self._finish_search_progress()
            self._flush_move_learning_updates()
            self._flush_search_result_updates()

        best_action = max(
            best_known_scores,
            key=lambda action: (
                best_known_scores[action][0],
                -action_order[action],
            ),
        )
        best_score, best_action_depth = best_known_scores[best_action]
        with self._cache_lock:
            if (
                self._cache is not None
                and self._cache_generation == cache_generation
            ):
                root_scope_id = self._cache.scope_id_for(root_key, best_action)
                self._cache.retain_scope(root_scope_id)
        if interrupted:
            log_warn(
                "AI search stopped before completing the next depth; using best "
                "known action {} (score={:+.2f}, evaluated at depth {})".format(
                    best_action, best_score, best_action_depth)
            )
        elapsed = time.monotonic() - search_started
        log_info(
            "AI search finished: action={}, score={:+.2f}, completed_depth={}, "
            "elapsed={:.3f}s, nodes={}".format(
                best_action,
                best_score,
                completed_depth,
                elapsed,
                self._nodes,
            )
        )
        self._metric_finish("wall_time_ns", metrics_started)
        metrics = self._metrics.snapshot() if self._metrics is not None else None
        if metrics is not None:
            _log_search_metrics(metrics)
        if is_enabled("DEBUG"):
            nodes_per_second = self._nodes / elapsed if elapsed > 0 else 0.0
            with self._cache_lock:
                cache_size = len(self._cache) if self._cache is not None else 0
                cache_evictions = self._cache.evictions if self._cache is not None else 0
            log_debug(
                "AI search metrics: workers={}, max_depth={}, completed_depth={}, "
                "elapsed={:.3f}s, nodes={}, nodes_per_second={:.1f}, "
                "action={}, score={:+.2f}".format(
                    worker_count,
                    self.config.max_depth,
                    completed_depth,
                    elapsed,
                    self._nodes,
                    nodes_per_second,
                    best_action,
                    best_score,
                )
            )
            log_debug(
                "AI cache metrics: enabled={}, entries={}, hits={}, score_hits={}, "
                "move_hints={}, evictions={}".format(
                    self.config.cache_enabled, cache_size, self._cache_hits,
                    self._cache_score_hits, self._cache_hints, cache_evictions)
            )
        if candidate_callback is not None:
            candidate_callback(best_action, best_action_depth, best_score)
        return SearchResult(
            best_action,
            best_score,
            completed_depth,
            self._nodes,
            metrics,
            self.action_has_learning_hint(best_action),
        )

    def _search_time_limit_for_depth(self, pondered_depth):
        if pondered_depth is None or self.config.max_depth <= 1:
            return self.config.time_limit_seconds
        pondered_depth = min(max(pondered_depth, 1), self.config.max_depth)
        depth_progress = (
            (pondered_depth - 1) / (self.config.max_depth - 1)
        )
        time_fraction = 1.0 - 0.8 * depth_progress
        return self.config.time_limit_seconds * time_fraction

    def cancel_ponder(self):
        """Sygnalizuje workerom przerwanie opcjonalnego wyszukiwania."""
        with self._ponder_state_lock:
            if self._ponder_active and self._worker_search_cancel_event is not None:
                self._worker_search_cancel_event.set()

    def ponder(
        self, state: GameState, cancellation_event: Optional[Event] = None
    ) -> PonderResult:
        """Analizuje możliwe odpowiedzi białych bez limitu czasu."""
        if not self.ponder_enabled or self._cache is None:
            return PonderResult(0, 0, 0, "disabled")
        if state.current_turn != COLOR.WHITE:
            return PonderResult(0, 0, 0, "not-white-to-move")
        if cancellation_event is None:
            cancellation_event = Event()
        if cancellation_event.is_set():
            return PonderResult(0, 0, 0, "cancelled")

        with self._cache_lock:
            self._ponder_completed_depths.clear()
        self.prepare_workers(
            cancellation_event=cancellation_event,
            force_pool=True,
        )
        worker_cancel_event = self._worker_search_cancel_event
        if worker_cancel_event is not None:
            worker_cancel_event.clear()

        with self._cache_lock:
            cache = self._cache
            if cache is None:
                return PonderResult(0, 0, 0, "disabled")
            cache_generation = self._cache_generation
            cache_limit = cache.max_entries
            if len(cache) >= cache_limit:
                return PonderResult(0, 0, 0, "cache-full")

        white_actions = GameSimulation.available_actions(state)
        if cancellation_event.is_set():
            return PonderResult(0, 0, 0, "cancelled")
        if not white_actions:
            return PonderResult(0, 0, 0, "no-legal-replies")

        root_states = []
        root_learning_eligible = []
        root_priorities = []
        root_order_keys = []
        root_branches = []
        task_groups = {}
        task_group_search_position_keys = {}
        task_count = 0
        next_expansion_dispatch = 0
        next_task = 0
        pending = {}
        ready_branches = []
        active_branches = set()
        total_nodes = 0
        stopped_reason = "max-depth"
        capacity_reached = False
        cache_reset = False
        task_worker_count = self._ponder_worker_count_for_tasks(
            self.ponder_worker_count)
        ponder_config = replace(
            self.config, cpu_worker_usage=self.ponder_cpu_worker_usage)

        def task_group_for(root_index):
            nonlocal task_count
            if root_index not in task_groups:
                root_state = root_states[root_index]
                root_key = root_state.cache_key()
                actions = self._order_actions_for_search(
                    root_state,
                    GameSimulation.available_actions(root_state),
                    root_learning_eligible[root_index],
                )
                persistent_position_key = (
                    self._persistent_search_position_key(root_state, root_key)
                )
                persistent_results = self._persistent_search_results(
                    root_state, actions, persistent_position_key)
                actions = self._order_actions_with_persistent_results(
                    root_state,
                    actions,
                    persistent_results,
                    self.config.max_depth,
                )
                task_groups[root_index] = (root_key, tuple(actions))
                task_group_search_position_keys[root_index] = (
                    self._persistent_search_position_key(root_state, root_key))
                task_count += len(actions)
            root_key, actions = task_groups[root_index]
            if root_index not in discovered_root_indexes:
                discovered_root_indexes.add(root_index)
                self._record_ponder_progress(
                    root_actions_discovered=len(actions))
            return root_states[root_index], root_key, actions

        def update_depth_progress():
            self._set_ponder_depth_progress(
                branch["completed_depth"] for branch in root_branches)

        def update_most_dangerous_white_moves():
            best_score_by_action = {}
            best_depth_by_action = {}
            for index, branch in enumerate(root_branches):
                score = branch["candidate_score"]
                depth = branch["candidate_depth"]
                if score is None or not math.isfinite(score):
                    continue
                action_index = root_order_keys[index][0]
                if (
                    action_index not in best_score_by_action
                    or score < best_score_by_action[action_index]
                    or (
                        score == best_score_by_action[action_index]
                        and depth > best_depth_by_action[action_index]
                    )
                ):
                    best_score_by_action[action_index] = score
                    best_depth_by_action[action_index] = depth
            top_actions = sorted(
                best_score_by_action.items(),
                key=lambda item: (item[1], item[0]),
            )[:5]
            self._set_dangerous_white_candidates(
                (
                    white_actions[action_index],
                    score,
                    best_depth_by_action[action_index],
                )
                for action_index, score in top_actions
            )

        def queue_branch(root_index):
            branch = root_branches[root_index]
            if (
                root_index not in active_branches
                or branch["in_flight"]
                or branch["terminal"]
                or branch["current_depth"] > self.config.max_depth
            ):
                return
            action_index, branch_index = root_order_keys[root_index]
            heapq.heappush(
                ready_branches,
                (
                    root_priorities[root_index],
                    action_index,
                    branch_index,
                    root_index,
                ),
            )

        def merge_result_entries(branch_root_key, branch_action, entries):
            nonlocal capacity_reached, cache_reset
            scoped_entries = self._entries_for_root_scope(
                branch_root_key, branch_action, entries, cache_generation)
            for entry in scoped_entries:
                with self._cache_lock:
                    if (
                        self._cache_generation != cache_generation
                        or self._cache is not cache
                    ):
                        cache_reset = True
                        return
                    is_new_entry = not cache.contains(entry.key, entry.depth)
                    if is_new_entry and len(cache) >= cache_limit:
                        capacity_reached = True
                        return
                    cache.put(entry)
                    if len(cache) >= cache_limit:
                        capacity_reached = True

        def all_work_complete():
            return (
                next_expansion_dispatch == len(white_actions)
                and not active_branches
                and not ready_branches
                and not pending
            )

        log_info(
            "AI pondering started: {} white actions, workers={}".format(
                len(white_actions),
                task_worker_count,
            )
        )
        self._begin_search_progress("pondering")
        self._begin_ponder_progress(len(white_actions))
        executor = self._worker_pool
        discovered_root_indexes = set()
        with self._ponder_state_lock:
            self._ponder_active = True
        try:
            while not all_work_complete():
                if cancellation_event.is_set():
                    stopped_reason = "cancelled"
                    if worker_cancel_event is not None:
                        worker_cancel_event.set()
                    for future in pending:
                        future.cancel()
                    break

                with self._cache_lock:
                    if (
                        self._cache_generation != cache_generation
                        or self._cache is not cache
                    ):
                        stopped_reason = "cache-reset"
                        cache_reset = True
                        break
                    if len(cache) >= cache_limit:
                        stopped_reason = "cache-full"
                        capacity_reached = True
                        break
                while len(pending) < task_worker_count:
                    while ready_branches:
                        _, _, _, root_index = heapq.heappop(ready_branches)
                        if root_index in active_branches:
                            break
                    else:
                        root_index = None

                    if root_index is not None:
                        branch = root_branches[root_index]
                        root_state, root_key, actions = task_group_for(root_index)
                        if not actions:
                            branch["terminal"] = True
                            branch["root_alpha"] = self.evaluate(root_state)
                            branch["completed_score"] = branch["root_alpha"]
                            branch["completed_depth"] = self.config.max_depth
                            branch["candidate_score"] = branch["root_alpha"]
                            branch["candidate_depth"] = 1
                            active_branches.remove(root_index)
                            with self._cache_lock:
                                if (
                                    self._cache_generation == cache_generation
                                    and self._cache is cache
                                ):
                                    self._ponder_completed_depths[root_key] = max(
                                        self.config.max_depth,
                                        self._ponder_completed_depths.get(
                                            root_key, 0),
                                    )
                            update_depth_progress()
                            update_most_dangerous_white_moves()
                            continue
                        if branch["in_flight"]:
                            continue
                        with self._cache_lock:
                            if (
                                self._cache_generation != cache_generation
                                or self._cache is not cache
                            ):
                                cache_reset = True
                                break
                            if len(cache) >= cache_limit:
                                capacity_reached = True
                                break
                            snapshot = cache.snapshot(_WORKER_CACHE_LIMIT)
                        action = actions[branch["next_action"]]
                        branch["next_action"] += 1
                        branch["in_flight"] = True
                        task_index = next_task
                        next_task += 1
                        future = executor.submit(
                            _evaluate_root_action,
                            root_state,
                            action,
                            branch["current_depth"],
                            replace(
                                ponder_config,
                                learning_path_eligible=(
                                    root_learning_eligible[root_index]),
                            ),
                            math.inf,
                            snapshot,
                            root_alpha=branch["root_alpha"],
                        )
                        pending[future] = (
                            "search",
                            task_index,
                            root_index,
                            branch["current_depth"],
                            root_state,
                            action,
                            root_key,
                            branch["root_alpha"],
                        )
                        continue

                    if next_expansion_dispatch < len(white_actions):
                        expansion_index = next_expansion_dispatch
                        next_expansion_dispatch += 1
                        future = executor.submit(
                            _expand_ponder_white_action_with_usage,
                            state,
                            white_actions[expansion_index],
                            self.ponder_cpu_worker_usage,
                        )
                        pending[future] = ("expand", expansion_index)
                        continue
                    break

                if cache_reset or capacity_reached:
                    stopped_reason = (
                        "cache-reset" if cache_reset else "cache-full")
                    if worker_cancel_event is not None:
                        worker_cancel_event.set()
                    for future in pending:
                        future.cancel()
                    break

                if not pending:
                    if all_work_complete():
                        break
                    stopped_reason = (
                        "no-legal-replies" if task_count == 0 else "incomplete")
                    break

                done, _ = wait(
                    set(pending), timeout=0.05, return_when=FIRST_COMPLETED)
                for future in sorted(
                    done,
                    key=lambda item: (
                        pending[item][0], pending[item][1]),
                ):
                    task_info = pending.pop(future)
                    result = future.result()
                    if task_info[0] == "expand":
                        expansion_index = task_info[1]
                        for branch_index, expanded_root in enumerate(result):
                            if (
                                isinstance(expanded_root, tuple)
                                and len(expanded_root) == 2
                                and isinstance(expanded_root[0], GameState)
                                and isinstance(expanded_root[1], bool)
                            ):
                                root_state, learning_path_eligible = expanded_root
                            else:
                                root_state = expanded_root
                                learning_path_eligible = (
                                        is_learning_position_eligible(root_state)
                                        and is_plain_move(
                                        white_actions[expansion_index])
                                )
                            root_index = len(root_branches)
                            root_states.append(root_state)
                            root_learning_eligible.append(
                                learning_path_eligible)
                            root_priorities.append(self.evaluate(root_state))
                            root_order_keys.append(
                                (expansion_index, branch_index))
                            root_branches.append({
                                "completed_depth": 0,
                                "completed_score": None,
                                "depth_action_scores": {},
                                "candidate_score": None,
                                "candidate_depth": 0,
                                "current_depth": 1,
                                "next_action": 0,
                                "root_alpha": -math.inf,
                                "in_flight": False,
                                "terminal": False,
                                "search_result_updates": [],
                                "root_action_results": [],
                            })
                            active_branches.add(root_index)
                            queue_branch(root_index)
                        self._record_ponder_progress(
                            white_actions_completed=1,
                            branches_generated=len(result),
                        )
                        update_depth_progress()
                        continue

                    (
                        _, _, root_index, search_depth, _, action,
                        root_key, root_alpha,
                    ) = task_info
                    total_nodes += result.nodes
                    self._add_completed_nodes(result.nodes)
                    self._merge_move_learning_updates(
                        getattr(result, "learning_updates", ()))
                    merge_result_entries(root_key, action, result.entries)
                    if result.score is None:
                        stopped_reason = "cancelled"
                        if worker_cancel_event is not None:
                            worker_cancel_event.set()
                        break

                    branch = root_branches[root_index]
                    branch["search_result_updates"].extend(
                        getattr(result, "search_result_updates", ()))
                    branch["root_action_results"].append((
                        action, result.score, result.bound, result.reliable))
                    if (
                        result.bound == Bound.UPPER
                        and result.reliable
                        and result.score < root_alpha
                    ):
                        pass
                    elif (
                        result.bound == Bound.EXACT
                        and result.reliable
                    ):
                        branch["root_alpha"] = max(
                            branch["root_alpha"], result.score)
                        branch["depth_action_scores"][action] = result.score
                    else:
                        raise RuntimeError(
                            "Ponder root action search returned an "
                            "unverified score")

                    self._record_ponder_progress(root_actions_completed=1)
                    branch["in_flight"] = False
                    _, _, actions = task_group_for(root_index)
                    if branch["next_action"] < len(actions):
                        queue_branch(root_index)
                    else:
                        branch["completed_depth"] = search_depth
                        branch["completed_score"] = branch["root_alpha"]
                        self._merge_search_result_updates(
                            branch["search_result_updates"])
                        branch["search_result_updates"] = []
                        if branch["depth_action_scores"]:
                            preferred_action = max(
                                branch["depth_action_scores"],
                                key=branch["depth_action_scores"].get,
                            )
                            best_score = branch["depth_action_scores"][
                                preferred_action]
                            root_state, _, _ = task_group_for(root_index)
                            self._record_best_search_result(
                                root_state,
                                preferred_action,
                                search_depth,
                                best_score,
                                task_group_search_position_keys[root_index],
                            )
                            for (
                                candidate_action,
                                candidate_score,
                                candidate_bound,
                                candidate_reliable,
                            ) in branch["root_action_results"]:
                                if (
                                    not candidate_reliable
                                    or candidate_action == preferred_action
                                ):
                                    continue
                                if (
                                    candidate_bound != Bound.EXACT
                                    or self._mover_relative_score(
                                        root_state, candidate_score)
                                    < self.config.learning_soft_cutoff_threshold
                                ):
                                    self._record_search_result(
                                        root_state,
                                        candidate_action,
                                        search_depth,
                                        candidate_score,
                                        candidate_bound,
                                        task_group_search_position_keys[root_index],
                                        kind="cutoff",
                                    )
                        if search_depth == 1 and branch["depth_action_scores"]:
                            preferred_action = max(
                                branch["depth_action_scores"],
                                key=branch["depth_action_scores"].get,
                            )
                            root_state, _, root_actions = task_group_for(
                                root_index)
                            self._record_move_learning(
                                root_state, preferred_action, "preferred",
                                root_learning_eligible[root_index])
                        if search_depth == 1:
                            branch["candidate_score"] = branch["root_alpha"]
                            branch["candidate_depth"] = 2
                            update_most_dangerous_white_moves()
                        root_state_key = task_groups[root_index][0]
                        with self._cache_lock:
                            if (
                                self._cache_generation == cache_generation
                                and self._cache is cache
                            ):
                                self._ponder_completed_depths[root_state_key] = max(
                                    search_depth,
                                    self._ponder_completed_depths.get(
                                        root_state_key, 0),
                                )
                        if search_depth >= self.config.max_depth:
                            active_branches.remove(root_index)
                        else:
                            branch["current_depth"] = search_depth + 1
                            branch["next_action"] = 0
                            branch["root_alpha"] = -math.inf
                            branch["depth_action_scores"] = {}
                            branch["root_action_results"] = []
                            queue_branch(root_index)
                        update_depth_progress()

                    if capacity_reached or cache_reset:
                        break

                if cancellation_event.is_set():
                    stopped_reason = "cancelled"
                if cache_reset or capacity_reached or stopped_reason != "max-depth":
                    if cache_reset:
                        stopped_reason = "cache-reset"
                    elif capacity_reached:
                        stopped_reason = "cache-full"
                    if worker_cancel_event is not None:
                        worker_cancel_event.set()
                    for future in pending:
                        future.cancel()
                    break

            if task_count == 0 and stopped_reason == "max-depth":
                stopped_reason = "no-legal-replies"
        except Exception:
            if worker_cancel_event is not None:
                worker_cancel_event.set()
            if executor is not None:
                self._discard_worker_pool(executor)
            raise
        finally:
            for future, task_info in sorted(
                pending.items(),
                key=lambda item: (
                    item[1][0], item[1][1]),
            ):
                if future.cancelled():
                    continue
                result = future.result()
                if task_info[0] == "search":
                    _, _, _, _, _, action, root_key, _ = task_info
                    total_nodes += result.nodes
                    self._add_completed_nodes(result.nodes)
                    if result.score is not None and result.reliable:
                        self._record_ponder_progress(root_actions_completed=1)
                    self._merge_move_learning_updates(
                        getattr(result, "learning_updates", ()))
                    merge_result_entries(root_key, action, result.entries)
            self._finish_search_progress()
            self._flush_move_learning_updates()
            self._flush_search_result_updates()
            with self._ponder_state_lock:
                if worker_cancel_event is not None:
                    worker_cancel_event.clear()
                self._ponder_active = False

        max_branch_depth = max(
            (branch["completed_depth"] for branch in root_branches),
            default=0,
        )
        log_info(
            "AI pondering finished: max_branch_depth={}, branches={}, "
            "root_actions={}, nodes={}, reason={}".format(
                max_branch_depth, len(root_states), task_count, total_nodes,
                stopped_reason)
        )
        return PonderResult(
            max_branch_depth, len(root_states), total_nodes, stopped_reason)

    def _ponder_worker_count_for_tasks(self, task_count):
        if not self.ponder_enabled or task_count <= 0:
            return 0
        return min(self.ponder_worker_count, task_count)

    @staticmethod
    def _states_after_player_turn(state: GameState, cancellation_event: Event):
        def continue_turn(current_state):
            if cancellation_event.is_set() or current_state.get_winner() is not None:
                return
            if current_state.current_turn != COLOR.WHITE:
                if current_state.current_turn == COLOR.BLACK:
                    yield current_state
                return
            for action in GameSimulation.available_actions(current_state):
                if cancellation_event.is_set():
                    return
                child = GameSimulation._apply_generated_action(
                    current_state, action)
                yield from continue_turn(child)

        return tuple(continue_turn(state))

    def _entries_for_root_scope(
        self, root_key, action, entries, cache_generation
    ):
        if not entries or self._cache is None:
            return entries
        with self._cache_lock:
            if self._cache_generation != cache_generation:
                return entries
            scope_id = self._cache.scope_id_for(root_key, action, create=True)
        return tuple(
            replace(
                entry,
                root_scope_ids=entry.root_scope_ids | frozenset((scope_id,)),
            )
            for entry in entries
        )

    def _worker_count_for_tasks(self, task_count):
        return min(self.search_worker_count, task_count)

    @staticmethod
    def _candidate_leader_index(completed_scores):
        if not completed_scores:
            return None
        return max(
            completed_scores,
            key=lambda index: (completed_scores[index], -index),
        )

    @staticmethod
    def _report_completed_candidate(
        actions, completed_scores, depth, callback, previous_leader=None
    ):
        if not completed_scores:
            return
        best_index = ChessAI._candidate_leader_index(completed_scores)
        if best_index != previous_leader:
            log_logic(
                "AI candidate leader at depth {}: {} => {:+.2f}".format(
                    depth, actions[best_index], completed_scores[best_index])
            )
        if callback is not None:
            callback(actions[best_index], depth, completed_scores[best_index])

    def _metric_start(self):
        return time.perf_counter_ns() if self._metrics is not None else None

    def _metric_finish(self, metric_name, started):
        if started is not None:
            self._metrics.add(metric_name, time.perf_counter_ns() - started)

    def _measure_search_call(
        self, elapsed_metric, calls_metric, function, *args
    ):
        started = self._metric_start()
        try:
            return function(*args)
        finally:
            if started is not None:
                self._metric_finish(elapsed_metric, started)
                self._metrics.add(calls_metric, 1)

    def _available_actions_for_search(self, state):
        if self._metrics is None:
            return GameSimulation.available_actions(state)
        actions = self._measure_search_call(
            "action_generation_ns", "action_generation_calls",
            GameSimulation.available_actions, state)
        self._metrics.add("generated_actions", len(actions))
        return actions

    def _order_actions_for_search(
        self, state, actions, learning_path_eligible=True
    ):
        previous = getattr(self, "_learning_ordering_allowed", True)
        self._learning_ordering_allowed = learning_path_eligible
        try:
            if self._metrics is None:
                return self._order_actions(state, actions)
            ordered = self._measure_search_call(
                "action_ordering_ns", "action_ordering_calls",
                self._order_actions, state, actions)
            self._metrics.add("actions_ordered", len(actions))
            return ordered
        finally:
            self._learning_ordering_allowed = previous

    def _apply_generated_action_for_search(self, state, action):
        if self._metrics is None:
            return GameSimulation._apply_generated_action(state, action)
        return self._measure_search_call(
            "action_application_ns", "action_application_calls",
            GameSimulation._apply_generated_action, state, action)

    def _evaluate_for_search(self, state):
        if self._metrics is None:
            return self.evaluate(state)
        return self._measure_search_call(
            "evaluation_ns", "evaluation_calls", self.evaluate, state)

    @staticmethod
    def _mover_relative_score(state, black_perspective_score):
        return (
            black_perspective_score
            if state.current_turn == COLOR.BLACK
            else -black_perspective_score
        )

    def _is_persistently_soft_cutoff(self, state, result):
        threshold = self.config.learning_soft_cutoff_threshold
        if result.bound == Bound.EXACT.value:
            return self._mover_relative_score(state, result.score) < threshold
        if state.current_turn == COLOR.BLACK:
            return (
                result.bound == Bound.UPPER.value
                and result.score < threshold
            )
        return (
            result.bound == Bound.LOWER.value
            and result.score > -threshold
        )

    @staticmethod
    def _search_result_at_depth(records, depth):
        matches = ChessAI._search_results_at_depth(records, depth)
        return next(
            (
                result for result in matches
                if result.kind == "best"
                and result.bound == Bound.EXACT.value
            ),
            matches[0] if matches else None,
        )

    @staticmethod
    def _search_results_at_depth(records, depth):
        matches = tuple(result for result in records if result.depth == depth)
        best = next(
            (result for result in matches if result.kind == "best"),
            None,
        )
        return (best,) if best is not None else matches

    def _order_actions_with_persistent_results(
        self, state, actions, results, depth,
    ):
        if not results:
            return actions
        original_order = {action: index for index, action in enumerate(actions)}
        current_results = {
            action: self._search_result_at_depth(records, depth)
            for action, records in results.items()
        }
        bad_actions = {
            action for action, result in current_results.items()
            if result is not None
            and self._is_persistently_soft_cutoff(state, result)
        }

        def action_key(action):
            records = results.get(action, ())
            result = current_results.get(action)
            if result is None and records:
                result = max(
                    records,
                    key=lambda item: (
                        item.depth,
                        item.kind == "best",
                        item.bound == Bound.EXACT.value,
                    ),
                )
            mover_score = (
                self._mover_relative_score(state, result.score)
                if result is not None else 0.0
            )
            return (
                action in bad_actions,
                -mover_score,
                original_order[action],
            )

        return sorted(actions, key=action_key)

    def _search(self, state: GameState, depth: int, alpha: float, beta: float) -> float:
        return self._search_with_proof(state, depth, alpha, beta)[0]

    def _search_with_proof(
        self, state: GameState, depth: int, alpha: float, beta: float,
        allow_lmr=True, learning_path_eligible=True,
    ):
        self._check_deadline()
        self._nodes += 1
        if self._metrics is not None:
            self._metrics.add("visited_nodes", 1)
        if (
            self._node_progress_callback is not None
            and self._nodes % _WORKER_NODE_UPDATE_INTERVAL == 0
        ):
            self._node_progress_callback(self._nodes)

        winner = state.get_winner()
        if winner is not None:
            return (100_000.0 if winner == COLOR.BLACK else -100_000.0), True
        if depth <= 0:
            return self._evaluate_for_search(state), True

        learning_path_eligible = (
                learning_path_eligible
                and getattr(self, "_initial_learning_path_eligible", True)
                and is_learning_position_eligible(state)
        )
        original_alpha, original_beta = alpha, beta
        key = None
        hint = None
        if self._cache is not None:
            started = self._metric_start()
            key = state.cache_key()
            self._metric_finish("cache_key_ns", started)
            if self._metrics is not None:
                self._metrics.add("cache_probes", 1)
            started = self._metric_start()
            entry = self._cache.get(key, depth)
            hint = self._cache.best_move(key)
            self._metric_finish("cache_lookup_ns", started)
            if entry is not None:
                self._cache_hits += 1
                if self._metrics is not None:
                    self._metrics.add("cache_hits", 1)
                if (
                    entry.bound == Bound.EXACT
                    or (entry.bound == Bound.LOWER and entry.score >= beta)
                    or (entry.bound == Bound.UPPER and entry.score <= alpha)
                ):
                    self._cache_score_hits += 1
                    if self._metrics is not None:
                        self._metrics.add("cache_score_hits", 1)
                    return entry.score, True

        actions = self._available_actions_for_search(state)
        if not actions:
            value = self._evaluate_for_search(state)
            if self._cache is not None:
                started = self._metric_start()
                self._cache.put(CacheEntry(key, depth, None, value, Bound.EXACT))
                self._metric_finish("cache_store_ns", started)
            return value, True
        persistent_position_key = self._persistent_search_position_key(
            state, key)
        persistent_results = self._persistent_search_results(
            state, actions, persistent_position_key)
        actions = self._order_actions_for_search(
            state, actions, learning_path_eligible)
        actions = self._order_actions_with_persistent_results(
            state, actions, persistent_results, depth)
        if hint in actions:
            actions.remove(hint)
            actions.insert(0, hint)
            self._cache_hints += 1
            if self._metrics is not None:
                self._metrics.add("cache_hints", 1)
        opposing_king_position = None
        king_threatened = False
        if _LMR_ENABLED and depth >= 3 and len(actions) > 3:
            opposing_color = (
                COLOR.WHITE if state.current_turn == COLOR.BLACK else COLOR.BLACK
            )
            opposing_king_position = self._king_position(state, opposing_color)
            current_king_position = self._king_position(state, state.current_turn)
            if current_king_position is not None:
                attack_map = ChessAI._attack_map(state)
                king_threatened = bool(
                    attack_map[opposing_color].get(current_king_position)
                )

        maximizing = state.current_turn == COLOR.BLACK
        current_depth_results = {
            action: self._search_results_at_depth(records, depth)
            for action, records in persistent_results.items()
        }
        bad_actions = {
            action for action, records in current_depth_results.items()
            if any(
                self._is_persistently_soft_cutoff(state, result)
                for result in records
            )
        }
        has_recommended_action = any(
            action not in bad_actions for action in actions)
        fallback_action = None
        if (
            not has_recommended_action
            and bad_actions
            and len(bad_actions) == len(actions)
        ):
            fallback_action = max(
                bad_actions,
                key=lambda action: self._mover_relative_score(
                    state,
                    max(
                        (
                            result.score
                            for result in current_depth_results[action]
                            if self._is_persistently_soft_cutoff(state, result)
                        ),
                        key=lambda score: self._mover_relative_score(
                            state, score),
                    ),
                ),
            )
        value = -math.inf if maximizing else math.inf
        best_action = None
        cutoff_action = None
        reliable = True
        completed_action_results = []
        for action_index, action in enumerate(actions):
            persisted_records = current_depth_results.get(action, ())
            soft_cutoff_result = next(
                (
                    result for result in persisted_records
                    if self._is_persistently_soft_cutoff(state, result)
                ),
                None,
            )
            if (
                soft_cutoff_result is not None
                and has_recommended_action
                and best_action is not None
                and self._mover_relative_score(state, value)
                >= self.config.learning_soft_cutoff_threshold
            ):
                continue
            if action == fallback_action:
                persisted_records = ()
            persisted_result = self._search_result_at_depth(
                persisted_records, depth)
            cutoff_result = None
            if (
                persisted_result is not None
                and persisted_result.bound == Bound.EXACT.value
                and (
                    persisted_result.kind == "best"
                    or (
                        not has_recommended_action
                        and action != fallback_action
                    )
                )
            ):
                action_value = persisted_result.score
                child_reliable = True
                completed_action_results.append(
                    (action, action_value, Bound.EXACT))
            else:
                skip_persisted_action = False
                for result in persisted_records:
                    if (
                        result.kind == "cutoff"
                        and (
                            (
                                maximizing
                                and result.bound == Bound.UPPER.value
                                and best_action is not None
                                and result.score <= alpha
                            )
                            or (
                                not maximizing
                                and result.bound == Bound.LOWER.value
                                and best_action is not None
                                and result.score >= beta
                            )
                        )
                    ):
                        skip_persisted_action = True
                        break
                    if (
                        result.kind == "cutoff"
                        and (
                            (
                                maximizing
                                and result.bound == Bound.LOWER.value
                                and result.score >= beta
                            )
                            or (
                                not maximizing
                                and result.bound == Bound.UPPER.value
                                and result.score <= alpha
                            )
                        )
                    ):
                        cutoff_result = result
                        break
                if skip_persisted_action:
                    continue
                if cutoff_result is not None:
                    action_value = cutoff_result.score
                    child_reliable = True
                    completed_action_results.append(
                        (action, action_value, Bound(cutoff_result.bound)))
                else:
                    persisted_result = None
            if persisted_result is None and cutoff_result is None:
                alpha_before, beta_before = alpha, beta
                child = self._apply_generated_action_for_search(state, action)
                child_learning_path_eligible = (
                    learning_path_eligible and is_plain_move(action))
                should_reduce = (
                    _LMR_ENABLED
                    and allow_lmr
                    and not king_threatened
                    and self._should_reduce_late_move(
                        state, action, depth, action_index)
                    and not self._move_attacks_king(
                        child, action, opposing_king_position)
                )
                if should_reduce:
                    if self._metrics is not None:
                        self._metrics.add("lmr_probes", 1)
                    action_value, child_reliable = self._search_with_proof(
                        child, depth - 2, alpha, beta, allow_lmr=allow_lmr,
                        learning_path_eligible=child_learning_path_eligible)
                    if (action_value > alpha if maximizing else action_value < beta):
                        if self._metrics is not None:
                            self._metrics.add("lmr_researches", 1)
                        action_value, child_reliable = self._search_with_proof(
                            child, depth - 1, alpha, beta, allow_lmr=allow_lmr,
                            learning_path_eligible=child_learning_path_eligible)
                    else:
                        # The reduced probe does not establish a full-depth bound.
                        child_reliable = False
                else:
                    action_value, child_reliable = self._search_with_proof(
                        child, depth - 1, alpha, beta, allow_lmr=allow_lmr,
                        learning_path_eligible=child_learning_path_eligible)
                if child_reliable:
                    action_bound = (
                        Bound.UPPER
                        if action_value <= alpha_before
                        else Bound.LOWER
                        if action_value >= beta_before
                        else Bound.EXACT
                    )
                    completed_action_results.append(
                        (action, action_value, action_bound))
            reliable = reliable and child_reliable
            if best_action is None or (
                action_value > value if maximizing else action_value < value
            ):
                value = action_value
                best_action = action
            if maximizing:
                alpha = max(alpha, value)
            else:
                beta = min(beta, value)
            if alpha >= beta:
                if self._metrics is not None:
                    self._metrics.add("alpha_beta_cutoffs", 1)
                cutoff_action = action
                break

        bound = None
        if reliable:
            if value <= original_alpha:
                bound = Bound.UPPER
            elif value >= original_beta:
                bound = Bound.LOWER
            else:
                bound = Bound.EXACT
        if bound == Bound.EXACT:
            self._record_best_search_result(
                state, best_action, depth, value, persistent_position_key)
        for action, action_value, action_bound in completed_action_results:
            if bound == Bound.EXACT and action == best_action:
                continue
            if (
                action_bound != Bound.EXACT
                or self._mover_relative_score(state, action_value)
                    < self.config.learning_soft_cutoff_threshold
            ):
                self._record_search_result(
                    state,
                    action,
                    depth,
                    action_value,
                    action_bound,
                    persistent_position_key,
                    kind="cutoff",
                )
        if (
            bound in (Bound.LOWER, Bound.UPPER)
            and cutoff_action is not None
        ):
            self._record_search_result(
                state,
                cutoff_action,
                depth,
                value,
                bound,
                persistent_position_key,
                kind="cutoff",
            )
        if bound == Bound.EXACT:
            self._record_move_learning(
                state, best_action, "preferred",
                learning_path_eligible)
        elif bound in (Bound.LOWER, Bound.UPPER) and cutoff_action is not None:
            self._record_move_learning(
                state, cutoff_action, "cutoff",
                learning_path_eligible)

        if self._cache is not None:
            started = self._metric_start()
            self._cache.put(CacheEntry(key, depth, best_action, value, bound))
            self._metric_finish("cache_store_ns", started)
        return value, reliable

    @staticmethod
    def _king_position(state, color):
        return next(
            (
                position
                for position, piece in state.pieces_locations.items()
                if piece.exists()
                and piece.get_color() == color
                and piece.get_type() == PIECE_TYPE.KING
            ),
            None,
        )

    @staticmethod
    def _move_attacks_king(state, action, opposing_king_position):
        if opposing_king_position is None:
            return False
        piece = state.pieces_locations[action.destination]
        return any(
            xy_to_id(*destination) == opposing_king_position
            for destination in GameSimulation.destinations_for(
                piece, action.destination, state.pieces_locations)
        )

    @staticmethod
    def _should_reduce_late_move(state, action, depth, action_index):
        if depth < 3 or action_index < 3:
            return False
        if action.action_type != GameActionType.MOVE or action.card_index != -1:
            return False

        piece = state.pieces_locations.get(action.source)
        target = state.pieces_locations.get(action.destination)
        if (
            piece is None
            or piece.get_type() == PIECE_TYPE.KING
            or not piece.can_receive_enchantment()
            or target is None
            or target.exists()
            or piece.get_effects(state.turns_started.get(piece.get_color(), 0))
        ):
            return False

        board_cards = state.board_cards or (
            [(state.board_card_position, state.board_enchantment)]
            if state.board_card_available and state.board_enchantment is not None
            else []
        )
        return not any(position == action.destination for position, _ in board_cards)

    @staticmethod
    def evaluate(state: GameState) -> float:
        """Ocenia materiał, ruchliwość, ogłuszenia, widoczne efekty i karty."""
        winner = state.get_winner()
        if winner is not None:
            return 100_000.0 if winner == COLOR.BLACK else -100_000.0

        score = 0.0
        basic_destinations = {}
        white_occupancy = 0
        black_occupancy = 0
        occupied = 0
        piece_values = []
        for position, piece in state.pieces_locations.items():
            if not piece.exists():
                continue
            bit = 1 << (position - 1)
            occupied |= bit
            color = piece.get_color()
            if color == COLOR.WHITE:
                white_occupancy |= bit
            elif color == COLOR.BLACK:
                black_occupancy |= bit
            sign = 1 if color == COLOR.BLACK else -1
            value = PIECE_VALUES[piece.get_type()]
            if piece.is_stunned():
                value *= 0.75
            value += 0.15 * len(piece.get_enchantments_to_alter_behavior())
            value -= 0.05 * sum(
                remaining or 0
                for _, _, remaining in piece.get_effects(
                    state.turns_started[color])
            )
            development = ChessAI._development_value(piece, position)
            piece_values.append((position, piece, sign, value, development))

        occupancy = BoardBitboards(
            white_occupancy, black_occupancy, occupied)
        for position, piece, sign, value, development in piece_values:
            score += sign * value
            score += sign * development
            if piece.can_receive_enchantment():
                destinations = GameSimulation.destinations_for(
                    piece, position, state.pieces_locations,
                    occupancy=occupancy)
                basic_destinations[position] = destinations
                mobility = len(destinations)
                score += sign * min(mobility, 12) * 0.025

        score += ChessAI._threat_score(
            state, basic_destinations, occupancy)

        for position, piece in state.pieces_locations.items():
            if (
                not piece.exists()
                or piece.get_type() != PIECE_TYPE.PAWN
                or not any(
                    enchantment.get_card_type() == EnchantmentCardType.PAWN_OFFICER
                    for enchantment in piece.get_passive_enchantments()
                )
            ):
                continue
            sign = 1 if piece.get_color() == COLOR.BLACK else -1
            score += sign * 0.25 * len(
                GameRules._officer_follower_positions(state, position, piece))

        for trap in state.rune_traps:
            opponent_color = (
                COLOR.WHITE if trap.owner == COLOR.BLACK else COLOR.BLACK)
            trap_x, trap_y = id_to_xy(trap.position)
            nearest_opponent = min(
                (
                    max(
                        abs(trap_x - id_to_xy(position)[0]),
                        abs(trap_y - id_to_xy(position)[1]),
                    )
                    for position, piece in state.pieces_locations.items()
                    if piece.exists() and piece.get_color() == opponent_color
                ),
                default=8,
            )
            sign = 1 if trap.owner == COLOR.BLACK else -1
            score += sign * max(0.0, 1.0 - nearest_opponent / 8) * 0.8

        for color in (COLOR.BLACK, COLOR.WHITE):
            sign = 1 if color == COLOR.BLACK else -1
            for card in state.get_cards_for(color):
                card_value = ChessAI._card_value(card)
                if card.is_reusable():
                    card_value *= min(1.0, card.get_remaining_uses() / 2)
                score += sign * card_value

        score += ChessAI._board_card_opportunity_score(state)
        return score

    @staticmethod
    def _card_value(card):
        card_type = card.get_card_type()
        if card_type.promoted_piece_type is not None:
            piece_value = PIECE_VALUES.get(card_type.piece_type, 0.0)
            upgrade_value = (
                PIECE_VALUES[card_type.promoted_piece_type] - piece_value
            )
            return max(0.0, upgrade_value * 0.45)
        return CARD_VALUES.get(card_type, 0.75)

    @staticmethod
    def _development_value(piece, position):
        piece_type = piece.get_type()
        x, y = id_to_xy(position)
        if piece_type in (PIECE_TYPE.KNIGHT, PIECE_TYPE.BISHOP):
            back_rank = 0 if piece.get_color() == COLOR.WHITE else 7
            progress = abs(y - back_rank)
            centrality = 3.5 - abs(x - 3.5)
            return min(progress, 3) * 0.07 + centrality * 0.035
        if piece_type == PIECE_TYPE.PAWN:
            progress = y if piece.get_color() == COLOR.WHITE else 7 - y
            return min(progress, 5) * 0.025
        return 0.0

    @staticmethod
    def _threat_score(state, basic_destinations=None, occupancy=None):
        """Penalizes valuable pieces that the opponent can capture next."""
        score = 0.0
        attack_map = ChessAI._attack_map(
            state, basic_destinations, occupancy)
        for target_position, target in state.pieces_locations.items():
            if not target.exists():
                continue
            attacker_color = (
                COLOR.BLACK if target.get_color() == COLOR.WHITE else COLOR.WHITE
            )
            attackers = attack_map[attacker_color].get(target_position, set())
            if not attackers:
                continue

            target_value = (
                80.0 if target.get_type() == PIECE_TYPE.KING
                else PIECE_VALUES[target.get_type()]
            )
            urgency = 0.75 if attacker_color == state.current_turn else 0.4
            exposure = min(1.0, 0.55 + 0.15 * (len(attackers) - 1))
            target_sign = 1 if target.get_color() == COLOR.BLACK else -1
            score -= target_sign * target_value * urgency * exposure
        return score

    @staticmethod
    def _attack_map(state, basic_destinations=None, occupancy=None):
        if occupancy is None:
            occupancy = BoardBitboards.from_locations(state.pieces_locations)
        attack_map = {COLOR.BLACK: {}, COLOR.WHITE: {}}
        for source, piece in state.pieces_locations.items():
            if not piece.exists() or not piece.can_receive_enchantment():
                continue
            color = piece.get_color()
            destinations = (
                basic_destinations[source]
                if basic_destinations is not None
                else GameSimulation.destinations_for(
                    piece, source, state.pieces_locations,
                    occupancy=occupancy)
            )
            ChessAI._record_attacks(attack_map[color], source, destinations)

            for card in state.get_cards_for(color):
                card_type = card.get_card_type()
                if (
                    card_type not in CARD_MOVEMENT_TYPES
                    or card_type.piece_type not in (PIECE_TYPE.EMPTY, piece.get_type())
                ):
                    continue
                card_destinations = GameSimulation.destinations_for(
                    piece, source, state.pieces_locations, card, occupancy)
                ChessAI._record_attacks(
                    attack_map[color],
                    source,
                    card_destinations,
                    rook_throw=(
                        card_type == EnchantmentCardType.ROOK_TOWER_THROW
                    ),
                )
        return attack_map

    @staticmethod
    def _record_attacks(attack_map, source, destinations, rook_throw=False):
        source_x, source_y = id_to_xy(source)
        for destination in destinations:
            target_x, target_y = destination
            if rook_throw:
                step_x = (target_x > source_x) - (target_x < source_x)
                step_y = (target_y > source_y) - (target_y < source_y)
                x, y = source_x + step_x, source_y + step_y
                while True:
                    position = xy_to_id(x, y)
                    attack_map.setdefault(position, set()).add(source)
                    if (x, y) == (target_x, target_y):
                        break
                    x += step_x
                    y += step_y
            else:
                position = xy_to_id(target_x, target_y)
                attack_map.setdefault(position, set()).add(source)

    @staticmethod
    def _board_card_opportunity_score(state):
        cards = state.board_cards or (
            [(state.board_card_position, state.board_enchantment)]
            if state.board_card_available and state.board_enchantment is not None
            else []
        )
        score = 0.0
        for card_position, enchantment in cards:
            x, y = id_to_xy(card_position)
            distances = {}
            for color in (COLOR.BLACK, COLOR.WHITE):
                eligible_distances = []
                for position, piece in state.pieces_locations.items():
                    if (
                        not piece.exists()
                        or piece.get_color() != color
                        or not piece.can_receive_enchantment()
                    ):
                        continue
                    piece_x, piece_y = id_to_xy(position)
                    eligible_distances.append(
                        max(abs(x - piece_x), abs(y - piece_y)))
                distances[color] = min(eligible_distances, default=8)

            card_value = ChessAI._card_value(enchantment)
            black_access = max(0.0, 1.0 - distances[COLOR.BLACK] / 8)
            white_access = max(0.0, 1.0 - distances[COLOR.WHITE] / 8)
            score += 0.3 * card_value * (black_access - white_access)
        return score

    def _order_actions(
        self, state, actions, learning_path_eligible=None
    ):
        if learning_path_eligible is None:
            learning_path_eligible = getattr(
                self, "_learning_ordering_allowed", True)
        maximizing = state.current_turn == COLOR.BLACK
        book_order = {
            move: index for index, move in enumerate(opening_hints(state))
        }
        learning_scores = (
            self._move_learning_action_scores(state, actions)
            if learning_path_eligible else {}
        )
        self._last_learning_hint_actions = frozenset(learning_scores)
        fallback_rank = len(book_order) + 1

        def action_order_key(action):
            score = self._quick_action_score(state, action)
            if state.current_turn == COLOR.WHITE:
                score = -score
            learning_score = learning_scores.get(action, 0.0)
            if not maximizing:
                learning_score = -learning_score
            move = (action.source, action.destination)
            rank = (
                book_order.get(move)
                if action.action_type == GameActionType.MOVE
                and action.card_index == -1
                else None
            )
            if rank is None:
                rank = fallback_rank
            return (
                score,
                learning_score,
                -rank if maximizing else rank,
            )

        return sorted(actions, key=action_order_key, reverse=maximizing)

    @staticmethod
    def _quick_action_score(state, action):
        score = 0.0
        target = state.pieces_locations.get(action.destination)
        if target is not None and target.exists():
            score += PIECE_VALUES[target.get_type()] * 1.5
        if action.promotion_type is not None:
            score += (
                PIECE_VALUES[action.promotion_type]
                - PIECE_VALUES[PIECE_TYPE.PAWN]
            )
        elif action.action_type == GameActionType.PROMOTE:
            score += 3
        elif action.action_type == GameActionType.RESURRECT:
            score += 2
        elif action.action_type == GameActionType.TELEPORT:
            score += 1
        elif action.action_type in (
            GameActionType.APPLY_PASSIVE,
            GameActionType.APPLY_BUFF,
        ):
            score += 0.5
        elif action.action_type == GameActionType.PLACE_RUNE:
            score += 0.75
        elif action.action_type == GameActionType.TREBUCHET:
            score += 0.5
        elif action.action_type == GameActionType.RECRUIT_PAWN:
            score += PIECE_VALUES[PIECE_TYPE.PAWN]

        if (
            action.card_index >= 0
            and action.card_index < len(state.get_cards_for(state.current_turn))
        ):
            card = state.get_cards_for(state.current_turn)[action.card_index]
            score += ChessAI._card_value(card)

        if target is not None and target.get_type() == PIECE_TYPE.KING:
            score += 100_000
        board_cards = state.board_cards or (
            [(state.board_card_position, state.board_enchantment)]
            if state.board_card_available and state.board_enchantment is not None
            else []
        )
        board_card = next(
            (card for card in board_cards if card[0] == action.destination),
            None,
        )
        if board_card is not None:
            score += ChessAI._card_value(board_card[1]) * 2
        if action.destination and action.source != action.destination:
            score += abs(action.destination - action.source) * 0.001
        return score

    def _check_deadline(self):
        if (
            _WORKER_SEARCH_CANCEL_EVENT is not None
            and _WORKER_SEARCH_CANCEL_EVENT.is_set()
        ):
            raise _SearchTimeout
        if time.monotonic() >= self._deadline:
            raise _SearchTimeout
        self._worker_usage_limiter.wait(
            self._deadline, _WORKER_SEARCH_CANCEL_EVENT)
