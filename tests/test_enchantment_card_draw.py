import pytest

from models.enchantment_cards import (
    EnchantmentCardType,
    _calculate_effective_weights,
    _log_effective_weights,
)
from utils.run_config import RunMode


def test_effective_weights_scale_by_sampled_reusable_uses():
    """Weryfikuje wpływ próbkowanej liczby użyć na wagę karty."""
    candidates = [
        (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 2),
        (EnchantmentCardType.KING_QUEEN_RESURRECTION, None),
    ]

    weights = _calculate_effective_weights(candidates)

    assert weights[0] == pytest.approx(0.4 * 2 / 3)
    assert weights[1] == 0.05


def test_effective_weight_log_is_descending_without_reordering_candidates(monkeypatch):
    """Sprawdza malejący porządek logu i niezmieniony porządek kandydatów."""
    candidates = [
        (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 2),
        (EnchantmentCardType.KING_QUEEN_RESURRECTION, None),
        (EnchantmentCardType.ROOK_TOWER_THROW, None),
    ]
    weights = _calculate_effective_weights(candidates)
    messages = []
    monkeypatch.setattr("models.enchantment_cards.log_debug", messages.append)

    _log_effective_weights(candidates, weights)

    logged_cards = [message.split(":")[0].strip() for message in messages[1:]]
    assert logged_cards == [
        EnchantmentCardType.ROOK_TOWER_THROW.name,
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.name,
        EnchantmentCardType.KING_QUEEN_RESURRECTION.name,
    ]
    assert [card_type for card_type, _ in candidates] == [
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD,
        EnchantmentCardType.KING_QUEEN_RESURRECTION,
        EnchantmentCardType.ROOK_TOWER_THROW,
    ]


def test_prod_draw_uses_weights_in_original_candidate_order(monkeypatch):
    """Potwierdza ważone losowanie PROD oraz kolejność jego kandydatów."""
    selected_candidate = (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 3)
    captured = {}

    def fake_choices(candidates, weights, k):
        captured["candidates"] = candidates
        captured["weights"] = weights
        captured["k"] = k
        return [selected_candidate]

    class FakeRandom:
        @staticmethod
        def randint(minimum, maximum):
            return 3

        @staticmethod
        def choices(candidates, weights, k):
            return fake_choices(candidates, weights, k)

    monkeypatch.setattr("models.enchantment_cards.RUN_MODE", RunMode.PROD)
    monkeypatch.setattr("models.enchantment_cards.log_debug", lambda message: None)

    result = EnchantmentCardType._random_choice_with_uses(FakeRandom())

    assert result == selected_candidate
    assert [candidate[0] for candidate in captured["candidates"]] == list(EnchantmentCardType)
    assert captured["weights"] == _calculate_effective_weights(captured["candidates"])
    assert captured["k"] == 1


def test_debug_draw_uses_uniform_choice_without_weighted_sampler(monkeypatch):
    """Potwierdza równomierne losowanie DEBUG bez wywołania samplera wag."""
    selected_candidate = (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 3)
    choice_calls = []
    choices_calls = []
    monkeypatch.setattr("models.enchantment_cards.RUN_MODE", RunMode.DEBUG)

    class FakeRandom:
        @staticmethod
        def randint(minimum, maximum):
            return 3

        @staticmethod
        def choice(candidates):
            choice_calls.append(candidates)
            return selected_candidate

        @staticmethod
        def choices(*args, **kwargs):
            choices_calls.append((args, kwargs))
            return [selected_candidate]

    monkeypatch.setattr("models.enchantment_cards.log_debug", lambda message: None)

    result = EnchantmentCardType._random_choice_with_uses(FakeRandom())

    assert result == selected_candidate
    assert len(choice_calls) == 1
    assert choices_calls == []
