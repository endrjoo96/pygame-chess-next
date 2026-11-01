from types import SimpleNamespace

from constants.piece_color import COLOR
from constants.pos import POS
from logic.chess_ai import ChessAI, SearchConfig
from logic.game_rules import GameActionType
from logic.game_simulation import GameSimulation
from logic.opening_book import opening_hints
from models.chess_pieces import Piece
from models.game_observation import GameObservation
from models.game_state import GameState
from models.starting_positions import pieces_starting_positions_map


def _new_classical_state():
    pieces_locations = {position: Piece() for position in range(1, 65)}
    for position, piece in pieces_starting_positions_map.items():
        pieces_locations[position.value] = Piece(
            piece.get_color(), piece.get_type(), position.value)

    return GameState(
        pieces_locations=pieces_locations,
        current_turn=COLOR.WHITE,
        turns_started={COLOR.WHITE: 1, COLOR.BLACK: 0},
        white_cards=[],
        black_cards=[],
        captured_white=[],
        captured_black=[],
        board_card_available=False,
        board_card_position=POS.D5.value,
        board_enchantment=None,
        pending_board_card_delay=None,
    )


def _play(state, source, destination):
    action = next(
        action
        for action in GameSimulation.available_actions(state)
        if action.action_type == GameActionType.MOVE
        and action.source == source.value
        and action.destination == destination.value
        and action.card_index == -1
    )
    return GameSimulation.apply(state, action)


def test_opening_book_suggests_common_responses_after_e4():
    state = _play(_new_classical_state(), POS.E2, POS.E4)

    hints = opening_hints(state)

    assert hints[0] == (POS.E7.value, POS.E5.value)
    assert (POS.C7.value, POS.C5.value) in hints


def test_opening_book_does_not_match_an_unlisted_position():
    state = _play(_new_classical_state(), POS.A2, POS.A3)

    assert opening_hints(state) == ()


def test_ai_prioritizes_only_legal_book_moves():
    state = _play(_new_classical_state(), POS.E2, POS.E4)
    state.pieces_locations[POS.E7.value].set_stunned_for_turns(1)
    legal_actions = GameSimulation.available_actions(state)

    ordered = ChessAI(
        SearchConfig(time_limit_seconds=1, max_depth=1), max_workers=1
    )._order_actions(state, legal_actions)

    assert (POS.E7.value, POS.E5.value) not in {
        (action.source, action.destination) for action in legal_actions
    }
    ordered_moves = [(action.source, action.destination) for action in ordered]
    assert ordered_moves.index((POS.C7.value, POS.C5.value)) < ordered_moves.index(
        (POS.B7.value, POS.B5.value)
    )
    assert len(ordered) == len(legal_actions)
    assert set(ordered) == set(legal_actions)


def test_search_evaluates_all_moves_and_can_choose_outside_the_book(monkeypatch):
    state = _play(_new_classical_state(), POS.E2, POS.E4)
    legal_actions = GameSimulation.available_actions(state)
    expected_action = next(
        action for action in legal_actions
        if action.source == POS.G8.value and action.destination == POS.F6.value
    )
    evaluated = []

    def evaluate_root_action(
        _state, action, _depth, _config, _deadline, _cache_snapshot=(),
        cache_size_callback=None,
    ):
        evaluated.append(action)
        score = 1.0 if action == expected_action else 0.0
        return SimpleNamespace(
            score=score,
            nodes=1,
            entries=(),
            hits=0,
            score_hits=0,
            hints=0,
        )

    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action", evaluate_root_action)
    ai = ChessAI(
        SearchConfig(time_limit_seconds=2, max_depth=1), max_workers=1
    )

    result = ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))

    assert set(evaluated) == set(legal_actions)
    assert result.action == expected_action
