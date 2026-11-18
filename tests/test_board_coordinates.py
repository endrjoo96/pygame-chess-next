import pygame

from constants.pos import xy_to_id
from processors.input_processor import get_clicked_chessboard_field_id
from utils import utils
from utils.board_coordinates import initialize_board_coordinates
from utils.gamecontext import GameContext


def test_clicks_map_to_the_same_logical_squares_from_both_viewpoints(monkeypatch):
    context = GameContext()
    monkeypatch.setattr(context, "board_offset_x", 0, raising=False)
    monkeypatch.setattr(context, "board_offset_y", 0, raising=False)
    monkeypatch.setattr(context, "chessboard_coordinates", [], raising=False)
    board_image = pygame.Surface((640, 640))
    square_length = 80

    for flipped in (False, True):
        initialize_board_coordinates(context, board_image, flipped=flipped)
        assert context.square_length == square_length

        for board_x in range(8):
            for board_y in range(8):
                screen_x = 7 - board_x if flipped else board_x
                screen_y = board_y if flipped else 7 - board_y
                click = pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=(
                        screen_x * square_length + square_length // 2,
                        screen_y * square_length + square_length // 2,
                    ),
                )
                utils.begin_input_frame([click])

                assert get_clicked_chessboard_field_id() == xy_to_id(
                    board_x, board_y)
