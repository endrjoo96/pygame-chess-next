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
    assert set(help_screen._icons) == {
        "PASSIVE",
        "BUFF",
        "REUSABLE",
        "DELAY_BEFORE_USE",
        "STUN_AFTER_USE",
    }
    assert all(
        ":{}:".format(token) in help_screen._markdown
        for token in help_screen._icons
    )
    assert all(
        icon.get_size() == (22, 22)
        for icon in help_screen._icons.values()
    )
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


def test_help_screen_scrollbar_can_be_dragged_with_the_mouse(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    document = (
        Path(__file__).resolve().parents[1] / "docs" / "game-help.md")
    help_screen = HelpScreen(document)
    screen = pygame.Surface((1240, 880))
    monkeypatch.setattr(
        "logic.stage.help_screen.utils.left_click_event", lambda: False)
    help_screen.draw(screen)
    thumb = help_screen._scrollbar_thumb
    track = help_screen._scrollbar_track
    assert thumb is not None
    assert track is not None

    thumb_center = thumb.center
    assert help_screen.begin_scroll_drag(thumb_center)
    help_screen.drag_scrollbar(track.bottom)

    assert help_screen._scroll == help_screen._max_scroll
    help_screen.end_scroll_drag()
    assert not help_screen._dragging_scrollbar
