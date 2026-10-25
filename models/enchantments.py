import random
from enum import Enum
from typing import List

from constants.enchantment_type import EnchantmentType
from constants.piece_type import PIECE_TYPE
from enchants_behaviors import knight_behaviors, pawn_behaviors, queen_behaviors, rook_behaviors


class Enchantment:
    def __init__(
        self, enchantment_types: List[EnchantmentType], description: str, piece_type_restriction: PIECE_TYPE,
        behavior_to_inject, card_type=None,
    ):
        self.__enchantment_types = enchantment_types
        self.__description = description
        self.__piece_type_restriction = piece_type_restriction
        self.__behavior_to_inject = behavior_to_inject
        self.__card_type = card_type
        self.__remaining_uses = 3 if EnchantmentType.REUSABLE in enchantment_types else 1

    def get_behavior_to_inject(self):
        return self.__behavior_to_inject

    def is_reusable(self) -> bool:
        return EnchantmentType.REUSABLE in self.__enchantment_types

    def get_remaining_uses(self) -> int:
        return self.__remaining_uses

    def consume_use(self) -> int:
        self.__remaining_uses -= 1
        return self.__remaining_uses

    def add_uses(self, count: int):
        self.__remaining_uses += count

    def get_card_type(self):
        return self.__card_type

    def get_enchantment_types(self) -> List[EnchantmentType]:
        return self.__enchantment_types.copy()

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


class EnchantmentCardType(Enum):
    PAWN_TWO_FIELDS_FORWARD = (
        [EnchantmentType.REUSABLE], "Wykonaj ruch o 2 pola do przodu", PIECE_TYPE.PAWN,
        pawn_behaviors.two_field_forward_move)
    PAWN_ONE_FIELD_BACKWARD = (
        [EnchantmentType.REUSABLE], "Wykonaj ruch do tyłu", PIECE_TYPE.PAWN,
        pawn_behaviors.one_field_backwards_move)
    KNIGHT_ONE_FIELD_ANY_DIRECTION = (
        [EnchantmentType.REUSABLE], "Skoczek porusza się o 1 pole w dowolnym kierunku",
        PIECE_TYPE.KNIGHT, knight_behaviors.one_field_in_any_direction)
    ROOK_JUMP_ALLIES = (
        [], "Wieża przeskakuje nad sojuszniczymi figurami, ale nie może zbijać",
        PIECE_TYPE.ROOK, rook_behaviors.move_through_allied_pieces_without_capturing)
    QUEEN_JUMP_ALLIES = (
        [EnchantmentType.MANDATORY],
        "Hetman przeskakuje nad sojusznikami do 4 pól, ale nie może zbijać",
        PIECE_TYPE.QUEEN, queen_behaviors.move_up_to_four_fields_through_allies_without_capturing)

    def __init__(self, enchantment_types, description, piece_type, behavior_to_inject):
        self.enchantment_types = enchantment_types
        self.description = description
        self.piece_type = piece_type
        self.behavior_to_inject = behavior_to_inject

    def create(self) -> Enchantment:
        return Enchantment(
            self.enchantment_types.copy(), self.description, self.piece_type, self.behavior_to_inject, self)

    @classmethod
    def random_choice(cls) -> "EnchantmentCardType":
        return random.choice(list(cls))

    @classmethod
    def create_random(cls) -> Enchantment:
        return cls.random_choice().create()


rook_jump_card = EnchantmentCardType.ROOK_JUMP_ALLIES.create()
available_cards = [
    card_type.create() if card_type != EnchantmentCardType.ROOK_JUMP_ALLIES else rook_jump_card
    for card_type in EnchantmentCardType
]
