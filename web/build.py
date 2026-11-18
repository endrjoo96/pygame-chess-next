"""Buduje statyczną aplikację Pygbag z wybranych modułów gry bez kodu AI."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
OUTPUT_DIR = WEB_DIR / "build"
PACKAGE_DIRS = (
    "constants",
    "enchants_behaviors",
    "models",
    "network",
    "processors",
    "utils",
)
EXCLUDED_MODELS = {
    "ai_search_metrics.py",
    "ai_search_stats.py",
    "game_observation.py",
}
LOGIC_FILES = (
    "logic/__init__.py",
    "logic/game_rules.py",
    "logic/game_simulation.py",
    "logic/stage/__init__.py",
    "logic/stage/action_animation.py",
    "logic/stage/game_logic_loop.py",
)


def _copy_python_tree(source_name, destination):
    source = ROOT / source_name
    for path in source.rglob("*.py"):
        if source_name == "models" and path.name in EXCLUDED_MODELS:
            continue
        target = destination / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _stage_application(app_dir, game_server_url):
    for package in PACKAGE_DIRS:
        _copy_python_tree(package, app_dir)
    for filename in LOGIC_FILES:
        source = ROOT / filename
        if source.exists():
            target = app_dir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    shutil.copy2(ROOT / "piecesprite.py", app_dir / "piecesprite.py")
    shutil.copytree(ROOT / "res", app_dir / "res")
    shutil.copy2(WEB_DIR / "main.py", app_dir / "main.py")
    shutil.copy2(WEB_DIR / "run.yaml", app_dir / "run.yaml")
    shutil.copy2(WEB_DIR / "network.js", app_dir / "network.js")
    (app_dir / "config.js").write_text(
        "window.CHESS_GAME_SERVER_URL = {};\n".format(
            json.dumps(game_server_url)),
        encoding="utf-8",
    )


def _publish_build(source_dir):
    built_web = source_dir / "build" / "web"
    if not built_web.is_dir():
        raise RuntimeError("Pygbag did not produce the expected build/web directory")
    index_path = built_web / "index.html"
    if not index_path.is_file():
        raise RuntimeError("Pygbag build is missing index.html")
    html = _set_canvas_viewport_scale(
        index_path.read_text(encoding="utf-8"))
    scripts = (
        '<script src="config.js"></script>\n'
        '<script src="network.js"></script>\n'
    )
    if "</body>" not in html:
        raise RuntimeError("Pygbag index.html has no closing body tag")
    if "network.js" not in html:
        html = html.replace("</body>", scripts + "</body>")
    index_path.write_text(html, encoding="utf-8")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    shutil.copytree(built_web, OUTPUT_DIR)
    shutil.copy2(source_dir / "config.js", OUTPUT_DIR / "config.js")
    shutil.copy2(source_dir / "network.js", OUTPUT_DIR / "network.js")


def _set_canvas_viewport_scale(html):
    """Make Pygbag fill the browser viewport instead of using its half-size default."""
    html, replacements = re.subn(
        r"(\bgui_divider\s*:\s*)\d+",
        r"\g<1>1",
        html,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("Pygbag index.html is missing the gui_divider setting")
    return html


def main():
    game_server_url = os.environ.get(
        "GAME_SERVER_URL",
        os.environ.get("SIGNALING_SERVER_URL", ""),
    ).strip()
    if game_server_url and not game_server_url.startswith(("wss://", "ws://")):
        raise ValueError("GAME_SERVER_URL must use ws:// or wss://")

    with tempfile.TemporaryDirectory(prefix="chess-next-web-") as temporary_dir:
        source_dir = Path(temporary_dir) / "app"
        source_dir.mkdir()
        _stage_application(source_dir, game_server_url)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pygbag",
                "--build",
                "--ume_block",
                "0",
                "--title",
                "Chess NEXT",
                str(source_dir),
            ],
            cwd=ROOT,
            check=True,
        )
        _publish_build(source_dir)
    print("Pages artifact created in {}".format(OUTPUT_DIR))


if __name__ == "__main__":
    main()
