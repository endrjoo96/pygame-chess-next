import random

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState


def make_game_state():
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


def test_observation_exposes_exact_hands_without_aliasing_them():
    state = make_game_state()

    observation = GameObservation.from_state(state, COLOR.BLACK)

    assert observation.own_cards[0].get_card_type() == EnchantmentCardType.PIECE_TELEPORT
    assert observation.opponent_cards[0].get_card_type() == EnchantmentCardType.PAWN_SWORDSMAN
    assert observation.own_cards is not state.black_cards
    assert observation.opponent_cards is not state.white_cards
    assert not hasattr(observation, "white_cards")
    assert not hasattr(observation, "black_cards")


def test_full_state_preserves_exact_hands_and_random_state():
    state = make_game_state()
    observation = GameObservation.from_state(state, COLOR.BLACK)

    result = observation.to_state()

    assert [card.get_card_type() for card in result.white_cards] == [
        EnchantmentCardType.PAWN_SWORDSMAN
    ]
    assert [card.get_card_type() for card in result.black_cards] == [
        EnchantmentCardType.PIECE_TELEPORT
    ]
    assert result.random_state == state.random_state
    assert result.white_cards is not observation.opponent_cards
    assert result.black_cards is not observation.own_cards

    result.white_cards[0].add_uses(1)
    assert state.white_cards[0].get_remaining_uses() == 1


def test_full_state_maps_hands_correctly_when_ai_is_white():
    state = make_game_state()
    observation = GameObservation.from_state(state, COLOR.WHITE)

    result = observation.to_state()

    assert result.white_cards[0].get_card_type() == EnchantmentCardType.PAWN_SWORDSMAN
    assert result.black_cards[0].get_card_type() == EnchantmentCardType.PIECE_TELEPORT
