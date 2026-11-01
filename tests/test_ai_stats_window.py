import pygame

from logic.stage.ai_stats_window import AIStatsWindow
from models.ai_search_stats import AISearchStats, AIWorkerStats


class RecordingSurface:
    def __init__(self, size):
        self._surface = pygame.Surface(size)
        self.blits = []

    def fill(self, color):
        self._surface.fill(color)

    def blit(self, source, destination):
        self.blits.append((destination, source.get_size()))
        return self._surface.blit(source, destination)

    def get_size(self):
        return self._surface.get_size()


class FakeWindow:
    def __init__(self, title, size, position, borderless):
        self.title = title
        self.position = position
        self.borderless = borderless
        self.id = 42
        self.surface = RecordingSurface(size)
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
    font_sizes = []

    class RecordingFont:
        def __init__(self, font_size):
            self.font_size = font_size

        def render(self, text, _antialias, color):
            rendered_text.append(text)
            image = pygame.Surface(
                (max(1, len(text) * 8), self.font_size), pygame.SRCALPHA)
            image.fill(color)
            return image

    def create_font(_font_name, font_size):
        font_sizes.append(font_size)
        return RecordingFont(font_size)

    monkeypatch.setattr("logic.stage.ai_stats_window.Window", FakeWindow)
    monkeypatch.setattr(
        ai_stats_window.pygame.font,
        "SysFont",
        create_font,
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
        cache_deepest_entry_depth=3,
        workers=(
            AIWorkerStats(
                1, "idle", pid=123, cache_entries=12,
                mode="search", root="C2"),
            AIWorkerStats(
                2, "busy", pid=456, cache_entries=20,
                mode="prepare", root="D7"),
        ),
        search_phase="searching",
        current_depth=3,
        completed_search_depth=2,
        live_visited_nodes=9876,
    ))
    candidate_blits = window._window.surface.blits[:]
    window.draw(AISearchStats(
        final_move="Wb8",
        final_score=1.5,
        completed_depth=3,
        visited_nodes=1234,
    ))
    window.draw(AISearchStats(
        cache_enabled=True,
        cache_entries=42,
        cache_limit=256,
        cache_deepest_entry_depth=3,
        search_phase="pondering",
        current_depth=0,
        completed_search_depth=0,
    ))

    assert window._window.flip_count == 3
    assert window._window.surface.get_size() == (700, 720)
    assert window._window.position == (0, 0)
    assert window._window.borderless
    assert font_sizes == [29, 21, 17]
    blits_by_x = {}
    for (x, y), (_, height) in candidate_blits:
        blits_by_x.setdefault(x, []).append((y, height))
    for column_blits in blits_by_x.values():
        column_blits.sort()
        assert all(
            next_y >= y + height
            for (y, height), (next_y, _) in zip(
                column_blits, column_blits[1:])
        )
    progress_ys = [
        position[1]
        for position, _ in candidate_blits
        if position[0] == 16 and 196 <= position[1] <= 232
    ]
    assert progress_ys == [196, 214, 232]
    for column_x in (16, 236, 350, 470):
        worker_row_ys = [
            position[1]
            for position, _ in candidate_blits
            if position[0] == column_x and position[1] >= 374
        ]
        assert worker_row_ys == [374, 392]
    assert "Myślę, że najlepszy ruch to..." in rendered_text
    assert "Ocena heurystyczna (czarne): +1.50 | głębokość: 3" in rendered_text
    assert "Ostatni wybrany ruch" in rendered_text
    assert "Wynik wyszukiwania (czarne): +1.50" in rendered_text
    assert "Ukończona głębokość: 3" in rendered_text
    assert "Odwiedzone węzły: 1 234" in rendered_text
    assert "Aktywność: wyszukiwanie" in rendered_text
    assert "Odwiedzone węzły: 9 876" in rendered_text
    assert "Głębokość wyszukiwania: aktualnie 3 | ukończona 2" in rendered_text
    assert "Główny: 42 / 256 | workery: 32 | wyparcia: 3" in rendered_text
    assert "Maks. głębokość wpisu cache: 3" in rendered_text
    assert "Głębokość ponderingu: aktualnie 0 | ukończona 0" in rendered_text
    assert "W01 PID 123" in rendered_text
    assert "idle" in rendered_text
    assert "search" in rendered_text
    assert "C2" in rendered_text
    assert "W02 PID 456" in rendered_text
    assert "busy" in rendered_text
    assert "prepare" in rendered_text
    assert "D7" in rendered_text
    assert "Stan" in rendered_text
    assert "Tryb" in rendered_text
    assert "Root" in rendered_text


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
    assert "Workery (1-17 z 28)" in rendered_text
    assert "W01" in rendered_text
    assert "W17" in rendered_text
    assert "W24" not in rendered_text

    rendered_text.clear()
    scroll_down = pygame.event.Event(
        pygame.MOUSEWHEEL,
        window=window._window,
        x=0,
        y=-1,
    )
    assert not window.handle_event(scroll_down)
    window.draw(stats)

    assert "Workery (3-19 z 28)" in rendered_text
    assert "W03" in rendered_text
    assert "W19" in rendered_text
    assert "W20" not in rendered_text
    assert "W01" not in rendered_text


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
