from typing import Optional

import pygame
from pygame._sdl2 import Window

from models.ai_search_stats import AISearchStats


class AIStatsWindow:
    def __init__(self):
        self._window = Window(
            "Statystyki AI",
            size=(700, 720),
            position=(0, 0),
            borderless=True,
        )
        self._dragging = False
        self._worker_scroll = 0
        self._title_font = pygame.font.SysFont(None, 29)
        self._body_font = pygame.font.SysFont(None, 21)
        self._detail_font = pygame.font.SysFont(None, 17)

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

    def draw(
        self,
        stats: AISearchStats,
        board_card_available: bool = False,
        board_card_delay: Optional[int] = None,
    ):
        if self._window is None:
            raise RuntimeError("The AI statistics window is closed")

        surface = self._window.get_surface()
        surface.fill((24, 24, 24))

        title = self._title_font.render("Statystyki AI", True, (255, 255, 255))
        surface.blit(title, (16, 14))

        countdown_text = self._board_card_countdown_text(
            board_card_available, board_card_delay)
        if countdown_text is not None:
            surface.blit(
                self._detail_font.render(countdown_text, True, (220, 220, 220)),
                (16, 43),
            )

        if stats.is_searching:
            self._draw_candidate(surface, stats)
        elif stats.final_move is not None:
            self._draw_final_result(surface, stats)
        else:
            message = self._body_font.render(
                "Oczekiwanie na ruch bota...", True, (220, 220, 220))
            surface.blit(message, (16, 60))

        self._draw_live_progress(surface, stats)
        self._draw_engine_diagnostics(surface, stats)
        self._window.flip()

    @staticmethod
    def _board_card_countdown_text(
        card_available: bool, delay: Optional[int],
    ) -> Optional[str]:
        if delay is None:
            return None
        if card_available and delay == 0:
            return "Kolejna karta pojawi się po zakończeniu tury"
        unit = "turę" if delay == 1 else (
            "tury"
            if delay % 10 in (2, 3, 4) and delay % 100 not in (12, 13, 14)
            else "tur"
        )
        if card_available:
            return "Kolejna karta pojawi się za {} {}".format(delay, unit)
        return "Karta pojawi się na planszy za {} {}".format(delay, unit)

    def _draw_candidate(self, surface, stats):
        caption = self._body_font.render(
            "Myślę, że najlepszy ruch to...", True, (220, 220, 220))
        surface.blit(caption, (16, 60))

        if stats.candidate_move is None:
            message = self._body_font.render(
                "Wyszukiwanie w toku...", True, (255, 255, 255))
            surface.blit(message, (16, 90))
            return

        move = self._title_font.render(
            stats.candidate_move, True, (255, 255, 255))
        surface.blit(move, (16, 90))
        detail = "Ocena heurystyczna (czarne): {:+.2f} | głębokość: {}".format(
            stats.candidate_score,
            stats.candidate_depth,
        )
        rendered_detail = self._detail_font.render(
            detail, True, (220, 220, 220))
        surface.blit(rendered_detail, (16, 126))

    def _draw_final_result(self, surface, stats):
        caption = self._body_font.render(
            "Ostatni wybrany ruch", True, (220, 220, 220))
        surface.blit(caption, (16, 60))

        move = self._title_font.render(
            stats.final_move, True, (255, 255, 255))
        surface.blit(move, (16, 90))

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
        surface.blit(score, (16, 126))
        surface.blit(depth, (16, 150))
        surface.blit(nodes, (16, 174))

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
                (16, 196 + line_index * 18),
            )

    def _draw_engine_diagnostics(self, surface, stats):
        cache_title = self._body_font.render(
            "Cache", True, (220, 220, 220))
        surface.blit(cache_title, (16, 260))

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
        surface.blit(cache_detail, (16, 282))

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
        surface.blit(cache_depth_text, (16, 304))

        workers = sorted(stats.workers, key=self._worker_sort_key)
        total_workers = len(workers)
        visible_workers = 17
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
            (16, 328),
        )

        for header, x in (
            ("Worker", 16),
            ("Stan", 236),
            ("Tryb", 350),
            ("Root", 470),
        ):
            surface.blit(
                self._detail_font.render(header, True, (160, 160, 160)),
                (x, 352),
            )

        if not stats.workers:
            surface.blit(
                self._detail_font.render(
                    "Brak danych o workerach", True, (180, 180, 180)),
                (16, 374),
            )
        else:
            state_colors = {
                "idle": (130, 220, 150),
                "busy": (255, 190, 110),
                "initializing": (255, 220, 120),
                "starting": (255, 220, 120),
            }
            for visible_index, worker in enumerate(workers[start:end]):
                if worker.is_local:
                    name = "Lokalny"
                else:
                    name = f"W{worker.worker_id:02d}"
                    if worker.pid is not None:
                        name += " PID {}".format(worker.pid)
                y = 374 + visible_index * 18
                worker_values = (
                    (name, 16, (200, 200, 200)),
                    (
                        worker.state,
                        236,
                        state_colors.get(worker.state, (200, 200, 200)),
                    ),
                    (worker.mode, 350, (220, 220, 220)),
                    (worker.root, 470, (220, 220, 220)),
                )
                for text, x, color in worker_values:
                    surface.blit(
                        self._detail_font.render(text, True, color),
                        (x, y),
                    )

        if total_workers > visible_workers:
            surface.blit(
                self._detail_font.render(
                    "Kółko myszy: przewijanie listy", True, (160, 160, 160)),
                (16, 692),
            )

    @staticmethod
    def _worker_sort_key(worker):
        if worker.state == "busy":
            mode_order = {"search": 0, "prepare": 1}
            return 0, mode_order.get(worker.mode, 2), worker.worker_id

        state_order = {
            "idle": 0,
            "initializing": 1,
            "starting": 2,
            "not-started": 3,
        }
        return 1, state_order.get(worker.state, 4), worker.worker_id

    def close(self):
        if self._window is not None:
            self._window.destroy()
            self._window = None
        self._dragging = False
        self._worker_scroll = 0
