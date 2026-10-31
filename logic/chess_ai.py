import math
import os
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Optional

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import id_to_xy, xy_to_id
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from logic.search_cache import Bound, CacheEntry, SearchCache
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState
from utils.logging import (
    is_enabled,
    log_debug,
    log_error,
    log_info,
    log_logic,
    log_warn,
)
from utils.run_config import (
    AI_SEARCH_CPU_PERCENT,
    AI_SEARCH_CACHE_ENABLED,
    AI_SEARCH_CACHE_MAX_ENTRIES,
    AI_SEARCH_MAX_DEPTH,
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


@dataclass(frozen=True)
class SearchConfig:
    """Limity obliczeń dla jednego wyboru ruchu."""

    time_limit_seconds: float = AI_SEARCH_TIME_LIMIT_SECONDS
    max_depth: int = AI_SEARCH_MAX_DEPTH
    cache_enabled: bool = AI_SEARCH_CACHE_ENABLED
    cache_max_entries: int = AI_SEARCH_CACHE_MAX_ENTRIES

    def __post_init__(self):
        if self.time_limit_seconds <= 0:
            raise ValueError("The search time limit must be positive")
        if self.max_depth < 1:
            raise ValueError("The search depth must be at least one")
        if not isinstance(self.cache_enabled, bool):
            raise ValueError("The search cache setting must be a boolean")
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


class _SearchTimeout(Exception):
    pass


@dataclass(frozen=True)
class _RootEvaluation:
    score: Optional[float]
    nodes: int
    entries: tuple = ()
    hits: int = 0
    score_hits: int = 0
    hints: int = 0


def _evaluate_root_action(state, action, depth, config, deadline, cache_snapshot=()):
    """Ocenia jeden ruch startowy w izolowanym workerze."""
    worker = ChessAI(config, max_workers=1)
    worker._deadline = deadline
    worker._nodes = 0
    if worker._cache is not None:
        worker._cache = SearchCache(min(config.cache_max_entries, _WORKER_CACHE_LIMIT))
        for entry in cache_snapshot:
            worker._cache.put(entry, updated=False)
    try:
        worker._check_deadline()
        child = GameSimulation._apply_generated_action(state, action)
        score = worker._search(child, depth - 1, -math.inf, math.inf)
    except _SearchTimeout:
        score = None
    entries = (
        worker._cache.snapshot(_WORKER_CACHE_LIMIT, updated_only=True)
        if worker._cache is not None else ()
    )
    return _RootEvaluation(
        score, worker._nodes, entries, worker._cache_hits,
        worker._cache_score_hits, worker._cache_hints)


class ChessAI:
    """Wybiera akcje z perspektywy czarnych, znając ręce obu graczy."""

    def __init__(
        self,
        config: SearchConfig = SearchConfig(),
        max_workers: Optional[int] = None,
        cpu_percent: int = AI_SEARCH_CPU_PERCENT,
    ):
        if max_workers is not None and max_workers < 1:
            raise ValueError("The worker count must be at least one")
        if not 1 <= cpu_percent <= 100:
            raise ValueError("The CPU usage percentage must be between 1 and 100")
        self.config = config
        logical_cpu_count = os.cpu_count() or 1
        self.max_workers = (
            max_workers
            if max_workers is not None
            else max(1, logical_cpu_count * cpu_percent // 100)
        )
        self._deadline = 0.0
        self._nodes = 0
        self._cache = SearchCache(config.cache_max_entries) if config.cache_enabled else None
        self._cache_lock = Lock()
        self._cache_generation = 0
        self._cache_hits = 0
        self._cache_score_hits = 0
        self._cache_hints = 0

    def clear_search_cache(self):
        with self._cache_lock:
            self._cache_generation += 1
            if self._cache is not None:
                self._cache = SearchCache(self.config.cache_max_entries)

    def search_cache_generation(self):
        with self._cache_lock:
            return self._cache_generation

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

        state = observation.to_state()
        root_actions = GameSimulation.available_actions(state)
        if not root_actions:
            log_info("AI search found no legal actions")
            return SearchResult(None, self.evaluate(state), 0, 0)

        search_started = time.monotonic()
        self._deadline = search_started + self.config.time_limit_seconds
        self._nodes = 0
        self._cache_hits = self._cache_score_hits = self._cache_hints = 0
        ordered_actions = self._order_actions(state, root_actions)
        action_order = {
            action: index for index, action in enumerate(ordered_actions)
        }
        with self._cache_lock:
            if cache_generation is None:
                cache_generation = self._cache_generation
            hint = (
                self._cache.best_move(state.cache_key())
                if self._cache is not None
                and cache_generation == self._cache_generation else None
            )
        if hint in ordered_actions:
            ordered_actions.remove(hint)
            ordered_actions.insert(0, hint)
            self._cache_hints += 1
        best_action = ordered_actions[0]
        best_score = self.evaluate(
            GameSimulation._apply_generated_action(state, best_action))
        best_known_scores = {best_action: (best_score, 0)}
        completed_depth = 0
        if progress_callback is not None:
            progress_callback(best_action, completed_depth)
        if candidate_callback is not None:
            candidate_callback(best_action, completed_depth, best_score)

        worker_count = self._worker_count_for_tasks(len(ordered_actions))
        log_info(
            "AI search started: {} root actions, max_depth={}, time_limit={:.2f}s, "
            "workers={}".format(
                len(ordered_actions),
                self.config.max_depth,
                self.config.time_limit_seconds,
                worker_count,
            )
        )
        executor = (
            ProcessPoolExecutor(max_workers=worker_count)
            if worker_count > 1
            else None
        )
        interrupted = False
        try:
            for depth in range(1, self.config.max_depth + 1):
                if time.monotonic() >= self._deadline:
                    interrupted = True
                    break
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
                next_merge = 0

                def record_result(index, result):
                    nonlocal next_merge
                    self._nodes += result.nodes
                    self._cache_hits += result.hits
                    self._cache_score_hits += result.score_hits
                    self._cache_hints += result.hints
                    outcomes[index] = result
                    while next_merge in outcomes:
                        completed = outcomes.pop(next_merge)
                        if iteration_cache is not None:
                            for entry in completed.entries:
                                iteration_cache.put(entry)
                        next_merge += 1
                    if result.score is None:
                        return
                    if is_enabled("DEBUG"):
                        log_debug(
                            "AI root action at depth {}: {} => {:.2f} "
                            "({} nodes)".format(
                                depth, ordered_actions[index], result.score, result.nodes)
                        )
                    previous_leader = self._candidate_leader_index(completed_scores)
                    completed_scores[index] = result.score
                    best_known_scores[ordered_actions[index]] = (result.score, depth)
                    self._report_completed_candidate(
                        ordered_actions, completed_scores, depth,
                        candidate_callback, previous_leader)

                if executor is None:
                    for action_index, action in enumerate(ordered_actions):
                        try:
                            result = _evaluate_root_action(
                                state, action, depth, self.config, self._deadline,
                                snapshot)
                        except Exception as error:
                            log_error(
                                "AI root task failed for {} at depth {}: {}".format(
                                    action, depth, error)
                            )
                            raise
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
                            and len(pending) < worker_count
                            and next_action < next_merge + worker_count
                        ):
                            future = executor.submit(
                                _evaluate_root_action, state, ordered_actions[next_action],
                                depth, self.config, self._deadline, snapshot)
                            pending[future] = next_action
                            next_action += 1
                        if not pending:
                            break
                        remaining = max(0.0, self._deadline - time.monotonic())
                        done, _ = wait(
                            set(pending),
                            timeout=min(0.05, remaining),
                            return_when=FIRST_COMPLETED,
                        )
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
                        executor.shutdown(wait=True, cancel_futures=True)
                        executor = None
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
                        for entry in outcomes[index].entries:
                            iteration_cache.put(entry)
                    with self._cache_lock:
                        if self._cache_generation == cache_generation:
                            for entry in iteration_cache.snapshot(self.config.cache_max_entries):
                                self._cache.put(entry)
                if len(completed_scores) != len(ordered_actions):
                    interrupted = True
                    break
                depth_scores = [
                    (completed_scores[index], action)
                    for index, action in enumerate(ordered_actions)
                ]

                best_score, best_action = max(
                    depth_scores,
                    key=lambda item: (item[0], -action_order[item[1]]))
                completed_depth = depth
                log_logic(
                    "AI search completed depth {}: best action={}, score={:+.2f}".format(
                        depth, best_action, best_score)
                )
                if progress_callback is not None:
                    progress_callback(best_action, completed_depth)
                if candidate_callback is not None:
                    candidate_callback(best_action, completed_depth, best_score)
                ordered_actions = [
                    action
                    for _, action in sorted(
                        depth_scores,
                        key=lambda item: (item[0], -action_order[item[1]]),
                        reverse=True)
                ]
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)

        best_action = max(
            best_known_scores,
            key=lambda action: (
                best_known_scores[action][0],
                -action_order[action],
            ),
        )
        best_score, best_action_depth = best_known_scores[best_action]
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
        return SearchResult(best_action, best_score, completed_depth, self._nodes)

    def _worker_count_for_tasks(self, task_count):
        return min(self.max_workers, task_count)

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

    def _search(self, state: GameState, depth: int, alpha: float, beta: float) -> float:
        return self._search_with_proof(state, depth, alpha, beta)[0]

    def _search_with_proof(
        self, state: GameState, depth: int, alpha: float, beta: float
    ):
        self._check_deadline()
        self._nodes += 1

        winner = state.get_winner()
        if winner is not None:
            return (100_000.0 if winner == COLOR.BLACK else -100_000.0), True
        if depth <= 0:
            return self.evaluate(state), True

        original_alpha, original_beta = alpha, beta
        key = state.cache_key() if self._cache is not None else None
        hint = None
        if self._cache is not None:
            entry = self._cache.get(key, depth)
            hint = self._cache.best_move(key)
            if entry is not None:
                self._cache_hits += 1
                if (
                    entry.bound == Bound.EXACT
                    or (entry.bound == Bound.LOWER and entry.score >= beta)
                    or (entry.bound == Bound.UPPER and entry.score <= alpha)
                ):
                    self._cache_score_hits += 1
                    return entry.score, True

        actions = GameSimulation.available_actions(state)
        if not actions:
            value = self.evaluate(state)
            if self._cache is not None:
                self._cache.put(CacheEntry(key, depth, None, value, Bound.EXACT))
            return value, True
        actions = self._order_actions(state, actions)
        if hint in actions:
            actions.remove(hint)
            actions.insert(0, hint)
            self._cache_hints += 1
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
        value = -math.inf if maximizing else math.inf
        best_action = None
        reliable = True
        for action_index, action in enumerate(actions):
            child = GameSimulation._apply_generated_action(state, action)
            if (
                _LMR_ENABLED
                and not king_threatened
                and self._should_reduce_late_move(
                    state, action, depth, action_index)
                and not self._move_attacks_king(
                    child, action, opposing_king_position)
            ):
                action_value, child_reliable = self._search_with_proof(
                    child, depth - 2, alpha, beta)
                if (action_value > alpha if maximizing else action_value < beta):
                    action_value, child_reliable = self._search_with_proof(
                        child, depth - 1, alpha, beta)
                else:
                    # The reduced probe does not establish a full-depth bound.
                    child_reliable = False
            else:
                action_value, child_reliable = self._search_with_proof(
                    child, depth - 1, alpha, beta)
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
                break

        if self._cache is not None:
            bound = None
            if reliable:
                if value <= original_alpha:
                    bound = Bound.UPPER
                elif value >= original_beta:
                    bound = Bound.LOWER
                else:
                    bound = Bound.EXACT
            self._cache.put(CacheEntry(key, depth, best_action, value, bound))
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
        for position, piece in state.pieces_locations.items():
            if not piece.exists():
                continue
            sign = 1 if piece.get_color() == COLOR.BLACK else -1
            value = PIECE_VALUES[piece.get_type()]
            if piece.is_stunned():
                value *= 0.75
            value += 0.15 * len(piece.get_enchantments_to_alter_behavior())
            value -= 0.05 * sum(
                remaining or 0
                for _, _, remaining in piece.get_effects(
                    state.turns_started[piece.get_color()])
            )
            score += sign * value
            score += sign * ChessAI._development_value(piece, position)

            if piece.can_receive_enchantment():
                destinations = GameSimulation.destinations_for(
                    piece, position, state.pieces_locations)
                basic_destinations[position] = destinations
                mobility = len(destinations)
                score += sign * min(mobility, 12) * 0.025

        score += ChessAI._threat_score(state, basic_destinations)

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
    def _threat_score(state, basic_destinations=None):
        """Penalizes valuable pieces that the opponent can capture next."""
        score = 0.0
        attack_map = ChessAI._attack_map(state, basic_destinations)
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
    def _attack_map(state, basic_destinations=None):
        attack_map = {COLOR.BLACK: {}, COLOR.WHITE: {}}
        for source, piece in state.pieces_locations.items():
            if not piece.exists() or not piece.can_receive_enchantment():
                continue
            color = piece.get_color()
            destinations = (
                basic_destinations[source]
                if basic_destinations is not None
                else GameSimulation.destinations_for(
                    piece, source, state.pieces_locations)
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
                    piece, source, state.pieces_locations, card)
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

    def _order_actions(self, state, actions):
        return sorted(
            actions,
            key=lambda action: self._quick_action_score(state, action),
            reverse=state.current_turn == COLOR.BLACK,
        )

    @staticmethod
    def _quick_action_score(state, action):
        score = 0.0
        target = state.pieces_locations.get(action.destination)
        if target is not None and target.exists():
            score += PIECE_VALUES[target.get_type()] * 1.5
        if action.action_type == GameActionType.PROMOTE:
            score += 3
        elif action.action_type == GameActionType.RESURRECT:
            score += 2
        elif action.action_type == GameActionType.TELEPORT:
            score += 1
        elif action.action_type == GameActionType.APPLY_PASSIVE:
            score += 0.5

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
        if time.monotonic() >= self._deadline:
            raise _SearchTimeout
