import math
import pickle
import random
import time
from dataclasses import dataclass

import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import (
    ChessAI, SearchConfig, _RootEvaluation, _SearchTimeout, _evaluate_root_action,
)
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from logic.search_cache import Bound, CacheEntry, SearchCache
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.enchantments import Enchantment
from models.game_observation import GameObservation
from models.game_state import GameState
from tests.test_chess_ai import make_black_to_move_state


def populated_state():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK, 57)
    state.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN, 9)
    state.white_cards = [
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(uses=2),
        EnchantmentCardType.PAWN_SWORDSMAN.create(),
    ]
    state.black_cards = [EnchantmentCardType.PIECE_TELEPORT.create()]
    card = EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD.create(uses=2)
    state.board_card_available = True
    state.board_card_position = 36
    state.board_enchantment = card
    state.board_cards = [(36, card)]
    return state


def test_state_key_survives_clone_observation_and_process_serialization():
    state = populated_state()
    card = state.white_cards[0]
    state.pieces_locations[9].set_enchantment(card)
    observation = GameObservation.from_state(state, COLOR.BLACK)

    cloned = state.clone()
    restored = observation.to_state()
    transported = pickle.loads(pickle.dumps(state))
    assert state.cache_key() == cloned.cache_key()
    assert state.cache_key() == restored.cache_key()
    assert state.cache_key() == transported.cache_key()
    assert restored.board_enchantment is restored.board_cards[0][1]
    assert restored.pieces_locations[9].get_effects(0)[0][0] is restored.white_cards[0]
    assert restored.white_cards[0] is not card


@pytest.mark.parametrize(
    "change",
    [
        lambda s: setattr(s, "current_turn", COLOR.WHITE),
        lambda s: s.turns_started.__setitem__(COLOR.BLACK, 2),
        lambda s: s.pieces_locations.__setitem__(
            57, Piece(COLOR.BLACK, PIECE_TYPE.ROOK, 58)),
        lambda s: s.pieces_locations.__setitem__(1, s.pieces_locations.pop(1)),
        lambda s: s.pieces_locations[57].set_stunned_for_turns(2),
        lambda s: s.pieces_locations[9].set_enchantment(
            EnchantmentCardType.PAWN_SWORDSMAN.create()),
        lambda s: s.pieces_locations[9].add_delayed_enchantment(
            EnchantmentCardType.PAWN_DETONATION_DELAYED_1.create(), 4),
        lambda s: s.pieces_locations[9].add_stun_effect(
            EnchantmentCardType.PAWN_UPGRADE_TO_KNIGHT.create(), 2),
        lambda s: s.white_cards.reverse(),
        lambda s: s.white_cards[0].consume_use(),
        lambda s: s.black_cards.clear(),
        lambda s: s.captured_black.append(Piece(COLOR.WHITE, PIECE_TYPE.PAWN, 9)),
        lambda s: setattr(s, "board_card_position", 37),
        lambda s: setattr(s, "pending_board_card_delay", 2),
        lambda s: setattr(s, "selected_card", (COLOR.BLACK, 0)),
        lambda s: setattr(s, "selected_piece_position", 57),
        lambda s: setattr(s, "selected_captured_piece", (COLOR.WHITE, 0)),
        lambda s: setattr(s, "double_move_step", 1),
        lambda s: setattr(s, "double_move_collected_board_card", True),
        lambda s: s.resurrection_moves.append(2),
        lambda s: setattr(s, "random_state", random.Random(24).getstate()),
        lambda s: s.board_cards.append(
            (37, EnchantmentCardType.PIECE_TELEPORT.create())),
    ],
)
def test_state_key_distinguishes_rule_relevant_changes(change):
    original = populated_state()
    changed = original.clone()
    change(changed)
    assert original.cache_key() != changed.cache_key()


def test_state_key_distinguishes_shared_and_independent_effect_objects():
    state = populated_state()
    state.pieces_locations[9].set_enchantment(state.white_cards[0])
    independent = state.clone()
    independent.white_cards[0] = EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(uses=2)
    assert state.cache_key() != independent.cache_key()


def test_state_key_distinguishes_remaining_stun_without_stun_effect():
    first = populated_state()
    second = first.clone()
    first.pieces_locations[57].set_stunned_for_turns(1)
    second.pieces_locations[57].set_stunned_for_turns(2)
    assert first.cache_key() != second.cache_key()


def test_unrepresentable_enchantment_behavior_is_reported():
    state = populated_state()
    state.white_cards.append(Enchantment(
        [], "custom", "custom", PIECE_TYPE.EMPTY, lambda *args: [], None))
    with pytest.raises(ValueError, match="behavior"):
        state.cache_key()


def test_cache_retains_deeper_verified_entries_and_is_bounded():
    cache = SearchCache(2)
    shallow = CacheEntry(("a",), 1, None, 1, Bound.EXACT)
    deep = CacheEntry(("b",), 3, None, 2, Bound.EXACT)
    hint = CacheEntry(("c",), 2, None, 3, None)
    for entry in (shallow, deep, hint):
        cache.put(entry)
    assert len(cache) == 2
    assert cache.get(("a",), 1) is None
    assert cache.get(("b",), 3) == deep
    assert cache.get(("c",), 2) == hint
    assert cache.evictions == 1
    cache.put(CacheEntry(("b",), 3, None, 9, None))
    assert cache.get(("b",), 3) == deep


@pytest.mark.parametrize(
    "settings",
    [
        {"cache_enabled": 1},
        {"cache_enabled": "true"},
        {"cache_max_entries": True},
        {"cache_max_entries": 0},
        {"cache_max_entries": 1.5},
    ],
)
def test_search_config_rejects_invalid_cache_settings(settings):
    with pytest.raises(ValueError, match="cache"):
        SearchConfig(**settings)


@dataclass(frozen=True)
class TreeState:
    name: str
    current_turn: COLOR

    def get_winner(self):
        return None

    def cache_key(self):
        return (self.name, self.current_turn)


@pytest.fixture
def tree(monkeypatch):
    root = TreeState("root", COLOR.BLACK)
    children = [
        TreeState("first", COLOR.WHITE),
        TreeState("second", COLOR.WHITE),
    ]
    actions = [GameAction(GameActionType.MOVE, 1, 2),
               GameAction(GameActionType.MOVE, 1, 3)]
    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", False)
    monkeypatch.setattr(
        GameSimulation, "available_actions",
        lambda state: actions if state == root else [],
    )
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action",
        lambda state, action: children[actions.index(action)],
    )
    monkeypatch.setattr(ChessAI, "_order_actions", lambda self, state, moves: list(moves))
    monkeypatch.setattr(
        ChessAI, "evaluate", staticmethod(
            lambda state: {"root": 0.0, "first": 1.0, "second": 3.0}[state.name]),
    )
    ai = ChessAI(SearchConfig(cache_enabled=True, cache_max_entries=32), max_workers=1)
    ai._deadline = time.monotonic() + 10
    return ai, root, actions


@pytest.mark.parametrize(
    ("alpha", "beta", "bound"),
    [(-math.inf, math.inf, Bound.EXACT), (4.0, math.inf, Bound.UPPER),
     (-math.inf, 2.0, Bound.LOWER)],
)
def test_cache_uses_exact_scores_and_valid_alpha_beta_cutoffs(tree, alpha, beta, bound):
    ai, root, _ = tree
    value, reliable = ai._search_with_proof(root, 1, alpha, beta)
    entry = ai._cache.get(root.cache_key(), 1)
    assert reliable
    assert value == 3.0
    assert entry.bound == bound
    nodes_before = ai._nodes
    assert ai._search_with_proof(root, 1, alpha, beta) == (3.0, True)
    assert ai._nodes == nodes_before + 1
    assert ai._cache_score_hits == 1


def test_bounds_do_not_replace_a_search_when_they_cannot_cut_off(tree):
    ai, root, _ = tree
    ai._cache.put(CacheEntry(root.cache_key(), 1, None, 2.0, Bound.LOWER))
    assert ai._search_with_proof(root, 1, -math.inf, math.inf) == (3.0, True)
    assert ai._cache_score_hits == 0


def test_white_player_minimizes_and_upper_bound_can_cut_off(monkeypatch):
    root = TreeState("white-root", COLOR.WHITE)
    actions = [GameAction(GameActionType.MOVE, 1, 2),
               GameAction(GameActionType.MOVE, 1, 3)]
    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", False)
    monkeypatch.setattr(
        GameSimulation, "available_actions",
        lambda state: actions if state == root else [],
    )
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action",
        lambda state, action: TreeState(str(action.destination), COLOR.BLACK),
    )
    monkeypatch.setattr(ChessAI, "_order_actions", lambda self, state, moves: list(moves))
    monkeypatch.setattr(
        ChessAI, "evaluate", staticmethod(
            lambda state: -2.0 if state.name == "2" else 3.0),
    )
    ai = ChessAI(SearchConfig(cache_max_entries=32), max_workers=1)
    ai._deadline = time.monotonic() + 10
    assert ai._search_with_proof(root, 1, 0.0, math.inf) == (-2.0, True)
    assert ai._cache.get(root.cache_key(), 1).bound == Bound.UPPER
    assert ai._search_with_proof(root, 1, 0.0, math.inf) == (-2.0, True)
    assert ai._cache_score_hits == 1


def test_transposed_subtree_preserves_fixed_depth_score_with_cache(monkeypatch):
    root = TreeState("root", COLOR.BLACK)
    w1 = TreeState("w1", COLOR.WHITE)
    w2 = TreeState("w2", COLOR.WHITE)
    shared = TreeState("shared", COLOR.BLACK)
    leaf4 = TreeState("four", COLOR.WHITE)
    leaf1 = TreeState("one", COLOR.WHITE)
    leaf3 = TreeState("three", COLOR.BLACK)
    leaf2 = TreeState("two", COLOR.BLACK)
    actions = [GameAction(GameActionType.MOVE, 1, 2),
               GameAction(GameActionType.MOVE, 1, 3)]
    edges = {
        root: (w1, w2), w1: (shared, leaf3), w2: (shared, leaf2),
        shared: (leaf4, leaf1),
    }
    values = {"four": 4.0, "one": 1.0, "three": 3.0, "two": 2.0}
    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", False)
    monkeypatch.setattr(
        GameSimulation, "available_actions", lambda state: actions if state in edges else [])
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action",
        lambda state, action: edges[state][actions.index(action)],
    )
    monkeypatch.setattr(ChessAI, "_order_actions", lambda self, state, moves: list(moves))
    monkeypatch.setattr(ChessAI, "evaluate", staticmethod(lambda state: values[state.name]))

    scores = []
    for enabled in (False, True):
        ai = ChessAI(SearchConfig(cache_enabled=enabled, cache_max_entries=32),
                     max_workers=1)
        ai._deadline = time.monotonic() + 10
        scores.append(ai._search(root, 3, -math.inf, math.inf))
        if enabled:
            assert ai._cache_score_hits > 0
    assert scores == [3.0, 3.0]


def test_scores_are_not_reused_at_another_depth(tree):
    ai, root, _ = tree
    ai._cache.put(CacheEntry(root.cache_key(), 2, None, 99.0, Bound.EXACT))
    assert ai._search_with_proof(root, 1, -math.inf, math.inf) == (3.0, True)
    assert ai._cache_score_hits == 0


def test_illegal_cached_move_is_not_used(tree):
    ai, root, _ = tree
    illegal = GameAction(GameActionType.MOVE, 50, 51)
    ai._cache.put(CacheEntry(root.cache_key(), 2, illegal, 99.0, None))
    assert ai._search(root, 1, -math.inf, math.inf) == 3.0
    assert ai._cache_hints == 0


def test_lmr_without_full_research_cannot_produce_a_cached_bound(monkeypatch):
    root = TreeState("root", COLOR.BLACK)
    actions = [GameAction(GameActionType.MOVE, 1, index) for index in range(2, 6)]
    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", True)
    monkeypatch.setattr(
        GameSimulation, "available_actions",
        lambda state: actions if state == root else [],
    )
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action",
        lambda state, action: TreeState(str(action.destination), COLOR.WHITE),
    )
    monkeypatch.setattr(ChessAI, "_order_actions", lambda self, state, moves: list(moves))
    monkeypatch.setattr(ChessAI, "_king_position", staticmethod(lambda state, color: None))
    monkeypatch.setattr(
        ChessAI, "_should_reduce_late_move",
        staticmethod(lambda state, action, depth, index: index >= 3),
    )
    monkeypatch.setattr(ChessAI, "_move_attacks_king", staticmethod(lambda *args: False))
    monkeypatch.setattr(
        ChessAI, "evaluate",
        staticmethod(lambda state: 10.0 if state.name == "2" else 0.0),
    )
    ai = ChessAI(SearchConfig(cache_max_entries=32), max_workers=1)
    ai._deadline = time.monotonic() + 10
    score, reliable = ai._search_with_proof(root, 3, -math.inf, math.inf)
    assert score == 10.0
    assert not reliable
    assert ai._cache.get(root.cache_key(), 3).bound is None
    before_nodes = ai._nodes
    ai._search(root, 3, -math.inf, math.inf)
    assert ai._nodes > before_nodes + 1


def test_fully_researched_lmr_move_can_produce_a_reliable_result(monkeypatch):
    root = TreeState("root", COLOR.BLACK)
    actions = [GameAction(GameActionType.MOVE, 1, index) for index in range(2, 6)]
    monkeypatch.setattr("logic.chess_ai._LMR_ENABLED", True)
    monkeypatch.setattr(
        GameSimulation, "available_actions",
        lambda state: actions if state == root else [],
    )
    monkeypatch.setattr(
        GameSimulation, "_apply_generated_action",
        lambda state, action: TreeState(str(action.destination), COLOR.WHITE),
    )
    monkeypatch.setattr(ChessAI, "_order_actions", lambda self, state, moves: list(moves))
    monkeypatch.setattr(ChessAI, "_king_position", staticmethod(lambda state, color: None))
    monkeypatch.setattr(
        ChessAI, "_should_reduce_late_move",
        staticmethod(lambda state, action, depth, index: index >= 3),
    )
    monkeypatch.setattr(ChessAI, "_move_attacks_king", staticmethod(lambda *args: False))
    monkeypatch.setattr(
        ChessAI, "evaluate",
        staticmethod(lambda state: 10.0 if state.name == "5" else 0.0),
    )
    ai = ChessAI(SearchConfig(cache_max_entries=32), max_workers=1)
    ai._deadline = time.monotonic() + 10
    score, reliable = ai._search_with_proof(root, 3, -math.inf, math.inf)
    assert (score, reliable) == (10.0, True)
    assert ai._cache.get(root.cache_key(), 3).bound == Bound.EXACT


def test_timeout_does_not_save_unfinished_node(tree, monkeypatch):
    ai, root, _ = tree
    checks = 0

    def check_deadline():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise _SearchTimeout

    monkeypatch.setattr(ai, "_check_deadline", check_deadline)
    with pytest.raises(_SearchTimeout):
        ai._search(root, 1, -math.inf, math.inf)
    assert ai._cache.get(root.cache_key(), 1) is None


def test_worker_returns_completed_entries_when_root_times_out(monkeypatch):
    state = populated_state()
    action = GameSimulation.available_actions(state)[0]
    entry = CacheEntry(("completed",), 1, action, 1.0, Bound.EXACT)

    def interrupted(worker, child, depth, alpha, beta):
        worker._cache.put(entry)
        raise _SearchTimeout

    monkeypatch.setattr(ChessAI, "_search", interrupted)
    result = _evaluate_root_action(
        state, action, 2, SearchConfig(cache_max_entries=4), time.monotonic() + 10)
    assert result.score is None
    assert result.entries == (entry,)


def test_worker_caches_double_move_continuation_for_same_player():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK, 57)
    state.black_cards = [EnchantmentCardType.PIECE_DOUBLE_MOVE.create(uses=2)]
    action = next(
        action for action in GameSimulation.available_actions(state)
        if action.card_index == 0
    )
    next_state = GameSimulation.apply(state, action)
    assert next_state.current_turn == COLOR.BLACK
    assert next_state.double_move_step == 1
    result = _evaluate_root_action(
        state, action, 2, SearchConfig(cache_max_entries=32), time.monotonic() + 10)
    key = GameObservation.from_state(next_state, COLOR.BLACK).to_state().cache_key()
    entry = next(entry for entry in result.entries if entry.key == key)
    assert entry.action in GameSimulation.available_actions(next_state)


def test_disabled_cache_never_creates_or_reads_keys(monkeypatch):
    state = populated_state()
    observation = GameObservation.from_state(state, COLOR.BLACK)

    def unexpected_key(self):
        pytest.fail("disabled cache must not inspect state keys")

    monkeypatch.setattr(GameState, "cache_key", unexpected_key)
    ai = ChessAI(SearchConfig(time_limit_seconds=5, max_depth=1, cache_enabled=False),
                 max_workers=1)
    result = ai.choose_action(observation)
    assert result.action in GameSimulation.available_actions(state)
    assert ai._cache is None


def test_cached_root_hint_preserves_original_tie_breaking(monkeypatch):
    state = populated_state()
    ai = ChessAI(SearchConfig(time_limit_seconds=5, max_depth=1, cache_max_entries=8),
                 max_workers=1)
    actions = ai._order_actions(state, GameSimulation.available_actions(state))
    hint = actions[-1]
    ai._cache.put(CacheEntry(state.cache_key(), 1, hint, 0.0, None))
    monkeypatch.setattr(ChessAI, "evaluate", staticmethod(lambda state: 0.0))
    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action",
        lambda state, action, depth, config, deadline, snapshot: _RootEvaluation(0.0, 1),
    )
    updates = []
    result = ai.choose_action(
        GameObservation.from_state(state, COLOR.BLACK),
        candidate_callback=lambda action, depth, score: updates.append((action, depth)),
    )
    assert updates[0] == (hint, 0)
    assert result.action == actions[0]


def test_reset_during_search_cannot_restore_previous_entries(monkeypatch):
    state = populated_state()
    observation = GameObservation.from_state(state, COLOR.BLACK)
    ai = ChessAI(SearchConfig(time_limit_seconds=5, max_depth=1, cache_max_entries=8),
                 max_workers=1)
    entry = CacheEntry(("old",), 1, None, 1.0, Bound.EXACT)
    calls = 0

    def root_result(search_state, action, depth, config, deadline, snapshot):
        nonlocal calls
        calls += 1
        if calls == 1:
            ai.clear_search_cache()
        return _RootEvaluation(1.0, 1, (entry,))

    monkeypatch.setattr("logic.chess_ai._evaluate_root_action", root_result)
    ai.choose_action(observation)
    assert calls > 0
    assert len(ai._cache) == 0


def test_search_queued_before_reset_cannot_populate_new_cache(monkeypatch):
    state = populated_state()
    ai = ChessAI(SearchConfig(time_limit_seconds=5, max_depth=1, cache_max_entries=8),
                 max_workers=1)
    generation = ai.search_cache_generation()
    ai.clear_search_cache()
    entry = CacheEntry(("old",), 1, None, 1.0, Bound.EXACT)
    monkeypatch.setattr(
        "logic.chess_ai._evaluate_root_action",
        lambda state, action, depth, config, deadline, snapshot:
            _RootEvaluation(1.0, 1, (entry,)),
    )
    ai.choose_action(
        GameObservation.from_state(state, COLOR.BLACK), cache_generation=generation)
    assert len(ai._cache) == 0


def test_cache_remembers_legal_move_after_real_opponent_response():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    state.pieces_locations[64] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    state.pieces_locations[8] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    ai = ChessAI(SearchConfig(time_limit_seconds=15, max_depth=3, cache_max_entries=512),
                 max_workers=1)
    result = ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))
    assert result.completed_depth == 3
    child = GameSimulation.apply(state, result.action)
    for response in GameSimulation.available_actions(child):
        next_state = GameSimulation.apply(child, response)
        observation = GameObservation.from_state(next_state, COLOR.BLACK)
        hint = ai._cache.best_move(observation.to_state().cache_key())
        if hint is not None:
            assert hint in GameSimulation.available_actions(next_state)
            ai.config = SearchConfig(
                time_limit_seconds=1e-12, max_depth=3, cache_max_entries=512)
            updates = []
            later = ai.choose_action(
                observation,
                candidate_callback=lambda action, depth, score: updates.append(action),
            )
            assert updates[0] == hint
            assert later.action == hint
            break
    else:
        pytest.fail("no remembered move matched any real opponent response")


def test_serial_and_parallel_search_use_equivalent_warm_snapshots():
    state = make_black_to_move_state()
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    state.white_cards = [EnchantmentCardType.PAWN_SWORDSMAN.create()]
    card = EnchantmentCardType.PIECE_TELEPORT.create()
    state.board_card_available = True
    state.board_enchantment = card
    state.board_cards = [(36, card)]
    observation = GameObservation.from_state(state, COLOR.BLACK)
    config = SearchConfig(time_limit_seconds=15, max_depth=2, cache_max_entries=128)
    serial = ChessAI(config, max_workers=1)
    initial = serial.choose_action(observation)
    assert initial.completed_depth == 2
    parallel = ChessAI(config, max_workers=2)
    for entry in serial._cache.snapshot(128):
        parallel._cache.put(entry)

    serial_result = serial.choose_action(observation)
    parallel_result = parallel.choose_action(observation)

    assert serial_result.completed_depth == parallel_result.completed_depth == 2
    assert serial_result.action == parallel_result.action
    assert serial_result.score == pytest.approx(parallel_result.score)
    assert serial._cache_score_hits > 0
    assert parallel._cache_score_hits > 0
