from collections import Counter, defaultdict
from concurrent.futures import Future
from threading import Event

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.chess_ai import ChessAI, SearchConfig
from logic.game_simulation import GameSimulation
from models.chess_pieces import Piece
from models.game_observation import GameObservation
from models.game_state import GameState
import utils.logging as app_logging
from utils.run_config import LogLevel


class ImmediateExecutor:
    @staticmethod
    def submit(function, *args, **kwargs):
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as error:
            future.set_exception(error)
        return future

    @staticmethod
    def shutdown(wait=True, cancel_futures=False):
        return None


def _make_sparse_game_state():
    state = GameState(
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
    )
    state.pieces_locations[8] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    state.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    state.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state.pieces_locations[64] = Piece(COLOR.BLACK, PIECE_TYPE.KING)
    return state


def _log_cache_snapshot(stage, ai):
    cache = _search_cache(ai)
    entries = cache.snapshot(cache.max_entries)
    depths_by_scope = defaultdict(Counter)
    for entry in entries:
        scope = ",".join(map(str, sorted(entry.root_scope_ids))) or "unscoped"
        depths_by_scope[scope][entry.depth] += 1

    scope_shape = Counter(
        tuple(sorted(depth_counts.items()))
        for depth_counts in depths_by_scope.values()
    )
    depth_shape = dict(sorted(Counter(entry.depth for entry in entries).items()))
    app_logging.log_info(
        "CACHE [{}]: entries={}/{}, states={}, deepest_depth={}, "
        "depths={}, branches={}, branch_shapes={}".format(
            stage,
            len(entries),
            cache.max_entries,
            len({entry.key for entry in entries}),
            cache.deepest_entry_depth,
            depth_shape,
            len(depths_by_scope),
            dict(scope_shape),
        )
    )


def _search_cache(ai):
    cache = getattr(ai, "_cache")
    assert cache is not None
    return cache


def test_cache_logs_search_move_and_ponder_transition(monkeypatch):
    monkeypatch.setattr("utils.logging.LOG_LEVEL", LogLevel.INFO)
    state = _make_sparse_game_state()
    ai = ChessAI(
        SearchConfig(time_limit_seconds=1, max_depth=4, cache_max_entries=2048),
        max_workers=1,
        ponder_cpu_percent=100,
    )

    decision = ai.choose_action(GameObservation.from_state(state, COLOR.BLACK))
    assert decision.action is not None
    assert decision.action in GameSimulation.available_actions(state)
    # assert decision.completed_depth == 6
    _log_cache_snapshot("after AI search simulation", ai)
    cache_size_after_search = len(_search_cache(ai))
    assert cache_size_after_search > 0

    moved_state = GameSimulation.apply(state, decision.action)
    assert moved_state.current_turn == COLOR.WHITE
    _log_cache_snapshot("after applying AI move", ai)
    assert len(_search_cache(ai)) == cache_size_after_search

    ai._worker_pool = ImmediateExecutor()
    ai._worker_search_cancel_event = Event()

    def log_ponder_transition(**_kwargs):
        _log_cache_snapshot("ponder transition", ai)

    ai.prepare_workers = log_ponder_transition
    ponder_result = ai.ponder(moved_state, Event())
    _log_cache_snapshot("after pondering", ai)

    assert ponder_result.stopped_reason in {"max-depth", "cache-full"}
    assert len(_search_cache(ai)) > cache_size_after_search
