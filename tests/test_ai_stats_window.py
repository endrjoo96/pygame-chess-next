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
        self._size = size
        self.resizable = False
        self.minimum_size = None
        self.id = 42
        self.surface = RecordingSurface(size)
        self.flip_count = 0
        self.destroyed = False

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, size):
        self._size = size
        self.surface = RecordingSurface(size)

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
        learning_database_size_bytes=1536,
        learning_database_limit_bytes=16 * 1024 * 1024,
        candidate_move_from_learning_database=True,
        workers=(
            AIWorkerStats(3, "idle", pid=789),
            AIWorkerStats(
                4, "busy", pid=456, mode="prepare", root="D7"),
            AIWorkerStats(
                2, "busy", pid=234, cache_entries=20,
                mode="search", root="C2", search_depth=3,
                learning_database_reading=True),
            AIWorkerStats(
                1, "idle", pid=123, cache_entries=12),
            AIWorkerStats(
                5, "busy", pid=567, mode="search", root="A1",
                search_depth=1),
            AIWorkerStats(
                6, "busy", pid=678, mode="prepare", root="E2"),
            AIWorkerStats(7, "starting"),
        ),
        search_phase="searching",
        current_depth=3,
        completed_search_depth=2,
        live_visited_nodes=9876,
    ), board_card_available=True, board_card_delay=3)
    candidate_blits = window._window.surface.blits[:]
    candidate_rendered_text = rendered_text[:]
    window.draw(AISearchStats(
        final_move="Wb8",
        final_score=1.5,
        completed_depth=3,
        visited_nodes=1234,
        final_move_from_learning_database=False,
    ))
    window.draw(AISearchStats(
        cache_enabled=True,
        cache_entries=42,
        cache_limit=256,
        cache_deepest_entry_depth=3,
        search_phase="pondering",
        current_depth=0,
        completed_search_depth=0,
        ponder_white_actions_completed=2,
        ponder_white_actions_total=4,
        ponder_branches_generated=7,
        ponder_root_actions_completed=8,
        ponder_root_actions_discovered=10,
        ponder_depth_counts=((1, 2), (2, 1)),
        ponder_max_branch_depth=2,
        ponder_dangerous_white_candidates=(
            ("e2-e4", -1.25, 2),
            ("d2-d4", -1.0, 2),
            ("c2-c4", -0.75, 2),
            ("g1-f3", -0.5, 2),
            ("b1-c3", -0.25, 2),
        ),
    ))
    ponder_blits = window._window.surface.blits[:]

    assert window._window.flip_count == 3
    assert window._window.surface.get_size() == (700, 720)
    assert window._window.position == (0, 0)
    assert not window._window.borderless
    assert window._window.resizable
    assert window._window.minimum_size == (700, 480)
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
    expected_worker_rows = [396 + row * 18 for row in range(7)]
    for column_x in (16, 236, 350, 470, 580, 640):
        worker_row_ys = [
            position[1]
            for position, _ in candidate_blits
            if position[0] == column_x and position[1] >= 396
        ]
        assert worker_row_ys == expected_worker_rows
    worker_labels = [
        text for text in candidate_rendered_text
        if text.startswith("W") and text[1:3].isdigit()
    ]
    assert worker_labels == [
        "W02 PID 234",
        "W05 PID 567",
        "W04 PID 456",
        "W06 PID 678",
        "W01 PID 123",
        "W03 PID 789",
        "W07",
    ]
    assert "Myślę, że najlepszy ruch to..." in rendered_text
    assert (
        "Ocena heurystyczna (czarne): +1.50 | głębokość: 3"
        in rendered_text
    )
    assert "Wskazówka z bazy: tak" in rendered_text
    assert "Ostatni wybrany ruch" in rendered_text
    assert "Wynik wyszukiwania (czarne): +1.50" in rendered_text
    assert "Ukończona głębokość: 3" in rendered_text
    assert (
        "Odwiedzone węzły: 1 234 | wskazówka z bazy: nie"
        in rendered_text
    )
    assert "Aktywność: wyszukiwanie" in rendered_text
    assert "Odwiedzone węzły: 9 876" in rendered_text
    assert "Głębokość wyszukiwania: aktualnie 3 | ukończona 2" in rendered_text
    assert "Kolejna karta pojawi się za 3 tury" in rendered_text
    assert "Główny: 42 / 256 | workery: 32 | wyparcia: 3" in rendered_text
    assert "Maks. głębokość wpisu cache: 3" in rendered_text
    assert "Baza wiedzy: 1.5 KiB / 16.0 MiB" in rendered_text
    assert "czyta" in rendered_text
    assert "DB" in rendered_text
    assert "Największa ukończona głębokość gałęzi: 2" in rendered_text
    assert "Najgroźniejsze ruchy białych dla czarnych:" in rendered_text
    assert "1. e2-e4 | czarne: -1.25 | po odpowiedzi czarnych" in rendered_text
    assert "2. d2-d4 | czarne: -1.00 | po odpowiedzi czarnych" in rendered_text
    assert "3. c2-c4 | czarne: -0.75 | po odpowiedzi czarnych" in rendered_text
    assert "4. g1-f3 | czarne: -0.50 | po odpowiedzi czarnych" in rendered_text
    assert "5. b1-c3 | czarne: -0.25 | po odpowiedzi czarnych" in rendered_text
    assert (
        "Gałęzie wg ukończonej głębokości: d1:2 | d2:1"
        in rendered_text
    )
    assert "Akcje białych rozwinięte: 2/4 | pozycje: 7" in rendered_text
    assert (
        "Odpowiedzi czarnych: 8 analiz ukończonych / 10 legalnych"
        in rendered_text
    )
    assert [
        position[1]
        for position, _ in ponder_blits
        if position[0] == 16 and position[1] in (250, 268)
    ] == [250, 268]
    assert (16, 286) in [
        position for position, _ in ponder_blits]
    assert (16, 376) in [
        position for position, _ in ponder_blits]
    assert "W01 PID 123" in rendered_text
    assert "idle" in rendered_text
    assert "search" in rendered_text
    assert "C2" in rendered_text
    assert "A1" in rendered_text
    assert "W02 PID 234" in rendered_text
    assert "W04 PID 456" in rendered_text
    assert "busy" in rendered_text
    assert "prepare" in rendered_text
    assert "D7" in rendered_text
    assert "E2" in rendered_text
    assert "Stan" in rendered_text
    assert "Tryb" in rendered_text
    assert "Root" in rendered_text
    assert "Głęb." in rendered_text
    assert "3" in rendered_text
    assert "1" in rendered_text


def test_board_card_countdown_text_uses_current_card_state():
    assert AIStatsWindow._board_card_countdown_text(True, 3) == (
        "Kolejna karta pojawi się za 3 tury")
    assert AIStatsWindow._board_card_countdown_text(True, 1) == (
        "Kolejna karta pojawi się za 1 turę")
    assert AIStatsWindow._board_card_countdown_text(True, 0) == (
        "Kolejna karta pojawi się po zakończeniu tury")
    assert AIStatsWindow._board_card_countdown_text(False, 2) == (
        "Karta pojawi się na planszy za 2 tury")
    assert AIStatsWindow._board_card_countdown_text(False, None) is None


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
    assert "Workery (1-15 z 28)" in rendered_text
    assert "W01" in rendered_text
    assert "W15" in rendered_text
    assert "W16" not in rendered_text

    rendered_text.clear()
    scroll_down = pygame.event.Event(
        pygame.MOUSEWHEEL,
        window=window._window,
        x=0,
        y=-1,
    )
    assert not window.handle_event(scroll_down)
    window.draw(stats)

    assert "Workery (3-17 z 28)" in rendered_text
    assert "W03" in rendered_text
    assert "W17" in rendered_text
    assert "W18" not in rendered_text
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


def test_stats_window_uses_system_frame_and_does_not_drag_from_content(
    monkeypatch,
):
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
    assert window._window.position == (0, 0)
    assert not window.handle_event(stop_drag)
    assert window._window.borderless is False
    assert window._window.resizable


def test_stats_window_reflows_worker_details_after_system_resize(monkeypatch):
    import logic.stage.ai_stats_window as ai_stats_window

    rendered_text = []

    class RecordingFont:
        @staticmethod
        def render(text, _antialias, color):
            rendered_text.append(text)
            image = pygame.Surface((max(1, len(text) * 8), 17), pygame.SRCALPHA)
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
    window._window.size = (1000, 920)

    window.draw(stats)
    assert "Workery (1-26 z 28)" in rendered_text
    assert "///" not in rendered_text
    root_header = next(
        position for position, _ in window._window.surface.blits
        if position[1] == 374 and position[0] > 600
    )
    assert root_header[0] == 674
