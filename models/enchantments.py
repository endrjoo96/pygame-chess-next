from typing import List, Optional

from constants.enchantment_type import EnchantmentType
from constants.piece_type import PIECE_TYPE


def _resolve_remaining_uses(enchantment_types, remaining_uses):
    is_reusable = EnchantmentType.REUSABLE in enchantment_types
    if is_reusable and remaining_uses is None:
        raise ValueError("Reusable enchantments must define their number of uses")
    if not is_reusable and remaining_uses is not None and (
        not isinstance(remaining_uses, int) or isinstance(remaining_uses, bool) or remaining_uses != 1
    ):
        raise ValueError("Non-reusable enchantments must have exactly one use")
    if is_reusable and (
        not isinstance(remaining_uses, int) or isinstance(remaining_uses, bool) or remaining_uses < 1
    ):
        raise ValueError("An enchantment must have a positive integer number of uses")
    return remaining_uses if is_reusable else 1


def _resolve_delay_before_use(enchantment_types, delay_before_use):
    has_delay = EnchantmentType.DELAY_BEFORE_USE in enchantment_types
    if has_delay and delay_before_use is None:
        raise ValueError("Delayed enchantments must define their delay")
    if not has_delay and delay_before_use is not None:
        raise ValueError("Only delayed enchantments can define a delay")
    if delay_before_use is not None and (
        not isinstance(delay_before_use, int) or isinstance(delay_before_use, bool) or delay_before_use < 1
    ):
        raise ValueError("An enchantment delay must be a positive integer")
    return delay_before_use if has_delay else 0


class Enchantment:
    def __init__(
        self, enchantment_types: List[EnchantmentType], title: str, description: str,
        piece_type_restriction: PIECE_TYPE, behavior_to_inject, card_type=None,
        remaining_uses: Optional[int] = None, delay_before_use: Optional[int] = None,
        allows_captured_piece_selection: bool = False,
    ):
        self.__remaining_uses = _resolve_remaining_uses(enchantment_types, remaining_uses)
        self.__delay_before_use = _resolve_delay_before_use(enchantment_types, delay_before_use)
        self.__enchantment_types = enchantment_types
        self.__title = title
        self.__description = description
        self.__piece_type_restriction = piece_type_restriction
        self.__behavior_to_inject = behavior_to_inject
        self.__card_type = card_type
        self.__allows_captured_piece_selection = allows_captured_piece_selection

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

    def allows_captured_piece_selection(self) -> bool:
        return self.__allows_captured_piece_selection

    def get_enchantment_types(self) -> List[EnchantmentType]:
        return self.__enchantment_types.copy()

    def is_mandatory(self) -> bool:
        return self.__enchantment_types.__contains__(EnchantmentType.MANDATORY)

    def get_description(self) -> str:
        return self.__description

    def get_title(self) -> str:
        return self.__title

    def get_rate_delay_before_use(self) -> int:
        return self.__delay_before_use

    def get_rate_stun_after_use(self) -> int:
        return self.__enchantment_types.count(EnchantmentType.STUN_AFTER_USE)

    def get_required_piece_type(self) -> PIECE_TYPE:
        return self.__piece_type_restriction
