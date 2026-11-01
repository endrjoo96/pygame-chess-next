import pygame

from logic.stage.ai_stats_window import AIStatsWindow
from models.ai_search_stats import AISearchStats, AIWorkerStats


class FakeWindow:
    def __init__(self, title, size, position, borderless):
        self.title = title
        self.position = position
        self.borderless = borderless
        self.id = 42
        self.surface = pygame.Surface(size)
        self.flip_count = 0
        self.destroyed = False

    def get_surface(self):
        return self.surface

    def flip(self):
        self.flip_count += 1

    def destroy(self):
        self.destroyed = True


def test_stats_window_draws_progress_and_final_results(monkeypatch):
    import logic.stage.ai_stats_window as ai_stats_window

    rendered_text = []

    class RecordingFont:
        @staticmethod
        def render(text, _antialias, color):
            rendered_text.append(text)
            image = pygame.Surface((max(1, len(text) * 8), 20), pygame.SRCALPHA)
            image.fill(color)
            return image

    monkeypatch.setattr("logic.stage.ai_stats_window.Window", FakeWindow)
    monkeypatch.setattr(
        ai_stats_window.pygame.font,
        "SysFont",
        lambda *args, **kwargs: RecordingFont(),
    )
    window = AIStatsWindow()

    window.draw(AISearchStats(
        is_searching=True,
        candidate_move="Wb8",
        candidate_score=1.5,
        candidate_depth=3,
        cache_enabled=True,
        cache_entries=42,
        cache_limit=256,
        cache_evictions=3,
        workers=(
            AIWorkerStats(1, "idle", pid=123, cache_entries=12),
            AIWorkerStats(2, "busy", pid=456, cache_entries=20),
        ),
    ))
    window.draw(AISearchStats(
        final_move="Wb8",
        final_score=1.5,
        completed_depth=3,
        visited_nodes=1234,
    ))

    assert window._window.flip_count == 2
    assert window._window.surface.get_size() == (620, 620)
    assert window._window.position == (0, 0)
    assert window._window.borderless
    assert "Myślę, że najlepszy ruch to..." in rendered_text
    assert "Ocena heurystyczna (czarne): +1.50 | głębokość: 3" in rendered_text
    assert "Ostatni wybrany ruch" in rendered_text
    assert "Wynik wyszukiwania (czarne): +1.50" in rendered_text
    assert "Ukończona głębokość: 3" in rendered_text
    assert "Odwiedzone węzły: 1 234" in rendered_text
    assert "Wpisy: 42 / 256 | workery: 32 | wyparcia: 3" in rendered_text
    assert "W01 PID 123: idle" in rendered_text
    assert "W02 PID 456: busy" in rendered_text


def test_stats_window_scrolls_worker_lists_over_visible_limit(monkeypatch):
    import logic.stage.ai_stats_window as ai_stats_window

    rendered_text = []

    class RecordingFont:
        @staticmethod
        def render(text, _antialias, color):
            rendered_text.append(text)
            image = pygame.Surface((max(1, len(text) * 8), 20), pygame.SRCALPHA)
            image.fill(color)
            return image

    monkeypatch.setattr("logic.stage.ai_stats_window.Window", FakeWindow)
    monkeypatch.setattr(
        ai_stats_window.pygame.font,
        "SysFont",
        lambda *args, **kwargs: RecordingFont(),
    )
    window = AIStatsWindow()
    workers = tuple(
        AIWorkerStats(worker_id, "idle")
        for worker_id in range(1, 29)
    )
    stats = AISearchStats(workers=workers)

    window.draw(stats)
    assert "Workery (1-24 z 28)" in rendered_text
    assert "W01: idle" in rendered_text
    assert "W24: idle" in rendered_text

    rendered_text.clear()
    scroll_down = pygame.event.Event(
        pygame.MOUSEWHEEL,
        window=window._window,
        x=0,
        y=-1,
    )
    assert not window.handle_event(scroll_down)
    window.draw(stats)

    assert "Workery (3-26 z 28)" in rendered_text
    assert "W03: idle" in rendered_text
    assert "W26: idle" in rendered_text
    assert "W01: idle" not in rendered_text


def test_stats_window_close_event_does_not_match_another_window(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    monkeypatch.setattr("logic.stage.ai_stats_window.Window", FakeWindow)
    window = AIStatsWindow()
    other_window_close = pygame.event.Event(
        pygame.WINDOWCLOSE, window=window._window.id + 1)
    own_window_close = pygame.event.Event(
        pygame.WINDOWCLOSE, window=window._window)
    stats_click = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        window=window._window,
        pos=(15, 15),
        button=1,
    )
    window_id_click = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        window=window._window.id,
        pos=(15, 15),
        button=1,
    )

    assert not window.handle_event(other_window_close)
    assert not window._window.destroyed
    assert not window.owns_event(other_window_close)
    assert window.owns_event(stats_click)
    assert window.owns_event(window_id_click)
    assert window.handle_event(own_window_close)
    assert window._window is None


def test_stats_window_can_be_dragged_from_anywhere_in_its_content(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    monkeypatch.setattr("logic.stage.ai_stats_window.Window", FakeWindow)
    window = AIStatsWindow()
    start_drag = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        window=window._window,
        button=1,
        pos=(300, 150),
    )
    move_window = pygame.event.Event(
        pygame.MOUSEMOTION,
        window=window._window,
        rel=(24, -12),
        pos=(324, 138),
    )
    stop_drag = pygame.event.Event(
        pygame.MOUSEBUTTONUP,
        window=window._window,
        button=1,
        pos=(324, 138),
    )

    assert not window.handle_event(start_drag)
    assert window.owns_event(start_drag)
    assert not window.handle_event(move_window)
    assert window._window.position == (24, -12)
    assert not window.handle_event(stop_drag)
    window.handle_event(move_window)
    assert window._window.position == (24, -12)
