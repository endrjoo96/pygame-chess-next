from dataclasses import dataclass


@dataclass(frozen=True)
class AISearchMetrics:
    wall_time_ns: int = 0
    observation_ns: int = 0
    visited_nodes: int = 0
    root_actions: int = 0
    action_generation_ns: int = 0
    action_generation_calls: int = 0
    generated_actions: int = 0
    action_ordering_ns: int = 0
    action_ordering_calls: int = 0
    actions_ordered: int = 0
    action_application_ns: int = 0
    action_application_calls: int = 0
    evaluation_ns: int = 0
    evaluation_calls: int = 0
    cache_key_ns: int = 0
    cache_lookup_ns: int = 0
    cache_store_ns: int = 0
    cache_probes: int = 0
    cache_hits: int = 0
    cache_score_hits: int = 0
    cache_hints: int = 0
    alpha_beta_cutoffs: int = 0
    lmr_probes: int = 0
    lmr_researches: int = 0
    worker_count: int = 0
    worker_tasks: int = 0
    worker_task_ns: int = 0
    worker_pool_startup_ns: int = 0
    worker_wait_ns: int = 0
