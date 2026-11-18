import pytest

import utils.run_config as run_config


def test_pytest_uses_run_test_yaml():
    assert run_config.RUN_CONFIG_PATH.name == "run.test.yaml"


def test_web_mode_uses_embedded_defaults_without_pyyaml(monkeypatch):
    monkeypatch.setattr(run_config, "yaml", None)
    monkeypatch.setenv("CHESS_WEB_MODE", "1")

    properties, path = run_config._load_properties()

    assert properties["mode"] == "PROD"
    assert properties["ui.action_animation_duration_ms"] == "0"
    assert properties["ai.search.learning.max_file_size"] == "16k"
    assert path == run_config.RUN_CONFIG_PATH


def test_missing_pyyaml_is_explicit_outside_web_mode(monkeypatch):
    monkeypatch.setattr(run_config, "yaml", None)
    monkeypatch.delenv("CHESS_WEB_MODE", raising=False)

    with pytest.raises(RuntimeError, match="PyYAML is required"):
        run_config._load_properties()


def test_run_config_loads_nested_yaml_values(monkeypatch, tmp_path):
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        """\
mode: PROD
log:
  level: " info "
game:
  seed: 42
ui:
  action_animation_duration_ms: 300
ai:
  search:
    max_depth: 7
    time_limit_seconds: 1.5
    cpu:
      workers: 4
      worker_usage: 50
    ponder:
      enabled: false
      cpu:
        workers: 2
        worker_usage: 75
    cache:
      enabled: false
      max_entries: 8k
    learning:
      enabled: true
      save_enabled: false
      database_path: data/custom.sqlite3
      max_file_size: 2G
    metrics:
      enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_config, "RUN_CONFIG_PATH", config_path)
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 4 * 1024 ** 3)

    assert run_config._load_run_config() == (
        run_config.RunMode.PROD,
        run_config.LogLevel.INFO,
        42,
        7,
        1.5,
        4,
        50,
        False,
        2,
        75,
        False,
        8 * 1024,
        True,
        False,
        2 * 1024 ** 3,
        True,
        -20.0,
        "data/custom.sqlite3",
        300,
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("DEBUG", run_config.RunMode.DEBUG),
        ("PROD", run_config.RunMode.PROD),
        ("DIAG", run_config.RunMode.DIAG),
    ],
)
def test_run_config_accepts_modes(monkeypatch, tmp_path, mode, expected):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": mode}, tmp_path / "run.yaml"),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024)

    assert run_config._load_run_config()[0] == expected


def test_run_config_rejects_unknown_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "INVALID"}, tmp_path / "run.yaml"),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024)

    with pytest.raises(ValueError, match="expected DEBUG, PROD, or DIAG"):
        run_config._load_run_config()


def test_run_config_rejects_duplicate_yaml_keys(monkeypatch, tmp_path):
    config_path = tmp_path / "run.yaml"
    config_path.write_text("mode: PROD\nmode: DEBUG\n", encoding="utf-8")
    monkeypatch.setattr(run_config, "RUN_CONFIG_PATH", config_path)

    with pytest.raises(ValueError, match="duplicate key 'mode'"):
        run_config._load_properties()


def test_run_config_rejects_non_mapping_yaml(monkeypatch, tmp_path):
    config_path = tmp_path / "run.yaml"
    config_path.write_text("- PROD\n- DEBUG\n", encoding="utf-8")
    monkeypatch.setattr(run_config, "RUN_CONFIG_PATH", config_path)

    with pytest.raises(ValueError, match="must be a YAML mapping"):
        run_config._load_properties()


def test_run_config_allows_missing_game_seed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )

    assert run_config._load_run_config()[2] is None


@pytest.mark.parametrize("seed_value", ["", "   "])
def test_run_config_allows_empty_game_seed(monkeypatch, tmp_path, seed_value):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "game.seed": seed_value},
            tmp_path / "run.yaml",
        ),
    )

    assert run_config._load_run_config()[2] is None


def test_run_config_defaults_log_level_to_warn(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
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
            tmp_path / "run.yaml",
        ),
    )

    assert run_config._load_run_config()[1] == expected


def test_run_config_rejects_unknown_log_level(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "log.level": "TRACE"},
            tmp_path / "run.yaml",
        ),
    )

    with pytest.raises(ValueError, match="log.level"):
        run_config._load_run_config()


def test_run_config_accepts_any_integer_game_seed(monkeypatch, tmp_path):
    seed = "-123456789012345678901234567890"
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD", "game.seed": seed}, tmp_path / "run.yaml"),
    )

    assert run_config._load_run_config()[2] == int(seed)


def test_run_config_rejects_non_integer_game_seed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "game.seed": "not-a-number"},
            tmp_path / "run.yaml",
        ),
    )

    with pytest.raises(ValueError, match="game.seed"):
        run_config._load_run_config()


def test_run_config_defaults_cpu_worker_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )

    assert run_config._load_run_config()[5:10] == (1, 100, True, 1, 100)


@pytest.mark.parametrize(
    ("ponder_settings", "expected_workers", "expected_usage"),
    [
        ({}, 4, 25),
        ({"ai.search.ponder.cpu.workers": "2"}, 2, 25),
        ({"ai.search.ponder.cpu.worker_usage": "75"}, 4, 75),
        (
            {
                "ai.search.ponder.cpu.workers": "2",
                "ai.search.ponder.cpu.worker_usage": "75",
            },
            2,
            75,
        ),
    ],
)
def test_ponder_cpu_settings_inherit_search_values_when_omitted(
    monkeypatch, tmp_path, ponder_settings, expected_workers, expected_usage
):
    settings = {
        "mode": "PROD",
        "ai.search.cpu.workers": "4",
        "ai.search.cpu.worker_usage": "25",
        **ponder_settings,
    }
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (settings, tmp_path / "run.yaml"),
    )

    assert run_config._load_run_config()[5:10] == (
        4,
        25,
        True,
        expected_workers,
        expected_usage,
    )


@pytest.mark.parametrize("usage", ["1", "50", "100"])
def test_run_config_accepts_cpu_worker_usage(monkeypatch, tmp_path, usage):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cpu.worker_usage": usage},
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[6] == int(usage)


@pytest.mark.parametrize("usage", ["0", "-1", "101", "50.5", "invalid"])
def test_run_config_rejects_invalid_cpu_worker_usage(
    monkeypatch, tmp_path, usage
):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cpu.worker_usage": usage},
            tmp_path / "run.yaml",
        ),
    )
    with pytest.raises(ValueError, match="ai.search.cpu.worker_usage"):
        run_config._load_run_config()


@pytest.mark.parametrize("workers", ["1", "4", "100"])
def test_run_config_accepts_explicit_worker_counts(monkeypatch, tmp_path, workers):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {
                "mode": "PROD",
                "ai.search.cpu.workers": workers,
                "ai.search.ponder.cpu.workers": workers,
            },
            tmp_path / "run.yaml",
        ),
    )

    config = run_config._load_run_config()
    assert config[5] == int(workers)
    assert config[8] == int(workers)


@pytest.mark.parametrize("workers", ["0", "-1", "1.5", "invalid"])
def test_run_config_rejects_invalid_worker_counts(
    monkeypatch, tmp_path, workers
):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cpu.workers": workers},
            tmp_path / "run.yaml",
        ),
    )

    with pytest.raises(ValueError, match="ai.search.cpu.workers"):
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
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )
    assert run_config._load_run_config()[10:12] == (True, 2048)


def test_search_metrics_default_to_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )
    assert run_config._load_run_config()[-4] is False


def test_ponder_cpu_worker_usage_defaults_to_full_usage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )
    assert run_config._load_run_config()[9] == 100


@pytest.mark.parametrize("workers", ["0", "-1", "1.5", "invalid"])
def test_run_config_rejects_invalid_ponder_worker_counts(
    monkeypatch, tmp_path, workers
):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.ponder.cpu.workers": workers},
            tmp_path / "run.yaml",
        ),
    )
    with pytest.raises(ValueError, match="ai.search.ponder.cpu.workers"):
        run_config._load_run_config()


@pytest.mark.parametrize("value", ["1", "50", "100"])
def test_ponder_cpu_worker_usage_accepts_one_through_one_hundred(
    monkeypatch, tmp_path, value
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.ponder.cpu.worker_usage": value},
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[9] == int(value)


@pytest.mark.parametrize("value", ["0", "-1", "101", "50.5", "invalid"])
def test_ponder_cpu_worker_usage_rejects_invalid_values(
    monkeypatch, tmp_path, value
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.ponder.cpu.worker_usage": value},
            tmp_path / "run.yaml",
        ),
    )
    with pytest.raises(ValueError, match="ai.search.ponder.cpu.worker_usage"):
        run_config._load_run_config()


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("FALSE", False)])
def test_run_config_accepts_ponder_enabled(monkeypatch, tmp_path, value, expected):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.ponder.enabled": value},
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[7] is expected


def test_run_config_rejects_invalid_ponder_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.ponder.enabled": "yes"},
            tmp_path / "run.yaml",
        ),
    )
    with pytest.raises(ValueError, match="ai.search.ponder.enabled"):
        run_config._load_run_config()


def test_run_config_rejects_legacy_cpu_properties(monkeypatch, tmp_path):
    for key in ("ai.search.cpu_percent", "ai.search.ponder.cpu_percent"):
        monkeypatch.setattr(
            run_config,
            "_load_properties",
            lambda key=key: (
                {"mode": "PROD", key: "50"},
                tmp_path / "run.yaml",
            ),
        )
        with pytest.raises(ValueError, match=key):
            run_config._load_run_config()


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("FALSE", False)])
def test_search_cache_enabled_configuration(monkeypatch, tmp_path, value, expected):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cache.enabled": value,
             "ai.search.cache.max_entries": "16384"},
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[10:12] == (expected, 16384)


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("FALSE", False)])
def test_search_metrics_enabled_configuration(
    monkeypatch, tmp_path, value, expected
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.metrics.enabled": value},
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[-4] is expected


@pytest.mark.parametrize(("value", "expected"), [("-20", -20.0), ("1.5", 1.5)])
def test_learning_soft_cutoff_threshold_configuration(
    monkeypatch, tmp_path, value, expected,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {
                "mode": "PROD",
                "ai.search.learning.soft_cutoff_threshold": value,
            },
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[-3] == expected


def test_learning_database_path_defaults_to_working_directory_name(
        monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024)
    assert run_config._load_run_config()[-2] == "move-learning.sqlite3"


def test_action_animation_duration_defaults_to_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024)

    assert run_config._load_run_config()[-1] == 0


@pytest.mark.parametrize("value", ["0", "300", "2000"])
def test_action_animation_duration_accepts_inclusive_range(
    monkeypatch, tmp_path, value,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {
                "mode": "PROD",
                "ui.action_animation_duration_ms": value,
            },
            tmp_path / "run.yaml",
        ),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024)

    assert run_config._load_run_config()[-1] == int(value)


@pytest.mark.parametrize("value", ["-1", "2001", "1.5", "invalid"])
def test_action_animation_duration_rejects_invalid_values(
    monkeypatch, tmp_path, value,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {
                "mode": "PROD",
                "ui.action_animation_duration_ms": value,
            },
            tmp_path / "run.yaml",
        ),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024)

    with pytest.raises(ValueError, match="ui.action_animation_duration_ms"):
        run_config._load_run_config()


@pytest.mark.parametrize("value", ["nan", "inf", "invalid"])
def test_run_config_rejects_non_finite_learning_cutoff_threshold(
    monkeypatch, tmp_path, value,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {
                "mode": "PROD",
                "ai.search.learning.soft_cutoff_threshold": value,
            },
            tmp_path / "run.yaml",
        ),
    )
    with pytest.raises(ValueError, match="soft_cutoff_threshold"):
        run_config._load_run_config()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("16384", 16384),
        ("16k", 16 * 1024),
        ("2M", 2 * 1024 ** 2),
        ("1G", 1024 ** 3),
    ],
)
def test_search_cache_max_entries_accepts_binary_suffixes(
    monkeypatch, tmp_path, value, expected
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.cache.max_entries": value},
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[11] == expected


@pytest.mark.parametrize(("key", "expected"), [
    ("ai.search.learning.enabled", False),
    ("ai.search.learning.save_enabled", False),
])
def test_move_learning_switches_default_to_disabled(
    monkeypatch, tmp_path, key, expected,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024 ** 3)
    config = run_config._load_run_config()
    assert config[12 if key.endswith(".enabled") else 13] is expected


@pytest.mark.parametrize(
    ("enabled", "save_enabled", "expected"),
    [
        ("false", "true", (False, True)),
        ("true", "false", (True, False)),
        ("true", "true", (True, True)),
    ],
)
def test_move_learning_switches_are_independent_config_values(
    monkeypatch, tmp_path, enabled, save_enabled, expected,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {
                "mode": "PROD",
                "ai.search.learning.enabled": enabled,
                "ai.search.learning.save_enabled": save_enabled,
            },
            tmp_path / "run.yaml",
        ),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size", lambda: 16 * 1024 ** 3)
    assert run_config._load_run_config()[12:14] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("16384", 16384),
        ("16k", 16 * 1024),
        ("2M", 2 * 1024 ** 2),
        ("1G", 1024 ** 3),
    ],
)
def test_move_learning_max_file_size_accepts_binary_suffixes(
    monkeypatch, tmp_path, value, expected,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: (
            {"mode": "PROD", "ai.search.learning.max_file_size": value},
            tmp_path / "run.yaml",
        ),
    )
    assert run_config._load_run_config()[14] == expected


def test_move_learning_max_file_size_defaults_to_quarter_physical_memory(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.yaml"),
    )
    monkeypatch.setattr(
        run_config, "_default_learning_max_file_size",
        lambda: 12 * 1024 ** 3,
    )
    assert run_config._load_run_config()[14] == 12 * 1024 ** 3


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ai.search.cache.enabled", "yes"),
        ("ai.search.cache.enabled", ""),
        ("ai.search.metrics.enabled", "yes"),
        ("ai.search.metrics.enabled", ""),
        ("ai.search.cache.max_entries", "0"),
        ("ai.search.cache.max_entries", "-1"),
        ("ai.search.cache.max_entries", "1.5"),
        ("ai.search.cache.max_entries", "1.5k"),
        ("ai.search.cache.max_entries", "1K"),
        ("ai.search.cache.max_entries", "1m"),
        ("ai.search.cache.max_entries", "1g"),
        ("ai.search.cache.max_entries", "k"),
        ("ai.search.cache.max_entries", "invalid"),
        ("ai.search.learning.enabled", "yes"),
        ("ai.search.learning.save_enabled", ""),
        ("ai.search.learning.max_file_size", "0"),
        ("ai.search.learning.max_file_size", "-1"),
        ("ai.search.learning.max_file_size", "1.5"),
        ("ai.search.learning.max_file_size", "1K"),
        ("ai.search.learning.max_file_size", "1m"),
        ("ai.search.learning.max_file_size", "1g"),
        ("ai.search.learning.max_file_size", "1k"),
        ("ai.search.learning.max_file_size", "invalid"),
        ("ai.search.learning.database_path", ""),
    ],
)
def test_search_cache_rejects_invalid_configuration(monkeypatch, tmp_path, key, value):
    monkeypatch.setattr(
        run_config, "_load_properties",
        lambda: ({"mode": "PROD", key: value}, tmp_path / "run.yaml"),
    )
    with pytest.raises(ValueError, match=key.replace(".", r"\.")):
        run_config._load_run_config()
