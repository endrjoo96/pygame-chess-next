import math
from typing import Optional

import pygame


class PositionEvaluationBar:
    """Rysuje i animuje przewagę białych lub czarnych przy planszy."""

    BAR_WIDTH = 14
    BAR_GAP = 4
    LABEL_GAP = 4
    ANIMATION_DURATION_MS = 200
    SCORE_SCALE = 4.0

    def __init__(self):
        self._font = pygame.font.SysFont(None, 20)
        self._target_score: Optional[float] = None
        self._start_score = 0.0
        self._animation_started_at = 0

    def draw(
        self, surface: pygame.Surface, board_rect: pygame.Rect, score: float,
    ) -> None:
        now = pygame.time.get_ticks()
        if self._target_score is None:
            self._target_score = score
            self._start_score = score
            self._animation_started_at = now
        elif score != self._target_score:
            self._start_score = self._animated_score(now)
            self._target_score = score
            self._animation_started_at = now

        displayed_score = self._animated_score(now)
        bar_rect = pygame.Rect(
            board_rect.right + self.BAR_GAP,
            board_rect.top,
            self.BAR_WIDTH,
            board_rect.height,
        )
        white_height = round(
            bar_rect.height * self._white_share(displayed_score))
        pygame.draw.rect(surface, (28, 28, 28), bar_rect)
        if white_height:
            pygame.draw.rect(
                surface,
                (240, 240, 240),
                pygame.Rect(
                    bar_rect.left,
                    bar_rect.bottom - white_height,
                    bar_rect.width,
                    white_height,
                ),
            )
        pygame.draw.rect(surface, (110, 110, 110), bar_rect, 1)

        score_text = self._font.render(
            "{:+.2f}".format(displayed_score), True, (235, 235, 235))
        surface.blit(
            score_text,
            (
                max(
                    0,
                    bar_rect.left - score_text.get_width() - self.LABEL_GAP,
                ),
                max(
                    0,
                    board_rect.top - score_text.get_height() - self.LABEL_GAP,
                ),
            ),
        )

    def _animated_score(self, now: int) -> float:
        if self._target_score is None:
            return 0.0
        progress = min(
            1.0,
            max(
                0.0,
                (now - self._animation_started_at)
                / self.ANIMATION_DURATION_MS,
            ),
        )
        eased_progress = 1 - (1 - progress) ** 3
        return self._start_score + (
            self._target_score - self._start_score
        ) * eased_progress

    @classmethod
    def _white_share(cls, score: float) -> float:
        return 0.5 + 0.5 * math.tanh(score / cls.SCORE_SCALE)
