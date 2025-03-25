from models.chess_pieces import PIECE_TYPE, COLOR, Piece
from constants.pos import xy_to_id


def process_possible_basic_moves(piece: Piece, xy_coord, pieces_locations):
    # list to store possible moves of the selected piece
    possible_positions_to_move = []
    # find the possible locations to put a piece
    # get x, y coordinate
    x_coord, y_coord = xy_coord

    match piece.get_type():
        case PIECE_TYPE.BISHOP:
            __add_diagonal_moves(possible_positions_to_move, xy_coord, pieces_locations)
        case PIECE_TYPE.PAWN:
            # convert list index to dictionary key
            # calculate moves for white pawn
            color_var = 1
            if piece.get_color() == COLOR.BLACK:
                color_var = -1
            if y_coord + (1 * color_var) < 8:
                # get row in front of black pawn
                front_piece: Piece = pieces_locations[xy_to_id(x_coord, y_coord + (1 * color_var))]
                # pawns cannot move when blocked by another piece
                if not front_piece.exists():
                    possible_positions_to_move.append([x_coord, y_coord + (1 * color_var)])
                    # black pawns can move two positions ahead for first move
                    if (piece.get_color() == COLOR.BLACK and y_coord == 6) or (
                            piece.get_color() == COLOR.WHITE and y_coord == 1):
                        y = y_coord + (2 * color_var)
                        front_piece: Piece = pieces_locations[xy_to_id(x_coord, y)]
                        if not front_piece.exists():
                            possible_positions_to_move.append([x_coord, y_coord + (2 * color_var)])
                __add_diag_hit_moves(possible_positions_to_move, piece.get_color(), xy_coord, pieces_locations)

        # calculate moves for rook
        case PIECE_TYPE.ROOK:
            # find linear moves
            __add_linear_moves(possible_positions_to_move, xy_coord, pieces_locations)

        # calculate moves for knight
        case PIECE_TYPE.KNIGHT:
            # left positions
            if (x_coord - 2) >= 0:
                if (y_coord - 1) >= 0:
                    possible_positions_to_move.append([x_coord - 2, y_coord - 1])
                if (y_coord + 1) < 8:
                    possible_positions_to_move.append([x_coord - 2, y_coord + 1])
            # top positions
            if (y_coord - 2) >= 0:
                if (x_coord - 1) >= 0:
                    possible_positions_to_move.append([x_coord - 1, y_coord - 2])
                if (x_coord + 1) < 8:
                    possible_positions_to_move.append([x_coord + 1, y_coord - 2])
            # right positions
            if (x_coord + 2) < 8:
                if (y_coord - 1) >= 0:
                    possible_positions_to_move.append([x_coord + 2, y_coord - 1])
                if (y_coord + 1) < 8:
                    possible_positions_to_move.append([x_coord + 2, y_coord + 1])
            # bottom positions
            if (y_coord + 2) < 8:
                if (x_coord - 1) >= 0:
                    possible_positions_to_move.append([x_coord - 1, y_coord + 2])
                if (x_coord + 1) < 8:
                    possible_positions_to_move.append([x_coord + 1, y_coord + 2])

        # calculate moves for king
        case PIECE_TYPE.KING:
            if (y_coord - 1) >= 0:
                # top spot
                possible_positions_to_move.append([x_coord, y_coord - 1])

            if (y_coord + 1) < 8:
                # bottom spot
                possible_positions_to_move.append([x_coord, y_coord + 1])

            if (x_coord - 1) >= 0:
                # left spot
                possible_positions_to_move.append([x_coord - 1, y_coord])
                # top left spot
                if (y_coord - 1) >= 0:
                    possible_positions_to_move.append([x_coord - 1, y_coord - 1])
                # bottom left spot
                if (y_coord + 1) < 8:
                    possible_positions_to_move.append([x_coord - 1, y_coord + 1])

            if (x_coord + 1) < 8:
                # right spot
                possible_positions_to_move.append([x_coord + 1, y_coord])
                # top right spot
                if (y_coord - 1) >= 0:
                    possible_positions_to_move.append([x_coord + 1, y_coord - 1])
                # bottom right spot
                if (y_coord + 1) < 8:
                    possible_positions_to_move.append([x_coord + 1, y_coord + 1])

        # calculate movs for queen
        case PIECE_TYPE.QUEEN:
            # find diagonal positions
            __add_diagonal_moves(possible_positions_to_move, xy_coord, pieces_locations)
            # find linear moves
            __add_linear_moves(possible_positions_to_move, xy_coord, pieces_locations)

    additional_behaviors = piece.get_enchantments_to_alter_behavior()
    for behavior in additional_behaviors:
        behavior(possible_positions_to_move, xy_coord, piece.get_color(), pieces_locations)

    # list of positions to be removed
    to_remove = []

    # remove positions that overlap other pieces of the current player
    for xy in possible_positions_to_move:
        pos = xy_to_id(xy[0], xy[1])

        # find the pieces to remove
        des_piece: Piece = pieces_locations[pos]
        if piece.get_color() == des_piece.get_color():
            to_remove.append(xy)

    # remove position from positions list
    for xy in to_remove:
        possible_positions_to_move.remove(xy)

    # return list containing possible moves for the selected piece
    return possible_positions_to_move


# helper function to find diagonal moves
def __add_diagonal_moves(positions, xy_coord, pieces_locations):
    # reset x and y coordinate values
    x, y = xy_coord
    # find top left diagonal spots
    while True:
        x = x - 1
        y = y - 1
        if x < 0 or y < 0:
            break
        else:
            positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break

    # reset x and y coordinate values
    x, y = xy_coord
    # find bottom right diagonal spots
    while True:
        x = x + 1
        y = y + 1
        if x > 7 or y > 7:
            break
        else:
            positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break

    # reset x and y coordinate values
    x, y = xy_coord
    # find bottom left diagonal spots
    while True:
        x = x - 1
        y = y + 1
        if x < 0 or y > 7:
            break
        else:
            positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break

    # reset x and y coordinate values
    x, y = xy_coord
    # find top right diagonal spots
    while True:
        x = x + 1
        y = y - 1
        if x > 7 or y < 0:
            break
        else:
            positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break


# helper function to find horizontal and vertical moves
def __add_linear_moves(positions, xy_coord, pieces_locations):
    # reset x, y coordniate value
    x, y = xy_coord
    # horizontal moves to the left
    while x > 0:
        x = x - 1
        positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break

    # reset x, y coordniate value
    x, y = xy_coord
    # horizontal moves to the right
    while x < 7:
        x = x + 1
        positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break
    # reset x, y coordniate value
    x, y = xy_coord
    # vertical moves upwards
    while y > 0:
        y = y - 1
        positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break

    # reset x, y coordniate value
    x, y = xy_coord
    # vertical moves downwards
    while y < 7:
        y = y + 1
        positions.append([x, y])
        p: Piece = pieces_locations[xy_to_id(x, y)]
        if p.exists():
            break


def __add_diag_hit_moves(possible_positions_to_move, color, xy_coord, pieces_locations):
    x_coord, y_coord = xy_coord
    color_var = 1
    if color == COLOR.BLACK: color_var = -1

    # diagonal to the left
    if x_coord - 1 >= 0 and y_coord + color_var < 8:
        x = x_coord - 1
        y = y_coord + color_var

        # convert list index to dictionary key
        to_capture: Piece = pieces_locations[xy_to_id(x, y)]

        if to_capture.exists() and to_capture.get_color() != color:
            possible_positions_to_move.append([x, y])

    # diagonal to the right
    if x_coord + 1 < 8 and y_coord + color_var < 8:
        x = x_coord + 1
        y = y_coord + color_var

        # convert list index to dictionary key
        to_capture: Piece = pieces_locations[xy_to_id(x, y)]

        if to_capture.exists() and to_capture.get_color() != color:
            possible_positions_to_move.append([x, y])