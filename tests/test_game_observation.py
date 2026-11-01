import random

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState, RuneTrap


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


def test_observation_preserves_en_passant_and_castling_rights():
    state = make_game_state()
    state.en_passant_target = 45
    state.pieces_locations[57].set_has_moved()

    observation = GameObservation.from_state(state, COLOR.BLACK)
    restored = observation.to_state()

    assert restored.en_passant_target == 45
    assert restored.pieces_locations[57].has_moved()
    restored.pieces_locations[57].set_has_moved(False)
    assert state.pieces_locations[57].has_moved()


def test_observation_preserves_all_en_passant_targets_and_rune_traps():
    state = make_game_state()
    state.en_passant_target = 45
    state.en_passant_targets = [45, 46]
    state.rune_traps = [
        RuneTrap(
            position=36,
            owner=COLOR.WHITE,
            enchantment=EnchantmentCardType.KNIGHT_RUNIC_TRAP.create(),
            placed_on_turn=2,
            remaining_owner_turns=1,
        )
    ]

    observation = GameObservation.from_state(state, COLOR.BLACK)
    restored = observation.to_state()

    assert restored.en_passant_target == 45
    assert restored.en_passant_targets == [45, 46]
    assert restored.rune_traps[0].position == 36
    assert restored.rune_traps[0].owner == COLOR.WHITE
    assert restored.rune_traps[0].remaining_owner_turns == 1
    restored.en_passant_targets.append(47)
    restored.rune_traps[0].remaining_owner_turns = 0
    assert state.en_passant_targets == [45, 46]
    assert state.rune_traps[0].remaining_owner_turns == 1
