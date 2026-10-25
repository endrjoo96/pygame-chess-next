from symtable import Function
from typing import List

from constants.enchantment_type import EnchantmentType
from constants.piece_type import PIECE_TYPE
from enchants_behaviors import knight_behaviors, pawn_behaviors, queen_behaviors, rook_behaviors


class Enchantment:
    def __init__(self, enchantment_types: List[EnchantmentType], description: str, piece_type_restriction: PIECE_TYPE, behavior_to_inject):
        self.__enchantment_types = enchantment_types
        self.__description = description
        self.__piece_type_restriction = piece_type_restriction
        self.__behavior_to_inject = behavior_to_inject

    def get_behavior_to_inject(self):
        return self.__behavior_to_inject

    def is_reusable(self) -> bool:
        return EnchantmentType.REUSABLE in self.__enchantment_types

    def is_mandatory(self) -> bool:
        return self.__enchantment_types.__contains__(EnchantmentType.MANDATORY)

    def get_description(self) -> str:
        return self.__description

    def get_rate_stun_after_cast(self) -> int:
        return self.__enchantment_types.count(EnchantmentType.STUN_AFTER_CAST)

    def get_rate_stun_after_use(self) -> int:
        return self.__enchantment_types.count(EnchantmentType.STUN_AFTER_USE)

    def get_required_piece_type(self) -> PIECE_TYPE:
        return self.__piece_type_restriction


rook_jump_card = Enchantment(
    [], "Wieża przeskakuje nad sojuszniczymi figurami, ale nie może zbijać",
    PIECE_TYPE.ROOK, rook_behaviors.move_through_allied_pieces_without_capturing)

available_cards = [
    Enchantment([EnchantmentType.REUSABLE], "Wykonaj ruch o 2 pola do przodu", PIECE_TYPE.PAWN,
                pawn_behaviors.two_field_forward_move),
    Enchantment([EnchantmentType.REUSABLE], "Wykonaj ruch do tyłu", PIECE_TYPE.PAWN,
                pawn_behaviors.one_field_backwards_move),
    Enchantment([EnchantmentType.REUSABLE], "Skoczek porusza się o 1 pole w dowolnym kierunku",
                PIECE_TYPE.KNIGHT, knight_behaviors.one_field_in_any_direction),
    rook_jump_card,
    Enchantment([EnchantmentType.MANDATORY],
                "Hetman przeskakuje nad sojusznikami do 4 pól, ale nie może zbijać",
                PIECE_TYPE.QUEEN,
                queen_behaviors.move_up_to_four_fields_through_allies_without_capturing),
]
