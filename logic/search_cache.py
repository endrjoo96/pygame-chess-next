import heapq
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Optional, Tuple

from logic.game_rules import GameAction


class Bound(Enum):
    EXACT = "exact"
    LOWER = "lower"
    UPPER = "upper"


@dataclass(frozen=True)
class CacheEntry:
    key: tuple
    depth: int
    action: Optional[GameAction]
    score: float
    bound: Optional[Bound]
    root_scope_ids: frozenset = frozenset()


class SearchCache:
    """Ograniczona tabela transpozycji; brak granicy oznacza tylko wskazówkę ruchu."""

    def __init__(
        self,
        max_entries: int,
        on_size_change: Optional[Callable[[int], None]] = None,
    ):
        if max_entries < 1:
            raise ValueError("The search cache limit must be positive")
        self.max_entries = max_entries
        self._on_size_change = on_size_change
        self._entries = {}
        self._by_state = {}
        self._depth_counts = {}
        self._heap = []
        self._deepest_entry_depth = None
        self._sequence = 0
        self._updated = set()
        self._read = set()
        self.evictions = 0
        self._scope_ids = {}
        self._scope_keys = {}
        self._next_scope_id = 0

    @staticmethod
    def _quality(entry):
        return (entry.depth, entry.bound is not None, entry.bound == Bound.EXACT)

    def put(self, entry: CacheEntry, updated=True):
        size_before = len(self._entries)
        key = (entry.key, entry.depth)
        old = self._entries.get(key)
        if old is not None:
            old_entry, _ = old
            scopes = old_entry.root_scope_ids | entry.root_scope_ids
            if self._quality(old_entry) > self._quality(entry):
                if scopes == old_entry.root_scope_ids:
                    return
                entry = replace(old_entry, root_scope_ids=scopes)
            else:
                entry = replace(entry, root_scope_ids=scopes)
        else:
            self._depth_counts[entry.depth] = (
                self._depth_counts.get(entry.depth, 0) + 1
            )
        self._sequence += 1
        sequence = self._sequence
        self._entries[key] = (entry, sequence)
        self._by_state.setdefault(entry.key, {})[entry.depth] = entry
        if (
            self._deepest_entry_depth is None
            or entry.depth > self._deepest_entry_depth
        ):
            self._deepest_entry_depth = entry.depth
        heapq.heappush(self._heap, (*self._quality(entry), sequence, key))
        if updated:
            self._updated.add(key)
        while len(self._entries) > self.max_entries:
            self._evict()
        if len(self._heap) > self.max_entries * 2 + 128:
            self._heap = [
                (*self._quality(value[0]), value[1], item_key)
                for item_key, value in self._entries.items()
            ]
            heapq.heapify(self._heap)
        self._notify_size_change(size_before)

    def _evict(self):
        while self._heap:
            *_, sequence, key = heapq.heappop(self._heap)
            current = self._entries.get(key)
            if current is None or current[1] != sequence:
                continue
            del self._entries[key]
            state_key, depth = key
            by_depth = self._by_state[state_key]
            del by_depth[depth]
            if not by_depth:
                del self._by_state[state_key]
            depth_count = self._depth_counts[depth] - 1
            if depth_count:
                self._depth_counts[depth] = depth_count
            else:
                del self._depth_counts[depth]
            if depth == self._deepest_entry_depth:
                self._deepest_entry_depth = max(self._depth_counts, default=None)
            self._updated.discard(key)
            self._read.discard(key)
            self.evictions += 1
            return

    def get(self, key: tuple, depth: int) -> Optional[CacheEntry]:
        cache_key = (key, depth)
        value = self._entries.get(cache_key)
        if value is not None:
            self._read.add(cache_key)
        return value[0] if value else None

    def contains(self, key: tuple, depth: int) -> bool:
        return (key, depth) in self._entries

    def best_move(self, key: tuple) -> Optional[GameAction]:
        entries = self._by_state.get(key, {})
        choices = [entry for entry in entries.values() if entry.action is not None]
        if not choices:
            return None
        best_entry = max(choices, key=self._quality)
        self._read.add((best_entry.key, best_entry.depth))
        return best_entry.action

    @property
    def deepest_entry_depth(self):
        return self._deepest_entry_depth

    def scope_id_for(self, root_key: tuple, action: GameAction, create=False):
        scope_key = (root_key, action)
        scope_id = self._scope_ids.get(scope_key)
        if scope_id is None and create:
            scope_id = self._next_scope_id
            self._next_scope_id += 1
            self._scope_ids[scope_key] = scope_id
            self._scope_keys[scope_id] = scope_key
        return scope_id

    def retain_scope(self, scope_id: Optional[int]):
        size_before = len(self._entries)
        if scope_id is None:
            self._entries.clear()
            self._by_state.clear()
            self._depth_counts.clear()
            self._heap.clear()
            self._updated.clear()
            self._read.clear()
            self._scope_ids.clear()
            self._scope_keys.clear()
            self._deepest_entry_depth = None
            self._notify_size_change(size_before)
            return

        retained = {}
        for key, (entry, sequence) in self._entries.items():
            if scope_id not in entry.root_scope_ids:
                continue
            entry = replace(entry, root_scope_ids=frozenset((scope_id,)))
            retained[key] = (entry, sequence)
        self._entries = retained
        self._depth_counts = {}
        for (_, depth), _ in retained.items():
            self._depth_counts[depth] = self._depth_counts.get(depth, 0) + 1
        self._deepest_entry_depth = max(
            self._depth_counts, default=None,
        )
        self._by_state = {}
        for (state_key, depth), (entry, _) in retained.items():
            self._by_state.setdefault(state_key, {})[depth] = entry
        self._heap = [
            (*self._quality(entry), sequence, key)
            for key, (entry, sequence) in retained.items()
        ]
        heapq.heapify(self._heap)
        self._updated.intersection_update(retained)
        self._read.intersection_update(retained)
        scope_key = self._scope_keys.get(scope_id)
        self._scope_ids = {scope_key: scope_id} if scope_key is not None else {}
        self._scope_keys = {scope_id: scope_key} if scope_key is not None else {}
        self._notify_size_change(size_before)

    def _notify_size_change(self, size_before):
        size_after = len(self._entries)
        if self._on_size_change is not None and size_before != size_after:
            self._on_size_change(size_after)

    def snapshot(
        self, limit: int, updated_only=False, touched_only=False
    ) -> Tuple[CacheEntry, ...]:
        if touched_only:
            selected_keys = self._updated | self._read
            values = (
                self._entries[key]
                for key in selected_keys if key in self._entries
            )
        elif updated_only:
            values = (
                self._entries[key] for key in self._updated if key in self._entries
            )
        else:
            values = self._entries.values()
        selected = heapq.nlargest(
            limit, values, key=lambda value: (*self._quality(value[0]), value[1]))
        return tuple(entry for entry, _ in reversed(selected))

    def __len__(self):
        return len(self._entries)
