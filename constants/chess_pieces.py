from enum import Enum

from constants.pos import POS


class PIECE_COLOR(Enum):
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


class PIECE:
    __color: PIECE_COLOR
    __type: PIECE_TYPE

    def __init__(self, color: PIECE_COLOR = PIECE_COLOR.EMPTY, piece_type: PIECE_TYPE = PIECE_TYPE.EMPTY):
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
        return self.__type != PIECE_TYPE.EMPTY or self.__color != PIECE_COLOR.EMPTY


pieces_starting_positions_map = {
    PIECE(PIECE_COLOR.WHITE, PIECE_TYPE.PAWN): [POS.A2, POS.B2, POS.C2, POS.D2, POS.E2, POS.F2, POS.G2, POS.H2],
    PIECE(PIECE_COLOR.WHITE, PIECE_TYPE.KNIGHT): [POS.B1, POS.G1],
    PIECE(PIECE_COLOR.WHITE, PIECE_TYPE.BISHOP): [POS.C1, POS.F1],
    PIECE(PIECE_COLOR.WHITE, PIECE_TYPE.ROOK): [POS.A1, POS.H1],
    PIECE(PIECE_COLOR.WHITE, PIECE_TYPE.KING): [POS.E1],
    PIECE(PIECE_COLOR.WHITE, PIECE_TYPE.QUEEN): [POS.D1],
    PIECE(PIECE_COLOR.BLACK, PIECE_TYPE.PAWN): [POS.A7, POS.B7, POS.C7, POS.D7, POS.E7, POS.F7, POS.G7, POS.H7],
    PIECE(PIECE_COLOR.BLACK, PIECE_TYPE.KNIGHT): [POS.B8, POS.G8],
    PIECE(PIECE_COLOR.BLACK, PIECE_TYPE.BISHOP): [POS.C8, POS.F8],
    PIECE(PIECE_COLOR.BLACK, PIECE_TYPE.ROOK): [POS.A8, POS.H8],
    PIECE(PIECE_COLOR.BLACK, PIECE_TYPE.KING): [POS.E8],
    PIECE(PIECE_COLOR.BLACK, PIECE_TYPE.QUEEN): [POS.D8],
}
