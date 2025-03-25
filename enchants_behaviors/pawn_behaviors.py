from constants.piece_color import COLOR
from constants.pos import xy_to_id


def pawn_two_field_forward_move(possible_positions_to_move, xy_coord, color, pieces_locations):
    x, y = xy_coord
    color_var = 1
    if color == COLOR.BLACK:
        color_var = -1
    if (color == COLOR.WHITE and y + 2 < 8) or (color == COLOR.BLACK and y - 2 >= 0):
        if not pieces_locations[xy_to_id(x, y + (2 * color_var))].exists():
            if not pieces_locations[xy_to_id(x, y + (1 * color_var))].exists():
                possible_positions_to_move.append([x, y + (2 * color_var)])


def pawn_one_field_backwards_move(possible_positions_to_move, xy_coord, color, pieces_locations):
    x, y = xy_coord
    if color == COLOR.WHITE:
        if y - 1 >= 0:
            possible_positions_to_move.append([x, y - 1])
    elif color == COLOR.BLACK:
        if y + 1 < 8:
            possible_positions_to_move.append([x, y + 1])
