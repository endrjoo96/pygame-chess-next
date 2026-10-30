import random

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState
from utils.run_config import RunMode


@pytest.fixture
def game_state():
    return GameState(
        pieces_locations={
            position: Piece(
                COLOR.BLACK if position == 57 else COLOR.EMPTY,
                PIECE_TYPE.ROOK if position == 57 else PIECE_TYPE.EMPTY,
            )
            for position in range(1, 65)
        },
        current_turn=COLOR.BLACK,
        turns_started={COLOR.WHITE: 1, COLOR.BLACK: 1},
        white_cards=[EnchantmentCardType.PAWN_SWORDSMAN.create()],
        black_cards=[EnchantmentCardType.PIECE_TELEPORT.create()],
        captured_white=[],
        captured_black=[],
        board_card_available=False,
        board_card_position=36,
        board_enchantment=None,
        pending_board_card_delay=None,
        random_state=random.Random(23).getstate(),
    )


def test_observation_exposes_own_hand_and_enemy_count_without_enemy_card_types(game_state):
    observation = GameObservation.from_state(game_state, COLOR.BLACK)

    assert len(observation.own_cards) == 1
    assert observation.own_cards[0].get_card_type() == EnchantmentCardType.PIECE_TELEPORT
    assert observation.opponent_card_count == 1
    assert not hasattr(observation, "white_cards")
    assert not hasattr(observation, "black_cards")
    assert not hasattr(observation, "opponent_cards")
    assert game_state.white_cards[0].get_card_type() == EnchantmentCardType.PAWN_SWORDSMAN


def test_determinized_hand_has_public_size_and_is_reproducible(game_state, monkeypatch):
    monkeypatch.setattr("models.enchantment_cards.RUN_MODE", RunMode.PROD)
    observation = GameObservation.from_state(game_state, COLOR.BLACK)

    first = observation.determinize(random.Random(91))
    repeated = observation.determinize(random.Random(91))

    assert len(first.white_cards) == observation.opponent_card_count
    assert [card.get_card_type() for card in first.white_cards] == [
        card.get_card_type() for card in repeated.white_cards
    ]
    assert [card.get_remaining_uses() for card in first.white_cards] == [
        card.get_remaining_uses() for card in repeated.white_cards
    ]
    assert first.black_cards[0].get_card_type() == EnchantmentCardType.PIECE_TELEPORT


def test_hidden_hand_sampling_uses_distribution_from_current_draw_mode(
    game_state, monkeypatch
):
    monkeypatch.setattr("models.enchantment_cards.RUN_MODE", RunMode.DEBUG)
    debug_probabilities = GameObservation.opponent_card_probabilities()
    assert sum(debug_probabilities.values()) == pytest.approx(1.0)
    assert len(set(debug_probabilities.values())) == 1

    monkeypatch.setattr("models.enchantment_cards.RUN_MODE", RunMode.PROD)
    production_probabilities = GameObservation.opponent_card_probabilities()
    assert sum(production_probabilities.values()) == pytest.approx(1.0)
    assert all(0 <= probability <= 1 for probability in production_probabilities.values())
    assert (
        production_probabilities[EnchantmentCardType.PAWN_DETONATION_DELAYED_2]
        > production_probabilities[EnchantmentCardType.ROOK_UPGRADE_TO_QUEEN]
    )


def test_determinization_rejects_impossible_public_card_count(game_state):
    observation = GameObservation.from_state(game_state, COLOR.BLACK)
    observation.opponent_card_count = 9

    with pytest.raises(ValueError, match="between 0 and 8"):
        observation.determinize(random.Random(1))
