import os
import sys
from datetime import datetime

from utils.run_config import LOG_LEVEL, LogLevel


LEVEL_COLORS = {
    LogLevel.ERROR: "\033[31m",
    LogLevel.WARN: "\033[33m",
    LogLevel.INFO: "\033[36m",
    LogLevel.LOGIC: "\033[32m",
    LogLevel.DEBUG: "\033[90m",
}
RESET_COLOR = "\033[0m"


def is_enabled(level):
    """Zwraca, czy komunikaty danego poziomu są włączone przez konfigurację."""
    if not isinstance(level, LogLevel):
        level = LogLevel[str(level).upper()]
    return LOG_LEVEL != LogLevel.OFF and level != LogLevel.OFF and level >= LOG_LEVEL


def _supports_color(stream):
    isatty = getattr(stream, "isatty", None)
    return "NO_COLOR" not in os.environ and callable(isatty) and isatty()


def log(level, message):
    """Wypisuje komunikat z czasem i poziomem, jeśli próg konfiguracji na to pozwala."""
    if not isinstance(level, LogLevel):
        level = LogLevel[str(level).upper()]
    if is_enabled(level):
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        if _supports_color(sys.stdout):
            prefix = "{}[{}]{}".format(
                LEVEL_COLORS[level], level.name, RESET_COLOR)
        else:
            prefix = "[{}]".format(level.name)
        print("{} {} {}".format(timestamp, prefix, message), flush=True)


def log_error(message):
    log(LogLevel.ERROR, message)


def log_warn(message):
    log(LogLevel.WARN, message)


def log_info(message):
    log(LogLevel.INFO, message)


def log_logic(message):
    log(LogLevel.LOGIC, message)


def log_debug(message):
    log(LogLevel.DEBUG, message)
