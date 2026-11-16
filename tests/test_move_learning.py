import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.game_rules import GameAction, GameActionType
from logic.move_learning import (
    MoveLearningAccumulator,
    MoveLearningStore,
    MoveLearningUpdate,
    learning_position_key,
    encode_action,
    is_learning_position_eligible,
    is_plain_move,
)
from logic.chess_ai import ChessAI, SearchConfig
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState


def make_learning_state():
    return GameState(
        pieces_locations={
            1: Piece(COLOR.WHITE, PIECE_TYPE.KING, 1),
            64: Piece(COLOR.BLACK, PIECE_TYPE.KING, 64),
        },
        current_turn=COLOR.BLACK,
        turns_started={COLOR.WHITE: 0, COLOR.BLACK: 0},
        white_cards=[],
        black_cards=[],
        captured_white=[],
        captured_black=[],
        board_card_available=False,
        board_card_position=0,
        board_enchantment=None,
        pending_board_card_delay=None,
    )


def test_learning_keys_allow_unused_cards_but_reject_active_effects():
    state = make_learning_state()
    initial_key = learning_position_key(state)
    card = EnchantmentCardType.ROOK_TREBUCHET.create()

    state.black_cards.append(card)
    state.board_card_available = True
    state.board_card_position = 18
    state.board_enchantment = card
    assert is_learning_position_eligible(state)
    assert learning_position_key(state) == initial_key

    state.pieces_locations[1].set_enchantment(card)
    assert not is_learning_position_eligible(state)
    assert learning_position_key(state) is None
    assert is_plain_move(GameAction(GameActionType.PROMOTE, 8))


def test_learning_key_distinguishes_turn_and_piece_move_rights():
    state = make_learning_state()
    initial_key = learning_position_key(state)

    state.current_turn = COLOR.WHITE
    assert learning_position_key(state) != initial_key

    state.current_turn = COLOR.BLACK
    state.pieces_locations[1].set_has_moved()
    assert learning_position_key(state) != initial_key


def test_move_learning_store_persists_only_legal_hints(tmp_path):
    state = make_learning_state()
    preferred = GameAction(GameActionType.MOVE, 1, 2)
    other = GameAction(GameActionType.MOVE, 1, 3)
    key = learning_position_key(state)
    store_path = tmp_path / "move-learning.sqlite3"
    store = MoveLearningStore(store_path, 64 * 1024)
    accumulator = MoveLearningAccumulator()
    accumulator.record(key, preferred, "preferred")
    accumulator.record(key, preferred, "cutoff")
    accumulator.record(key, other, "worst")

    store.apply_updates(accumulator.snapshot())
    scores = store.get_action_scores(state, [preferred])
    assert scores[preferred] > 0
    assert other not in scores
    store.close()

    read_only = MoveLearningStore(
        store_path, 64 * 1024, read_only=True)
    assert read_only.get_action_scores(state, [preferred]) == scores
    with pytest.raises(RuntimeError, match="not writable"):
        read_only.apply_updates((MoveLearningUpdate(key, encode_action(other), 1),))
    read_only.close()


def test_move_learning_store_keeps_database_within_size_limit(tmp_path):
    action = GameAction(GameActionType.MOVE, 1, 2)
    action_key = encode_action(action)
    updates = tuple(
        MoveLearningUpdate(
            "{:064x}".format(index + 1), action_key, preferred=1)
        for index in range(500)
    )
    store_path = tmp_path / "bounded-learning.sqlite3"
    store = MoveLearningStore(store_path, 32 * 1024)
    store.apply_updates(updates)
    store.close()

    assert store_path.stat().st_size <= 32 * 1024


def test_learning_signals_are_limited_to_plain_card_free_paths():
    state = make_learning_state()
    normal_move = GameAction(GameActionType.MOVE, 10, 9)
    card_move = GameAction(GameActionType.TELEPORT, 10, 11, card_index=0)
    ai = ChessAI(
        SearchConfig(
            learning_enabled=True,
            learning_save_enabled=True,
            cache_enabled=False,
        ),
        max_workers=1,
        initialize_move_learning=False,
    )

    ai._record_move_learning(state, normal_move, "preferred", True)
    ai._record_move_learning(state, card_move, "preferred", True)
    ai._record_move_learning(state, normal_move, "preferred", False)

    updates = ai._move_learning_updates.snapshot()
    assert len(updates) == 1
    assert updates[0].action_key == encode_action(normal_move)
    ai.close()


def test_saved_hint_moves_legal_plain_action_ahead_when_tied(tmp_path):
    state = make_learning_state()
    preferred = GameAction(GameActionType.MOVE, 10, 9)
    other = GameAction(GameActionType.MOVE, 10, 11)
    key = learning_position_key(state)
    store = MoveLearningStore(tmp_path / "ordering.sqlite3", 64 * 1024)
    accumulator = MoveLearningAccumulator()
    accumulator.record(key, preferred, "preferred")
    store.apply_updates(accumulator.snapshot())
    ai = ChessAI(
        SearchConfig(
            learning_enabled=True,
            learning_save_enabled=False,
            cache_enabled=False,
        ),
        max_workers=1,
        initialize_move_learning=False,
    )
    ai._move_learning_store = store

    ordered = ai._order_actions(state, [other, preferred])

    assert ordered == [preferred, other]
    ai.close()
