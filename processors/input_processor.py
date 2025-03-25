import pygame

from constants.pos import xy_to_id
from utils.gamecontext import GameContext
from models.chess_pieces import COLOR
from utils import utils


def get_clicked_chessboard_field_id():
    context = GameContext()
    # get mouse event
    mouse_event = utils.get_mouse_event()
    # if there's a mouse event
    if mouse_event and utils.left_click_event():
        for i in range(len(context.chessboard_coordinates)):
            for j in range(len(context.chessboard_coordinates)):
                rect = pygame.Rect(context.chessboard_coordinates[i][j][0], context.chessboard_coordinates[i][j][1],
                                   context.square_length, context.square_length)
                collision = rect.collidepoint(mouse_event[0], mouse_event[1])
                if collision:
                    selected = [rect.x, rect.y]
                    # find x, y coordinates the selected square
                    k = int((selected[0] - context.board_offset_x) / context.square_length)
                    l = ((int((selected[1] - context.board_offset_y) / context.square_length)) - 7) * -1
                    return xy_to_id(k, l)
    else:
        return None

def get_clicked_captured_piece_index() -> tuple:
    context = GameContext()
    # get mouse event
    mouse_event = utils.get_mouse_event()
    # if there's a mouse event
    if mouse_event and utils.left_click_event():
        coordinates = __calculate_clicked_captured_square_for(context.captured_white_coordinates, mouse_event, context)
        if coordinates:
            row, col = coordinates
            return COLOR.WHITE, (col*2)+row
        else:
            coordinates = __calculate_clicked_captured_square_for(context.captured_black_coordinates, mouse_event, context)
            if coordinates:
                row, col = coordinates
                return COLOR.BLACK, (col*2)+row
    return None, None

def __calculate_clicked_captured_square_for(coordinates_array, mouse_event, context) -> []:
    for i in range(len(coordinates_array)):
        for j in range(len(coordinates_array[i])):
            rect = pygame.Rect(coordinates_array[i][j][0], coordinates_array[i][j][1],
                               context.piece_cell_thumbnail_width, context.piece_cell_thumbnail_height)
            collision = rect.collidepoint(mouse_event[0], mouse_event[1])
            if collision:
                return [i, j]
    return []