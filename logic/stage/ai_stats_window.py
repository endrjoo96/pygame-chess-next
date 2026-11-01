import pygame
from pygame._sdl2 import Window

from models.ai_search_stats import AISearchStats


class AIStatsWindow:
    def __init__(self):
        self._window = Window(
            "Statystyki AI",
            size=(620, 620),
            position=(0, 0),
            borderless=True,
        )
        self._dragging = False
        self._worker_scroll = 0
        self._title_font = pygame.font.SysFont(None, 30)
        self._body_font = pygame.font.SysFont(None, 22)
        self._detail_font = pygame.font.SysFont(None, 18)

    def handle_event(self, event):
        if self._window is None or not self.owns_event(event):
            return False

        if event.type == pygame.WINDOWCLOSE:
            self.close()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging = False
        elif event.type == pygame.MOUSEMOTION and self._dragging:
            x, y = self._window.position
            dx, dy = event.rel
            self._window.position = (x + dx, y + dy)
        elif event.type == pygame.MOUSEWHEEL:
            self._worker_scroll = max(0, self._worker_scroll - event.y * 2)
        return False

    def owns_event(self, event):
        event_window = getattr(event, "window", None)
        event_window_id = getattr(event_window, "id", event_window)
        return (
            self._window is not None
            and event_window_id == self._window.id
        )

    def draw(self, stats: AISearchStats):
        if self._window is None:
            raise RuntimeError("The AI statistics window is closed")

        surface = self._window.get_surface()
        surface.fill((24, 24, 24))

        title = self._title_font.render("Statystyki AI", True, (255, 255, 255))
        surface.blit(title, (20, 18))

        if stats.is_searching:
            self._draw_candidate(surface, stats)
        elif stats.final_move is not None:
            self._draw_final_result(surface, stats)
        else:
            message = self._body_font.render(
                "Oczekiwanie na ruch bota...", True, (220, 220, 220))
            surface.blit(message, (20, 75))

        self._draw_live_progress(surface, stats)
        self._draw_engine_diagnostics(surface, stats)
        self._window.flip()

    def _draw_candidate(self, surface, stats):
        caption = self._body_font.render(
            "Myślę, że najlepszy ruch to...", True, (220, 220, 220))
        surface.blit(caption, (20, 70))

        if stats.candidate_move is None:
            message = self._body_font.render(
                "Wyszukiwanie w toku...", True, (255, 255, 255))
            surface.blit(message, (20, 106))
            return

        move = self._title_font.render(
            stats.candidate_move, True, (255, 255, 255))
        surface.blit(move, (20, 104))
        detail = "Ocena heurystyczna (czarne): {:+.2f} | głębokość: {}".format(
            stats.candidate_score,
            stats.candidate_depth,
        )
        rendered_detail = self._detail_font.render(
            detail, True, (220, 220, 220))
        surface.blit(rendered_detail, (20, 146))

    def _draw_final_result(self, surface, stats):
        caption = self._body_font.render(
            "Ostatni wybrany ruch", True, (220, 220, 220))
        surface.blit(caption, (20, 70))

        move = self._title_font.render(
            stats.final_move, True, (255, 255, 255))
        surface.blit(move, (20, 104))

        score = self._detail_font.render(
            "Wynik wyszukiwania (czarne): {:+.2f}".format(stats.final_score),
            True,
            (220, 220, 220),
        )
        depth = self._detail_font.render(
            "Ukończona głębokość: {}".format(stats.completed_depth),
            True,
            (220, 220, 220),
        )
        nodes = self._detail_font.render(
            "Odwiedzone węzły: {}".format(
                format(stats.visited_nodes, ",").replace(",", " ")),
            True,
            (220, 220, 220),
        )
        surface.blit(score, (20, 146))
        surface.blit(depth, (20, 174))
        surface.blit(nodes, (20, 202))

    def _draw_live_progress(self, surface, stats):
        phase = stats.search_phase or (
            "searching" if stats.is_searching else "idle")
        phase_label = {
            "searching": "wyszukiwanie",
            "pondering": "pondering",
            "idle": "bezczynny",
        }.get(phase, phase)
        depth_label = {
            "searching": "Głębokość wyszukiwania",
            "pondering": "Głębokość ponderingu",
            "idle": "Ostatnia głębokość",
        }.get(phase, "Głębokość etapu")
        visited_nodes = (
            format(stats.live_visited_nodes, ",").replace(",", " ")
            if stats.live_visited_nodes is not None else "?"
        )
        current_depth = (
            stats.current_depth
            if stats.current_depth is not None else "-"
        )
        completed_depth = (
            stats.completed_search_depth
            if stats.completed_search_depth is not None else "-"
        )
        lines = (
            "Aktywność: {}".format(phase_label),
            "Odwiedzone węzły: {}".format(visited_nodes),
            "{}: aktualnie {} | ukończona {}".format(
                depth_label, current_depth, completed_depth),
        )
        for line_index, text in enumerate(lines):
            surface.blit(
                self._detail_font.render(text, True, (220, 220, 220)),
                (20, 218 + line_index * 20),
            )

    def _draw_engine_diagnostics(self, surface, stats):
        cache_title = self._body_font.render(
            "Cache", True, (220, 220, 220))
        surface.blit(cache_title, (20, 284))

        if stats.cache_enabled is False:
            cache_text = "Wyłączony"
        elif stats.cache_entries is not None:
            cache_limit = (
                format(stats.cache_limit, ",").replace(",", " ")
                if stats.cache_limit is not None else "?"
            )
            cache_evictions = (
                format(stats.cache_evictions, ",").replace(",", " ")
                if stats.cache_evictions is not None else "?"
            )
            worker_cache_entries = sum(
                worker.cache_entries or 0
                for worker in stats.workers
            )
            cache_text = "Główny: {} / {} | workery: {} | wyparcia: {}".format(
                format(stats.cache_entries, ",").replace(",", " "),
                cache_limit,
                format(worker_cache_entries, ",").replace(",", " "),
                cache_evictions,
            )
        else:
            cache_text = "Brak danych"
        cache_detail = self._detail_font.render(
            cache_text, True, (220, 220, 220))
        surface.blit(cache_detail, (20, 312))

        if stats.cache_enabled is False:
            cache_depth = "wyłączony"
        elif stats.cache_deepest_entry_depth is not None:
            cache_depth = str(stats.cache_deepest_entry_depth)
        elif stats.cache_entries == 0:
            cache_depth = "brak wpisów"
        else:
            cache_depth = "?"
        cache_depth_text = self._detail_font.render(
            "Maks. głębokość wpisu cache: {}".format(cache_depth),
            True,
            (220, 220, 220),
        )
        surface.blit(cache_depth_text, (20, 334))

        total_workers = len(stats.workers)
        visible_workers = 24
        self._worker_scroll = min(
            max(0, self._worker_scroll),
            max(0, total_workers - visible_workers),
        )
        start = self._worker_scroll
        end = min(start + visible_workers, total_workers)
        worker_heading = (
            "Workery ({}-{} z {})".format(start + 1, end, total_workers)
            if total_workers > 0 else "Workery"
        )
        surface.blit(
            self._body_font.render(worker_heading, True, (220, 220, 220)),
            (20, 356),
        )

        if not stats.workers:
            surface.blit(
                self._detail_font.render(
                    "Brak danych o workerach", True, (180, 180, 180)),
                (20, 380),
            )
        else:
            state_colors = {
                "idle": (130, 220, 150),
                "busy": (255, 190, 110),
                "initializing": (255, 220, 120),
                "starting": (255, 220, 120),
            }
            for visible_index, worker in enumerate(stats.workers[start:end]):
                column = visible_index % 2
                row = visible_index // 2
                if worker.is_local:
                    name = "Lokalny"
                else:
                    name = f"W{worker.worker_id:02d}"
                    if worker.pid is not None:
                        name += " PID {}".format(worker.pid)
                text = "{}: {}".format(name, worker.state)
                surface.blit(
                    self._detail_font.render(
                        text,
                        True,
                        state_colors.get(worker.state, (200, 200, 200)),
                    ),
                    (20 + column * 300, 380 + row * 18),
                )

        if total_workers > visible_workers:
            surface.blit(
                self._detail_font.render(
                    "Kółko myszy: przewijanie listy", True, (160, 160, 160)),
                (20, 600),
            )

    def close(self):
        if self._window is not None:
            self._window.destroy()
            self._window = None
        self._dragging = False
        self._worker_scroll = 0
