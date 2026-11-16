import math
import os
import secrets
from enum import Enum, IntEnum
from pathlib import Path

import yaml


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_CONFIG_PATH = Path(
    os.environ.get(
        "CHESS_RUN_CONFIG_PATH",
        str(_PROJECT_ROOT / "run.yaml"),
    )
)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from None
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate key {!r}".format(key),
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class RunMode(Enum):
    DEBUG = "DEBUG"
    PROD = "PROD"


class LogLevel(IntEnum):
    ERROR = 50
    WARN = 40
    INFO = 30
    LOGIC = 20
    DEBUG = 10
    OFF = 100


def _load_properties():
    """Odczytuje run.yaml i spłaszcza zagnieżdżone ustawienia do kluczy z kropkami."""
    properties_path = RUN_CONFIG_PATH
    try:
        with properties_path.open(encoding="utf-8") as config_file:
            config = yaml.load(config_file, Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as error:
        raise ValueError(
            "Invalid YAML in {}: {}".format(properties_path, error)
        ) from None

    if not isinstance(config, dict):
        raise ValueError(
            "Configuration in {} must be a YAML mapping".format(properties_path)
        )

    properties = {}

    def flatten(mapping, prefix=""):
        for key, value in mapping.items():
            if not isinstance(key, str) or not key:
                raise ValueError(
                    "Configuration keys in {} must be non-empty strings".format(
                        properties_path)
                )
            full_key = "{}.{}".format(prefix, key) if prefix else key
            if isinstance(value, dict):
                flatten(value, full_key)
            elif full_key in properties:
                raise ValueError(
                    "Duplicate setting '{}' in {}".format(
                        full_key, properties_path)
                )
            elif value is None:
                properties[full_key] = ""
            elif isinstance(value, bool):
                properties[full_key] = str(value).lower()
            elif isinstance(value, str):
                properties[full_key] = value.strip()
            elif isinstance(value, (int, float)):
                properties[full_key] = str(value)
            else:
                raise ValueError(
                    "Invalid value for '{}' in {}; expected a scalar".format(
                        full_key, properties_path)
                )

    flatten(config)
    return properties, properties_path


def _parse_cache_max_entries(value):
    multipliers = {"k": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
    multiplier = 1
    if value and value[-1] in multipliers:
        multiplier = multipliers[value[-1]]
        value = value[:-1]
    return int(value) * multiplier


def _load_run_config():
    """Waliduje ustawienia uruchomienia i zwraca je w postaci typowanej."""
    properties, properties_path = _load_properties()
    legacy_cpu_properties = {
        "ai.search.cpu_percent": "ai.search.cpu.workers and ai.search.cpu.worker_usage",
        "ai.search.ponder.cpu_percent": (
            "ai.search.ponder.cpu.workers and "
            "ai.search.ponder.cpu.worker_usage"
        ),
    }
    for key, replacement in legacy_cpu_properties.items():
        if key in properties:
            raise ValueError(
                "'{}' is no longer supported in {}; use {}".format(
                    key, properties_path, replacement)
            )
    if "mode" not in properties:
        raise ValueError("Missing 'mode' property in {}".format(properties_path))

    try:
        run_mode = RunMode(properties["mode"])
    except ValueError:
        raise ValueError(
            "Invalid mode {!r} in {}; expected DEBUG or PROD".format(
                properties["mode"], properties_path)
        ) from None

    log_level_value = properties.get("log.level", "WARN").upper()
    try:
        log_level = LogLevel[log_level_value]
    except KeyError:
        raise ValueError(
            "Invalid 'log.level' {!r} in {}; expected ERROR, WARN, INFO, LOGIC, "
            "DEBUG, or OFF".format(log_level_value, properties_path)
        ) from None
    game_seed_value = properties.get("game.seed", "").strip()
    game_seed = None
    if game_seed_value:
        try:
            game_seed = int(game_seed_value)
        except ValueError:
            raise ValueError(
                "Invalid 'game.seed' in {}; expected an integer".format(properties_path)
            ) from None

    try:
        ai_search_max_depth = int(properties.get("ai.search.max_depth", "4"))
    except ValueError:
        raise ValueError(
            "Invalid 'ai.search.max_depth' in {}; expected a positive integer".format(
                properties_path)
        ) from None
    try:
        ai_search_time_limit_seconds = float(
            properties.get("ai.search.time_limit_seconds", "2.0"))
    except ValueError:
        raise ValueError(
            "Invalid 'ai.search.time_limit_seconds' in {}; expected a positive number".format(
                properties_path)
        ) from None

    try:
        ai_search_cpu_workers = int(properties.get("ai.search.cpu.workers", "1"))
    except ValueError:
        raise ValueError(
            "Invalid 'ai.search.cpu.workers' in {}; expected a positive integer".format(
                properties_path)
        ) from None
    try:
        ai_search_cpu_worker_usage = int(
            properties.get("ai.search.cpu.worker_usage", "100"))
    except ValueError:
        raise ValueError(
            "Invalid 'ai.search.cpu.worker_usage' in {}; expected an integer "
            "from 1 to 100".format(properties_path)
        ) from None
    ai_search_ponder_enabled_value = properties.get(
        "ai.search.ponder.enabled", "true").lower()
    if ai_search_ponder_enabled_value not in ("true", "false"):
        raise ValueError(
            "'ai.search.ponder.enabled' must be true or false in {}".format(
                properties_path))
    try:
        ai_search_ponder_cpu_workers = int(
            properties.get(
                "ai.search.ponder.cpu.workers",
                properties.get("ai.search.cpu.workers", "1"),
            )
        )
    except ValueError:
        raise ValueError(
            "Invalid 'ai.search.ponder.cpu.workers' in {}; expected a positive "
            "integer".format(properties_path)
        ) from None
    try:
        ai_search_ponder_cpu_worker_usage = int(
            properties.get(
                "ai.search.ponder.cpu.worker_usage",
                properties.get("ai.search.cpu.worker_usage", "100"),
            )
        )
    except ValueError:
        raise ValueError(
            "Invalid 'ai.search.ponder.cpu.worker_usage' in {}; expected an "
            "integer from 1 to 100".format(properties_path)
        ) from None

    if ai_search_max_depth < 1:
        raise ValueError("'ai.search.max_depth' must be at least one in {}".format(properties_path))
    if not math.isfinite(ai_search_time_limit_seconds) or ai_search_time_limit_seconds <= 0:
        raise ValueError(
            "'ai.search.time_limit_seconds' must be a positive finite number in {}".format(
                properties_path))
    if ai_search_cpu_workers < 1:
        raise ValueError(
            "'ai.search.cpu.workers' must be at least one in {}".format(
                properties_path))
    if not 1 <= ai_search_cpu_worker_usage <= 100:
        raise ValueError(
            "'ai.search.cpu.worker_usage' must be between 1 and 100 in {}".format(
                properties_path))
    if ai_search_ponder_cpu_workers < 1:
        raise ValueError(
            "'ai.search.ponder.cpu.workers' must be at least one in {}".format(
                properties_path))
    if not 1 <= ai_search_ponder_cpu_worker_usage <= 100:
        raise ValueError(
            "'ai.search.ponder.cpu.worker_usage' must be between 1 and 100 in {}".format(
                properties_path))

    cache_enabled_value = properties.get("ai.search.cache.enabled", "true").lower()
    if cache_enabled_value not in ("true", "false"):
        raise ValueError(
            "'ai.search.cache.enabled' must be true or false in {}".format(
                properties_path))
    try:
        cache_max_entries = _parse_cache_max_entries(
            properties.get("ai.search.cache.max_entries", "2048"))
    except ValueError:
        raise ValueError(
            "'ai.search.cache.max_entries' must be a positive integer or use "
            "a k, M, or G suffix in {}".format(properties_path)) from None
    if cache_max_entries < 1:
        raise ValueError(
            "'ai.search.cache.max_entries' must be a positive integer or use "
            "a k, M, or G suffix in {}".format(properties_path))

    ai_search_metrics_enabled_value = properties.get(
        "ai.search.metrics.enabled", "false").lower()
    if ai_search_metrics_enabled_value not in ("true", "false"):
        raise ValueError(
            "'ai.search.metrics.enabled' must be true or false in {}".format(
                properties_path))

    return (
        run_mode,
        log_level,
        game_seed,
        ai_search_max_depth,
        ai_search_time_limit_seconds,
        ai_search_cpu_workers,
        ai_search_cpu_worker_usage,
        ai_search_ponder_enabled_value == "true",
        ai_search_ponder_cpu_workers,
        ai_search_ponder_cpu_worker_usage,
        cache_enabled_value == "true",
        cache_max_entries,
        ai_search_metrics_enabled_value == "true",
    )


(
    RUN_MODE,
    LOG_LEVEL,
    GAME_SEED,
    AI_SEARCH_MAX_DEPTH,
    AI_SEARCH_TIME_LIMIT_SECONDS,
    AI_SEARCH_CPU_WORKERS,
    AI_SEARCH_CPU_WORKER_USAGE,
    AI_SEARCH_PONDER_ENABLED,
    AI_SEARCH_PONDER_CPU_WORKERS,
    AI_SEARCH_PONDER_CPU_WORKER_USAGE,
    AI_SEARCH_CACHE_ENABLED,
    AI_SEARCH_CACHE_MAX_ENTRIES,
    AI_SEARCH_METRICS_ENABLED,
) = _load_run_config()


def resolve_game_seed():
    """Zwraca seed z konfiguracji lub losuje 64-bitowy seed dla nowej partii."""
    return GAME_SEED if GAME_SEED is not None else secrets.randbits(64)
