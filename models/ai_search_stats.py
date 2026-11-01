from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class AIWorkerStats:
    worker_id: int
    state: str
    pid: Optional[int] = None
    is_local: bool = False
    cache_entries: Optional[int] = None


@dataclass(frozen=True)
class AISearchStats:
    is_searching: bool = False
    candidate_move: Optional[str] = None
    candidate_score: Optional[float] = None
    candidate_depth: Optional[int] = None
    final_move: Optional[str] = None
    final_score: Optional[float] = None
    completed_depth: Optional[int] = None
    visited_nodes: Optional[int] = None
    cache_enabled: Optional[bool] = None
    cache_entries: Optional[int] = None
    cache_limit: Optional[int] = None
    cache_evictions: Optional[int] = None
    workers: Tuple[AIWorkerStats, ...] = ()
