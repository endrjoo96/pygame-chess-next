import hashlib
import json
import math
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from constants.piece_color import COLOR
from logic.game_rules import GameAction, GameActionType
from models.game_state import GameState


_SCHEMA_VERSION = 3
_SEARCH_RESULT_EVALUATION_VERSION = 1
_MOVE_HINT_KEY_VERSION = 2
_LEGACY_MOVE_HINT_KEY_VERSIONS = (1,)
_MIN_DATABASE_SIZE_BYTES = 16 * 1024
_MAX_SIGNAL_COUNT = 255
_MAX_LOCAL_UPDATES = 2048
_MAX_LOCAL_SEARCH_RESULT_UPDATES = 8192
_MAX_HINTS_PER_POSITION = 32
_HINT_CACHE_SIZE = 2048
_SEARCH_RESULT_CACHE_SIZE = 2048
_PRUNE_BATCH_SIZE = 256
_WRITE_BATCH_SIZE = 128
_DAY_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class MoveLearningUpdate:
    position_key: str
    action_key: str
    preferred: int = 0
    cutoff: int = 0
    worst: int = 0


@dataclass(frozen=True)
class SearchResultUpdate:
    position_key: str
    action_key: str
    depth: int
    score: float
    bound: str
    evaluation_version: int = _SEARCH_RESULT_EVALUATION_VERSION
    kind: str = "cutoff"


def _stable_state_value(value):
    from enum import Enum

    if isinstance(value, Enum):
        return [
            "enum",
            value.__class__.__module__,
            value.__class__.__qualname__,
            _stable_state_value(value.value),
        ]
    if isinstance(value, tuple):
        return ["tuple", [_stable_state_value(item) for item in value]]
    if isinstance(value, list):
        return ["list", [_stable_state_value(item) for item in value]]
    if isinstance(value, dict):
        items = [
            [
                _stable_state_value(key),
                _stable_state_value(item),
            ]
            for key, item in value.items()
        ]
        items.sort(key=lambda item: json.dumps(
            item, separators=(",", ":"), sort_keys=True))
        return [
            "dict",
            items,
        ]
    if isinstance(value, float):
        return ["float", value.hex()]
    if callable(value):
        module = getattr(value, "__module__", None)
        name = getattr(value, "__qualname__", None)
        if module is not None and name is not None:
            return ["callable", module, name]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(
        "Unsupported value in persistent game-state key: {}".format(
            type(value).__name__))


def search_result_position_key(state, state_cache_key=None):
    if not isinstance(state, GameState):
        return None
    if state_cache_key is None:
        state_cache_key = state.cache_key()
    payload = [
        "search-state",
        _SEARCH_RESULT_EVALUATION_VERSION,
        _stable_state_value(state_cache_key),
    ]
    encoded = json.dumps(
        payload, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class SearchResultAccumulator:
    def __init__(self):
        self._updates = OrderedDict()

    def record(
        self, position_key, action, depth, score, bound, kind="cutoff",
    ):
        if (
            not isinstance(depth, int)
            or isinstance(depth, bool)
            or depth < 1
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(score)
        ):
            return
        bound_value = getattr(bound, "value", bound)
        if bound_value not in ("exact", "lower", "upper"):
            raise ValueError("Unknown search-result bound {!r}".format(bound))
        if kind not in ("best", "cutoff"):
            raise ValueError("Unknown search-result kind {!r}".format(kind))
        update = SearchResultUpdate(
            position_key,
            encode_action(action),
            depth,
            float(score),
            bound_value,
            _SEARCH_RESULT_EVALUATION_VERSION,
            kind,
        )
        key = (
            update.position_key,
            update.action_key,
            update.depth,
            update.bound,
            update.evaluation_version,
            update.kind,
        )
        previous = self._updates.get(key)
        if previous is not None:
            if bound_value == "lower" and previous.score > update.score:
                update = previous
            elif bound_value == "upper" and previous.score < update.score:
                update = previous
            self._updates.move_to_end(key)
        elif len(self._updates) >= _MAX_LOCAL_SEARCH_RESULT_UPDATES:
            self._updates.popitem(last=False)
        self._updates[key] = update

    def merge(self, updates):
        for update in updates:
            self.record(
                update.position_key,
                decode_action(update.action_key),
                update.depth,
                update.score,
                update.bound,
                update.kind,
            )

    def snapshot(self):
        return tuple(self._updates.values())


class MoveLearningAccumulator:
    def __init__(self):
        self._updates = OrderedDict()

    def record(self, position_key, action, signal):
        action_key = encode_action(action)
        key = position_key, action_key
        values = self._updates.get(key)
        if values is None:
            if len(self._updates) >= _MAX_LOCAL_UPDATES:
                self._updates.popitem(last=False)
            values = [0, 0, 0]
            self._updates[key] = values
        else:
            self._updates.move_to_end(key)
        signal_index = {"preferred": 0, "cutoff": 1, "worst": 2}.get(signal)
        if signal_index is None:
            raise ValueError("Unknown move-learning signal {!r}".format(signal))
        values[signal_index] = min(
            _MAX_SIGNAL_COUNT, values[signal_index] + 1)

    def merge(self, updates):
        for update in updates:
            key = update.position_key, update.action_key
            values = self._updates.get(key)
            if values is None:
                if len(self._updates) >= _MAX_LOCAL_UPDATES:
                    self._updates.popitem(last=False)
                values = [0, 0, 0]
                self._updates[key] = values
            else:
                self._updates.move_to_end(key)
            for index, count in enumerate((
                update.preferred, update.cutoff, update.worst,
            )):
                values[index] = min(
                    _MAX_SIGNAL_COUNT,
                    values[index] + max(0, count),
                )

    def snapshot(self):
        return tuple(
            MoveLearningUpdate(
                position_key,
                action_key,
                values[0],
                values[1],
                values[2],
            )
            for (position_key, action_key), values in self._updates.items()
        )


def default_move_learning_path(configured_path=None):
    if configured_path is None:
        configured_path = "move-learning.sqlite3"
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def is_plain_move(action):
    return (
        action.action_type in (
            GameActionType.MOVE,
            GameActionType.PROMOTE,
        )
        and action.card_index == -1
    )


def has_collectible_board_card(state):
    return (
        isinstance(state, GameState)
        and (state.board_card_available or bool(state.board_cards))
    )


def is_learning_position_eligible(state):
    if not isinstance(state, GameState):
        return False
    if state.get_winner() is not None:
        return False
    if (
        state.pending_board_card_delay is not None
        or state.rune_traps
        or has_collectible_board_card(state)
    ):
        return False
    if (
        state.selected_card is not None
        or state.selected_piece_position
        or state.selected_captured_piece is not None
        or state.double_move_step
        or state.double_move_collected_board_card
        or state.resurrection_moves
    ):
        return False
    for piece in state.pieces_locations.values():
        if not piece.exists():
            continue
        if piece.is_stunned() or piece.get_effects(
            state.turns_started[piece.get_color()]
        ):
            return False
    return True


def learning_position_key(state, version=_MOVE_HINT_KEY_VERSION):
    if not is_learning_position_eligible(state):
        return None
    position = [
        [
            square,
            piece.get_color().value,
            piece.get_type().value,
            piece.get_starting_position(),
            piece.has_moved(),
        ]
        for square, piece in sorted(state.pieces_locations.items())
        if piece.exists()
    ]
    payload = {
        "version": version,
        "turn": state.current_turn.value,
        "pieces": position,
        "en_passant_target": state.en_passant_target,
        "en_passant_targets": list(state.en_passant_targets),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def encode_action(action):
    payload = (
        action.action_type.value,
        action.source,
        action.destination,
        action.card_index,
        action.captured_color.value,
        action.captured_index,
        action.secondary_source,
    )
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def decode_action(action_key):
    values = json.loads(action_key)
    if not isinstance(values, list) or len(values) != 7:
        raise ValueError("Invalid serialized move-learning action")
    return GameAction(
        GameActionType(values[0]),
        values[1],
        values[2],
        values[3],
        COLOR(values[4]),
        values[5],
        values[6],
    )


class MoveLearningStore:
    """Versioned, bounded SQLite store for move hints and search results."""

    def __init__(self, path, max_file_size_bytes, read_only=False):
        if (
            not isinstance(max_file_size_bytes, int)
            or isinstance(max_file_size_bytes, bool)
            or max_file_size_bytes < _MIN_DATABASE_SIZE_BYTES
        ):
            raise ValueError(
                "The move-learning database limit must be at least {} bytes"
                .format(_MIN_DATABASE_SIZE_BYTES)
            )
        self.path = Path(path)
        self.max_file_size_bytes = max_file_size_bytes
        self.read_only = read_only
        self._connection = None
        self._lock = RLock()
        self._hint_cache = OrderedDict()
        self._search_result_cache = OrderedDict()
        self._supports_search_results = False
        self._supports_best_moves = False
        self._legacy_search_results = False
        self._connect()

    @classmethod
    def open_from_config(
        cls, enabled, save_enabled, max_file_size_bytes, path=None,
    ):
        if not enabled:
            return None
        if path is None:
            path = default_move_learning_path()
        if not save_enabled and not Path(path).exists():
            return None
        return cls(
            path,
            max_file_size_bytes,
            read_only=not save_enabled,
        )

    def _connect(self):
        if self.read_only:
            if not self.path.exists():
                return
            if self.path.stat().st_size > self.max_file_size_bytes:
                raise sqlite3.DatabaseError(
                    "Move-learning database exceeds its configured size limit"
                )
            uri = self.path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(
                uri, uri=True, timeout=1.0, check_same_thread=False,
                isolation_level=None,
            )
            try:
                connection.execute("PRAGMA query_only = ON")
                schema_version = self._check_schema(
                    connection, allow_uninitialized=False)
                self._supports_search_results = schema_version >= 2
                self._supports_best_moves = schema_version >= 3
                self._legacy_search_results = schema_version == 2
                self._connection = connection
            except Exception:
                connection.close()
                raise
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        connection = sqlite3.connect(
            str(self.path), timeout=1.0, check_same_thread=False,
            isolation_level=None,
        )
        try:
            connection.execute("PRAGMA busy_timeout = 1000")
            if is_new:
                connection.execute("PRAGMA page_size = 1024")
                connection.execute("PRAGMA auto_vacuum = INCREMENTAL")
            self._check_schema(connection, allow_uninitialized=True)
            self._supports_search_results = True
            self._supports_best_moves = True
            self._legacy_search_results = False
            self._connection = connection
            self._enforce_size_limit()
            self._set_max_page_count()
        except Exception:
            connection.close()
            self._connection = None
            raise

    @staticmethod
    def _check_schema(connection, allow_uninitialized):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0 and allow_uninitialized:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if tables:
                raise sqlite3.DatabaseError(
                    "Move-learning database has no supported schema version"
                )
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
                CREATE INDEX move_hints_last_seen
                    ON move_hints(last_seen);
                CREATE TABLE search_cutoffs (
                    position_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    score REAL NOT NULL,
                    bound TEXT NOT NULL CHECK (
                        bound IN ('exact', 'lower', 'upper')
                    ),
                    evaluation_version INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    PRIMARY KEY (
                        position_key, action_key, depth,
                        evaluation_version, bound
                    )
                );
                CREATE TABLE best_moves (
                    position_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    score REAL NOT NULL,
                    evaluation_version INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    PRIMARY KEY (position_key, evaluation_version)
                );
                PRAGMA user_version = 3;
                """
            )
            version = _SCHEMA_VERSION
        if version == 1 and allow_uninitialized:
            connection.executescript(
                """
                CREATE TABLE search_cutoffs (
                    position_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    score REAL NOT NULL,
                    bound TEXT NOT NULL CHECK (
                        bound IN ('exact', 'lower', 'upper')
                    ),
                    evaluation_version INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    PRIMARY KEY (
                        position_key, action_key, depth,
                        evaluation_version, bound
                    )
                );
                CREATE TABLE best_moves (
                    position_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    score REAL NOT NULL,
                    evaluation_version INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    PRIMARY KEY (position_key, evaluation_version)
                );
                PRAGMA user_version = 3;
                """
            )
            version = 3
        if version == 2 and allow_uninitialized:
            connection.executescript(
                """
                ALTER TABLE search_results RENAME TO search_cutoffs;
                CREATE TABLE best_moves (
                    position_key TEXT NOT NULL,
                    action_key TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    score REAL NOT NULL,
                    evaluation_version INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    PRIMARY KEY (position_key, evaluation_version)
                );
                PRAGMA user_version = 3;
                """
            )
            version = 3
        if version not in (1, 2, _SCHEMA_VERSION):
            raise sqlite3.DatabaseError(
                "Unsupported move-learning database schema version {}".format(
                    version)
            )
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'move_hints'"
        ).fetchone()
        if table is None:
            raise sqlite3.DatabaseError(
                "Move-learning database is missing its hint table"
            )
        if version == 2:
            results_table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'search_results'"
            ).fetchone()
            if results_table is None:
                raise sqlite3.DatabaseError(
                    "Move-learning database is missing its search-result table"
                )
        if version >= 3:
            for table_name in ("search_cutoffs", "best_moves"):
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name = ?",
                    (table_name,),
                ).fetchone()
                if table is None:
                    raise sqlite3.DatabaseError(
                        "Move-learning database is missing its {} table"
                        .format(table_name))
        return version

    def _page_size(self):
        return self._connection.execute(
            "PRAGMA page_size"
        ).fetchone()[0]

    def _set_max_page_count(self):
        page_size = self._page_size()
        max_pages = max(1, self.max_file_size_bytes // page_size)
        actual = self._connection.execute(
            "PRAGMA max_page_count = {}".format(max_pages)
        ).fetchone()[0]
        page_count = self._connection.execute(
            "PRAGMA page_count"
        ).fetchone()[0]
        if actual > max_pages or page_count > max_pages:
            raise sqlite3.DatabaseError(
                "Move-learning database cannot fit within its configured limit"
            )

    def _enforce_size_limit(self):
        while self.path.exists() and self.path.stat().st_size > self.max_file_size_bytes:
            row_count = sum(
                self._connection.execute(
                    "SELECT COUNT(*) FROM {}".format(table)
                ).fetchone()[0]
                for table in self._storage_tables()
            )
            if row_count == 0:
                raise sqlite3.DatabaseError(
                    "Move-learning database schema exceeds its configured limit"
                )
            self._delete_oldest(max(
                1, min(_PRUNE_BATCH_SIZE, row_count // 8 or 1)))

    def _delete_oldest(self, count):
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            tables = self._storage_tables()
            oldest = []
            for table in tables:
                row = self._connection.execute(
                    "SELECT MIN(last_seen) FROM {}".format(table)
                ).fetchone()[0]
                if row is not None:
                    oldest.append((row, table))
            if oldest:
                _, table = min(oldest)
                self._connection.execute(
                    "DELETE FROM {} WHERE rowid IN ("
                    "SELECT rowid FROM {} "
                    "ORDER BY last_seen ASC, rowid ASC LIMIT ?)".format(
                        table, table),
                    (count,),
                )
            self._connection.execute("COMMIT")
        except sqlite3.Error:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        self._connection.execute(
            "PRAGMA incremental_vacuum({})".format(count))
        self._hint_cache.clear()
        self._search_result_cache.clear()

    def _storage_tables(self):
        tables = ["move_hints"]
        if self._legacy_search_results:
            tables.append("search_results")
        elif self._supports_search_results:
            tables.append("search_cutoffs")
        if self._supports_best_moves:
            tables.append("best_moves")
        return tables

    def get_action_scores(self, state, actions):
        current_position_key = learning_position_key(state)
        if current_position_key is None:
            return {}
        scores = self.get_hints(current_position_key, actions)
        for version in _LEGACY_MOVE_HINT_KEY_VERSIONS:
            legacy_key = learning_position_key(state, version)
            if legacy_key is None or legacy_key == current_position_key:
                continue
            for action, score in self.get_hints(legacy_key, actions).items():
                scores.setdefault(action, score)
        return scores

    def get_search_results(
        self, state, legal_actions=None, state_key=None,
    ):
        if self._connection is None or not self._supports_search_results:
            return {}
        position_key = state_key or search_result_position_key(state)
        if position_key is None:
            return {}
        cache_key = (position_key, _SEARCH_RESULT_EVALUATION_VERSION)
        with self._lock:
            cached = self._search_result_cache.get(cache_key)
            if cached is None:
                cached = {}
                if self._legacy_search_results:
                    cutoff_rows = self._connection.execute(
                        "SELECT action_key, depth, score, bound, "
                        "evaluation_version FROM search_results "
                        "WHERE position_key = ? AND evaluation_version = ? "
                        "ORDER BY depth DESC, last_seen DESC",
                        cache_key,
                    ).fetchall()
                elif self._supports_search_results:
                    cutoff_rows = self._connection.execute(
                        "SELECT action_key, depth, score, bound, "
                        "evaluation_version FROM search_cutoffs "
                        "WHERE position_key = ? AND evaluation_version = ? "
                        "ORDER BY depth DESC, last_seen DESC",
                        cache_key,
                    ).fetchall()
                else:
                    cutoff_rows = ()
                for action_key, depth, score, bound, evaluation_version in cutoff_rows:
                    try:
                        action = decode_action(action_key)
                    except (ValueError, TypeError, json.JSONDecodeError) as error:
                        raise sqlite3.DatabaseError(
                            "Invalid persistent search action: {}".format(error)
                        ) from None
                    cached.setdefault(action, []).append(SearchResultUpdate(
                        position_key,
                        action_key,
                        depth,
                        score,
                        bound,
                        evaluation_version,
                        "cutoff",
                    ))
                if self._supports_best_moves:
                    best_rows = self._connection.execute(
                        "SELECT action_key, depth, score, evaluation_version "
                        "FROM best_moves WHERE position_key = ? "
                        "AND evaluation_version = ?",
                        cache_key,
                    ).fetchall()
                    for action_key, depth, score, evaluation_version in best_rows:
                        try:
                            action = decode_action(action_key)
                        except (
                            ValueError, TypeError, json.JSONDecodeError,
                        ) as error:
                            raise sqlite3.DatabaseError(
                                "Invalid persistent best action: {}".format(
                                    error)
                            ) from None
                        cached.setdefault(action, []).append(
                            SearchResultUpdate(
                                position_key,
                                action_key,
                                depth,
                                score,
                                "exact",
                                evaluation_version,
                                "best",
                            ))
                cached = {
                    action: tuple(records)
                    for action, records in cached.items()
                }
                self._search_result_cache[cache_key] = cached
                if len(self._search_result_cache) > _SEARCH_RESULT_CACHE_SIZE:
                    self._search_result_cache.popitem(last=False)
            else:
                self._search_result_cache.move_to_end(cache_key)
            if legal_actions is None:
                return dict(cached)
            legal = set(legal_actions)
            return {
                action: records
                for action, records in cached.items()
                if action in legal
            }

    def clear_hint_cache(self):
        with self._lock:
            self._hint_cache.clear()

    def get_hints(self, position_key, legal_actions=None):
        if self._connection is None:
            return {}
        with self._lock:
            cached = self._hint_cache.get(position_key)
            if cached is None:
                rows = self._connection.execute(
                    "SELECT action_key, preferred_count, cutoff_count, "
                    "worst_count, last_seen FROM move_hints "
                    "WHERE position_key = ? "
                    "ORDER BY (preferred_count + 2 * cutoff_count - "
                    "2 * worst_count) DESC, last_seen DESC "
                    "LIMIT ?",
                    (position_key, _MAX_HINTS_PER_POSITION),
                ).fetchall()
                now = int(time.time())
                cached = {}
                for action_key, preferred, cutoff, worst, last_seen in rows:
                    try:
                        action = decode_action(action_key)
                    except (ValueError, TypeError, json.JSONDecodeError) as error:
                        raise sqlite3.DatabaseError(
                            "Invalid move-learning action record: {}".format(error)
                        ) from None
                    raw_score = preferred + 2 * cutoff - 2 * worst
                    age_days = max(0, now - last_seen) / _DAY_SECONDS
                    cached[action] = math.tanh(raw_score / 8.0) * math.exp(
                        -age_days / 180.0)
                self._hint_cache[position_key] = cached
                if len(self._hint_cache) > _HINT_CACHE_SIZE:
                    self._hint_cache.popitem(last=False)
            else:
                self._hint_cache.move_to_end(position_key)
            if legal_actions is None:
                return dict(cached)
            legal = set(legal_actions)
            return {
                action: score for action, score in cached.items()
                if action in legal
            }

    def apply_updates(self, updates):
        if not updates:
            return
        if self.read_only or self._connection is None:
            raise RuntimeError("The move-learning store is not writable")
        with self._lock:
            batch_size = min(_WRITE_BATCH_SIZE, len(updates))
            offset = 0
            while offset < len(updates):
                batch = updates[offset:offset + batch_size]
                try:
                    self._write_updates(batch)
                except sqlite3.OperationalError as error:
                    if "full" not in str(error).lower():
                        raise
                    row_count = self._search_result_row_count()
                    if row_count:
                        self._delete_oldest(max(
                            1,
                            min(_PRUNE_BATCH_SIZE, row_count // 8 or 1),
                        ))
                    elif batch_size > 1:
                        batch_size = max(1, batch_size // 2)
                    else:
                        raise
                    continue
                offset += len(batch)
            self._hint_cache.clear()
            self._enforce_size_limit()
            self._set_max_page_count()

    def apply_search_result_updates(self, updates):
        if not updates:
            return
        if self.read_only or self._connection is None:
            raise RuntimeError("The move-learning store is not writable")
        if not self._supports_search_results or not self._supports_best_moves:
            raise sqlite3.DatabaseError(
                "The move-learning database does not support search results")
        with self._lock:
            batch_size = min(_WRITE_BATCH_SIZE, len(updates))
            offset = 0
            while offset < len(updates):
                batch = updates[offset:offset + batch_size]
                try:
                    self._write_search_result_updates(batch)
                except sqlite3.OperationalError as error:
                    if "full" not in str(error).lower():
                        raise
                    row_count = self._search_result_row_count()
                    if row_count:
                        self._delete_oldest(max(
                            1,
                            min(_PRUNE_BATCH_SIZE, row_count // 8 or 1),
                        ))
                    elif batch_size > 1:
                        batch_size = max(1, batch_size // 2)
                    else:
                        raise
                    continue
                offset += len(batch)
            self._search_result_cache.clear()
            self._enforce_size_limit()
            self._set_max_page_count()

    def _write_search_result_updates(self, updates):
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            now = int(time.time())
            for update in updates:
                if (
                    update.depth < 1
                    or update.evaluation_version
                    != _SEARCH_RESULT_EVALUATION_VERSION
                    or update.bound not in ("exact", "lower", "upper")
                    or update.kind not in ("best", "cutoff")
                    or not math.isfinite(update.score)
                ):
                    continue
                if update.kind == "best":
                    if update.bound != "exact":
                        continue
                    connection.execute(
                        """
                        INSERT INTO best_moves (
                            position_key, action_key, depth, score,
                            evaluation_version, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT (position_key, evaluation_version)
                        DO UPDATE SET
                            action_key = excluded.action_key,
                            depth = excluded.depth,
                            score = excluded.score,
                            last_seen = excluded.last_seen
                        WHERE excluded.depth >= best_moves.depth
                        """,
                        (
                            update.position_key,
                            update.action_key,
                            update.depth,
                            update.score,
                            update.evaluation_version,
                            now,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO search_cutoffs (
                            position_key, action_key, depth, score, bound,
                            evaluation_version, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (
                            position_key, action_key, depth,
                            evaluation_version, bound
                        ) DO UPDATE SET
                            score = CASE
                                WHEN excluded.bound = 'lower'
                                    THEN MAX(search_cutoffs.score, excluded.score)
                                WHEN excluded.bound = 'upper'
                                    THEN MIN(search_cutoffs.score, excluded.score)
                                ELSE excluded.score
                            END,
                            last_seen = excluded.last_seen
                        """,
                        (
                            update.position_key,
                            update.action_key,
                            update.depth,
                            update.score,
                            update.bound,
                            update.evaluation_version,
                            now,
                        ),
                    )
            connection.execute("COMMIT")
        except sqlite3.Error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    def _search_result_row_count(self):
        return sum(
            self._connection.execute(
                "SELECT COUNT(*) FROM {}".format(table)
            ).fetchone()[0]
            for table in self._storage_tables()
        )

    def _write_updates(self, updates):
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            now = int(time.time())
            for update in updates:
                connection.execute(
                    """
                    INSERT INTO move_hints (
                        position_key, action_key, preferred_count,
                        cutoff_count, worst_count, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(position_key, action_key) DO UPDATE SET
                        preferred_count = MIN(?, preferred_count + excluded.preferred_count),
                        cutoff_count = MIN(?, cutoff_count + excluded.cutoff_count),
                        worst_count = MIN(?, worst_count + excluded.worst_count),
                        last_seen = excluded.last_seen
                    """,
                    (
                        update.position_key,
                        update.action_key,
                        min(_MAX_SIGNAL_COUNT, update.preferred),
                        min(_MAX_SIGNAL_COUNT, update.cutoff),
                        min(_MAX_SIGNAL_COUNT, update.worst),
                        now,
                        _MAX_SIGNAL_COUNT,
                        _MAX_SIGNAL_COUNT,
                        _MAX_SIGNAL_COUNT,
                    ),
                )
            connection.execute("COMMIT")
        except sqlite3.Error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._hint_cache.clear()
            self._search_result_cache.clear()
