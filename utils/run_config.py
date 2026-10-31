import math
import secrets
from enum import Enum, IntEnum
from pathlib import Path


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
    """Odczytuje plik run.properties i zwraca słownik ustawień oraz jego ścieżkę."""
    properties_path = Path(__file__).resolve().parent.parent / "run.properties"
    properties = {}
    for line_number, line in enumerate(properties_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue

        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError("Invalid property at {}:{}".format(properties_path, line_number))
        key = key.strip()
        if key in properties:
            raise ValueError("Duplicate property '{}' in {}".format(key, properties_path))
        properties[key] = value.strip()
    return properties, properties_path


def _load_run_config():
    """Waliduje ustawienia uruchomienia i zwraca je w postaci typowanej."""
    properties, properties_path = _load_properties()
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
    game_seed = None
    if "game.seed" in properties:
        try:
            game_seed = int(properties["game.seed"])
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
        ai_search_cpu_percent = int(properties.get("ai.search.cpu_percent", "100"))
    except ValueError:
        raise ValueError(
            "Invalid 'ai.search.cpu_percent' in {}; expected an integer from 1 to 100".format(
                properties_path)
        ) from None

    if ai_search_max_depth < 1:
        raise ValueError("'ai.search.max_depth' must be at least one in {}".format(properties_path))
    if not math.isfinite(ai_search_time_limit_seconds) or ai_search_time_limit_seconds <= 0:
        raise ValueError(
            "'ai.search.time_limit_seconds' must be a positive finite number in {}".format(
                properties_path))
    if not 1 <= ai_search_cpu_percent <= 100:
        raise ValueError(
            "'ai.search.cpu_percent' must be between 1 and 100 in {}".format(
                properties_path))

    return (
        run_mode,
        log_level,
        game_seed,
        ai_search_max_depth,
        ai_search_time_limit_seconds,
        ai_search_cpu_percent,
    )


(
    RUN_MODE,
    LOG_LEVEL,
    GAME_SEED,
    AI_SEARCH_MAX_DEPTH,
    AI_SEARCH_TIME_LIMIT_SECONDS,
    AI_SEARCH_CPU_PERCENT,
) = _load_run_config()


def resolve_game_seed():
    """Zwraca seed z konfiguracji lub losuje 64-bitowy seed dla nowej partii."""
    return GAME_SEED if GAME_SEED is not None else secrets.randbits(64)
