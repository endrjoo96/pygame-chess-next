import random
from enum import Enum
from typing import List, Optional

from constants.enchantment_type import EnchantmentType
from constants.piece_type import PIECE_TYPE
from enchants_behaviors import any_piece_behaviors, knight_behaviors, pawn_behaviors, queen_behaviors, rook_behaviors


def _resolve_remaining_uses(enchantment_types, remaining_uses):
    is_reusable = EnchantmentType.REUSABLE in enchantment_types
    if is_reusable and remaining_uses is None:
        raise ValueError("Reusable enchantments must define their number of uses")
    if not is_reusable and remaining_uses not in (None, 1):
        raise ValueError("Non-reusable enchantments must have exactly one use")
    if remaining_uses is not None and remaining_uses < 1:
        raise ValueError("An enchantment must have at least one use")
    return remaining_uses if is_reusable else 1


class Enchantment:
    def __init__(
        self, enchantment_types: List[EnchantmentType], title: str, description: str,
        piece_type_restriction: PIECE_TYPE, behavior_to_inject, card_type=None,
        remaining_uses: Optional[int] = None,
    ):
        self.__remaining_uses = _resolve_remaining_uses(enchantment_types, remaining_uses)
        self.__enchantment_types = enchantment_types
        self.__title = title
        self.__description = description
        self.__piece_type_restriction = piece_type_restriction
        self.__behavior_to_inject = behavior_to_inject
        self.__card_type = card_type

    def get_behavior_to_inject(self):
        return self.__behavior_to_inject

    def is_reusable(self) -> bool:
        return EnchantmentType.REUSABLE in self.__enchantment_types

    def is_passive(self) -> bool:
        return EnchantmentType.PASSIVE in self.__enchantment_types

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

    def get_title(self) -> str:
        return self.__title

    def get_rate_delay_before_use(self) -> int:
        return self.__enchantment_types.count(EnchantmentType.DELAY_BEFORE_USE)

    def get_rate_stun_after_use(self) -> int:
        return self.__enchantment_types.count(EnchantmentType.STUN_AFTER_USE)

    def get_required_piece_type(self) -> PIECE_TYPE:
        return self.__piece_type_restriction


class EnchantmentCardType(Enum):
    PAWN_TWO_FIELDS_FORWARD = (
        [EnchantmentType.REUSABLE], "TITLE", "Wykonaj ruch o 2 pola do przodu", PIECE_TYPE.PAWN,
        pawn_behaviors.two_field_forward_move, 3)
    PAWN_ONE_FIELD_BACKWARD = (
        [EnchantmentType.REUSABLE], "TITLE", "Wykonaj ruch do tyłu", PIECE_TYPE.PAWN,
        pawn_behaviors.one_field_backwards_move, 3)
    KNIGHT_ONE_FIELD_ANY_DIRECTION = (
        [EnchantmentType.REUSABLE], "TITLE", "Skoczek porusza się o 1 pole w dowolnym kierunku",
        PIECE_TYPE.KNIGHT, knight_behaviors.one_field_in_any_direction, 3)
    ROOK_JUMP_ALLIES = (
        [], "TITLE", "Wieża przeskakuje nad sojuszniczymi figurami, ale nie może zbijać",
        PIECE_TYPE.ROOK, rook_behaviors.move_through_allied_pieces_without_capturing)
    QUEEN_JUMP_ALLIES = (
        [EnchantmentType.MANDATORY],
        "TITLE", "Hetman przeskakuje nad sojusznikami do 4 pól, ale nie może zbijać",
        PIECE_TYPE.QUEEN, queen_behaviors.move_up_to_four_fields_through_allies_without_capturing)
    PAWN_DETONATION = (
        [EnchantmentType.PASSIVE], "TITLE",
        "Detonuje pion, niszcząc wszystkie figury w promieniu 1 pola, włącznie z sojuszniczymi.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves)
    PAWN_DETONATION_DELAYED = (
        [EnchantmentType.PASSIVE, EnchantmentType.DELAY_BEFORE_USE], "TITLE",
        "Po 1 turze detonuje pion, niszcząc wszystkie figury w promieniu 1 pola, włącznie z sojuszniczymi.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves)

    def __init__(self, enchantment_types, title, description, piece_type, behavior_to_inject, remaining_uses=None):
        self.enchantment_types = enchantment_types
        self.title = title
        self.description = description
        self.piece_type = piece_type
        self.behavior_to_inject = behavior_to_inject
        self.remaining_uses = _resolve_remaining_uses(enchantment_types, remaining_uses)

    def create(self) -> Enchantment:
        return Enchantment(
            self.enchantment_types.copy(), self.title, self.description, self.piece_type,
            self.behavior_to_inject, self,
            self.remaining_uses)

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
