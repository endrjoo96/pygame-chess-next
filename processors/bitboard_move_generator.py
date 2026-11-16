from dataclasses import dataclass

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import xy_to_id
from enchants_behaviors import any_piece_behaviors
from models.enchantment_cards import EnchantmentCardType
from models.enchantments import Enchantment


BOARD_MASK = (1 << 64) - 1
_SQUARE_BITS = tuple(1 << square for square in range(64))
_SQUARE_COORDINATES = tuple(
    (square % 8, square // 8) for square in range(64)
)
_ROOK_DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))
_BISHOP_DIRECTIONS = ((-1, -1), (1, 1), (-1, 1), (1, -1))
_ROOK_CARD_DIRECTIONS = ((0, -1), (0, 1), (-1, 0), (1, 0))
_QUEEN_CARD_DIRECTIONS = _ROOK_CARD_DIRECTIONS + (
    (-1, -1), (-1, 1), (1, -1), (1, 1),
)
_KING_OFFSETS = (
    (0, -1), (0, 1), (-1, 0), (-1, -1),
    (-1, 1), (1, 0), (1, -1), (1, 1),
)
_KNIGHT_OFFSETS = (
    (-2, -1), (-2, 1), (-1, -2), (1, -2),
    (2, -1), (2, 1), (-1, 2), (1, 2),
)


def _precompute_offsets(offsets):
    result = []
    for square in range(64):
        x, y = square % 8, square // 8
        targets = []
        for offset_x, offset_y in offsets:
            target_x, target_y = x + offset_x, y + offset_y
            if 0 <= target_x < 8 and 0 <= target_y < 8:
                targets.append(target_y * 8 + target_x)
        result.append(tuple(targets))
    return tuple(result)


def _precompute_rays(directions):
    result = []
    for square in range(64):
        x, y = square % 8, square // 8
        square_rays = []
        for direction_x, direction_y in directions:
            ray = []
            target_x, target_y = x + direction_x, y + direction_y
            while 0 <= target_x < 8 and 0 <= target_y < 8:
                ray.append(target_y * 8 + target_x)
                target_x += direction_x
                target_y += direction_y
            square_rays.append(tuple(ray))
        result.append(tuple(square_rays))
    return tuple(result)


_KING_TARGETS = _precompute_offsets(_KING_OFFSETS)
_KNIGHT_TARGETS = _precompute_offsets(_KNIGHT_OFFSETS)
_ROOK_RAYS = _precompute_rays(_ROOK_DIRECTIONS)
_BISHOP_RAYS = _precompute_rays(_BISHOP_DIRECTIONS)
_QUEEN_RAYS = tuple(
    bishop_rays + rook_rays
    for bishop_rays, rook_rays in zip(_BISHOP_RAYS, _ROOK_RAYS)
)
_CARD_ROOK_RAYS = _precompute_rays(_ROOK_CARD_DIRECTIONS)
_CARD_QUEEN_RAYS = _precompute_rays(_QUEEN_CARD_DIRECTIONS)
_KING_MASKS = tuple(
    sum(_SQUARE_BITS[target] for target in targets)
    for targets in _KING_TARGETS
)
_KNIGHT_MASKS = tuple(
    sum(_SQUARE_BITS[target] for target in targets)
    for targets in _KNIGHT_TARGETS
)
_BITBOARD_MOVEMENT_TYPES = {
    EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD,
    EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD,
    EnchantmentCardType.PAWN_SWORDSMAN,
    EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION,
    EnchantmentCardType.ROOK_JUMP_ALLIES,
    EnchantmentCardType.QUEEN_JUMP_ALLIES,
    EnchantmentCardType.ROOK_TOWER_THROW,
}
_MOVEMENT_TYPES_BY_BEHAVIOR = {
    card_type.behavior_to_inject: card_type
    for card_type in _BITBOARD_MOVEMENT_TYPES
}


@dataclass(frozen=True)
class BoardBitboards:
    """Bitboard occupancy snapshot; bit zero represents A1 and bit 63 H8."""

    white: int
    black: int
    occupied: int

    @classmethod
    def from_locations(cls, pieces_locations):
        white = 0
        black = 0
        occupied = 0
        for position, piece in pieces_locations.items():
            if not piece.exists():
                continue
            bit = _SQUARE_BITS[position - 1]
            occupied |= bit
            if piece.get_color() == COLOR.WHITE:
                white |= bit
            elif piece.get_color() == COLOR.BLACK:
                black |= bit
        return cls(white, black, occupied)

    def color_mask(self, color):
        if color == COLOR.WHITE:
            return self.white
        if color == COLOR.BLACK:
            return self.black
        return 0


def _ray_moves(
    source,
    occupancy,
    color,
    rays,
    *,
    through_allies=False,
    max_distance=None,
):
    own = occupancy.color_mask(color)
    moves = []
    mask = 0
    for ray in rays[source]:
        for distance, target in enumerate(ray, start=1):
            if max_distance is not None and distance > max_distance:
                break
            bit = _SQUARE_BITS[target]
            is_occupied = bool(occupancy.occupied & bit)
            if through_allies and is_occupied:
                if own & bit:
                    continue
                break
            moves.append(target)
            mask |= bit
            if is_occupied:
                break
    return mask, moves


def _pawn_capture_moves(x, target_y, color, occupancy):
    opponent = occupancy.occupied & ~occupancy.color_mask(color) & BOARD_MASK
    mask = 0
    moves = []
    for target_x in (x - 1, x + 1):
        if not 0 <= target_x < 8:
            continue
        target = target_y * 8 + target_x
        bit = _SQUARE_BITS[target]
        if opponent & bit:
            moves.append(target)
            mask |= bit
    return mask, moves


def _base_moves(piece, source, occupancy):
    color = piece.get_color()
    own = occupancy.color_mask(color)
    source_index = source - 1
    piece_type = piece.get_type()

    if piece_type == PIECE_TYPE.KNIGHT:
        return _KNIGHT_MASKS[source_index], list(_KNIGHT_TARGETS[source_index])
    if piece_type == PIECE_TYPE.KING:
        return _KING_MASKS[source_index], list(_KING_TARGETS[source_index])
    if piece_type in (PIECE_TYPE.ROOK, PIECE_TYPE.BISHOP, PIECE_TYPE.QUEEN):
        if piece_type == PIECE_TYPE.ROOK:
            rays = _ROOK_RAYS[source_index]
        elif piece_type == PIECE_TYPE.BISHOP:
            rays = _BISHOP_RAYS[source_index]
        else:
            rays = _QUEEN_RAYS[source_index]
        mask = 0
        moves = []
        for ray in rays:
            for target in ray:
                bit = _SQUARE_BITS[target]
                moves.append(target)
                mask |= bit
                if occupancy.occupied & bit:
                    break
        return mask & ~own, moves
    if piece_type != PIECE_TYPE.PAWN:
        return 0, []

    x, y = source_index % 8, source_index // 8
    direction = 1 if color == COLOR.WHITE else -1
    next_y = y + direction
    mask = 0
    moves = []
    if 0 <= next_y < 8:
        forward = source_index + 8 * direction
        forward_bit = _SQUARE_BITS[forward]
        if not occupancy.occupied & forward_bit:
            moves.append(forward)
            mask |= forward_bit
            starting_row = 1 if color == COLOR.WHITE else 6
            double_y = y + 2 * direction
            if (
                y == starting_row
                and not piece.has_moved()
                and 0 <= double_y < 8
            ):
                double = source_index + 16 * direction
                double_bit = _SQUARE_BITS[double]
                if not occupancy.occupied & double_bit:
                    moves.append(double)
                    mask |= double_bit
        capture_mask, capture_moves = _pawn_capture_moves(
            x, next_y, color, occupancy)
        mask |= capture_mask
        moves.extend(capture_moves)
    return mask, moves


def _card_moves(card_type, piece, source, occupancy):
    color = piece.get_color()
    source_index = source - 1
    x, y = source_index % 8, source_index // 8

    if card_type == EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD:
        target_y = y + (2 if color == COLOR.WHITE else -2)
        if not 0 <= target_y < 8:
            return 0, []
        middle_y = y + (1 if color == COLOR.WHITE else -1)
        target = target_y * 8 + x
        middle = middle_y * 8 + x
        if occupancy.occupied & (_SQUARE_BITS[target] | _SQUARE_BITS[middle]):
            return 0, []
        return _SQUARE_BITS[target], [target]

    if card_type == EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD:
        target_y = y + (-1 if color == COLOR.WHITE else 1)
        if not 0 <= target_y < 8:
            return 0, []
        moves = []
        mask = 0
        center = target_y * 8 + x
        center_bit = _SQUARE_BITS[center]
        if not occupancy.occupied & center_bit:
            moves.append(center)
            mask |= center_bit
        capture_mask, capture_moves = _pawn_capture_moves(
            x, target_y, color, occupancy)
        mask |= capture_mask
        moves.extend(capture_moves)
        return mask, moves

    if card_type == EnchantmentCardType.PAWN_SWORDSMAN:
        moves = []
        mask = 0
        for target_x in (x - 1, x + 1):
            if not 0 <= target_x < 8:
                continue
            target = y * 8 + target_x
            bit = _SQUARE_BITS[target]
            if not occupancy.occupied & bit:
                moves.append(target)
                mask |= bit
        return mask, moves

    if card_type == EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION:
        return _KING_MASKS[source_index], list(_KING_TARGETS[source_index])

    if card_type == EnchantmentCardType.ROOK_JUMP_ALLIES:
        return _ray_moves(
            source_index, occupancy, color, _CARD_ROOK_RAYS,
            through_allies=True)

    if card_type == EnchantmentCardType.QUEEN_JUMP_ALLIES:
        return _ray_moves(
            source_index, occupancy, color, _CARD_QUEEN_RAYS,
            through_allies=True, max_distance=4)

    if card_type == EnchantmentCardType.ROOK_TOWER_THROW:
        moves = [
            ray[-1]
            for ray in _CARD_ROOK_RAYS[source_index]
            if ray
        ]
        return sum(_SQUARE_BITS[target] for target in moves), moves

    return None


def _effect_moves(enchantment, piece, source, pieces_locations, occupancy):
    if isinstance(enchantment, Enchantment):
        card_type = enchantment.get_card_type()
        behavior = enchantment.get_behavior_to_inject()
    else:
        behavior = enchantment
        card_type = _MOVEMENT_TYPES_BY_BEHAVIOR.get(behavior)
    if card_type is not None:
        moves = _card_moves(card_type, piece, source, occupancy)
        if moves is not None:
            return moves

    if behavior is any_piece_behaviors.no_additional_moves:
        return 0, []
    possible_positions = []
    behavior(
        possible_positions,
        [(source - 1) % 8, (source - 1) // 8],
        piece.get_color(),
        pieces_locations,
    )
    return None, [
        position[1] * 8 + position[0] for position in possible_positions
    ]


def _to_coordinates(mask, ordered_squares, color, occupancy):
    legal_mask = mask & ~occupancy.color_mask(color) & BOARD_MASK
    return [
        list(_SQUARE_COORDINATES[target])
        for target in ordered_squares
        if legal_mask & _SQUARE_BITS[target]
    ]


def generate_possible_moves(
    piece,
    xy_coord,
    pieces_locations,
    active_enchantment=None,
    occupancy=None,
):
    """Generate movement destinations with bitboards and legacy ordering."""
    if occupancy is None:
        occupancy = BoardBitboards.from_locations(pieces_locations)
    x, y = xy_coord
    source = xy_to_id(x, y)

    if active_enchantment is not None:
        mask, ordered_squares = _effect_moves(
            active_enchantment,
            piece,
            source,
            pieces_locations,
            occupancy,
        )
        if mask is None:
            own = occupancy.color_mask(piece.get_color())
            ordered_squares = [
                target for target in ordered_squares
                if not own & _SQUARE_BITS[target]
            ]
            return [
                list(_SQUARE_COORDINATES[target])
                for target in ordered_squares
            ]
        if (
            active_enchantment.get_card_type()
            == EnchantmentCardType.ROOK_TOWER_THROW
        ):
            return [[target % 8, target // 8] for target in ordered_squares]
        return _to_coordinates(
            mask, ordered_squares, piece.get_color(), occupancy)

    mask, ordered_squares = _base_moves(piece, source, occupancy)
    for enchantment in piece.get_enchantments_to_alter_behavior():
        effect_mask, effect_squares = _effect_moves(
            enchantment, piece, source, pieces_locations, occupancy)
        if effect_mask is None:
            ordered_squares.extend(effect_squares)
            for target in effect_squares:
                mask |= _SQUARE_BITS[target]
            continue
        ordered_squares.extend(effect_squares)
        mask |= effect_mask
    if mask == 0:
        return []
    return _to_coordinates(
        mask, ordered_squares, piece.get_color(), occupancy)
