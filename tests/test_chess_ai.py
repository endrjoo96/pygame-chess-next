import random

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import ChessAI, SearchConfig
from logic.game_simulation import GameSimulation
from models.chess_pieces import Piece
from models.game_observation import GameObservation
from models.game_state import GameState


def make_black_to_move_state():
    return GameState(
        pieces_locations={position: Piece() for position in range(1, 65)},
        current_turn=COLOR.BLACK,
        turns_started={COLOR.WHITE: 1, COLOR.BLACK: 1},
        white_cards=[],
        black_cards=[],
        captured_white=[],
        captured_black=[],
        board_card_available=False,
        board_card_position=36,
        board_enchantment=None,
        pending_board_card_delay=None,
        random_state=random.Random(23).getstate(),
    )


def test_ai_finds_immediate_king_capture():
    state = make_black_to_move_state()
    state.pieces_locations[1] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[2] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(SearchConfig(time_limit_seconds=2, max_depth=1, hidden_hand_samples=1))

    decision = ai.choose_action(observation, random.Random(5))

    assert decision.action is not None
    result = GameSimulation.apply(state, decision.action)
    assert result.get_winner() == COLOR.BLACK
    assert decision.completed_depth == 1


def test_ai_returns_a_legal_fallback_when_search_budget_expires():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(SearchConfig(time_limit_seconds=1e-12, max_depth=4, hidden_hand_samples=1))

    decision = ai.choose_action(observation, random.Random(5))

    assert decision.action in GameSimulation.available_actions(state)
    assert decision.completed_depth == 0


def test_ai_only_accepts_black_to_move_observations():
    state = make_black_to_move_state()
    state.current_turn = COLOR.WHITE
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI()

    with pytest.raises(ValueError, match="not the AI player's turn"):
        ai.choose_action(observation)
