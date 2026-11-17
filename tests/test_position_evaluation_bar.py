import pygame

from logic.stage.position_evaluation_bar import PositionEvaluationBar


def test_evaluation_score_maps_to_a_balanced_white_black_bar():
    assert PositionEvaluationBar._white_share(0) == 0.5
    assert PositionEvaluationBar._white_share(2) > 0.5
    assert PositionEvaluationBar._white_share(-2) < 0.5
    assert PositionEvaluationBar._white_share(40) > 0.99
    assert PositionEvaluationBar._white_share(-40) < 0.01


def test_evaluation_bar_animates_score_and_displays_it(monkeypatch):
    if not pygame.font.get_init():
        pygame.font.init()

    ticks = [0]
    rendered_text = []

    class RecordingFont:
        @staticmethod
        def render(text, _antialias, _color):
            rendered_text.append(text)
            return pygame.Surface((max(1, len(text) * 8), 20), pygame.SRCALPHA)

    monkeypatch.setattr(
        "logic.stage.position_evaluation_bar.pygame.time.get_ticks",
        lambda: ticks[0],
    )
    monkeypatch.setattr(
        "logic.stage.position_evaluation_bar.pygame.font.SysFont",
        lambda *args, **kwargs: RecordingFont(),
    )
    bar = PositionEvaluationBar()
    surface = pygame.Surface((1100, 800))
    board_rect = pygame.Rect(300, 120, 640, 640)
    card_panel_color = (180, 0, 180)
    pygame.draw.rect(surface, card_panel_color, pygame.Rect(960, 0, 140, 800))

    bar.draw(surface, board_rect, 0.0)
    assert surface.get_at((954, 121))[:3] == (28, 28, 28)
    assert surface.get_at((954, 758))[:3] == (240, 240, 240)
    assert surface.get_at((980, 300))[:3] == card_panel_color

    ticks[0] = 10
    bar.draw(surface, board_rect, 2.0)
    assert bar._animated_score(10) == 0.0
    ticks[0] = 110
    bar.draw(surface, board_rect, 2.0)
    assert 0 < bar._animated_score(110) < 2.0
    ticks[0] = 210
    bar.draw(surface, board_rect, 2.0)

    assert bar._animated_score(210) == 2.0
    assert rendered_text[-1] == "+2.00"
