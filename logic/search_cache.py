import heapq
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

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


class SearchCache:
    """Ograniczona tabela transpozycji; brak granicy oznacza tylko wskazówkę ruchu."""

    def __init__(self, max_entries: int):
        if max_entries < 1:
            raise ValueError("The search cache limit must be positive")
        self.max_entries = max_entries
        self._entries = {}
        self._by_state = {}
        self._heap = []
        self._sequence = 0
        self._updated = set()
        self.evictions = 0

    @staticmethod
    def _quality(entry):
        return (entry.depth, entry.bound is not None, entry.bound == Bound.EXACT)

    def put(self, entry: CacheEntry, updated=True):
        key = (entry.key, entry.depth)
        old = self._entries.get(key)
        if old is not None and self._quality(old[0]) > self._quality(entry):
            return
        self._sequence += 1
        sequence = self._sequence
        self._entries[key] = (entry, sequence)
        self._by_state.setdefault(entry.key, {})[entry.depth] = entry
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
            self._updated.discard(key)
            self.evictions += 1
            return

    def get(self, key: tuple, depth: int) -> Optional[CacheEntry]:
        value = self._entries.get((key, depth))
        return value[0] if value else None

    def best_move(self, key: tuple) -> Optional[GameAction]:
        entries = self._by_state.get(key, {})
        choices = [entry for entry in entries.values() if entry.action is not None]
        return max(choices, key=self._quality).action if choices else None

    def snapshot(self, limit: int, updated_only=False) -> Tuple[CacheEntry, ...]:
        values = (
            (self._entries[key] for key in self._updated if key in self._entries)
            if updated_only else self._entries.values()
        )
        selected = heapq.nlargest(
            limit, values, key=lambda value: (*self._quality(value[0]), value[1]))
        return tuple(entry for entry, _ in reversed(selected))

    def __len__(self):
        return len(self._entries)
