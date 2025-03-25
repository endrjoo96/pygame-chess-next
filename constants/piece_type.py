from enum import Enum


class PIECE_TYPE(Enum):
    PAWN = "pawn"
    KNIGHT = "knight"
    BISHOP = "bishop"
    ROOK = "rook"
    KING = "king"
    QUEEN = "queen"
    EMPTY = ""