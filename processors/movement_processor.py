from typing import Optional

from models.chess_pieces import Piece
from models.enchantments import Enchantment
from processors.bitboard_move_generator import (
    BoardBitboards,
    generate_possible_moves,
)


def process_possible_basic_moves(
    piece: Piece,
    xy_coord,
    pieces_locations,
    active_enchantment: Optional[Enchantment] = None,
    occupancy: Optional[BoardBitboards] = None,
):
    """Wyznacza ruchy figury bitboardami, uwzględniając efekty i karty."""
    return generate_possible_moves(
        piece,
        xy_coord,
        pieces_locations,
        active_enchantment,
        occupancy,
    )
