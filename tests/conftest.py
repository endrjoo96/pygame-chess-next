import os
from pathlib import Path

import pytest


os.environ["CHESS_RUN_CONFIG_PATH"] = str(
    Path(__file__).resolve().parent.parent / "run.test.yaml"
)


@pytest.fixture(autouse=True)
def isolate_move_learning_database(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "logic.chess_ai.AI_SEARCH_LEARNING_DATABASE_PATH",
        str(tmp_path / "move-learning.sqlite3"),
    )
