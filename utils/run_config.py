import math
import os
import secrets
from enum import Enum, IntEnum
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    if os.environ.get("CHESS_WEB_MODE") != "1":
        raise
    yaml = None

from utils.system_info import physical_memory_bytes


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_CONFIG_PATH = Path(
    os.environ.get(
        "CHESS_RUN_CONFIG_PATH",
        str(_PROJECT_ROOT / "run.yaml"),
    )
)


if yaml is None:
    class _UniqueKeySafeLoader:
        pass
else:
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


if yaml is not None:
    _UniqueKeySafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_unique_mapping,
    )


class RunMode(Enum):
    DEBUG = "DEBUG"
    PROD = "PROD"
    DIAG = "DIAG"


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
    if yaml is None:
        if os.environ.get("CHESS_WEB_MODE") != "1":
            raise RuntimeError("PyYAML is required to load run configuration")
        return {
            "mode": "PROD",
            "log.level": "WARN",
            "ai.search.learning.max_file_size": "16k",
            "ui.action_animation_duration_ms": "0",
        }, properties_path
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
    return _parse_binary_size(value)


def _parse_binary_size(value):
    multipliers = {"k": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
    multiplier = 1
    if value and value[-1] in multipliers:
        multiplier = multipliers[value[-1]]
        value = value[:-1]
    result = int(value) * multiplier
    if result < 1:
        raise ValueError("The size must be positive")
    return result


def _default_learning_max_file_size():
    try:
        return physical_memory_bytes() // 4
    except OSError as error:
        raise ValueError(
            "Unable to determine physical memory for the default "
            "'ai.search.learning.max_file_size'; set it explicitly"
        ) from error


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
            "Invalid mode {!r} in {}; expected DEBUG, PROD, or DIAG".format(
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

    learning_enabled_value = properties.get(
        "ai.search.learning.enabled", "false").lower()
    if learning_enabled_value not in ("true", "false"):
        raise ValueError(
            "'ai.search.learning.enabled' must be true or false in {}".format(
                properties_path))
    learning_save_enabled_value = properties.get(
        "ai.search.learning.save_enabled", "false").lower()
    if learning_save_enabled_value not in ("true", "false"):
        raise ValueError(
            "'ai.search.learning.save_enabled' must be true or false in "
            "{}".format(properties_path))
    learning_size_value = properties.get("ai.search.learning.max_file_size")
    if learning_size_value is None:
        learning_size_value = str(_default_learning_max_file_size())
    try:
        learning_max_file_size = _parse_binary_size(learning_size_value)
    except ValueError:
        raise ValueError(
            "'ai.search.learning.max_file_size' must be a positive integer "
            "or use a k, M, or G suffix in {}".format(properties_path)
        ) from None
    if learning_max_file_size < 16 * 1024:
        raise ValueError(
            "'ai.search.learning.max_file_size' must be at least 16k in "
            "{}".format(properties_path)
        )

    ai_search_metrics_enabled_value = properties.get(
        "ai.search.metrics.enabled", "false").lower()
    if ai_search_metrics_enabled_value not in ("true", "false"):
        raise ValueError(
            "'ai.search.metrics.enabled' must be true or false in {}".format(
                properties_path))

    try:
        ai_search_learning_soft_cutoff_threshold = float(
            properties.get(
                "ai.search.learning.soft_cutoff_threshold", "-20"))
    except ValueError:
        raise ValueError(
            "'ai.search.learning.soft_cutoff_threshold' must be a finite "
            "number in {}".format(properties_path)
        ) from None
    if not math.isfinite(ai_search_learning_soft_cutoff_threshold):
        raise ValueError(
            "'ai.search.learning.soft_cutoff_threshold' must be a finite "
            "number in {}".format(properties_path))

    ai_search_learning_database_path = properties.get(
        "ai.search.learning.database_path", "move-learning.sqlite3")
    if not ai_search_learning_database_path:
        raise ValueError(
            "'ai.search.learning.database_path' must be a non-empty path "
            "in {}".format(properties_path))

    try:
        ui_action_animation_duration_ms = int(
            properties.get("ui.action_animation_duration_ms", "0"))
    except ValueError:
        raise ValueError(
            "Invalid 'ui.action_animation_duration_ms' in {}; expected an "
            "integer from 0 to 2000".format(properties_path)
        ) from None
    if not 0 <= ui_action_animation_duration_ms <= 2000:
        raise ValueError(
            "'ui.action_animation_duration_ms' must be between 0 and 2000 "
            "in {}".format(properties_path)
        )

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
        learning_enabled_value == "true",
        learning_save_enabled_value == "true",
        learning_max_file_size,
        ai_search_metrics_enabled_value == "true",
        ai_search_learning_soft_cutoff_threshold,
        ai_search_learning_database_path,
        ui_action_animation_duration_ms,
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
    AI_SEARCH_LEARNING_ENABLED,
    AI_SEARCH_LEARNING_SAVE_ENABLED,
    AI_SEARCH_LEARNING_MAX_FILE_SIZE,
    AI_SEARCH_METRICS_ENABLED,
    AI_SEARCH_LEARNING_SOFT_CUTOFF_THRESHOLD,
    AI_SEARCH_LEARNING_DATABASE_PATH,
    UI_ACTION_ANIMATION_DURATION_MS,
) = _load_run_config()


def resolve_game_seed():
    """Zwraca seed z konfiguracji lub losuje 64-bitowy seed dla nowej partii."""
    return GAME_SEED if GAME_SEED is not None else secrets.randbits(64)
