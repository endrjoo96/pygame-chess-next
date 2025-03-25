from enum import Enum
from typing import List

from constants.pos import POS
from models.enchantments import Enchantment


class COLOR(Enum):
    BLACK = "black"
    WHITE = "white"
    EMPTY = ""


class PIECE_TYPE(Enum):
    PAWN = "pawn"
    KNIGHT = "knight"
    BISHOP = "bishop"
    ROOK = "rook"
    KING = "king"
    QUEEN = "queen"
    EMPTY = ""


class Piece:
    __color: COLOR
    __type: PIECE_TYPE
    __enchantments: List[Enchantment] = []

    def __init__(self, color: COLOR = COLOR.EMPTY, piece_type: PIECE_TYPE = PIECE_TYPE.EMPTY):
        self.__color, self.__type = color, piece_type

    def full_name(self):
        if not self.exists():
            return ""
        return str(self.__color.value + "_" + self.__type.value)

    def get_type(self):
        return self.__type

    def get_color(self):
        return self.__color

    def exists(self):
        return self.__type != PIECE_TYPE.EMPTY or self.__color != COLOR.EMPTY

    def set_enchantment(self, enchantment: Enchantment):
        self.__enchantments.append(enchantment)




pieces_starting_positions_map = {
    Piece(COLOR.WHITE, PIECE_TYPE.PAWN): [POS.A2, POS.B2, POS.C2, POS.D2, POS.E2, POS.F2, POS.G2, POS.H2],
    Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT): [POS.B1, POS.G1],
    Piece(COLOR.WHITE, PIECE_TYPE.BISHOP): [POS.C1, POS.F1],
    Piece(COLOR.WHITE, PIECE_TYPE.ROOK): [POS.A1, POS.H1],
    Piece(COLOR.WHITE, PIECE_TYPE.KING): [POS.E1],
    Piece(COLOR.WHITE, PIECE_TYPE.QUEEN): [POS.D1],
    Piece(COLOR.BLACK, PIECE_TYPE.PAWN): [POS.A7, POS.B7, POS.C7, POS.D7, POS.E7, POS.F7, POS.G7, POS.H7],
    Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT): [POS.B8, POS.G8],
    Piece(COLOR.BLACK, PIECE_TYPE.BISHOP): [POS.C8, POS.F8],
    Piece(COLOR.BLACK, PIECE_TYPE.ROOK): [POS.A8, POS.H8],
    Piece(COLOR.BLACK, PIECE_TYPE.KING): [POS.E8],
    Piece(COLOR.BLACK, PIECE_TYPE.QUEEN): [POS.D8],
}
