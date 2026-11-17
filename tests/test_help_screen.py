from pathlib import Path

import pygame

from logic.stage.help_screen import HelpScreen


def test_help_screen_loads_markdown_and_supports_scrolling(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    document = (
        Path(__file__).resolve().parents[1] / "docs" / "game-help.md")
    help_screen = HelpScreen(document, pygame.Surface((1240, 880)))
    screen = pygame.Surface((1240, 880))
    monkeypatch.setattr(
        "logic.stage.help_screen.utils.left_click_event", lambda: False)

    assert not help_screen.draw(screen)
    assert "Kamikaze z opóźnieniem — 2 tury" in help_screen._markdown
    assert sum(
        line.startswith("### ")
        for line in help_screen._markdown.splitlines()
    ) == 32
    assert help_screen._max_scroll > 0

    help_screen.scroll(-1)
    assert help_screen._scroll > 0


def test_help_screen_return_button_closes_the_screen(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    document = (
        Path(__file__).resolve().parents[1] / "docs" / "game-help.md")
    help_screen = HelpScreen(document)
    screen = pygame.Surface((1240, 880))
    monkeypatch.setattr(
        "logic.stage.help_screen.utils.left_click_event", lambda: True)
    monkeypatch.setattr(
        "logic.stage.help_screen.utils.get_mouse_event",
        lambda: (1149, 845),
    )

    assert help_screen.draw(screen)
