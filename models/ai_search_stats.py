from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class AIWorkerStats:
    worker_id: int
    state: str
    pid: Optional[int] = None
    is_local: bool = False
    cache_entries: Optional[int] = None
    visited_nodes: Optional[int] = None
    mode: str = "-"
    root: str = "-"
    search_depth: Optional[int] = None


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
    cache_deepest_entry_depth: Optional[int] = None
    workers: Tuple[AIWorkerStats, ...] = ()
    search_phase: Optional[str] = None
    current_depth: Optional[int] = None
    completed_search_depth: Optional[int] = None
    live_visited_nodes: Optional[int] = None
    ponder_white_actions_completed: Optional[int] = None
    ponder_white_actions_total: Optional[int] = None
    ponder_branches_generated: Optional[int] = None
    ponder_root_actions_completed: Optional[int] = None
    ponder_root_actions_discovered: Optional[int] = None
    ponder_depth_counts: Tuple[Tuple[int, int], ...] = ()
    ponder_max_branch_depth: Optional[int] = None
    ponder_dangerous_white_candidates: Tuple[
        Tuple[str, float, int], ...
    ] = ()
