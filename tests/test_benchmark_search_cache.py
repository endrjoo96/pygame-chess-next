import random

import pytest

from benchmarks import benchmark_search_cache as benchmark
from benchmarks.benchmark_move_generation import make_seeded_position
from constants.piece_color import COLOR
from logic.search_cache import Bound, CacheEntry
from models.enchantment_cards import EnchantmentCardType


@pytest.mark.parametrize(
    "value,expected",
    [("6k", 6144), ("2M", 2 * 1024 ** 2), ("3G", 3 * 1024 ** 3), ("128", 128)],
)
def test_cache_limit_parser(value, expected):
    assert benchmark.parse_cache_limit(value) == expected


@pytest.mark.parametrize("value", ["0", "-1", "1K", "invalid"])
def test_cache_limit_parser_rejects_invalid_values(value):
    with pytest.raises((ValueError, TypeError)):
        benchmark.parse_cache_limit(value)


def test_cache_profiles_compare_main_and_worker_capacity():
    profiles = benchmark.cache_profiles(
        [6144, 16384, 65536], [256, 64, 512])

    assert profiles == (
        ("off", 0, 256),
        ("baseline", 6144, 256),
        ("main-16384", 16384, 256),
        ("main-65536", 65536, 256),
        ("worker-64", 6144, 64),
        ("worker-512", 6144, 512),
    )


def test_board_signature_intentionally_ignores_hands_and_rng():
    state = make_seeded_position(20261116, 13)
    with_card = state.clone()
    with_card.black_cards = [EnchantmentCardType.PIECE_TELEPORT.create()]
    with_card.random_state = random.Random(1729).getstate()

    assert benchmark.board_signature(state) == benchmark.board_signature(with_card)
    assert state.cache_key() != with_card.cache_key()


def test_same_action_replay_counts_exact_and_board_only_recurrence():
    first = benchmark.make_trajectory(
        seed=20261116, move_seed=24, plies=4, base_plies=13,
        base_seed=20261116)
    replay = benchmark.make_trajectory(
        seed=20261116, move_seed=24, plies=4, base_plies=13,
        base_seed=20261116)
    other_rng = benchmark.make_trajectory(
        seed=20261117, move_seed=24, plies=4, base_plies=13,
        base_seed=20261116)

    assert [record["key"] for record in first] == [
        record["key"] for record in replay]
    assert [record["board"] for record in first] == [
        record["board"] for record in other_rng]
    assert all(
        first_record["key"] != other_record["key"]
        for first_record, other_record in zip(first, other_rng)
    )

    summary = benchmark.recurrence_summary(first + replay + other_rng)

    assert summary["exact_duplicate_groups"] == len(first)
    assert summary["board_duplicate_groups"] == len(first)
    assert summary["board_groups_with_distinct_full_states"] == len(first)
    assert summary["board_only_collision_pairs"] == 2 * len(first)


def test_recurrence_summary_counts_duplicate_full_state_records():
    state = make_seeded_position(20261116, 13)
    key = state.cache_key()
    board = benchmark.board_signature(state)

    summary = benchmark.recurrence_summary([
        {"key": key, "board": board},
        {"key": key, "board": board},
        {"key": state.clone().cache_key(), "board": board},
    ])

    assert summary["exact_unique_states"] == 1
    assert summary["exact_duplicate_groups"] == 1
    assert summary["exact_repeat_records"] == 2
    assert summary["board_only_collision_pairs"] == 0


def test_disk_snapshot_keeps_only_exact_entries_at_requested_depth():
    entries = (
        CacheEntry(("deep",), 3, None, 1.0, Bound.EXACT),
        CacheEntry(("shallow",), 2, None, 2.0, Bound.EXACT),
        CacheEntry(("bound",), 4, None, 3.0, Bound.LOWER),
        CacheEntry(("hint",), 5, None, 4.0, None),
    )

    selected = benchmark.qualifying_entries(entries, minimum_depth=3)

    assert selected == (entries[0],)


def test_pickle_roundtrip_measures_and_removes_temporary_file(tmp_path):
    entries = (CacheEntry(("state",), 3, None, 1.25, Bound.EXACT),)

    result = benchmark._measure_pickle_roundtrip(entries, str(tmp_path))

    assert result["entries"] == 1
    assert result["bytes"] > 0
    assert result["roundtrip_equal"]
    assert list(tmp_path.iterdir()) == []
