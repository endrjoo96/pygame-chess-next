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
    game.screen = object()
    game.chess = None
    return game


def test_ai_startup_reports_worker_progress_before_creating_game(monkeypatch):
    game = make_game()
    ai = FakeAI()
    created_games = []
    monkeypatch.setattr("logic.stage.main_menu_loop.ChessAI", lambda: ai)
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


def test_loading_screen_renders_worker_progress_bar():
    if not pygame.font.get_init():
        pygame.font.init()
    game = make_game()
    game.screen = pygame.Surface((800, 600))
    game._loading_progress = ("Uruchamianie workerów AI", 2, 4)

    game.draw_loading_screen()

    assert game.screen.get_at((200, 312)) == (80, 190, 110, 255)
