from io import StringIO
import re

import pytest

import utils.logging as app_logging
from utils.run_config import LogLevel


@pytest.mark.parametrize(
    ("configured_level", "expected_levels"),
    [
        (LogLevel.ERROR, ["ERROR"]),
        (LogLevel.WARN, ["ERROR", "WARN"]),
        (LogLevel.INFO, ["ERROR", "WARN", "INFO"]),
        (LogLevel.LOGIC, ["ERROR", "WARN", "INFO", "LOGIC"]),
        (LogLevel.DEBUG, ["ERROR", "WARN", "INFO", "LOGIC", "DEBUG"]),
        (LogLevel.OFF, []),
    ],
)
def test_log_level_filters_hierarchically(
    monkeypatch, capsys, configured_level, expected_levels
):
    monkeypatch.setattr(app_logging, "LOG_LEVEL", configured_level)

    app_logging.log_error("error message")
    app_logging.log_warn("warn message")
    app_logging.log_info("info message")
    app_logging.log_logic("logic message")
    app_logging.log_debug("debug message")

    output = capsys.readouterr().out.splitlines()
    assert [re.search(r"\[(\w+)\]", line).group(1) for line in output] == expected_levels
    assert all(
        re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}.* \[\w+\] ", line)
        for line in output
    )


def test_is_enabled_accepts_level_names(monkeypatch):
    monkeypatch.setattr(app_logging, "LOG_LEVEL", LogLevel.LOGIC)

    assert app_logging.is_enabled("INFO")
    assert app_logging.is_enabled(LogLevel.LOGIC)
    assert not app_logging.is_enabled("DEBUG")


@pytest.mark.parametrize(
    ("level", "color"),
    [
        (LogLevel.ERROR, "\033[31m"),
        (LogLevel.WARN, "\033[33m"),
        (LogLevel.INFO, "\033[36m"),
        (LogLevel.LOGIC, "\033[32m"),
        (LogLevel.DEBUG, "\033[90m"),
    ],
)
def test_log_colors_only_the_level_prefix(monkeypatch, level, color):
    class TtyStream(StringIO):
        def isatty(self):
            return True

    stream = TtyStream()
    monkeypatch.setattr(app_logging, "LOG_LEVEL", LogLevel.DEBUG)
    monkeypatch.setattr(app_logging.sys, "stdout", stream)

    app_logging.log(level, "message")

    output = stream.getvalue()
    assert "{}[{}]\033[0m message".format(color, level.name) in output


def test_log_omits_colors_for_redirected_output(monkeypatch):
    stream = StringIO()
    monkeypatch.setattr(app_logging, "LOG_LEVEL", LogLevel.INFO)
    monkeypatch.setattr(app_logging.sys, "stdout", stream)

    app_logging.log_info("message")

    assert "[INFO] message" in stream.getvalue()
    assert "\033[" not in stream.getvalue()


def test_no_color_environment_variable_disables_ansi(monkeypatch):
    class TtyStream(StringIO):
        def isatty(self):
            return True

    stream = TtyStream()
    monkeypatch.setattr(app_logging, "LOG_LEVEL", LogLevel.INFO)
    monkeypatch.setattr(app_logging.sys, "stdout", stream)
    monkeypatch.setenv("NO_COLOR", "")

    app_logging.log_info("message")

    assert "[INFO] message" in stream.getvalue()
    assert "\033[" not in stream.getvalue()
