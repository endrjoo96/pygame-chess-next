import math
from enum import Enum
from pathlib import Path


class RunMode(Enum):
    DEBUG = "DEBUG"
    PROD = "PROD"


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

    log_debug_enabled = properties.get("log.debug.enabled", "false").lower() == "true"
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

    if ai_search_max_depth < 1:
        raise ValueError("'ai.search.max_depth' must be at least one in {}".format(properties_path))
    if not math.isfinite(ai_search_time_limit_seconds) or ai_search_time_limit_seconds <= 0:
        raise ValueError(
            "'ai.search.time_limit_seconds' must be a positive finite number in {}".format(
                properties_path))

    return (
        run_mode,
        log_debug_enabled,
        ai_search_max_depth,
        ai_search_time_limit_seconds,
    )


(
    RUN_MODE,
    LOG_DEBUG_ENABLED,
    AI_SEARCH_MAX_DEPTH,
    AI_SEARCH_TIME_LIMIT_SECONDS,
) = _load_run_config()
