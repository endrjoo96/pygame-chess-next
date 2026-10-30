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
    """Waliduje wymagany tryb uruchomienia i zwraca tryb oraz ustawienie logowania."""
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
    return run_mode, log_debug_enabled


RUN_MODE, LOG_DEBUG_ENABLED = _load_run_config()
