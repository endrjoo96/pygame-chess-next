import pytest

import utils.run_config as run_config


def test_run_config_allows_missing_game_seed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_config,
        "_load_properties",
        lambda: ({"mode": "PROD"}, tmp_path / "run.properties"),
    )

    assert run_config._load_run_config()[2] is None


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

    assert run_config._load_run_config()[-1] == 100


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

    assert run_config._load_run_config()[-1] == int(cpu_percent)


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
