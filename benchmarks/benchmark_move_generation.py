import argparse
import copy
import cProfile
import pstats
import random
import statistics
import time
import tracemalloc
from dataclasses import dataclass

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import ChessAI, SearchConfig, SearchResult
from logic.game_rules import GameActionType
from logic.game_simulation import GameSimulation
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState, RuneTrap
from models.starting_positions import pieces_starting_positions_map


@dataclass(frozen=True)
class SearchSample:
    elapsed_seconds: float
    result: SearchResult
    started_depth: int


class BenchmarkChessAI(ChessAI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_depth = 0

    def _set_current_search_depth(self, depth):
        self.started_depth = depth
        super()._set_current_search_depth(depth)


def make_seeded_position(seed, plies=13):
    state = GameState(
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
        random_state=random.Random(seed).getstate(),
    )
    for position, piece in pieces_starting_positions_map.items():
        state.pieces_locations[position.value] = copy.deepcopy(piece)

    chooser = random.Random(seed)
    for _ in range(plies):
        actions = [
            action for action in GameSimulation.available_actions(state)
            if action.action_type == GameActionType.MOVE and action.card_index == -1
        ]
        if not actions:
            raise RuntimeError("Seeded benchmark position ran out of moves")
        state = GameSimulation.apply(state, chooser.choice(actions))
    if state.current_turn != COLOR.BLACK:
        raise RuntimeError("The benchmark root must be black to move")
    return state


def make_card_position(state):
    state = state.clone()
    state.black_cards = [
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(uses=2),
        EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION.create(uses=2),
        EnchantmentCardType.ROOK_JUMP_ALLIES.create(),
    ]
    state.white_cards = [
        EnchantmentCardType.PAWN_SWORDSMAN.create(),
    ]
    black_pawns = [
        piece for piece in state.pieces_locations.values()
        if piece.exists()
        and piece.get_color() == COLOR.BLACK
        and piece.get_type() == PIECE_TYPE.PAWN
    ]
    if black_pawns:
        black_pawns[0].set_enchantment(
            EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD.create())
        black_pawns[0].set_enchantment(
            EnchantmentCardType.PAWN_SWORDSMAN.create())
    return state


def make_complex_card_position(state):
    state = make_card_position(state)
    state.black_cards.extend([
        EnchantmentCardType.PIECE_DOUBLE_MOVE.create(uses=2),
        EnchantmentCardType.ROOK_TOWER_THROW.create(),
    ])
    state.white_cards.extend([
        EnchantmentCardType.KNIGHT_RUNIC_TRAP.create(),
        EnchantmentCardType.ROOK_TOWER_THROW.create(),
    ])
    empty_positions = [
        position for position, piece in state.pieces_locations.items()
        if not piece.exists()
    ]
    if len(empty_positions) < 2:
        raise RuntimeError("The complex benchmark requires two empty squares")
    board_position, trap_position = empty_positions[:2]
    board_card = EnchantmentCardType.PIECE_TELEPORT.create()
    state.board_card_available = True
    state.board_card_position = board_position
    state.board_enchantment = board_card
    state.board_cards = [(board_position, board_card)]
    state.rune_traps.append(RuneTrap(
        trap_position,
        COLOR.WHITE,
        EnchantmentCardType.KNIGHT_RUNIC_TRAP.create(),
        placed_on_turn=state.turns_started[COLOR.WHITE],
    ))
    stunned_piece = next(
        (
            piece for piece in state.pieces_locations.values()
            if piece.exists()
            and piece.get_color() == COLOR.BLACK
            and piece.get_type() != PIECE_TYPE.KING
        ),
        None,
    )
    if stunned_piece is None:
        raise RuntimeError("The complex benchmark requires a black piece")
    stunned_piece.set_stunned_for_turns(2)
    return state


def measure_actions(state, iterations, repeats):
    samples = []
    action_count = None
    actions = []
    for _ in range(repeats):
        started = time.perf_counter()
        for _ in range(iterations):
            actions = GameSimulation.available_actions(state)
        samples.append(time.perf_counter() - started)
        if action_count is None:
            action_count = len(actions)
        elif action_count != len(actions):
            raise RuntimeError("Action generation changed during benchmark")
    return statistics.median(samples), action_count


def measure_search(
    state, depth, repeats, time_limit_seconds=120, workers=1,
    cache_enabled=False, metrics_enabled=True, strict_results=True,
):
    if repeats < 1:
        raise ValueError("Search repeats must be positive")
    observation = GameObservation.from_state(state, COLOR.BLACK)
    samples = []
    result_summary = None
    for _ in range(repeats):
        ai = BenchmarkChessAI(
            SearchConfig(
                time_limit_seconds=time_limit_seconds,
                max_depth=depth,
                cache_enabled=cache_enabled,
                metrics_enabled=metrics_enabled,
            ),
            max_workers=workers,
        )
        try:
            started = time.perf_counter()
            result = ai.choose_action(observation)
            elapsed = time.perf_counter() - started
            summary = (
                result.action,
                result.score,
                result.completed_depth,
                result.visited_nodes,
            )
            if result_summary is None:
                result_summary = summary
            elif strict_results and summary != result_summary:
                raise RuntimeError("AI result changed during benchmark")
            samples.append(SearchSample(elapsed, result, ai.started_depth))
        finally:
            ai.shutdown_worker_pool()
    return samples


def _print_search_result(name, samples):
    elapsed_samples = [sample.elapsed_seconds for sample in samples]
    rates = [
        sample.result.visited_nodes / sample.elapsed_seconds
        for sample in samples if sample.elapsed_seconds > 0
    ]
    print(
        "{}: repeats={} median_search_ms={:.3f} range_ms={:.3f}..{:.3f} "
        "median_nodes_per_second={:.0f}".format(
            name, len(samples), statistics.median(elapsed_samples) * 1000,
            min(elapsed_samples) * 1000, max(elapsed_samples) * 1000,
            statistics.median(rates) if rates else 0,
        )
    )
    for index, sample in enumerate(samples, 1):
        result = sample.result
        print(
            "{} sample={}: elapsed_ms={:.3f} depth={} started_depth={} "
            "nodes={} score={:.12g} action={}".format(
                name, index, sample.elapsed_seconds * 1000,
                result.completed_depth, sample.started_depth,
                result.visited_nodes, result.score, result.action,
            )
        )
        if result.metrics is not None:
            _print_search_metrics(name, index, result.metrics)


def _print_search_metrics(name, index, metrics):
    if metrics is None:
        return
    print(
        "{} sample={} profile: actions={} ({} calls, {:.2f}ms), "
        "ordering={} ({} calls, {:.2f}ms), apply={} calls ({:.2f}ms), "
        "evaluate={} calls ({:.2f}ms), cache={}/{}/{}, "
        "cache_key/lookup/store={:.2f}/{:.2f}/{:.2f}ms, hints={}, cutoffs={}, "
        "LMR={}/{}, workers={}, tasks={}, task_sum={:.2f}ms, "
        "pool_start={:.2f}ms, wait={:.2f}ms".format(
            name,
            index,
            metrics.generated_actions,
            metrics.action_generation_calls,
            metrics.action_generation_ns / 1_000_000,
            metrics.actions_ordered,
            metrics.action_ordering_calls,
            metrics.action_ordering_ns / 1_000_000,
            metrics.action_application_calls,
            metrics.action_application_ns / 1_000_000,
            metrics.evaluation_calls,
            metrics.evaluation_ns / 1_000_000,
            metrics.cache_probes,
            metrics.cache_hits,
            metrics.cache_score_hits,
            metrics.cache_key_ns / 1_000_000,
            metrics.cache_lookup_ns / 1_000_000,
            metrics.cache_store_ns / 1_000_000,
            metrics.cache_hints,
            metrics.alpha_beta_cutoffs,
            metrics.lmr_probes,
            metrics.lmr_researches,
            metrics.worker_count,
            metrics.worker_tasks,
            metrics.worker_task_ns / 1_000_000,
            metrics.worker_pool_startup_ns / 1_000_000,
            metrics.worker_wait_ns / 1_000_000,
        )
    )


def _run_benchmark(args):
    ordinary = make_seeded_position(args.seed, args.plies)
    card_position = make_card_position(ordinary)
    positions = [
        ("seeded-position", "seeded-search", ordinary, 2),
        ("movement-cards-and-effects", "movement-card-search", card_position, 1),
    ]
    if args.extended:
        positions.append((
            "complex-cards-and-effects", "complex-card-search",
            make_complex_card_position(ordinary), 1,
        ))

    fixed_cache = args.cache == "on"
    budget_cache = args.cache != "off"

    print(
        "seed={} plies={} iterations={} repeats={} search_repeats={} "
        "workers={} budget_seconds={} metrics={} fixed_cache={} "
        "budget_cache={} extended={}".format(
            args.seed,
            args.plies,
            args.iterations,
            args.repeats,
            args.search_repeats,
            args.workers,
            args.budget_seconds,
            args.metrics,
            fixed_cache,
            budget_cache,
            args.extended,
        )
    )
    for name, _, state, _ in positions:
        elapsed, count = measure_actions(
            state, args.iterations, args.repeats)
        print(
            "{}: actions={} median_action_generation_ms={:.3f}".format(
                name, count, elapsed * 1000 / args.iterations))

    for _, name, state, depth in positions:
        samples = measure_search(
            state,
            depth,
            args.search_repeats,
            workers=args.workers,
            cache_enabled=fixed_cache,
            metrics_enabled=args.metrics == "on",
            strict_results=args.workers == 1,
        )
        _print_search_result(name, samples)

    if args.budget_seconds > 0:
        for _, name, state, _ in positions:
            samples = measure_search(
                state,
                depth=64,
                repeats=args.budget_repeats,
                time_limit_seconds=args.budget_seconds,
                workers=args.workers,
                cache_enabled=budget_cache,
                metrics_enabled=args.metrics == "on",
                strict_results=False,
            )
            _print_search_result(name.replace("-search", "-budget-search"), samples)


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic benchmark for move generation and AI search")
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--plies", type=int, default=13)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--search-repeats", type=int, default=3)
    parser.add_argument("--budget-seconds", type=float, default=0)
    parser.add_argument("--budget-repeats", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--cache", choices=("auto", "on", "off"), default="auto",
        help="auto disables cache for fixed depth and enables it for timed runs",
    )
    parser.add_argument(
        "--extended", action="store_true",
        help="include a position with extra cards, a trap, and a stunned piece",
    )
    parser.add_argument(
        "--metrics",
        choices=("on", "off"),
        default="on",
        help="enable or disable timing instrumentation in benchmark searches",
    )
    profiling = parser.add_mutually_exclusive_group()
    profiling.add_argument("--profile", action="store_true")
    profiling.add_argument("--memory-profile", action="store_true")
    args = parser.parse_args()
    if (
        args.iterations < 1
        or args.repeats < 1
        or args.search_repeats < 1
        or args.budget_repeats < 1
    ):
        parser.error("iteration and repeat counts must be positive")
    if args.budget_seconds < 0:
        parser.error("--budget-seconds must not be negative")
    if args.plies < 1 or args.plies % 2 == 0:
        parser.error("--plies must be a positive odd number")
    if args.workers < 1:
        parser.error("--workers must be positive")
    if (args.profile or args.memory_profile) and args.budget_seconds:
        parser.error(
            "disable time-budget runs with --budget-seconds 0 while profiling")

    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        try:
            _run_benchmark(args)
        finally:
            profiler.disable()
        pstats.Stats(profiler).strip_dirs().sort_stats("cumtime").print_stats(30)
    elif args.memory_profile:
        tracemalloc.start()
        try:
            _run_benchmark(args)
            snapshot = tracemalloc.take_snapshot()
        finally:
            tracemalloc.stop()
        print("Top allocation sites:")
        for statistic in snapshot.statistics("lineno")[:20]:
            print(statistic)
    else:
        _run_benchmark(args)


if __name__ == "__main__":
    main()
