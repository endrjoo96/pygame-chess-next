from concurrent.futures import Future
from threading import Event, Lock

import pygame

from logic.stage.main_menu_loop import Game


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
    game.paused = False
    game._pause_background = None
    game.running = True
    game.winner = None
    game.screen = object()
    game.chess = None
    return game


def test_ai_startup_reports_worker_progress_before_creating_game(monkeypatch):
    game = make_game()
    ai = FakeAI()
    created_games = []
    stats_windows = []

    def create_stats_window():
        window = FakeStatsWindow()
        stats_windows.append(window)
        return window

    monkeypatch.setattr("logic.stage.main_menu_loop.ChessAI", lambda: ai)
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


def test_loading_screen_renders_worker_progress_bar():
    if not pygame.font.get_init():
        pygame.font.init()
    game = make_game()
    game.screen = pygame.Surface((800, 600))
    game._loading_progress = ("Uruchamianie workerów AI", 2, 4)

    game.draw_loading_screen()

    assert game.screen.get_at((200, 312)) == (80, 190, 110, 255)


def test_pause_menu_has_requested_actions_and_toggles_debug_window(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()
    game = make_game()
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
        "resume", "main_menu", "quit", "toggle_debug"]
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


def test_escape_opens_and_closes_pause_during_a_game():
    game = make_game()
    game.screen = pygame.Surface((800, 600))
    game.menu_showed = True
    escape_event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)

    game._handle_app_event(escape_event)

    assert game.paused
    assert game._pause_background.get_size() == (800, 600)

    game._handle_app_event(escape_event)

    assert not game.paused
    assert game._pause_background is None


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
