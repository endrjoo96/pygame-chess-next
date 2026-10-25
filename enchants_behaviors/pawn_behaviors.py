from constants.piece_color import COLOR
from constants.pos import xy_to_id


def two_field_forward_move(possible_positions_to_move, xy_coord, color, pieces_locations):
    x, y = xy_coord
    color_var = 1
    if color == COLOR.BLACK:
        color_var = -1
    if (color == COLOR.WHITE and y + 2 < 8) or (color == COLOR.BLACK and y - 2 >= 0):
        if not pieces_locations[xy_to_id(x, y + (2 * color_var))].exists():
            if not pieces_locations[xy_to_id(x, y + (1 * color_var))].exists():
                possible_positions_to_move.append([x, y + (2 * color_var)])


def one_field_backwards_move(possible_positions_to_move, xy_coord, color, pieces_locations):
    x, y = xy_coord
    target_y = y - 1 if color == COLOR.WHITE else y + 1
    if not 0 <= target_y < 8:
        return

    if not pieces_locations[xy_to_id(x, target_y)].exists():
        possible_positions_to_move.append([x, target_y])

    for target_x in (x - 1, x + 1):
        if not 0 <= target_x < 8:
            continue
        target_piece = pieces_locations[xy_to_id(target_x, target_y)]
        if target_piece.exists() and target_piece.get_color() != color:
            possible_positions_to_move.append([target_x, target_y])


def move_one_field_horizontally(possible_positions_to_move, xy_coord, color, pieces_locations):
    x, y = xy_coord
    for target_x in (x - 1, x + 1):
        if 0 <= target_x < 8 and not pieces_locations[xy_to_id(target_x, y)].exists():
            possible_positions_to_move.append([target_x, y])
