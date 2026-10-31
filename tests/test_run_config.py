import pytest

import utils.run_config as run_config


def test_run_config_allows_missing_game_seed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.properties"),
    )

    assert run_config._load_run_config()[2] is None


def test_run_config_defaults_log_level_to_warn(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.properties"),
    )

    assert run_config._load_run_config()[1] == run_config.LogLevel.WARN


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ERROR", run_config.LogLevel.ERROR),
        ("warn", run_config.LogLevel.WARN),
        ("INFO", run_config.LogLevel.INFO),
        ("LOGIC", run_config.LogLevel.LOGIC),
        ("DEBUG", run_config.LogLevel.DEBUG),
        ("off", run_config.LogLevel.OFF),
    ],
)
def test_run_config_accepts_log_levels(monkeypatch, tmp_path, value, expected):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "log.level": value},
            tmp_path / "run.properties",
        ),
    )

    assert run_config._load_run_config()[1] == expected


def test_run_config_rejects_unknown_log_level(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "log.level": "TRACE"},
            tmp_path / "run.properties",
        ),
    )

    with pytest.raises(ValueError, match="log.level"):
        run_config._load_run_config()


def test_run_config_accepts_any_integer_game_seed(monkeypatch, tmp_path):
    seed = "-123456789012345678901234567890"
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD", "game.seed": seed}, tmp_path / "run.properties"),
    )

    assert run_config._load_run_config()[2] == int(seed)


def test_run_config_rejects_non_integer_game_seed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "game.seed": "not-a-number"},
            tmp_path / "run.properties",
        ),
    )

    with pytest.raises(ValueError, match="game.seed"):
        run_config._load_run_config()


def test_run_config_defaults_cpu_usage_percentage_to_full_capacity(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.properties"),
    )

    assert run_config._load_run_config()[5] == 100


@pytest.mark.parametrize("cpu_percent", ["1", "99", "100"])
def test_run_config_accepts_cpu_usage_percentage(monkeypatch, tmp_path, cpu_percent):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cpu_percent": cpu_percent},
            tmp_path / "run.properties",
        ),
    )

    assert run_config._load_run_config()[5] == int(cpu_percent)


@pytest.mark.parametrize("cpu_percent", ["0", "101", "-1", "50.5", "invalid"])
def test_run_config_rejects_invalid_cpu_usage_percentage(
    monkeypatch, tmp_path, cpu_percent
):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cpu_percent": cpu_percent},
            tmp_path / "run.properties",
        ),
    )

    with pytest.raises(ValueError, match="ai.search.cpu_percent"):
        run_config._load_run_config()


def test_missing_game_seed_is_generated_when_requested(monkeypatch):
    calls = []

    def fake_randbits(bit_count):
        calls.append(bit_count)
        return 987654321

    monkeypatch.setattr(run_config, "GAME_SEED", None)
    monkeypatch.setattr(run_config.secrets, "randbits", fake_randbits)

    assert run_config.resolve_game_seed() == 987654321
    assert calls == [64]


def test_configured_game_seed_is_used_as_is(monkeypatch):
    for seed in (-7, 2 ** 100):
        monkeypatch.setattr(run_config, "GAME_SEED", seed)
        assert run_config.resolve_game_seed() == seed


def test_search_cache_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.properties"),
    )
    assert run_config._load_run_config()[-2:] == (True, 2048)


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("FALSE", False)])
def test_search_cache_enabled_configuration(monkeypatch, tmp_path, value, expected):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cache.enabled": value,
             "ai.search.cache.max_entries": "16384"},
            tmp_path / "run.properties",
        ),
    )
    assert run_config._load_run_config()[-2:] == (expected, 16384)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ai.search.cache.enabled", "yes"),
        ("ai.search.cache.enabled", ""),
        ("ai.search.cache.max_entries", "0"),
        ("ai.search.cache.max_entries", "-1"),
        ("ai.search.cache.max_entries", "1.5"),
        ("ai.search.cache.max_entries", "invalid"),
    ],
)
def test_search_cache_rejects_invalid_configuration(monkeypatch, tmp_path, key, value):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD", key: value}, tmp_path / "run.properties"),
    )
    with pytest.raises(ValueError, match=key.replace(".", r"\.")):
        run_config._load_run_config()
