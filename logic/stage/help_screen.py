import re
from pathlib import Path

import pygame

from utils import utils


_ICON_SIZE = 22
_ICON_TOKEN = re.compile(
    r":(PASSIVE|BUFF|REUSABLE|DELAY_BEFORE_USE|STUN_AFTER_USE):")
_ICON_FILES = {
    "PASSIVE": "card_mod_passive.png",
    "BUFF": "card_mod_buff.png",
    "REUSABLE": "card_mod_reusable.png",
    "DELAY_BEFORE_USE": "card_mod_delay.png",
    "STUN_AFTER_USE": "card_mod_stun.png",
}


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
        self._scrollbar_track = None
        self._scrollbar_thumb = None
        self._dragging_scrollbar = False
        self._scrollbar_drag_offset = 0
        self._title_font = pygame.font.SysFont(None, 40, bold=True)
        self._heading_font = pygame.font.SysFont(None, 28, bold=True)
        self._card_font = pygame.font.SysFont(None, 22, bold=True)
        self._body_font = pygame.font.SysFont(None, 19)
        self._footer_font = pygame.font.SysFont(None, 18)
        self._button_font = pygame.font.SysFont(None, 22)
        resource_dir = Path(__file__).resolve().parents[2] / "res"
        self._icons = {
            token: pygame.transform.smoothscale(
                pygame.image.load(str(resource_dir / filename)),
                (_ICON_SIZE, _ICON_SIZE),
            )
            for token, filename in _ICON_FILES.items()
        }

    def scroll(self, amount):
        self._scroll = max(
            0, min(self._max_scroll, self._scroll - amount * 54))

    def begin_scroll_drag(self, position):
        self._dragging_scrollbar = False
        if self._scrollbar_thumb is None or self._scrollbar_track is None:
            return False
        if self._scrollbar_thumb.collidepoint(position):
            self._scrollbar_drag_offset = (
                position[1] - self._scrollbar_thumb.top)
        elif self._scrollbar_track.collidepoint(position):
            self._scrollbar_drag_offset = self._scrollbar_thumb.height // 2
        else:
            return False

        self._dragging_scrollbar = True
        self._drag_scrollbar_to(position[1])
        return True

    def drag_scrollbar(self, y):
        if self._dragging_scrollbar:
            self._drag_scrollbar_to(y)

    def end_scroll_drag(self):
        self._dragging_scrollbar = False

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
            for wrapped_line in self._wrap_inline(font, text, text_width):
                line_height = max(
                    font.get_linesize(),
                    _ICON_SIZE if any(kind == "icon" for kind, _, _ in wrapped_line)
                    else 0,
                )
                x = 12
                for kind, value, gap in wrapped_line:
                    x += gap
                    if kind == "icon":
                        image = self._icons[value]
                    else:
                        image = font.render(value, True, color)
                    rendered_lines.append((
                        image,
                        (
                            x,
                            y + (line_height - image.get_height()) // 2,
                        ),
                    ))
                    x += image.get_width()
                y += line_height + spacing

        self._content_width = width
        self._content_height = y + 16
        self._content_surface = pygame.Surface(
            (width, self._content_height), pygame.SRCALPHA)
        for image, position in rendered_lines:
            self._content_surface.blit(image, position)

    def _wrap_inline(self, font, text, max_width):
        tokens = []
        pieces = _ICON_TOKEN.split(text)
        for index, piece in enumerate(pieces):
            if index % 2:
                tokens.append(("icon", piece))
            else:
                tokens.extend(
                    ("text", word) for word in piece.split())

        lines = [[]]
        line_width = 0
        space_width = font.size(" ")[0]
        for kind, value in tokens:
            token_width = (
                self._icons[value].get_width()
                if kind == "icon"
                else font.size(value)[0]
            )
            gap = space_width if lines[-1] else 0
            if lines[-1] and line_width + gap + token_width > max_width:
                lines.append([])
                line_width = 0
                gap = 0
            lines[-1].append((kind, value, gap))
            line_width += gap + token_width
        return [line for line in lines if line]

    def _draw_scrollbar(self, screen, view_rect):
        self._scrollbar_track = None
        self._scrollbar_thumb = None
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
        thumb = pygame.Rect(track.x, thumb_top, track.width, thumb_height)
        self._scrollbar_track = track
        self._scrollbar_thumb = thumb
        pygame.draw.rect(screen, (190, 190, 190), thumb, border_radius=2)

    def _drag_scrollbar_to(self, y):
        if self._scrollbar_track is None or self._scrollbar_thumb is None:
            return
        thumb_travel = (
            self._scrollbar_track.height - self._scrollbar_thumb.height)
        if thumb_travel <= 0:
            return
        thumb_top = max(
            self._scrollbar_track.top,
            min(
                self._scrollbar_track.bottom - self._scrollbar_thumb.height,
                y - self._scrollbar_drag_offset,
            ),
        )
        progress = (
            (thumb_top - self._scrollbar_track.top) / thumb_travel)
        self._scroll = round(progress * self._max_scroll)
