import argparse
import ctypes
import json
import os
import pickle
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

from benchmarks.benchmark_move_generation import (
    BenchmarkChessAI,
    make_card_position,
    make_complex_card_position,
    make_seeded_position,
)
from constants.piece_color import COLOR
import logic.chess_ai as chess_ai
from logic.chess_ai import SearchConfig
from logic.game_simulation import GameSimulation
from logic.opening_book import _OPENING_BOOK
from logic.search_cache import Bound
from models.game_observation import GameObservation
from utils.logging import LogLevel
import utils.logging as logging


_DEFAULT_WORKER_CACHE = 256
_WIN_PROCESS_MEMORY = None


def parse_cache_limit(value):
    multipliers = {"k": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
    multiplier = multipliers.get(value[-1:], 1)
    if multiplier != 1:
        value = value[:-1]
    limit = int(value) * multiplier
    if limit < 1:
        raise ValueError("Cache limits must be positive")
    return limit


def cache_profiles(main_limits, worker_limits):
    if not main_limits or not worker_limits:
        raise ValueError("At least one main and worker cache limit is required")
    if any(limit < 1 for limit in main_limits + worker_limits):
        raise ValueError("Cache limits must be positive")

    profiles = [("off", 0, _DEFAULT_WORKER_CACHE)]
    profiles.append(("baseline", main_limits[0], worker_limits[0]))
    profiles.extend(
        ("main-{}".format(limit), limit, worker_limits[0])
        for limit in main_limits[1:]
    )
    profiles.extend(
        ("worker-{}".format(limit), main_limits[0], limit)
        for limit in worker_limits[1:]
    )
    unique = {}
    for profile in profiles:
        unique[(profile[1], profile[2])] = profile
    return tuple(unique.values())


def board_signature(state):
    return (
        state.current_turn,
        tuple(
            (position, piece.get_color(), piece.get_type(), piece.has_moved())
            for position, piece in sorted(state.pieces_locations.items())
            if piece.exists()
        ),
    )


def recurrence_summary(records):
    exact_groups = {}
    board_groups = {}
    for index, record in enumerate(records):
        record.setdefault("trajectory_id", "record-{}".format(index))
        exact_groups.setdefault(record["key"], []).append(record)
        board_groups.setdefault(record["board"], []).append(record)

    exact_duplicates = [
        group for group in exact_groups.values() if len(group) > 1
    ]
    board_duplicates = [
        group for group in board_groups.values() if len(group) > 1
    ]
    ambiguous_board_groups = [
        group for group in board_duplicates
        if len({record["key"] for record in group}) > 1
    ]
    exact_cross_trajectory_groups = [
        group for group in exact_duplicates
        if len({record["trajectory_id"] for record in group}) > 1
    ]
    board_cross_trajectory_groups = [
        group for group in board_duplicates
        if len({record["trajectory_id"] for record in group}) > 1
    ]
    return {
        "state_records": len(records),
        "exact_unique_states": len(exact_groups),
        "exact_duplicate_groups": len(exact_duplicates),
        "exact_repeat_records": sum(
            len(group) - 1 for group in exact_duplicates),
        "exact_groups_repeated_across_trajectories": len(
            exact_cross_trajectory_groups),
        "board_unique_positions": len(board_groups),
        "board_duplicate_groups": len(board_duplicates),
        "board_groups_repeated_across_trajectories": len(
            board_cross_trajectory_groups),
        "board_repeat_records": sum(
            len(group) - 1 for group in board_duplicates),
        "board_groups_with_distinct_full_states": len(ambiguous_board_groups),
        "board_only_collision_pairs": sum(
            len(group) * (len(group) - 1) // 2
            - sum(
                count * (count - 1) // 2
                for count in Counter(record["key"] for record in group).values()
            )
            for group in ambiguous_board_groups
        ),
    }


def _process_memory_api():
    global _WIN_PROCESS_MEMORY
    if os.name != "nt":
        return None
    if _WIN_PROCESS_MEMORY is not None:
        return _WIN_PROCESS_MEMORY

    from ctypes import wintypes

    size_t = ctypes.c_size_t

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", size_t),
            ("WorkingSetSize", size_t),
            ("QuotaPeakPagedPoolUsage", size_t),
            ("QuotaPagedPoolUsage", size_t),
            ("QuotaPeakNonPagedPoolUsage", size_t),
            ("QuotaNonPagedPoolUsage", size_t),
            ("PagefileUsage", size_t),
            ("PeakPagefileUsage", size_t),
            ("PrivateUsage", size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    _WIN_PROCESS_MEMORY = (
        kernel32, psapi, ProcessMemoryCounters,
        0x0400 | 0x0010,  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    )
    return _WIN_PROCESS_MEMORY


def process_memory_bytes(process_id):
    api = _process_memory_api()
    if api is None:
        return None
    kernel32, psapi, counters_type, access = api
    handle = kernel32.OpenProcess(access, False, process_id)
    if not handle:
        return None
    try:
        counters = counters_type()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            return None
        return counters.PrivateUsage, counters.WorkingSetSize
    finally:
        kernel32.CloseHandle(handle)


class ProcessMemorySampler:
    def __init__(self, ai, interval=0.1):
        self.ai = ai
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample_until_stopped)
        self._samples = []

    @staticmethod
    def _worker_process_ids(ai):
        pool = getattr(ai, "_worker_pool", None)
        processes = getattr(pool, "_processes", None) or {}
        return [
            process.pid for process in processes.values()
            if process.pid is not None
        ]

    def sample(self):
        if os.name != "nt":
            return
        process_ids = [os.getpid(), *self._worker_process_ids(self.ai)]
        values = [
            value for process_id in set(process_ids)
            if (value := process_memory_bytes(process_id)) is not None
        ]
        if values:
            self._samples.append((
                len(values), sum(value[0] for value in values),
                sum(value[1] for value in values)))

    def _sample_until_stopped(self):
        while not self._stop.is_set():
            self.sample()
            self._stop.wait(self.interval)

    def start(self):
        self.sample()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()
        self.sample()

    def result(self):
        if not self._samples:
            return {
                "process_memory_available": False,
                "process_private_bytes_peak": None,
                "process_private_bytes_growth": None,
                "process_working_set_bytes_peak": None,
                "process_working_set_bytes_growth": None,
                "sampled_processes_peak": 0,
            }
        private_bytes = [private for _, private, _ in self._samples]
        working_set_bytes = [working for _, _, working in self._samples]
        return {
            "process_memory_available": True,
            "process_private_bytes_peak": max(private_bytes),
            "process_private_bytes_growth": (
                max(private_bytes) - private_bytes[0]),
            "process_working_set_bytes_peak": max(working_set_bytes),
            "process_working_set_bytes_growth": (
                max(working_set_bytes) - working_set_bytes[0]),
            "sampled_processes_peak": max(
                count for count, _, _ in self._samples),
        }


def run_search(state, profile, budget, max_depth, workers, worker_cache_limit):
    name, main_limit, _ = profile
    cache_enabled = main_limit > 0
    config = SearchConfig(
        time_limit_seconds=budget,
        max_depth=max_depth,
        cache_enabled=cache_enabled,
        cache_max_entries=main_limit if cache_enabled else 1,
        metrics_enabled=True,
    )
    ai = BenchmarkChessAI(config, max_workers=workers)
    sampler = ProcessMemorySampler(ai)
    result = None
    started = time.perf_counter()
    previous_limit = chess_ai._WORKER_CACHE_LIMIT
    try:
        chess_ai._WORKER_CACHE_LIMIT = worker_cache_limit
        sampler.start()
        result = ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))
        elapsed = time.perf_counter() - started
    finally:
        sampler.stop()
        chess_ai._WORKER_CACHE_LIMIT = previous_limit
        memory = sampler.result()
        cache = ai._cache
        cache_entries = len(cache) if cache is not None else 0
        cache_evictions = cache.evictions if cache is not None else 0
        snapshot = cache.snapshot(config.cache_max_entries) if cache else ()
        ai.shutdown_worker_pool()

    metrics = result.metrics
    return {
        "case": None,
        "profile": name,
        "main_cache_limit": main_limit,
        "worker_cache_limit": worker_cache_limit,
        "worker_limit_applies_to_local_table": workers == 1,
        "workers": workers,
        "elapsed_seconds": elapsed,
        "completed_depth": result.completed_depth,
        "started_depth": ai.started_depth,
        "nodes": result.visited_nodes,
        "nodes_per_second": result.visited_nodes / elapsed,
        "score": result.score,
        "action": str(result.action),
        "cache_entries": cache_entries,
        "cache_evictions": cache_evictions,
        "cache_probes": metrics.cache_probes if metrics else 0,
        "cache_hits": metrics.cache_hits if metrics else 0,
        "cache_score_hits": metrics.cache_score_hits if metrics else 0,
        "cache_hints": metrics.cache_hints if metrics else 0,
        "exact_deep_entries": sum(
            entry.bound == Bound.EXACT and entry.depth >= 3
            for entry in snapshot
        ),
        **memory,
    }


def make_trajectory(
    seed, move_seed, plies, base_plies, base_seed=20261116,
    trajectory_id=None,
):
    state = make_seeded_position(base_seed, base_plies)
    state.random_state = random.Random(seed).getstate()
    chooser = random.Random(move_seed)
    records = []
    if trajectory_id is None:
        trajectory_id = "trajectory-{}".format(id(records))
    for _ in range(plies + 1):
        records.append({
            "key": state.cache_key(),
            "board": board_signature(state),
            "trajectory_id": trajectory_id,
        })
        if state.get_winner() is not None:
            break
        actions = GameSimulation.available_actions(state)
        if not actions:
            break
        state = GameSimulation.apply(
            state, chooser.choice(actions), advance_board_card_clock=False)
    return records


def measure_recurrence(seed, base_plies, history_plies, game_count):
    replay_records = []
    replay_seed = seed + 100_000
    for replay in range(2):
        replay_records.extend(make_trajectory(
            replay_seed, 1, history_plies, base_plies, seed,
            "same-seed-replay-{}".format(replay + 1)))
    distinct_game_records = []
    distinct_post_move_records = []
    for game_index in range(game_count):
        game_seed = seed + 200_000 + game_index
        move_seed = seed + game_index
        trajectory = make_trajectory(
            game_seed, move_seed, history_plies, base_plies, seed,
            "game-{}".format(game_index + 1))
        distinct_game_records.extend(trajectory)
        distinct_post_move_records.extend(trajectory[1:])

    baseline = make_seeded_position(seed, base_plies)
    card_variant = make_card_position(baseline)
    complex_variant = make_complex_card_position(baseline)
    comparison = {
        "same_board_different_cards": (
            board_signature(baseline) == board_signature(card_variant)
            and baseline.cache_key() != card_variant.cache_key()
        ),
        "same_board_different_effects_or_traps": (
            board_signature(card_variant) == board_signature(complex_variant)
            and card_variant.cache_key() != complex_variant.cache_key()
        ),
        "same_board_different_rng": (
            board_signature(baseline)
            == board_signature(_with_random_state(baseline, seed + 1))
            and baseline.cache_key()
            != _with_random_state(baseline, seed + 1).cache_key()
        ),
    }
    return {
        "same_seed_replays": recurrence_summary(replay_records),
        "distinct_games": recurrence_summary(distinct_game_records),
        "distinct_games_after_first_move": recurrence_summary(
            distinct_post_move_records),
        "field_comparisons": comparison,
    }


def _with_random_state(state, seed):
    cloned = state.clone()
    cloned.random_state = random.Random(seed).getstate()
    return cloned


def qualifying_entries(entries, minimum_depth):
    return tuple(
        entry for entry in entries
        if entry.bound == Bound.EXACT and entry.depth >= minimum_depth
    )


def _measure_pickle_roundtrip(payload, directory=None, repeats=5):
    encoded = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    write_samples = []
    read_samples = []
    roundtrip_equal = True
    for _ in range(repeats):
        with tempfile.NamedTemporaryFile(dir=directory) as file:
            write_started = time.perf_counter()
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
            write_samples.append(time.perf_counter() - write_started)
            file.seek(0)
            read_started = time.perf_counter()
            restored = pickle.load(file)
            read_samples.append(time.perf_counter() - read_started)
            roundtrip_equal = roundtrip_equal and restored == payload
    return {
        "entries": len(payload),
        "bytes": len(encoded),
        "write_seconds_median": statistics.median(write_samples),
        "write_seconds_range": [min(write_samples), max(write_samples)],
        "read_seconds_median": statistics.median(read_samples),
        "read_seconds_range": [min(read_samples), max(read_samples)],
        "roundtrip_equal": roundtrip_equal,
    }


def measure_disk_cache(
    seed, plies, workers, cache_limit, budget, disk_repeats=5, directory=None,
):
    positions = [
        ("ordinary", make_seeded_position(seed, plies)),
        ("cards", make_card_position(make_seeded_position(seed, plies))),
        ("complex", make_complex_card_position(
            make_seeded_position(seed, plies))),
    ]
    output = []
    for case, state in positions:
        config = SearchConfig(
            time_limit_seconds=budget,
            max_depth=64,
            cache_enabled=True,
            cache_max_entries=cache_limit,
            metrics_enabled=False,
        )
        ai = BenchmarkChessAI(config, max_workers=workers)
        try:
            result = ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))
            if result.completed_depth < 1:
                raise RuntimeError(
                    "Disk cache sample did not finish depth 1: " + case)
            entries = ai._cache.snapshot(cache_limit)
        finally:
            ai.shutdown_worker_pool()
        minimum_depth = max(1, result.completed_depth - 1)
        selected = qualifying_entries(entries, minimum_depth=minimum_depth)
        output.append({
            "case": case,
            "completed_depth": result.completed_depth,
            "cache_entries": len(entries),
            "exact_entry_minimum_depth": minimum_depth,
            "exact_entries_at_minimum_depth_or_deeper": len(selected),
            "full_snapshot": _measure_pickle_roundtrip(
                entries, directory, repeats=disk_repeats),
            "selected_exact_snapshot": _measure_pickle_roundtrip(
                selected, directory, repeats=disk_repeats),
        })

    opening_book = tuple(_OPENING_BOOK.items())
    output.append({
        "case": "existing_classic_opening_hints",
        "positions": len(opening_book),
        "roundtrip": _measure_pickle_roundtrip(
            opening_book, directory, repeats=disk_repeats),
    })
    return output


def _median(values):
    return statistics.median(values) if values else None


def _run_isolated_capacity_sample(args, case, profile):
    command = [
        sys.executable,
        "-m",
        "benchmarks.benchmark_search_cache",
        "--sample-case", case,
        "--sample-profile", profile[0],
        "--sample-main-limit", str(profile[1]),
        "--sample-worker-limit", str(profile[2]),
        "--seed", str(args.seed),
        "--plies", str(args.plies),
        "--budget", str(args.budget),
        "--workers", str(args.workers),
    ]
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True, cwd=Path.cwd())
    sample_lines = [
        line[6:] for line in completed.stdout.splitlines()
        if line.startswith("BENCH ")
    ]
    if len(sample_lines) != 1:
        raise RuntimeError(
            "Isolated benchmark returned {} samples: {}".format(
                len(sample_lines), completed.stdout))
    return json.loads(sample_lines[0])


def run_capacity_benchmarks(args):
    cases = ("ordinary", "cards", "complex")
    profiles = cache_profiles(args.main_limits, args.worker_limits)
    for case in cases:
        rows = []
        for repeat in range(args.repeats):
            order = list(profiles)
            random.Random(args.seed + repeat).shuffle(order)
            for profile in order:
                row = _run_isolated_capacity_sample(args, case, profile)
                row["case"] = case
                row["repeat"] = repeat + 1
                rows.append(row)
                print("BENCH " + json.dumps(row), flush=True)

        summaries = {}
        for profile in profiles:
            samples = [
                row for row in rows if row["profile"] == profile[0]
            ]
            summaries[profile[0]] = {
                "median_elapsed_seconds": _median(
                    [row["elapsed_seconds"] for row in samples]),
                "median_nodes_per_second": _median(
                    [row["nodes_per_second"] for row in samples]),
                "median_completed_depth": _median(
                    [row["completed_depth"] for row in samples]),
                "median_cache_hits": _median(
                    [row["cache_hits"] for row in samples]),
                "median_score_hits": _median(
                    [row["cache_score_hits"] for row in samples]),
                "median_cache_evictions": _median(
                    [row["cache_evictions"] for row in samples]),
                "median_cache_entries": _median(
                    [row["cache_entries"] for row in samples]),
                "median_exact_deep_entries": _median(
                    [row["exact_deep_entries"] for row in samples]),
                "median_private_bytes_growth": _median(
                    [
                        row["process_private_bytes_growth"]
                        for row in samples
                        if row["process_private_bytes_growth"] is not None
                    ]),
                "median_working_set_bytes_growth": _median(
                    [
                        row["process_working_set_bytes_growth"]
                        for row in samples
                        if row["process_working_set_bytes_growth"] is not None
                    ]),
            }
        print("SUMMARY " + json.dumps({
            "case": case,
            "seed": args.seed,
            "summaries": summaries,
        }), flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Measure search cache capacity, state recurrence, and disk cost")
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--plies", type=int, default=13)
    parser.add_argument("--history-plies", type=int, default=24)
    parser.add_argument("--game-count", type=int, default=8)
    parser.add_argument("--budget", type=float, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--disk-repeats", type=int, default=5)
    parser.add_argument(
        "--main-limits", nargs="+", type=parse_cache_limit,
        default=[6144, 16384, 65536],
    )
    parser.add_argument(
        "--worker-limits", nargs="+", type=parse_cache_limit,
        default=[256, 64, 128],
    )
    parser.add_argument(
        "--only",
        choices=("all", "capacity", "recurrence", "disk"),
        default="all",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sample-case", choices=("ordinary", "cards", "complex"),
                        help=argparse.SUPPRESS)
    parser.add_argument("--sample-profile", help=argparse.SUPPRESS)
    parser.add_argument("--sample-main-limit", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--sample-worker-limit", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.plies < 1 or args.plies % 2 == 0:
        parser.error("--plies must be a positive odd number")
    if args.history_plies < 1 or args.game_count < 1:
        parser.error("history length and game count must be positive")
    if (
        args.budget <= 0 or args.repeats < 1 or args.workers < 1
        or args.disk_repeats < 1
    ):
        parser.error("budget, repeats, workers, and disk repeats must be positive")

    logging.LOG_LEVEL = LogLevel.OFF
    if args.sample_case is not None:
        if (
            args.sample_profile is None
            or args.sample_main_limit is None
            or args.sample_worker_limit is None
        ):
            parser.error("isolated sample requires a complete profile")
        base = make_seeded_position(args.seed, args.plies)
        state = (
            base if args.sample_case == "ordinary"
            else make_card_position(base) if args.sample_case == "cards"
            else make_complex_card_position(base)
        )
        profile = (
            args.sample_profile, args.sample_main_limit,
            args.sample_worker_limit)
        row = run_search(
            state, profile, args.budget, 64, args.workers,
            args.sample_worker_limit)
        row["case"] = args.sample_case
        print("BENCH " + json.dumps(row), flush=True)
        return
    if args.only in ("all", "capacity"):
        print("CONFIG " + json.dumps({
            "seed": args.seed,
            "plies": args.plies,
            "budget": args.budget,
            "repeats": args.repeats,
            "workers": args.workers,
            "main_limits": args.main_limits,
            "worker_limits": args.worker_limits,
            "process_memory_available": os.name == "nt",
        }), flush=True)
        run_capacity_benchmarks(args)
    if args.only in ("all", "recurrence"):
        print("RECURRENCE " + json.dumps({
            "seed": args.seed,
            **measure_recurrence(
                args.seed, args.plies, args.history_plies, args.game_count),
        }), flush=True)
    if args.only in ("all", "disk"):
        directory = str(args.output_dir) if args.output_dir else None
        if args.output_dir is not None:
            args.output_dir.mkdir(parents=True, exist_ok=True)
        disk_results = measure_disk_cache(
            args.seed, args.plies, args.workers, args.main_limits[0],
            args.budget, args.disk_repeats, directory)
        print("DISK " + json.dumps({
            "seed": args.seed,
            "results": disk_results,
            "pickle_trust": "Only load files produced by this local benchmark.",
            "output_directory": directory,
        }), flush=True)


if __name__ == "__main__":
    main()
