from constants.pos import POS


class PIECE_COLOR:
    BLACK = "black"
    WHITE = "white"
    EMPTY = ""


class PIECE_TYPE:
    PAWN = "pawn"
    KNIGHT = "knight"
    BISHOP = "bishop"
    ROOK = "rook"
    KING = "king"
    QUEEN = "queen"
    EMPTY = ""


class PIECE(PIECE_COLOR, PIECE_TYPE):
    __color, __piece = "", ""

    def __init__(self, color, piece):
        self.__color, self.__piece = color, piece

    def __init__(self):
        pass

    def full_name(self):
        if not self.__color and not self.__piece:
            return ""
        return str(self.__color + "_" + self.__piece)

    def is_empty(self):
        return not self.full_name()


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
