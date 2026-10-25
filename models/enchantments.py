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
    if not is_reusable and remaining_uses is not None and (
        not isinstance(remaining_uses, int) or isinstance(remaining_uses, bool) or remaining_uses != 1
    ):
        raise ValueError("Non-reusable enchantments must have exactly one use")
    if is_reusable and (
        not isinstance(remaining_uses, int) or isinstance(remaining_uses, bool) or remaining_uses < 1
    ):
        raise ValueError("An enchantment must have a positive integer number of uses")
    return remaining_uses if is_reusable else 1


def _resolve_remaining_uses_range(enchantment_types, remaining_uses):
    if EnchantmentType.REUSABLE not in enchantment_types:
        _resolve_remaining_uses(enchantment_types, remaining_uses)
        return None

    if isinstance(remaining_uses, tuple) and len(remaining_uses) == 2:
        minimum, maximum = remaining_uses
    else:
        minimum = maximum = remaining_uses

    _resolve_remaining_uses(enchantment_types, minimum)
    _resolve_remaining_uses(enchantment_types, maximum)
    if minimum > maximum:
        raise ValueError("The minimum number of uses cannot exceed the maximum")
    return minimum, maximum


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


def _resolve_rarity(rarity):
    if isinstance(rarity, bool) or not isinstance(rarity, (int, float)) or not 0 <= rarity <= 1:
        raise ValueError("An enchantment rarity must be a number between 0 and 1")
    return float(rarity)


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


class EnchantmentCardType(Enum):
    PAWN_TWO_FIELDS_FORWARD = (
        [EnchantmentType.REUSABLE], 0.4, "Skok do przodu", "Wykonaj ruch o 2 pola do przodu", PIECE_TYPE.PAWN,
        pawn_behaviors.two_field_forward_move, (1, 3))
    PAWN_ONE_FIELD_BACKWARD = (
        [EnchantmentType.REUSABLE], 0.4, "Ruch do tyłu", "Wykonaj ruch do tyłu. Pozwala również na zbicie",
        PIECE_TYPE.PAWN, pawn_behaviors.one_field_backwards_move, (1, 3))
    KNIGHT_ONE_FIELD_ANY_DIRECTION = (
        [EnchantmentType.REUSABLE], 0.75, "Przesunięcie skoczka",
        "Skoczek porusza się o 1 pole w dowolnym kierunku",
        PIECE_TYPE.KNIGHT, knight_behaviors.one_field_in_any_direction, (1, 3))
    ROOK_JUMP_ALLIES = (
        [], 0.65, "Wystrzał wieży", "Wieża przeskakuje nad sojuszniczymi figurami, ale nie może zbijać",
        PIECE_TYPE.ROOK, rook_behaviors.move_through_allied_pieces_without_capturing)
    QUEEN_JUMP_ALLIES = (
        [EnchantmentType.MANDATORY], 0.45,
        "Wystrzał hetmana", "Hetman przeskakuje nad sojusznikami do 4 pól, ale nie może zbijać",
        PIECE_TYPE.QUEEN, queen_behaviors.move_up_to_four_fields_through_allies_without_capturing)
    PAWN_DETONATION = (
        [EnchantmentType.PASSIVE], 0.1, "Kamikaze",
        "Detonuje pion, niszcząc wszystkie figury w promieniu 1 pola, włącznie z sojuszniczymi.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves)
    PAWN_DETONATION_DELAYED_1 = (
        [EnchantmentType.PASSIVE, EnchantmentType.DELAY_BEFORE_USE], 0.3, "Kamikaze z opóźnieniem",
        "Po 1 turze detonuje pion, niszcząc wszystkie figury w promieniu 1 pola, włącznie z sojuszniczymi.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves, None, 1)
    PAWN_DETONATION_DELAYED_2 = (
        [EnchantmentType.PASSIVE, EnchantmentType.DELAY_BEFORE_USE], 0.6, "Kamikaze z opóźnieniem",
        "Po 2 turach detonuje pion, niszcząc wszystkie figury w promieniu 1 pola, włącznie z sojuszniczymi.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves, None, 2)
    PAWN_SWORDSMAN = (
        [EnchantmentType.PASSIVE], 0.75, "Szermierz", "Pozwala na poruszanie się na boki.",
        PIECE_TYPE.PAWN, pawn_behaviors.move_one_field_horizontally)
    KING_PAWN_RESURRECTION = (
        [], 0.35, "Wskrzeszenie piona",
        "Wskrzesza zbitego przez przeciwnika piona i umieszcza go w promieniu 1 od króla",
        PIECE_TYPE.KING, any_piece_behaviors.no_additional_moves, None, None, True, PIECE_TYPE.PAWN)
    KING_KNIGHT_RESURRECTION = (
        [], 0.2, "Wskrzeszenie skoczka",
        "Wskrzesza zbitego przez przeciwnika skoczka i umieszcza go w promieniu 1 pola od króla",
        PIECE_TYPE.KING, any_piece_behaviors.no_additional_moves, None, None, True, PIECE_TYPE.KNIGHT)
    KING_BISHOP_RESURRECTION = (
        [], 0.2, "Wskrzeszenie gońca",
        "Wskrzesza zbitego przez przeciwnika gońca i umieszcza go w promieniu 1 pola od króla",
        PIECE_TYPE.KING, any_piece_behaviors.no_additional_moves, None, None, True, PIECE_TYPE.BISHOP)
    KING_ROOK_RESURRECTION = (
        [], 0.15, "Wskrzeszenie wieży",
        "Wskrzesza zbita przez przeciwnika wieżę i umieszcza ją w promieniu 1 pola od króla",
        PIECE_TYPE.KING, any_piece_behaviors.no_additional_moves, None, None, True, PIECE_TYPE.ROOK)
    KING_QUEEN_RESURRECTION = (
        [], 0.05, "Wskrzeszenie hetmana",
        "Wskrzesza zbitego przez przeciwnika hetmana i umieszcza go w promieniu 1 pola od króla",
        PIECE_TYPE.KING, any_piece_behaviors.no_additional_moves, None, None, True, PIECE_TYPE.QUEEN)
    ROOK_TOWER_THROW = (
        [EnchantmentType.MANDATORY, EnchantmentType.STUN_AFTER_USE, EnchantmentType.STUN_AFTER_USE], 0.3,
        "Rzut wieżą", "Zbija wszystkie figury na swojej drodze, w tym własne. "
        "Porusza się do końca planszy. Blokuje ruch na dwie tury.",
        PIECE_TYPE.ROOK, rook_behaviors.move_to_board_edge)

    def __init__(
        self, enchantment_types, rarity, title, description, piece_type, behavior_to_inject,
        remaining_uses=None, delay_before_use=None, allows_captured_piece_selection=False,
        resurrected_piece_type=None,
    ):
        self.enchantment_types = enchantment_types
        self.rarity = _resolve_rarity(rarity)
        self.title = title
        self.description = description
        self.piece_type = piece_type
        self.behavior_to_inject = behavior_to_inject
        self.remaining_uses_range = _resolve_remaining_uses_range(enchantment_types, remaining_uses)
        self.delay_before_use = _resolve_delay_before_use(enchantment_types, delay_before_use)
        self.allows_captured_piece_selection = allows_captured_piece_selection
        self.resurrected_piece_type = resurrected_piece_type

    def create(self, uses=None) -> Enchantment:
        if self.remaining_uses_range is None:
            if uses is not None:
                _resolve_remaining_uses(self.enchantment_types, uses)
            remaining_uses = None
        elif uses is None:
            remaining_uses = random.randint(*self.remaining_uses_range)
        else:
            _resolve_remaining_uses(self.enchantment_types, uses)
            minimum, maximum = self.remaining_uses_range
            if not minimum <= uses <= maximum:
                raise ValueError("The selected number of uses is outside the card's configured range")
            remaining_uses = uses

        return Enchantment(
            self.enchantment_types.copy(), self.title, self.description, self.piece_type,
            self.behavior_to_inject, self, remaining_uses,
            self.delay_before_use if self.delay_before_use else None,
            self.allows_captured_piece_selection)

    def with_uses(self, uses: int):
        _resolve_remaining_uses(self.enchantment_types, uses)
        if self.remaining_uses_range is not None:
            minimum, maximum = self.remaining_uses_range
            if not minimum <= uses <= maximum:
                raise ValueError("The selected number of uses is outside the card's configured range")
        return ConfiguredEnchantmentCard(self, uses)

    @classmethod
    def random_choice(cls) -> "EnchantmentCardType":
        card_types = list(cls)
        weights = [card_type.rarity for card_type in card_types]
        if not any(weights):
            raise ValueError("At least one enchantment must have a non-zero rarity")
        return random.choices(card_types, weights=weights, k=1)[0]

    @classmethod
    def create_random(cls) -> Enchantment:
        return cls.random_choice().create()


class ConfiguredEnchantmentCard:
    def __init__(self, card_type: EnchantmentCardType, uses: int):
        self.card_type = card_type
        self.uses = uses

    def create(self) -> Enchantment:
        return self.card_type.create(uses=self.uses)


rook_jump_card = EnchantmentCardType.ROOK_JUMP_ALLIES.create()
available_cards = [
    card_type.create() if card_type != EnchantmentCardType.ROOK_JUMP_ALLIES else rook_jump_card
    for card_type in EnchantmentCardType
]
