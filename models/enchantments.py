import importlib
from functools import lru_cache
from types import FunctionType
from typing import List, Optional

from constants.enchantment_type import EnchantmentType
from constants.piece_type import PIECE_TYPE


@lru_cache(maxsize=256)
def _behavior_cache_key(behavior):
    if behavior is None:
        return None
    if not isinstance(behavior, FunctionType) or "<locals>" in behavior.__qualname__:
        raise ValueError("Enchantment behavior cannot be represented in the search cache")
    resolved = importlib.import_module(behavior.__module__)
    for name in behavior.__qualname__.split("."):
        resolved = getattr(resolved, name)
    if resolved is not behavior:
        raise ValueError("Enchantment behavior is not a stable module-level function")
    return behavior.__module__, behavior.__qualname__, behavior


def _resolve_remaining_uses(enchantment_types, remaining_uses):
    """Waliduje liczbę użyć względem wielokrotnego użytku i zwraca jej wartość domyślną."""
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
    """Sprawdza zgodność opóźnienia z typami zaklęcia i zwraca opóźnienie domyślne."""
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
        """Tworzy zaklęcie, walidując użycia i opóźnienie oraz zapamiętując jego reguły."""
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
        """Zwraca funkcję rozszerzającą ruch figury."""
        return self.__behavior_to_inject

    def is_reusable(self) -> bool:
        """Sprawdza, czy zaklęcie może być używane więcej niż raz."""
        return EnchantmentType.REUSABLE in self.__enchantment_types

    def is_passive(self) -> bool:
        """Sprawdza, czy zaklęcie działa jako efekt pasywny."""
        return EnchantmentType.PASSIVE in self.__enchantment_types

    def get_remaining_uses(self) -> int:
        """Zwraca liczbę pozostałych użyć."""
        return self.__remaining_uses

    def consume_use(self) -> int:
        """Zużywa jedno użycie i zwraca liczbę pozostałych."""
        self.__remaining_uses -= 1
        return self.__remaining_uses

    def add_uses(self, count: int):
        """Dodaje podaną liczbę użyć do zaklęcia wielokrotnego użytku."""
        self.__remaining_uses += count

    def get_card_type(self):
        """Zwraca typ karty, z którego utworzono zaklęcie."""
        return self.__card_type

    def allows_captured_piece_selection(self) -> bool:
        """Określa, czy karta pozwala wybrać figurę z listy zbitych."""
        return self.__allows_captured_piece_selection

    def get_enchantment_types(self) -> List[EnchantmentType]:
        """Zwraca kopię znaczników określających zachowanie zaklęcia."""
        return self.__enchantment_types.copy()

    def is_mandatory(self) -> bool:
        """Sprawdza, czy efekt jest obowiązkowy dla figury."""
        return self.__enchantment_types.__contains__(EnchantmentType.MANDATORY)

    def get_description(self) -> str:
        """Zwraca opis zaklęcia wyświetlany na karcie."""
        return self.__description

    def get_title(self) -> str:
        """Zwraca tytuł zaklęcia wyświetlany na karcie."""
        return self.__title

    def get_rate_delay_before_use(self) -> int:
        """Zwraca liczbę tur opóźnienia przed aktywacją."""
        return self.__delay_before_use

    def get_rate_stun_after_use(self) -> int:
        """Zwraca liczbę tur ogłuszenia przypisaną do zaklęcia."""
        return self.__enchantment_types.count(EnchantmentType.STUN_AFTER_USE)

    def get_required_piece_type(self) -> PIECE_TYPE:
        """Zwraca wymagany typ figury; EMPTY oznacza brak ograniczenia."""
        return self.__piece_type_restriction

    def cache_key(self):
        return (
            tuple(self.__enchantment_types), self.__piece_type_restriction,
            _behavior_cache_key(self.__behavior_to_inject), self.__card_type,
            self.__remaining_uses, self.__delay_before_use,
            self.__allows_captured_piece_selection,
        )
