from concurrent.futures import Future
from threading import Event, Lock
from types import SimpleNamespace

import pygame
import pytest

from logic.stage.main_menu_loop import Game
from utils.run_config import RunMode


class ImmediateExecutor:
    def __init__(self):
        self.submissions = 0

    def submit(self, function, *args, **kwargs):
        self.submissions += 1
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as error:
            future.set_exception(error)
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        return None


class FakeAI:
    def __init__(self, fail=False):
        self.max_workers = 3
        self.fail = fail
        self.shutdown_calls = 0
        self.minimum_progress_interval_seconds = None

    def prepare_workers(
        self,
        progress_callback,
        cancellation_event,
        minimum_progress_interval_seconds=0.0,
    ):
        self.minimum_progress_interval_seconds = (
            minimum_progress_interval_seconds
        )
        if self.fail:
            raise RuntimeError("worker startup failed")
        for ready_workers in range(1, self.max_workers + 1):
            progress_callback(ready_workers, self.max_workers)

    def shutdown_worker_pool(self):
        self.shutdown_calls += 1


class FakeStatsWindow:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeChess:
    def __init__(self, black_ai=None):
        self.black_ai = black_ai
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def make_game(play_against_ai=True):
    game = Game.__new__(Game)
    game.play_against_ai = play_against_ai
    game._startup_executor = ImmediateExecutor()
    game._loading = False
    game._loading_future = None
    game._loading_ai = None
    game._loading_seed = None
    game._loading_cancel_event = Event()
    game._loading_progress_lock = Lock()
    game._loading_progress = ("", 0, 0)
    game._loading_error = None
    game.menu_showed = False
    game.ai_stats_window = None
    game._help_screen = None
    game.paused = False
    game._pause_background = None
    game.running = True
    game.winner = None
    game.screen = object()
    game.chess = None
    return game


def test_game_initialization_supports_window_without_dynamic_attributes(
    monkeypatch,
):
    class FakeScreen:
        def fill(self, _color):
            pass

    class FakeImage:
        def convert(self):
            return self

    class StrictWindow:
        __slots__ = ()

        @staticmethod
        def from_display_module():
            return StrictWindow()

    screen = FakeScreen()
    monkeypatch.setattr("logic.stage.main_menu_loop.Window", StrictWindow)
    monkeypatch.setattr("logic.stage.main_menu_loop.PositionEvaluationBar", object)
    monkeypatch.setattr("logic.stage.main_menu_loop.Game._create_blurred_menu_background",
                        lambda _self: None)
    monkeypatch.setattr(pygame.display, "init", lambda: None)
    monkeypatch.setattr(pygame.display, "set_mode", lambda *_args: screen)
    monkeypatch.setattr(pygame.display, "set_caption", lambda _title: None)
    monkeypatch.setattr(pygame.display, "set_icon", lambda _icon: None)
    monkeypatch.setattr(pygame.display, "flip", lambda: None)
    monkeypatch.setattr(pygame.font, "init", lambda: None)
    monkeypatch.setattr(pygame.image, "load", lambda _path: FakeImage())
    monkeypatch.setattr(pygame.time, "Clock", object)

    game = Game()

    assert game.screen is screen
    assert isinstance(game.window, StrictWindow)


@pytest.mark.parametrize("run_mode", [RunMode.DEBUG, RunMode.DIAG])
def test_ai_startup_reports_worker_progress_before_creating_game(
    monkeypatch, run_mode,
):
    game = make_game()
    ai = FakeAI()
    created_games = []
    stats_windows = []

    def create_stats_window():
        window = FakeStatsWindow()
        stats_windows.append(window)
        return window

    monkeypatch.setattr("logic.stage.main_menu_loop.ChessAI", lambda: ai)
    monkeypatch.setattr("logic.stage.main_menu_loop.RUN_MODE", run_mode)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.AIStatsWindow", create_stats_window)
    monkeypatch.setattr("logic.stage.main_menu_loop.resolve_game_seed", lambda: 23)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.GameLogicLoop",
        lambda screen, black_ai, seed: created_games.append((screen, black_ai, seed)),
    )

    game._start_new_game()

    assert game._loading
    assert game._loading_progress == ("Uruchamianie workerów AI", 3, 3)
    assert created_games == []
    assert ai.minimum_progress_interval_seconds == 0.06

    game._finish_startup_if_ready()

    assert game.menu_showed
    assert not game._loading
    assert created_games == [(game.screen, ai, 23)]
    assert game.ai_stats_window is stats_windows[0]


def test_starting_without_ai_skips_worker_initialization(monkeypatch):
    game = make_game(play_against_ai=False)
    created_games = []
    monkeypatch.setattr("logic.stage.main_menu_loop.resolve_game_seed", lambda: 24)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.GameLogicLoop",
        lambda screen, black_ai, seed: created_games.append((screen, black_ai, seed)),
    )

    game._start_new_game()

    assert game._startup_executor.submissions == 0
    assert game.menu_showed
    assert game.ai_stats_window is None
    assert created_games == [(game.screen, None, 24)]


def test_prod_mode_skips_diagnostics_and_hides_pause_toggle(monkeypatch):
    game = make_game()
    game._loading_future = Future()
    game._loading_future.set_result(None)
    game._loading_ai = FakeAI()
    game._loading_seed = 27
    monkeypatch.setattr("logic.stage.main_menu_loop.RUN_MODE", RunMode.PROD)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.GameLogicLoop",
        lambda _screen, black_ai, seed: FakeChess(black_ai),
    )

    def unexpected_stats_window():
        raise AssertionError("PROD must not create an AI diagnostics window")

    monkeypatch.setattr(
        "logic.stage.main_menu_loop.AIStatsWindow", unexpected_stats_window)

    game._finish_startup_if_ready()

    assert game.menu_showed
    assert game.ai_stats_window is None
    assert [action for action, _ in game._pause_menu_options()] == [
        "resume", "main_menu", "quit", "help"]
    game._handle_pause_menu_action("toggle_debug")
    assert game.ai_stats_window is None


def test_worker_startup_failure_is_shown_and_pool_is_shutdown(monkeypatch):
    game = make_game()
    ai = FakeAI(fail=True)
    monkeypatch.setattr("logic.stage.main_menu_loop.ChessAI", lambda: ai)
    monkeypatch.setattr("logic.stage.main_menu_loop.resolve_game_seed", lambda: 25)
    monkeypatch.setattr("logic.stage.main_menu_loop.log_error", lambda message: None)

    game._start_new_game()
    game._finish_startup_if_ready()

    assert not game.menu_showed
    assert not game._loading
    assert game._loading_error == "worker startup failed"
    assert ai.shutdown_calls == 1


def test_game_initialization_failure_closes_stats_window(monkeypatch):
    game = make_game()
    ai = FakeAI()
    stats_windows = []

    def create_stats_window():
        window = FakeStatsWindow()
        stats_windows.append(window)
        return window

    monkeypatch.setattr("logic.stage.main_menu_loop.ChessAI", lambda: ai)
    monkeypatch.setattr("logic.stage.main_menu_loop.RUN_MODE", RunMode.DIAG)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.AIStatsWindow", create_stats_window)
    monkeypatch.setattr("logic.stage.main_menu_loop.resolve_game_seed", lambda: 26)

    def fail_game_initialization(screen, black_ai, seed):
        assert screen is game.screen
        assert black_ai is ai
        assert seed == 26
        raise RuntimeError("game initialization failed")

    monkeypatch.setattr(
        "logic.stage.main_menu_loop.GameLogicLoop",
        fail_game_initialization,
    )
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.log_error", lambda message: None)

    game._start_new_game()
    game._finish_startup_if_ready()

    assert not game.menu_showed
    assert game._loading_error == "game initialization failed"
    assert stats_windows[0].closed
    assert game.ai_stats_window is None
    assert ai.shutdown_calls == 1


def test_game_draws_position_evaluation_to_the_right_of_the_board():
    draw_calls = []

    class GameChessStub:
        is_ai_thinking = True
        position_evaluation = 0.75

        @staticmethod
        def play_turn():
            return None

        @staticmethod
        def draw_pieces():
            draw_calls.append("pieces")

        @staticmethod
        def draw_ai_thinking_overlay():
            draw_calls.append("thinking_overlay")

    class RecordingEvaluationBar:
        def __init__(self):
            self.draw_args = None

        def draw(self, target_surface, target_board_rect, target_score):
            draw_calls.append("evaluation_bar")
            self.draw_args = (
                target_surface, target_board_rect, target_score)

    game = Game.__new__(Game)
    game.winner = None
    game.screen = pygame.Surface((1240, 880))
    game.board_img = pygame.Surface((640, 640))
    game.chess = GameChessStub()
    game.position_evaluation_bar = RecordingEvaluationBar()

    game.game()

    surface, board_rect, score = game.position_evaluation_bar.draw_args
    assert surface is game.screen
    assert board_rect == pygame.Rect(300, 120, 640, 640)
    assert score == 0.75
    assert draw_calls == ["evaluation_bar", "pieces", "thinking_overlay"]


def test_main_menu_help_button_opens_the_help_screen(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()

    class FakeHelpScreen:
        def __init__(self, path, background):
            self.path = path
            self.background = background

    game = make_game()
    game.screen = pygame.Surface((1240, 880))
    game._blurred_menu_background = pygame.Surface((1240, 880))
    game.play_against_ai = False
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.HelpScreen", FakeHelpScreen)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.utils.left_click_event", lambda: True)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.utils.get_mouse_event",
        lambda: (620, 560),
    )
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.pygame.key.get_pressed",
        lambda: [0] * 512,
    )

    game.menu()

    assert isinstance(game._help_screen, FakeHelpScreen)
    assert game._help_screen.background is game._blurred_menu_background


def test_pause_menu_help_opens_without_leaving_pause(monkeypatch):
    class FakeHelpScreen:
        def __init__(self, path, background):
            self.path = path
            self.background = background

    game = make_game()
    game.paused = True
    game._pause_background = pygame.Surface((800, 600))
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.HelpScreen", FakeHelpScreen)

    game._handle_pause_menu_action("help")

    assert game.paused
    assert isinstance(game._help_screen, FakeHelpScreen)
    assert game._help_screen.background is game._pause_background


def test_help_screen_scrolls_and_escape_returns_to_pause():
    class ScrollableHelpScreen:
        def __init__(self):
            self.scroll_amounts = []

        def scroll(self, amount):
            self.scroll_amounts.append(amount)

    game = make_game()
    game.menu_showed = True
    game.paused = True
    game._help_screen = ScrollableHelpScreen()

    game._handle_app_event(
        pygame.event.Event(pygame.MOUSEWHEEL, y=-1))
    assert game._help_screen.scroll_amounts == [-1]

    game._handle_app_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert game._help_screen is None
    assert game.paused


@pytest.mark.parametrize(
    "event_type", [pygame.VIDEORESIZE, pygame.WINDOWRESIZED])
def test_window_resize_keeps_minimum_game_dimensions(event_type):
    class FakeWindow:
        size = (900, 1000)

    game = make_game()
    game.window = FakeWindow()

    game._handle_app_event(pygame.event.Event(event_type))

    assert game.window.size == (1240, 1000)


def test_menu_uses_its_blurred_board_background(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    game = Game.__new__(Game)
    game.screen = pygame.Surface((1240, 880))
    game._blurred_menu_background = pygame.Surface((1240, 880))
    game._blurred_menu_background.fill((60, 70, 80))
    game.play_against_ai = False
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.utils.left_click_event", lambda: False)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.pygame.key.get_pressed",
        lambda: [0] * 512,
    )

    game.menu()

    assert game.screen.get_at((0, 0))[:3] == (60, 70, 80)


def test_loading_screen_renders_worker_progress_bar():
    if not pygame.font.get_init():
        pygame.font.init()
    game = make_game()
    game.screen = pygame.Surface((800, 600))
    game._loading_progress = ("Uruchamianie workerów AI", 2, 4)

    game.draw_loading_screen()

    assert game.screen.get_at((200, 312)) == (80, 190, 110, 255)


def test_winner_screen_keeps_the_board_visible_under_a_translucent_overlay(
    monkeypatch,
):
    if not pygame.font.get_init():
        pygame.font.init()
    game = make_game()
    game.screen = pygame.Surface((1240, 880))
    game.board_img = pygame.Surface((640, 640))
    game.board_img.fill((40, 90, 140))

    class FakeChess:
        draw_calls = 0

        def draw_pieces(self):
            self.draw_calls += 1

    game.chess = FakeChess()
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.utils.left_click_event", lambda: False)
    monkeypatch.setattr(
        pygame.key, "get_pressed", lambda: {pygame.K_RETURN: False})
    winner = SimpleNamespace(value="black")

    game.declare_winner(winner)
    board_pixel = game.screen.get_at((350, 130))
    game.declare_winner(winner)

    assert board_pixel[:3] != (40, 90, 140)
    assert board_pixel[:3] != (255, 255, 255)
    assert game.screen.get_at((350, 130)) == board_pixel
    assert game.chess.draw_calls == 2


def test_pause_menu_has_requested_actions_and_toggles_debug_window(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    game = make_game()
    monkeypatch.setattr("logic.stage.main_menu_loop.RUN_MODE", RunMode.DIAG)
    game.screen = pygame.Surface((800, 600))
    game.paused = True
    game._pause_background = pygame.Surface((800, 600))
    game.chess = FakeChess(black_ai=object())
    stats_windows = []

    def create_stats_window():
        window = FakeStatsWindow()
        stats_windows.append(window)
        return window

    monkeypatch.setattr(
        "logic.stage.main_menu_loop.AIStatsWindow", create_stats_window)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.utils.left_click_event", lambda: True)
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.utils.get_mouse_event",
        lambda: game._pause_menu_buttons()[0][2].center,
    )

    assert [action for action, _ in game._pause_menu_options()] == [
        "resume", "main_menu", "quit", "help", "toggle_debug"]
    game.draw_pause_menu()
    assert not game.paused

    game.paused = True
    game._pause_background = pygame.Surface((800, 600))
    game._handle_pause_menu_action("toggle_debug")
    assert game.ai_stats_window is stats_windows[0]
    assert game._pause_menu_options()[-1][1] == "Zamknij okno debugowania"

    game._handle_pause_menu_action("toggle_debug")
    assert game.ai_stats_window is None
    assert stats_windows[0].closed


def test_escape_opens_and_closes_pause_during_a_game(monkeypatch):
    game = make_game()
    game.screen = pygame.Surface((800, 600))
    game.menu_showed = True
    blurred_background = pygame.Surface((800, 600))
    monkeypatch.setattr(
        "logic.stage.main_menu_loop.blur_surface",
        lambda _surface: blurred_background,
    )
    escape_event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)

    game._handle_app_event(escape_event)

    assert game.paused
    assert game._pause_background is blurred_background

    game._handle_app_event(escape_event)

    assert not game.paused
    assert game._pause_background is None


def test_space_does_not_reset_game_during_action_animation():
    class AnimatingChess:
        is_action_animation_active = True
        reset_calls = 0

        def reset(self):
            self.reset_calls += 1

    game = make_game()
    game.menu_showed = True
    game.chess = AnimatingChess()

    game._handle_app_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

    assert game.chess.reset_calls == 0


def test_pause_menu_can_end_game_and_return_to_main_menu():
    game = make_game()
    chess = FakeChess(black_ai=object())
    stats_window = FakeStatsWindow()
    game.chess = chess
    game.ai_stats_window = stats_window
    game.menu_showed = True
    game.paused = True
    game.winner = "white"

    game._handle_pause_menu_action("main_menu")

    assert chess.close_calls == 1
    assert stats_window.closed
    assert game.chess is None
    assert game.ai_stats_window is None
    assert not game.menu_showed
    assert not game.paused
    assert game.winner is None


def test_pause_menu_quit_stops_the_game():
    game = make_game()
    game.paused = True

    game._handle_pause_menu_action("quit")

    assert not game.running
