from pathlib import Path

import pygame

from utils import utils


class HelpScreen:
    def __init__(self, markdown_path: Path, background=None):
        self._markdown = markdown_path.read_text(encoding="utf-8")
        self._background = background
        self._overlay = None
        self._content_surface = None
        self._content_width = None
        self._content_height = 0
        self._scroll = 0
        self._max_scroll = 0
        self._title_font = pygame.font.SysFont(None, 40, bold=True)
        self._heading_font = pygame.font.SysFont(None, 28, bold=True)
        self._card_font = pygame.font.SysFont(None, 22, bold=True)
        self._body_font = pygame.font.SysFont(None, 19)
        self._footer_font = pygame.font.SysFont(None, 18)
        self._button_font = pygame.font.SysFont(None, 22)

    def scroll(self, amount):
        self._scroll = max(
            0, min(self._max_scroll, self._scroll - amount * 54))

    def draw(self, screen):
        screen_size = screen.get_size()
        if self._background is not None:
            background = self._background
            if background.get_size() != screen_size:
                background = pygame.transform.smoothscale(
                    background, screen_size)
            screen.blit(background, (0, 0))
        else:
            screen.fill((24, 24, 24))

        if self._overlay is None or self._overlay.get_size() != screen_size:
            self._overlay = pygame.Surface(screen_size, pygame.SRCALPHA)
            self._overlay.fill((0, 0, 0, 170))
        screen.blit(self._overlay, (0, 0))

        title = self._title_font.render("Pomoc", True, (255, 255, 255))
        screen.blit(title, (32, 20))
        view_rect = pygame.Rect(
            32, 76, screen_size[0] - 64, screen_size[1] - 142)
        self._ensure_content(view_rect.width - 14)
        self._max_scroll = max(0, self._content_height - view_rect.height)
        self._scroll = min(self._scroll, self._max_scroll)
        screen.blit(
            self._content_surface,
            view_rect.topleft,
            pygame.Rect(
                0,
                self._scroll,
                self._content_width,
                view_rect.height,
            ),
        )
        self._draw_scrollbar(screen, view_rect)

        footer = self._footer_font.render(
            "Kółko myszy: przewijanie | Esc: powrót",
            True,
            (230, 230, 230),
        )
        screen.blit(footer, (32, screen_size[1] - 42))
        back_button = pygame.Rect(
            screen_size[0] - 150, screen_size[1] - 54, 118, 38)
        pygame.draw.rect(
            screen, (55, 55, 55), back_button, border_radius=6)
        back_label = self._button_font.render(
            "Powrót", True, (255, 255, 255))
        screen.blit(
            back_label,
            (
                back_button.centerx - back_label.get_width() // 2,
                back_button.centery - back_label.get_height() // 2,
            ),
        )

        if utils.left_click_event():
            mouse_position = utils.get_mouse_event()
            return back_button.collidepoint(mouse_position)
        return False

    def _ensure_content(self, width):
        if self._content_surface is not None and self._content_width == width:
            return

        rendered_lines = []
        y = 16
        text_width = max(1, width - 24)
        for source_line in self._markdown.splitlines():
            line = source_line.strip()
            if not line or line == "---":
                y += 10
                continue

            if line.startswith("### "):
                font = self._card_font
                color = (245, 205, 120)
                text = line[4:]
                spacing = 7
            elif line.startswith("## "):
                font = self._heading_font
                color = (170, 210, 255)
                text = line[3:]
                spacing = 10
            elif line.startswith("# "):
                font = self._title_font
                color = (255, 255, 255)
                text = line[2:]
                spacing = 10
            else:
                font = self._body_font
                color = (238, 238, 238)
                text = "- " + line[2:] if line.startswith("- ") else line
                spacing = 2

            text = text.replace("**", "").replace("`", "")
            for wrapped_line in self._wrap_line(font, text, text_width):
                rendered_lines.append((
                    font.render(wrapped_line, True, color),
                    (12, y),
                ))
                y += font.get_linesize() + spacing

        self._content_width = width
        self._content_height = y + 16
        self._content_surface = pygame.Surface(
            (width, self._content_height), pygame.SRCALPHA)
        for image, position in rendered_lines:
            self._content_surface.blit(image, position)

    @staticmethod
    def _wrap_line(font, text, max_width):
        words = text.split()
        if not words:
            return ("",)
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = "{} {}".format(current, word)
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _draw_scrollbar(self, screen, view_rect):
        if self._max_scroll <= 0:
            return

        track = pygame.Rect(
            view_rect.right - 5, view_rect.top, 4, view_rect.height)
        pygame.draw.rect(screen, (80, 80, 80), track, border_radius=2)
        thumb_height = max(
            28,
            round(view_rect.height * view_rect.height / self._content_height),
        )
        thumb_travel = view_rect.height - thumb_height
        thumb_top = view_rect.top + round(
            thumb_travel * self._scroll / self._max_scroll)
        pygame.draw.rect(
            screen,
            (190, 190, 190),
            pygame.Rect(track.x, thumb_top, track.width, thumb_height),
            border_radius=2,
        )
