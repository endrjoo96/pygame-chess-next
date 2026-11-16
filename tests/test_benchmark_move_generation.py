import pytest

from benchmarks import benchmark_move_generation as benchmark
from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import SearchResult
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from models.ai_search_metrics import AISearchMetrics


def _mock_searches(monkeypatch, results):
    remaining = iter(results)
    instances = []

    class FakeAI:
        def __init__(self, config, max_workers):
            self.config = config
            self.max_workers = max_workers
            self.started_depth = 0
            self.closed = False
            instances.append(self)

        def choose_action(self, observation):
            assert observation.own_color == COLOR.BLACK
            result = next(remaining)
            self.started_depth = result.completed_depth + 1
            return result

        def shutdown_worker_pool(self):
            self.closed = True

    monkeypatch.setattr(benchmark, "BenchmarkChessAI", FakeAI)
    return instances


def test_timed_samples_keep_individual_results_and_metrics(monkeypatch, capsys):
    first = SearchResult(
        GameAction(GameActionType.MOVE, 1, 2), 1.0, 2, 100,
        AISearchMetrics(action_application_ns=3_000_000),
    )
    second = SearchResult(
        GameAction(GameActionType.MOVE, 1, 3), 2.0, 3, 150,
        AISearchMetrics(action_application_ns=8_000_000),
    )
    instances = _mock_searches(monkeypatch, [first, second])
    state = benchmark.make_seeded_position(20261116)

    samples = benchmark.measure_search(
        state, depth=64, repeats=2, time_limit_seconds=5,
        cache_enabled=True, metrics_enabled=True, strict_results=False,
    )
    benchmark._print_search_result("timed", samples)
    output = capsys.readouterr().out

    assert [sample.result for sample in samples] == [first, second]
    assert [sample.started_depth for sample in samples] == [3, 4]
    assert "timed sample=1: " in output
    assert "timed sample=2: " in output
    assert "apply=0 calls (3.00ms)" in output
    assert "apply=0 calls (8.00ms)" in output
    assert all(instance.closed for instance in instances)
    assert all(instance.config.cache_enabled for instance in instances)
    assert all(instance.config.metrics_enabled for instance in instances)


def test_fixed_depth_samples_reject_changed_results(monkeypatch):
    action = GameAction(GameActionType.MOVE, 1, 2)
    first = SearchResult(action, 1.0, 2, 100)
    second = SearchResult(action, 1.0, 2, 101)
    instances = _mock_searches(monkeypatch, [first, second])
    state = benchmark.make_seeded_position(20261116)

    with pytest.raises(RuntimeError, match="AI result changed"):
        benchmark.measure_search(state, depth=2, repeats=2)

    assert all(instance.closed for instance in instances)


def test_extended_position_has_isolated_cards_trap_and_stun():
    original = benchmark.make_seeded_position(20261116)
    original_key = original.cache_key()

    state = benchmark.make_complex_card_position(original)

    assert state.current_turn == COLOR.BLACK
    assert state.white_cards and state.black_cards
    assert state.board_cards[0][1] is state.board_enchantment
    assert len(state.rune_traps) == 1
    assert not state.pieces_locations[state.rune_traps[0].position].exists()
    assert any(
        piece.exists() and piece.get_color() == COLOR.BLACK
        and piece.get_type() != PIECE_TYPE.KING and piece.is_stunned()
        for piece in state.pieces_locations.values()
    )
    assert GameSimulation.available_actions(state)
    assert original.cache_key() == original_key


def test_seeded_positions_are_reproducible_across_game_seeds(monkeypatch):
    first = benchmark.make_card_position(benchmark.make_seeded_position(20261116))
    monkeypatch.setattr("models.enchantment_cards.GAME_SEED", 100)
    second = benchmark.make_card_position(benchmark.make_seeded_position(20261116))

    assert first.cache_key() == second.cache_key()


def test_search_samples_report_the_started_depth():
    state = benchmark.make_seeded_position(20261116)

    samples = benchmark.measure_search(
        state, depth=1, repeats=1, workers=1, metrics_enabled=False,
    )

    assert len(samples) == 1
    assert samples[0].started_depth == samples[0].result.completed_depth == 1
    assert samples[0].result.action in GameSimulation.available_actions(state)
    assert samples[0].result.metrics is None
