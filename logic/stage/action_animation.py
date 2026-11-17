import math
from dataclasses import dataclass
from typing import Optional, Tuple

import pygame

from constants.piece_color import COLOR
from constants.pos import id_to_xy
from logic.game_rules import GameAction, GameActionType
from utils.gamecontext import GameContext


@dataclass(frozen=True)
class PieceMotion:
    piece_name: str
    start: Tuple[int, int]
    end: Tuple[int, int]
    destination: int
    start_size: Optional[Tuple[int, int]] = None
    end_size: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class CardMotion:
    image: pygame.Surface
    start: Tuple[int, int]
    end: Tuple[int, int]
    end_size: Tuple[int, int]
    hand_slot: Tuple[COLOR, int]


class ActionAnimation:
    def __init__(
        self,
        duration_ms: int,
        piece_motions=(),
        card_motion: Optional[CardMotion] = None,
        started_at: Optional[int] = None,
        captured_slot=None,
    ):
        self.duration_ms = duration_ms
        self.piece_motions = tuple(piece_motions)
        self.card_motion = card_motion
        self._captured_slot = captured_slot
        self.started_at = (
            pygame.time.get_ticks() if started_at is None else started_at)

    @classmethod
    def from_transition(
        cls,
        before_state,
        after_state,
        action: GameAction,
        context: GameContext,
        cards_processor,
        chess_pieces,
        duration_ms: int,
    ):
        if duration_ms == 0:
            return None

        piece_motions = cls._piece_motions(
            before_state, after_state, action, context)
        card_motion = cls._card_motion(
            before_state,
            action,
            context,
            cards_processor,
            chess_pieces,
        )
        if not piece_motions and card_motion is None:
            return None
        captured_slot = (
            (action.captured_color, action.captured_index)
            if action.action_type == GameActionType.RESURRECT and piece_motions
            else None
        )
        return cls(
            duration_ms, piece_motions, card_motion,
            captured_slot=captured_slot)

    @staticmethod
    def _board_point(context, position):
        x, y = id_to_xy(position)
        return tuple(context.chessboard_coordinates[x][y])

    @classmethod
    def _make_piece_motion(
        cls, before_state, after_state, context, source, destination,
    ):
        if source not in range(1, 65) or destination not in range(1, 65):
            return None

        before_piece = before_state.pieces_locations[source]
        after_piece = after_state.pieces_locations[destination]
        if (
            not before_piece.exists()
            or not after_piece.exists()
            or before_piece.get_color() != after_piece.get_color()
            or before_piece.get_type() != after_piece.get_type()
        ):
            return None
        return PieceMotion(
            before_piece.full_name(),
            cls._board_point(context, source),
            cls._board_point(context, destination),
            destination,
        )

    @classmethod
    def _piece_motions(cls, before_state, after_state, action, context):
        if action.action_type in (
            GameActionType.MOVE,
            GameActionType.RETURN_TO_START,
        ):
            motion = cls._make_piece_motion(
                before_state, after_state, context,
                action.source, action.destination)
            return (motion,) if motion is not None else ()

        if action.action_type == GameActionType.TELEPORT:
            motions = (
                cls._make_piece_motion(
                    before_state, after_state, context,
                    action.source, action.destination),
                cls._make_piece_motion(
                    before_state, after_state, context,
                    action.destination, action.source),
            )
            return tuple(motion for motion in motions if motion is not None)

        if action.action_type == GameActionType.TREBUCHET:
            motion = cls._make_piece_motion(
                before_state, after_state, context,
                action.secondary_source, action.destination)
            return (motion,) if motion is not None else ()

        if action.action_type == GameActionType.RESURRECT:
            captured = before_state.get_captured_for(action.captured_color)
            if not 0 <= action.captured_index < len(captured):
                return ()
            before_piece = captured[action.captured_index]
            if action.destination not in range(1, 65):
                return ()
            after_piece = after_state.pieces_locations[action.destination]
            if (
                not after_piece.exists()
                or before_piece.get_color() != after_piece.get_color()
                or before_piece.get_type() != after_piece.get_type()
            ):
                return ()
            starting_point = (
                context.captured_white_starting_point
                if action.captured_color == COLOR.WHITE
                else context.captured_black_starting_point
            )
            if not starting_point:
                return ()
            start = (
                starting_point[0]
                + (action.captured_index // 2)
                * context.piece_cell_thumbnail_width,
                starting_point[1]
                + (action.captured_index % 2)
                * context.piece_cell_thumbnail_height,
            )
            return (PieceMotion(
                before_piece.full_name(),
                start,
                cls._board_point(context, action.destination),
                action.destination,
                (
                    context.piece_cell_thumbnail_width,
                    context.piece_cell_thumbnail_height,
                ),
                (context.square_length, context.square_length),
            ),)

        return ()

    @classmethod
    def _card_motion(
        cls, before_state, action, context, cards_processor, chess_pieces,
    ):
        if action.card_index < 0:
            return None

        card_color = before_state.current_turn
        cards = before_state.get_cards_for(card_color)
        if action.card_index >= len(cards):
            return None
        card_rows = (
            context.white_cards_coordinates
            if card_color == COLOR.WHITE
            else context.black_cards_coordinates
        )
        row, column = divmod(
            action.card_index, cards_processor.CARD_COLUMNS)
        if row >= len(card_rows) or column >= len(card_rows[row]):
            return None

        card_width = context.card_width
        card_height = context.card_height
        if card_width <= 0 or card_height <= 0:
            return None
        image = pygame.Surface(
            (card_width, card_height), pygame.SRCALPHA)
        cards_processor.render_preview(
            image,
            chess_pieces,
            cards[action.card_index],
            (0, 0),
            card_color,
        )
        image_width, image_height = image.get_size()
        target_size_scale = min(
            1.0,
            0.72 * context.square_length / image_width,
            0.72 * context.square_length / image_height,
        )
        end_size = (
            max(1, round(image_width * target_size_scale)),
            max(1, round(image_height * target_size_scale)),
        )

        target_position = (
            action.destination
            if action.destination in range(1, 65)
            else action.source
        )
        if target_position in range(1, 65):
            target_x, target_y = cls._board_point(context, target_position)
        else:
            board_x, board_y = context.board_starting_point
            target_x = board_x + 4 * context.square_length
            target_y = board_y + 4 * context.square_length
        end = (
            target_x + (context.square_length - end_size[0]) // 2,
            target_y + (context.square_length - end_size[1]) // 2,
        )
        return CardMotion(
            image,
            tuple(card_rows[row][column]),
            end,
            end_size,
            (card_color, action.card_index),
        )

    def _raw_progress(self, now=None):
        if self.duration_ms <= 0:
            return 1.0
        if now is None:
            now = pygame.time.get_ticks()
        return min(
            1.0,
            max(0.0, (now - self.started_at) / self.duration_ms),
        )

    @property
    def is_active(self):
        return self.is_active_at(pygame.time.get_ticks())

    def is_active_at(self, now):
        return self.duration_ms > 0 and self._raw_progress(now) < 1.0

    def hidden_piece_positions(self, now=None):
        if now is None:
            now = pygame.time.get_ticks()
        if not self.is_active_at(now):
            return ()
        return tuple(motion.destination for motion in self.piece_motions)

    @property
    def hidden_card_slot(self):
        return self.hidden_card_slot_at(pygame.time.get_ticks())

    def hidden_card_slot_at(self, now):
        if self.is_active_at(now) and self.card_motion is not None:
            return self.card_motion.hand_slot
        return None

    @property
    def hidden_captured_slot(self):
        return self.hidden_captured_slot_at(pygame.time.get_ticks())

    def hidden_captured_slot_at(self, now):
        return self._captured_slot if self.is_active_at(now) else None

    def draw(self, surface, chess_pieces, now=None):
        if now is None:
            now = pygame.time.get_ticks()
        raw_progress = self._raw_progress(now)
        if not self.is_active_at(now):
            return False
        progress = raw_progress * raw_progress * (3 - 2 * raw_progress)

        for motion in self.piece_motions:
            position = (
                round(motion.start[0] + (motion.end[0] - motion.start[0]) * progress),
                round(motion.start[1] + (motion.end[1] - motion.start[1]) * progress),
            )
            if motion.start_size is None or motion.end_size is None:
                chess_pieces.draw(surface, motion.piece_name, position)
            else:
                sprite = pygame.Surface(motion.end_size, pygame.SRCALPHA)
                chess_pieces.draw(sprite, motion.piece_name, (0, 0))
                size = (
                    max(1, round(
                        motion.start_size[0]
                        + (motion.end_size[0] - motion.start_size[0])
                        * progress)),
                    max(1, round(
                        motion.start_size[1]
                        + (motion.end_size[1] - motion.start_size[1])
                        * progress)),
                )
                surface.blit(
                    pygame.transform.smoothscale(sprite, size), position)

        if self.card_motion is not None:
            self._draw_card(surface, self.card_motion, raw_progress, progress)
        return True

    @staticmethod
    def _draw_card(surface, motion, raw_progress, progress):
        start_width, start_height = motion.image.get_size()
        width = max(
            1,
            round(start_width + (motion.end_size[0] - start_width) * progress),
        )
        height = max(
            1,
            round(start_height + (motion.end_size[1] - start_height) * progress),
        )
        image = (
            motion.image
            if (width, height) == motion.image.get_size()
            else pygame.transform.smoothscale(motion.image, (width, height))
        )
        arc_height = min(48, height)
        x = round(motion.start[0] + (motion.end[0] - motion.start[0]) * progress)
        y = round(
            motion.start[1] + (motion.end[1] - motion.start[1]) * progress
            - math.sin(math.pi * raw_progress) * arc_height
        )
        surface.blit(image, (x, y))
