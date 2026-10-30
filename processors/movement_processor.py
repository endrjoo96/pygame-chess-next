from models.chess_pieces import PIECE_TYPE, COLOR, Piece
from models.enchantment_cards import EnchantmentCardType
from constants.pos import xy_to_id


def process_possible_basic_moves(piece: Piece, xy_coord, pieces_locations, active_enchantment=None):
    """Wyznacza legalne ruchy figury, uwzględniając planszę i aktywne modyfikatory."""
    possible_positions_to_move = []
    if active_enchantment is not None:
        active_enchantment.get_behavior_to_inject()(
            possible_positions_to_move, xy_coord, piece.get_color(), pieces_locations)
        if active_enchantment.get_card_type() == EnchantmentCardType.ROOK_TOWER_THROW:
            return possible_positions_to_move
        return __exclude_allied_occupied_positions(
            possible_positions_to_move, piece.get_color(), pieces_locations)

    match piece.get_type():
        case PIECE_TYPE.BISHOP:
            __add_diagonal_moves(possible_positions_to_move, xy_coord, pieces_locations)
        case PIECE_TYPE.PAWN:
            __add_pawn_moves(possible_positions_to_move, piece, xy_coord, pieces_locations)
        case PIECE_TYPE.ROOK:
            __add_linear_moves(possible_positions_to_move, xy_coord, pieces_locations)
        case PIECE_TYPE.KNIGHT:
            __add_knight_moves(possible_positions_to_move, xy_coord)
        case PIECE_TYPE.KING:
            __add_king_moves(possible_positions_to_move, xy_coord)
        case PIECE_TYPE.QUEEN:
            __add_diagonal_moves(possible_positions_to_move, xy_coord, pieces_locations)
            __add_linear_moves(possible_positions_to_move, xy_coord, pieces_locations)

    for behavior in piece.get_enchantments_to_alter_behavior():
        behavior(possible_positions_to_move, xy_coord, piece.get_color(), pieces_locations)

    return __exclude_allied_occupied_positions(
        possible_positions_to_move, piece.get_color(), pieces_locations)


def __add_diagonal_moves(positions, xy_coord, pieces_locations):
    """Dodaje ruchy promieniowe gońca i odpowiadające im przekątne hetmana."""
    __add_ray_moves(positions, xy_coord, pieces_locations, (
        (-1, -1), (1, 1), (-1, 1), (1, -1),
    ))


def __add_linear_moves(positions, xy_coord, pieces_locations):
    """Dodaje ruchy wieży i liniowe kierunki hetmana, zatrzymując się na zbitku."""
    __add_ray_moves(positions, xy_coord, pieces_locations, (
        (-1, 0), (1, 0), (0, -1), (0, 1),
    ))


def __add_ray_moves(positions, xy_coord, pieces_locations, directions):
    """Przechodzi po podanych kierunkach, uwzględniając pierwsze napotkane pole."""
    start_x, start_y = xy_coord
    for direction_x, direction_y in directions:
        x, y = start_x + direction_x, start_y + direction_y
        while 0 <= x < 8 and 0 <= y < 8:
            positions.append([x, y])
            if pieces_locations[xy_to_id(x, y)].exists():
                break
            x += direction_x
            y += direction_y


def __add_pawn_moves(positions, piece, xy_coord, pieces_locations):
    """Dodaje ruchy naprzód i dostępne zbicia ukośne piona."""
    x, y = xy_coord
    direction = 1 if piece.get_color() == COLOR.WHITE else -1
    next_y = y + direction
    if not 0 <= next_y < 8:
        return

    if not pieces_locations[xy_to_id(x, next_y)].exists():
        positions.append([x, next_y])
        starting_row = 1 if piece.get_color() == COLOR.WHITE else 6
        double_y = y + 2 * direction
        if y == starting_row and not pieces_locations[xy_to_id(x, double_y)].exists():
            positions.append([x, double_y])
    __add_diag_hit_moves(positions, piece.get_color(), xy_coord, pieces_locations)


def __add_knight_moves(positions, xy_coord):
    """Dopisuje skoczkowe przesunięcia w ustalonej kolejności, pomijając brzeg planszy."""
    x, y = xy_coord
    for offset_x, offset_y in (
        (-2, -1), (-2, 1), (-1, -2), (1, -2),
        (2, -1), (2, 1), (-1, 2), (1, 2),
    ):
        target_x, target_y = x + offset_x, y + offset_y
        if 0 <= target_x < 8 and 0 <= target_y < 8:
            positions.append([target_x, target_y])


def __add_king_moves(positions, xy_coord):
    """Dopisuje sąsiednie pola króla w kolejności zgodnej z poprzednią implementacją."""
    x, y = xy_coord
    for offset_x, offset_y in (
        (0, -1), (0, 1), (-1, 0), (-1, -1),
        (-1, 1), (1, 0), (1, -1), (1, 1),
    ):
        target_x, target_y = x + offset_x, y + offset_y
        if 0 <= target_x < 8 and 0 <= target_y < 8:
            positions.append([target_x, target_y])


def __add_diag_hit_moves(possible_positions_to_move, color, xy_coord, pieces_locations):
    """Dodaje pionowi ukośne pola zbicia, jeśli zajmuje je figura przeciwnika."""
    x_coord, y_coord = xy_coord
    direction = 1 if color == COLOR.WHITE else -1
    for target_x in (x_coord - 1, x_coord + 1):
        target_y = y_coord + direction
        if not (0 <= target_x < 8 and 0 <= target_y < 8):
            continue
        target_piece = pieces_locations[xy_to_id(target_x, target_y)]
        if target_piece.exists() and target_piece.get_color() != color:
            possible_positions_to_move.append([target_x, target_y])


def __exclude_allied_occupied_positions(positions, color, pieces_locations):
    """Usuwa ruchy kończące się na figurze sojuszniczej, zachowując kolejność pól."""
    return [
        position for position in positions
        if pieces_locations[xy_to_id(position[0], position[1])].get_color() != color
    ]