import argparse
import copy
import cProfile
import random
import statistics
import time
import tracemalloc
import pstats
from dataclasses import fields

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import ChessAI, SearchConfig
from logic.game_rules import GameActionType
from logic.game_simulation import GameSimulation
from models.ai_search_metrics import AISearchMetrics
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState
from models.starting_positions import pieces_starting_positions_map


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
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(),
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
    cache_enabled=False, metrics_enabled=True,
):
    observation = GameObservation.from_state(state, COLOR.BLACK)
    samples = []
    result_summary = None
    metric_samples = []
    for _ in range(repeats):
        ai = ChessAI(
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
            samples.append(time.perf_counter() - started)
            summary = (
                str(result.action),
                result.score,
                result.completed_depth,
                result.visited_nodes,
            )
            if result_summary is None:
                result_summary = summary
            elif summary != result_summary:
                raise RuntimeError("AI result changed during benchmark")
            if result.metrics is not None:
                metric_samples.append(result.metrics)
        finally:
            ai.shutdown_worker_pool()
    if result_summary is None:
        raise RuntimeError("AI search did not produce a benchmark result")
    metrics = None
    if metric_samples:
        metrics = AISearchMetrics(**{
            field.name: int(statistics.median(
                getattr(sample, field.name) for sample in metric_samples))
            for field in fields(AISearchMetrics)
        })
    return statistics.median(samples), result_summary, metrics


def _print_search_result(name, elapsed, summary, metrics):
    action, score, completed_depth, nodes = summary
    print(
        "{}: median_search_ms={:.3f} depth={} nodes={} score={:.2f} "
        "action={}".format(
            name, elapsed * 1000, completed_depth, nodes, score, action))
    if metrics is None:
        return
    wall_seconds = metrics.wall_time_ns / 1_000_000_000
    nodes_per_second = nodes / wall_seconds if wall_seconds > 0 else 0
    print(
        "{} profile: nodes/s={:.0f}, actions={} ({} calls, {:.2f}ms), "
        "ordering={} ({} calls, {:.2f}ms), apply={} calls ({:.2f}ms), "
        "evaluate={} calls ({:.2f}ms), cache={}/{}/{}, cutoffs={}, "
        "LMR={}/{}, workers={}, tasks={}, task_sum={:.2f}ms, "
        "pool_start={:.2f}ms, wait={:.2f}ms".format(
            name,
            nodes_per_second,
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
    ordinary = make_seeded_position(args.seed)
    card_position = make_card_position(ordinary)

    print(
        "seed={} plies=13 iterations={} repeats={} search_repeats={} "
        "workers={} budget_seconds={} metrics={}".format(
            args.seed,
            args.iterations,
            args.repeats,
            args.search_repeats,
            args.workers,
            args.budget_seconds,
            args.metrics,
        )
    )
    for name, state in (
        ("seeded-position", ordinary),
        ("movement-cards-and-effects", card_position),
    ):
        elapsed, count = measure_actions(
            state, args.iterations, args.repeats)
        print(
            "{}: actions={} median_action_generation_ms={:.3f}".format(
                name, count, elapsed * 1000 / args.iterations))

    for name, state, depth in (
        ("seeded-search", ordinary, 2),
        ("movement-card-search", card_position, 1),
    ):
        elapsed, summary, metrics = measure_search(
            state,
            depth,
            args.search_repeats,
            workers=args.workers,
            metrics_enabled=args.metrics == "on",
        )
        _print_search_result(name, elapsed, summary, metrics)

    if args.budget_seconds > 0:
        for name, state in (
            ("seeded-budget-search", ordinary),
            ("movement-card-budget-search", card_position),
        ):
            elapsed, summary, metrics = measure_search(
                state,
                depth=64,
                repeats=args.budget_repeats,
                time_limit_seconds=args.budget_seconds,
                workers=args.workers,
                cache_enabled=True,
                metrics_enabled=args.metrics == "on",
            )
            _print_search_result(name, elapsed, summary, metrics)


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic benchmark for move generation and AI search")
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--search-repeats", type=int, default=3)
    parser.add_argument("--budget-seconds", type=float, default=0)
    parser.add_argument("--budget-repeats", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
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
