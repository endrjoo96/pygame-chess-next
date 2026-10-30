import unittest
from unittest.mock import patch

from models.enchantment_cards import (
    EnchantmentCardType,
    _calculate_effective_weights,
    _log_effective_weights,
)
from utils.run_config import RunMode


class EnchantmentCardDrawTests(unittest.TestCase):
    def test_effective_weights_scale_by_sampled_reusable_uses(self):
        """Weryfikuje wpływ próbkowanej liczby użyć na wagę karty."""
        candidates = [
            (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 2),
            (EnchantmentCardType.KING_QUEEN_RESURRECTION, None),
        ]

        weights = _calculate_effective_weights(candidates)

        self.assertAlmostEqual(0.4 * 2 / 3, weights[0])
        self.assertEqual(0.05, weights[1])

    def test_effective_weight_log_is_descending_without_reordering_candidates(self):
        """Sprawdza malejący porządek logu i niezmieniony porządek kandydatów."""
        candidates = [
            (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 2),
            (EnchantmentCardType.KING_QUEEN_RESURRECTION, None),
            (EnchantmentCardType.ROOK_TOWER_THROW, None),
        ]
        weights = _calculate_effective_weights(candidates)

        with patch("models.enchantment_cards.debug_log") as log:
            _log_effective_weights(candidates, weights)

        logged_cards = [call.args[0].split(":")[0].strip() for call in log.call_args_list[1:]]
        self.assertEqual(
            [
                EnchantmentCardType.ROOK_TOWER_THROW.name,
                EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.name,
                EnchantmentCardType.KING_QUEEN_RESURRECTION.name,
            ],
            logged_cards,
        )
        self.assertEqual(
            [EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD,
             EnchantmentCardType.KING_QUEEN_RESURRECTION,
             EnchantmentCardType.ROOK_TOWER_THROW],
            [card_type for card_type, _ in candidates],
        )

    def test_prod_draw_uses_weights_in_original_candidate_order(self):
        """Potwierdza ważone losowanie PROD oraz kolejność jego kandydatów."""
        selected_candidate = (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 3)
        with patch("models.enchantment_cards.RUN_MODE", RunMode.PROD), patch(
            "models.enchantment_cards.random.randint", return_value=3
        ), patch(
            "models.enchantment_cards.random.choices",
            return_value=[selected_candidate],
        ) as choices, patch("models.enchantment_cards.debug_log"):
            result = EnchantmentCardType._random_choice_with_uses()

        self.assertEqual(selected_candidate, result)
        sampled_candidates = choices.call_args.args[0]
        self.assertEqual(
            list(EnchantmentCardType),
            [candidate[0] for candidate in sampled_candidates],
        )
        self.assertEqual(
            _calculate_effective_weights(sampled_candidates),
            choices.call_args.kwargs["weights"],
        )

    def test_debug_draw_uses_uniform_choice_without_weighted_sampler(self):
        """Potwierdza równomierne losowanie DEBUG bez wywołania samplera wag."""
        selected_candidate = (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 3)
        with patch("models.enchantment_cards.RUN_MODE", RunMode.DEBUG), patch(
            "models.enchantment_cards.random.randint", return_value=3
        ), patch(
            "models.enchantment_cards.random.choice",
            return_value=selected_candidate,
        ), patch("models.enchantment_cards.random.choices") as weighted_choice, patch(
            "models.enchantment_cards.debug_log"
        ):
            result = EnchantmentCardType._random_choice_with_uses()

        self.assertEqual(selected_candidate, result)
        weighted_choice.assert_not_called()


if __name__ == "__main__":
    unittest.main()
