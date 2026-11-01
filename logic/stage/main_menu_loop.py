import os
import textwrap
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock
from typing import Optional

import pygame
from pygame._sdl2 import Window
from pygame.locals import *

from logic.chess_ai import ChessAI, WorkerPoolInitializationCancelled
from logic.stage.game_logic_loop import GameLogicLoop
from utils.gamecontext import GameContext
from utils import utils
from utils.logging import log_error
from utils.run_config import resolve_game_seed


_WORKER_PROGRESS_DISPLAY_SECONDS = 0.06


class Game:

    def __init__(self):
        """Przygotowuje okno gry, zasoby graficzne, zegar i stan menu."""
        context = GameContext()
        # flag to know if game menu has been showed
        self.menu_showed = False
        self.play_against_ai = True
        self.chess = None
        # flag to set game loop
        self.running = True
        self.winner = None
        # base folder for program resources
        self.resources = "res"
        self._startup_executor = ThreadPoolExecutor(max_workers=1)
        self._loading = False
        self._loading_future: Optional[Future] = None
        self._loading_ai = None
        self._loading_seed = None
        self._loading_cancel_event = Event()
        self._loading_progress_lock = Lock()
        self._loading_progress = ("", 0, 0)
        self._loading_error = None

        # initialize game window
        pygame.display.init()
        # initialize font for text
        pygame.font.init()

        # create game window
        self.screen = pygame.display.set_mode(
            [context.screen_width, context.screen_height], pygame.RESIZABLE | pygame.SCALED)
        self.window = Window.from_display_module()
        self.window.minimum_size = (context.screen_width, context.screen_height)

        # set background color
        self.screen.fill(context.bg_color)

        # get location of chess board image
        board_src = os.path.join(self.resources, "board.png")
        # load the chess board image
        self.board_img = pygame.image.load(board_src).convert()

        # set window caption
        pygame.display.set_caption(context.window_title)

        # set game icon
        pygame.display.set_icon(pygame.image.load(context.icon_src))
        # update display
        pygame.display.flip()
        # set game clock
        self.clock = pygame.time.Clock()

    def start_game(self):
        """Inicjalizuje geometrię planszy i prowadzi główną pętlę zdarzeń gry."""
        context = GameContext()

        """Function containing logic game loop"""

        # get the width of a chess board square
        context.square_length = self.board_img.get_rect().width // 8

        # calculate coordinates of the each square on the board
        for x in range(0, 8):
            context.chessboard_coordinates.append([])
            for y in range(0, 8):
                context.chessboard_coordinates[x].append([context.board_offset_x + (x * context.square_length),
                                                          context.board_offset_y + (y * context.square_length)])
            context.chessboard_coordinates[x].reverse()

        # create class object that handles the gameplay logic
        # game loop
        try:
            while self.running:
                self.clock.tick(20)
                events = pygame.event.get()
                utils.begin_input_frame(events)
                for event in events:
                    key_pressed = pygame.key.get_pressed()
                    if event.type == pygame.QUIT or key_pressed[K_ESCAPE]:
                        self.running = False
                    elif (
                        self._loading_error is not None
                        and event.type == pygame.KEYDOWN
                        and event.key == K_RETURN
                    ):
                        self._dismiss_loading_error()
                    elif key_pressed[K_SPACE]:
                        if self.chess is not None:
                            self.chess.reset()

                if self.running and self._loading:
                    self._finish_startup_if_ready()
                if self._loading or self._loading_error is not None:
                    self.draw_loading_screen()
                elif not self.menu_showed:
                    self.menu()
                else:
                    self.game()

                pygame.display.flip()
                pygame.event.pump()
        finally:
            try:
                self._shutdown_resources()
            finally:
                pygame.quit()

    def menu(self):
        """Rysuje menu startowe i przełącza do gry po kliknięciu lub Enterze."""
        context = GameContext()
        """method to show game menu"""
        # black color
        black_color = (0, 0, 0)
        # coordinates for "Play" button
        start_btn = pygame.Rect(0, 0, 100, 50)
        start_btn.center = self.screen.get_rect().center
        # show play button
        pygame.draw.rect(self.screen, black_color, start_btn)

        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        big_font = pygame.font.SysFont(context.comic_sans_font, 50)
        small_font = pygame.font.SysFont(context.comic_sans_font, 20)
        # create text to be shown on the game menu
        welcome_text = big_font.render("Chess NEXT", False, black_color)
        created_by = small_font.render("Created by jerne_official", True, black_color)
        start_btn_label = small_font.render("Graj", True, white_color)
        ai_toggle_label = small_font.render(
            "Bot czarnych: {}".format(
                "włączony" if self.play_against_ai else "wyłączony"
            ),
            True,
            white_color,
        )

        # show welcome text
        self.screen.blit(welcome_text,
                         ((self.screen.get_width() - welcome_text.get_width()) // 2,
                          150))
        # show credit text
        self.screen.blit(created_by,
                         ((self.screen.get_width() - created_by.get_width()) // 2,
                          self.screen.get_height() - created_by.get_height() - 100))
        # show text on the Play button
        self.screen.blit(start_btn_label,
                         ((start_btn.x + (start_btn.width - start_btn_label.get_width()) // 2,
                           start_btn.y + (start_btn.height - start_btn_label.get_height()) // 2)))
        ai_toggle_btn = pygame.Rect(
            0, 0, ai_toggle_label.get_width() + 24, 36)
        ai_toggle_btn.center = (
            self.screen.get_rect().centerx,
            start_btn.bottom + 45,
        )
        pygame.draw.rect(self.screen, black_color, ai_toggle_btn)
        self.screen.blit(
            ai_toggle_label,
            (
                ai_toggle_btn.x + (ai_toggle_btn.width - ai_toggle_label.get_width()) // 2,
                ai_toggle_btn.y + (ai_toggle_btn.height - ai_toggle_label.get_height()) // 2,
            ),
        )

        # get pressed keys
        key_pressed = pygame.key.get_pressed()
        #

        # check if left mouse button was clicked
        if utils.left_click_event():
            # call function to get mouse event
            mouse_coords = utils.get_mouse_event()
            if ai_toggle_btn.collidepoint(mouse_coords[0], mouse_coords[1]):
                self.play_against_ai = not self.play_against_ai
            elif start_btn.collidepoint(mouse_coords[0], mouse_coords[1]):
                # change button behavior as it is hovered
                pygame.draw.rect(self.screen, white_color, start_btn, 3)

                self._start_new_game()
        # check if enter or return key was pressed
        elif key_pressed[K_RETURN]:
            self._start_new_game()

    def _start_new_game(self):
        """Tworzy nową partię dopiero po wybraniu jej seeda przy starcie."""
        seed = resolve_game_seed()
        if not self.play_against_ai:
            self.chess = GameLogicLoop(self.screen, black_ai=None, seed=seed)
            self.menu_showed = True
            return

        self._loading_ai = ChessAI()
        self._loading_seed = seed
        self._loading_error = None
        self._loading_cancel_event.clear()
        self._report_loading_progress(
            "Uruchamianie workerów AI", 0, self._loading_ai.max_workers)
        self._loading = True
        try:
            self._loading_future = self._startup_executor.submit(
                self._loading_ai.prepare_workers,
                self._report_worker_progress,
                self._loading_cancel_event,
                minimum_progress_interval_seconds=(
                    _WORKER_PROGRESS_DISPLAY_SECONDS
                ),
            )
        except Exception as error:
            log_error("AI worker initialization could not be scheduled: {}".format(error))
            self._loading = False
            self._loading_error = str(error)

    def _report_worker_progress(self, ready_workers, worker_count):
        self._report_loading_progress(
            "Uruchamianie workerów AI", ready_workers, worker_count)

    def _report_loading_progress(self, step, completed, total):
        with self._loading_progress_lock:
            self._loading_progress = (step, completed, total)

    def _finish_startup_if_ready(self):
        if self._loading_future is None or not self._loading_future.done():
            return

        try:
            self._loading_future.result()
            self.chess = GameLogicLoop(
                self.screen,
                black_ai=self._loading_ai,
                seed=self._loading_seed,
            )
        except WorkerPoolInitializationCancelled:
            self._loading_error = "Inicjalizacja workerów AI została anulowana."
            self._loading = False
        except Exception as error:
            log_error("Game startup failed: {}".format(error))
            self._loading_error = str(error)
            self._loading = False
            if self._loading_ai is not None:
                self._loading_ai.shutdown_worker_pool()
        else:
            self.menu_showed = True
            self._loading = False
        finally:
            self._loading_future = None
            self._loading_ai = None if self.menu_showed else self._loading_ai
            self._loading_seed = None if self.menu_showed else self._loading_seed

    def draw_loading_screen(self):
        """Wyświetla postęp przygotowania workerów przed rozpoczęciem partii."""
        self.screen.fill((24, 24, 24))
        title_font = pygame.font.SysFont(None, 36)
        detail_font = pygame.font.SysFont(None, 22)
        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2

        if self._loading_error is not None:
            title = title_font.render("Nie udało się uruchomić gry", True, (255, 255, 255))
            self.screen.blit(
                title, (center_x - title.get_width() // 2, center_y - 90))
            lines = textwrap.wrap(self._loading_error, width=58) or [""]
            for index, line in enumerate(lines[:4]):
                rendered = detail_font.render(line, True, (255, 190, 190))
                self.screen.blit(
                    rendered,
                    (center_x - rendered.get_width() // 2, center_y - 40 + index * 26),
                )
            prompt = detail_font.render(
                "Naciśnij Enter, aby wrócić do menu", True, (220, 220, 220))
            self.screen.blit(
                prompt, (center_x - prompt.get_width() // 2, center_y + 90))
            return

        title = title_font.render("Przygotowywanie gry...", True, (255, 255, 255))
        self.screen.blit(title, (center_x - title.get_width() // 2, center_y - 75))
        with self._loading_progress_lock:
            step, completed, total = self._loading_progress

        bar_width = min(440, max(180, self.screen.get_width() - 80))
        bar_rect = pygame.Rect(
            center_x - bar_width // 2, center_y, bar_width, 24)
        pygame.draw.rect(self.screen, (90, 90, 90), bar_rect, border_radius=8)
        fraction = min(1.0, completed / total) if total else 0.0
        fill_rect = bar_rect.copy()
        fill_rect.width = round(bar_width * fraction)
        if fill_rect.width:
            pygame.draw.rect(
                self.screen, (80, 190, 110), fill_rect, border_radius=8)

        detail = "{} ({}/{})".format(step, completed, total)
        rendered_detail = detail_font.render(detail, True, (230, 230, 230))
        self.screen.blit(
            rendered_detail,
            (center_x - rendered_detail.get_width() // 2, center_y + 38),
        )

    def _dismiss_loading_error(self):
        self._loading_error = None
        self._loading_ai = None
        self._loading_seed = None
        with self._loading_progress_lock:
            self._loading_progress = ("", 0, 0)

    def _shutdown_resources(self):
        self._loading_cancel_event.set()
        if self._loading_future is not None:
            try:
                self._loading_future.result()
            except WorkerPoolInitializationCancelled:
                pass
            except Exception as error:
                log_error("AI worker initialization failed during shutdown: {}".format(error))
        try:
            if self.chess is not None:
                self.chess.close()
            elif self._loading_ai is not None:
                self._loading_ai.shutdown_worker_pool()
        finally:
            self._startup_executor.shutdown(wait=True, cancel_futures=True)

    def game(self):
        """Rysuje planszę, wykonuje turę i wyświetla ekran zwycięzcy po zakończeniu."""
        if self.winner is not None:
            self.declare_winner(self.winner)
            return

        context = GameContext()
        # background color
        color = (0, 0, 0)
        # set backgound color
        self.screen.fill(color)

        # show the chess board
        self.screen.blit(self.board_img, context.board_starting_point)

        # call self.chess. something
        winner = self.chess.play_turn()
        # draw pieces on the chess board
        self.chess.draw_pieces()
        if self.chess.is_ai_thinking:
            self.chess.draw_ai_thinking_overlay()

        if winner:
            self.winner = winner
            self.declare_winner(winner)

    def declare_winner(self, winner):
        """Wyświetla zwycięzcę i obsługuje rozpoczęcie nowej partii."""
        context = GameContext()
        # background color
        bg_color = (255, 255, 255)
        # set background color
        self.screen.fill(bg_color)
        # black color
        black_color = (0, 0, 0)
        # coordinates for play again button
        reset_btn = pygame.Rect(0, 0, 100, 50)
        reset_btn.center = self.screen.get_rect().center
        # show reset button
        pygame.draw.rect(self.screen, black_color, reset_btn)

        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        big_font = pygame.font.SysFont(context.comic_sans_font, 50)
        small_font = pygame.font.SysFont(context.comic_sans_font, 20)

        # text to show winner
        text = str(winner.value).capitalize() + " wins!"
        winner_text = big_font.render(text, False, black_color)

        # create text to be shown on the reset button
        reset_label = "Play Again"
        reset_btn_label = small_font.render(reset_label, True, white_color)

        # show winner text
        self.screen.blit(winner_text,
                         ((self.screen.get_width() - winner_text.get_width()) // 2,
                          150))

        # show text on the reset button
        self.screen.blit(reset_btn_label,
                         ((reset_btn.x + (reset_btn.width - reset_btn_label.get_width()) // 2,
                           reset_btn.y + (reset_btn.height - reset_btn_label.get_height()) // 2)))

        # check if left mouse button was clicked
        if utils.left_click_event():
            mouse_coords = utils.get_mouse_event()

            # check if reset button was clicked
            if reset_btn.collidepoint(mouse_coords[0], mouse_coords[1]):
                pygame.draw.rect(self.screen, white_color, reset_btn, 3)
                self.chess.reset()
                self.winner = None
        elif pygame.key.get_pressed()[K_RETURN]:
            self.chess.reset()
            self.winner = None
