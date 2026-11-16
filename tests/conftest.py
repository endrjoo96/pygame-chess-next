import os
from pathlib import Path


os.environ["CHESS_RUN_CONFIG_PATH"] = str(
    Path(__file__).resolve().parent.parent / "run.test.yaml"
)
