from typing import List

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import POS
from models.enchantments import Enchantment


class Piece:
    def __init__(self, color: COLOR = COLOR.EMPTY, piece_type: PIECE_TYPE = PIECE_TYPE.EMPTY):
        self.__color: COLOR = color
        self.__type: PIECE_TYPE = piece_type
        self.__enchantments: List[Enchantment] = []

    def full_name(self) -> str:
        if not self.exists():
            return ""
        return self.__color.value + "_" + self.__type.value

    def get_type(self) -> PIECE_TYPE:
        return self.__type

    def get_color(self) -> COLOR:
        return self.__color

    def exists(self) -> bool:
        return self.__type != PIECE_TYPE.EMPTY or self.__color != COLOR.EMPTY

    def set_enchantment(self, enchantment: Enchantment):
        if enchantment.is_mandatory():
            self.__enchantments.insert(0, enchantment)
        else:
            self.__enchantments.append(enchantment)

    def get_enchantments_to_alter_behavior(self):
        list_of_behaviors = []
        for enchant in self.__enchantments:
            list_of_behaviors.append(enchant.get_behavior_to_inject())
            if enchant.is_mandatory(): break
        return list_of_behaviors


pieces_starting_positions_map = {
    POS.A1: Piece(COLOR.WHITE, PIECE_TYPE.ROOK),
    POS.B1: Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT),
    POS.C1: Piece(COLOR.WHITE, PIECE_TYPE.BISHOP),
    POS.D1: Piece(COLOR.WHITE, PIECE_TYPE.QUEEN),
    POS.E1: Piece(COLOR.WHITE, PIECE_TYPE.KING),
    POS.F1: Piece(COLOR.WHITE, PIECE_TYPE.BISHOP),
    POS.G1: Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT),
    POS.H1: Piece(COLOR.WHITE, PIECE_TYPE.ROOK),
    POS.A2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),
    POS.B2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),
    POS.C2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),
    POS.D2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),
    POS.E2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),
    POS.F2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),
    POS.G2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),
    POS.H2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN),

    POS.A8: Piece(COLOR.BLACK, PIECE_TYPE.ROOK),
    POS.B8: Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT),
    POS.C8: Piece(COLOR.BLACK, PIECE_TYPE.BISHOP),
    POS.D8: Piece(COLOR.BLACK, PIECE_TYPE.QUEEN),
    POS.E8: Piece(COLOR.BLACK, PIECE_TYPE.KING),
    POS.F8: Piece(COLOR.BLACK, PIECE_TYPE.BISHOP),
    POS.G8: Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT),
    POS.H8: Piece(COLOR.BLACK, PIECE_TYPE.ROOK),
    POS.A7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
    POS.B7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
    POS.C7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
    POS.D7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
    POS.E7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
    POS.F7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
    POS.G7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
    POS.H7: Piece(COLOR.BLACK, PIECE_TYPE.PAWN),

}
