import random
import sqlite3

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from logic.move_learning import (
    MoveLearningAccumulator,
    MoveLearningStore,
    MoveLearningUpdate,
    learning_position_key,
    encode_action,
    is_learning_position_eligible,
    is_plain_move,
    search_result_position_key,
    SearchResultAccumulator,
)
from logic.chess_ai import ChessAI, SearchConfig
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_state import GameState
from models.game_observation import GameObservation


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


def test_empty_search_result_schema_fits_minimum_file_limit(tmp_path):
    store_path = tmp_path / "minimum-size.sqlite3"
    store = MoveLearningStore(store_path, 16 * 1024)
    store.close()

    assert store_path.stat().st_size <= 16 * 1024


def test_search_result_key_covers_full_state_and_is_stable():
    state = make_learning_state()
    initial_key = search_result_position_key(state)

    assert search_result_position_key(state.clone()) == initial_key
    card = EnchantmentCardType.PIECE_TELEPORT.create()
    state.black_cards.append(card)
    state.board_card_available = True
    state.board_card_position = 18
    state.board_enchantment = card
    state.board_cards = [(18, card)]
    state.pieces_locations[1].set_enchantment(card)
    assert search_result_position_key(state) != initial_key
    assert search_result_position_key(state.clone()) == search_result_position_key(
        state)

    random_state = make_learning_state()
    random_state.random_state = random.Random(31).getstate()
    assert search_result_position_key(random_state) != initial_key


def test_search_results_persist_per_action_depth_and_bound(tmp_path):
    state = make_learning_state()
    key = search_result_position_key(state)
    preferred = GameAction(GameActionType.MOVE, 1, 2)
    alternative = GameAction(GameActionType.MOVE, 1, 3)
    accumulator = SearchResultAccumulator()
    accumulator.record(key, preferred, 4, 12.5, "exact")
    accumulator.record(key, preferred, 4, 10.0, "upper")
    accumulator.record(key, preferred, 4, 9.0, "upper")
    accumulator.record(key, preferred, 3, 5.0, "exact")
    accumulator.record(key, alternative, 4, -25.0, "exact")
    path = tmp_path / "search-results.sqlite3"

    store = MoveLearningStore(path, 64 * 1024)
    store.apply_search_result_updates(accumulator.snapshot())
    results = store.get_search_results(state, [preferred])
    assert {
        (result.depth, result.bound, result.score)
        for result in results[preferred]
    } == {
        (4, "exact", 12.5),
        (4, "upper", 9.0),
        (3, "exact", 5.0),
    }
    assert alternative not in results
    store.close()

    read_only = MoveLearningStore(path, 64 * 1024, read_only=True)
    assert read_only.get_search_results(state)[preferred] == results[preferred]
    with pytest.raises(RuntimeError, match="not writable"):
        read_only.apply_search_result_updates(accumulator.snapshot())
    read_only.close()


def test_v1_database_migrates_without_losing_move_hints(tmp_path):
    path = tmp_path / "old-learning.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE move_hints (
            position_key TEXT NOT NULL,
            action_key TEXT NOT NULL,
            preferred_count INTEGER NOT NULL DEFAULT 0,
            cutoff_count INTEGER NOT NULL DEFAULT 0,
            worst_count INTEGER NOT NULL DEFAULT 0,
            last_seen INTEGER NOT NULL,
            PRIMARY KEY (position_key, action_key)
        );
        CREATE INDEX move_hints_last_seen ON move_hints(last_seen);
        PRAGMA user_version = 1;
        """
    )
    connection.close()

    state = make_learning_state()
    legacy_reader = MoveLearningStore(path, 64 * 1024, read_only=True)
    assert legacy_reader.get_search_results(state) == {}
    legacy_reader.close()

    action = GameAction(GameActionType.MOVE, 1, 2)
    key = learning_position_key(state)
    legacy_update = MoveLearningUpdate(
        key, encode_action(action), preferred=1)
    writable = MoveLearningStore(path, 64 * 1024)
    writable.apply_updates((legacy_update,))
    writable.close()

    read_only = MoveLearningStore(path, 64 * 1024, read_only=True)
    assert read_only.get_action_scores(state, [action])[action] > 0
    assert read_only.get_search_results(state) == {}
    read_only.close()


def test_search_reuses_persisted_exact_root_results(monkeypatch, tmp_path):
    import logic.chess_ai as chess_ai_module

    state = make_learning_state()
    state.pieces_locations = {
        position: state.pieces_locations.get(position, Piece())
        for position in range(1, 65)
    }
    observation = GameObservation.from_state(state, COLOR.BLACK)
    actions = GameSimulation.available_actions(state)
    ai = ChessAI(
        SearchConfig(
            time_limit_seconds=5,
            max_depth=2,
            cache_enabled=True,
            learning_enabled=True,
            learning_save_enabled=True,
            learning_max_file_size_bytes=128 * 1024,
        ),
        max_workers=1,
        ponder_enabled=False,
    )
    ai._learning_database_path = tmp_path / "persistent-results.sqlite3"
    ai._move_learning_store.close()
    ai._move_learning_store = MoveLearningStore(
        ai._learning_database_path, 128 * 1024)
    chess_ai_module._WORKER_MOVE_LEARNING_STORE = ai._move_learning_store
    original_evaluate_root_action = chess_ai_module._evaluate_root_action
    root_evaluation_count = []

    def count_root_evaluation(*args, **kwargs):
        root_evaluation_count.append(args[1])
        return original_evaluate_root_action(*args, **kwargs)

    monkeypatch.setattr(
        chess_ai_module, "_evaluate_root_action", count_root_evaluation)

    first = ai.choose_action(observation)
    first_count = len(root_evaluation_count)
    assert first.action is not None
    assert first_count == len(actions) * 2
    persisted_results = ai._move_learning_store.get_search_results(state, actions)
    assert persisted_results
    assert any(
        result.bound == "exact"
        for records in persisted_results.values()
        for result in records
    )
    assert any(
        result.bound == "upper"
        for records in persisted_results.values()
        for result in records
    )
    assert {
        result.depth
        for records in persisted_results.values()
        for result in records
    } == {1, 2}
    child_state = GameSimulation._apply_generated_action(state, actions[0])
    child_actions = GameSimulation.available_actions(child_state)
    assert ai._move_learning_store.get_search_results(
        child_state, child_actions)

    ai.clear_search_cache()
    root_evaluation_count.clear()
    second = ai.choose_action(observation)

    assert second.action is not None
    assert len(root_evaluation_count) < first_count
    ai.close()


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
