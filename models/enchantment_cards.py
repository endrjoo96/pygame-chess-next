import random
from enum import Enum

from constants.enchantment_type import EnchantmentType
from constants.piece_type import PIECE_TYPE
from enchants_behaviors import any_piece_behaviors, knight_behaviors, pawn_behaviors, queen_behaviors, rook_behaviors
from models.enchantments import (
    Enchantment,
    _resolve_delay_before_use,
    _resolve_remaining_uses,
)
from utils.run_config import RUN_MODE, RunMode


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


def _resolve_rarity(rarity):
    if isinstance(rarity, bool) or not isinstance(rarity, (int, float)) or not 0 <= rarity <= 1:
        raise ValueError("An enchantment rarity must be a number between 0 and 1")
    return float(rarity)


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
        "Porusza się do końca planszy.",
        PIECE_TYPE.ROOK, rook_behaviors.move_to_board_edge)
    PIECE_UPGRADE = (
        [], 0.2, "Awans figury",
        "Awansuje wybraną figurę: pion -> skoczek -> goniec -> wieża -> hetman.",
        PIECE_TYPE.EMPTY, any_piece_behaviors.no_additional_moves)
    RETURN_TO_START = (
        [EnchantmentType.REUSABLE], 0.4, "Powrót na start",
        "Przenieś wybraną figurę na jej pole startowe, jeśli jest wolne. Ruch nie zbija figur.",
        PIECE_TYPE.EMPTY, any_piece_behaviors.no_additional_moves, (1, 3))
    PIECE_TELEPORT = (
        [], 0.2, "Teleportacja",
        "Zamień miejscami swoją figurę z dowolną inną.",
        PIECE_TYPE.EMPTY, any_piece_behaviors.no_additional_moves)
    PIECE_DOUBLE_MOVE = (
        [EnchantmentType.REUSABLE], 0.2, "Podwójny ruch",
        "Pozwala wykonać dwa ruchy tą samą figurą w jednej turze.",
        PIECE_TYPE.EMPTY, any_piece_behaviors.no_additional_moves, (1, 3))

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
    def _random_choice_with_uses(cls):
        card_types_with_uses = [
            (
                card_type,
                random.randint(*card_type.remaining_uses_range)
                if card_type.remaining_uses_range is not None
                else None,
            )
            for card_type in cls
        ]
        if RUN_MODE is RunMode.DEBUG:
            return random.choice(card_types_with_uses)

        weights = [
            card_type.rarity
            * (
                uses / card_type.remaining_uses_range[1]
                if uses is not None
                else 1
            )
            for card_type, uses in card_types_with_uses
        ]
        if not any(weights):
            raise ValueError("At least one enchantment must have a non-zero rarity")
        return random.choices(card_types_with_uses, weights=weights, k=1)[0]

    @classmethod
    def random_choice(cls) -> "EnchantmentCardType":
        return cls._random_choice_with_uses()[0]

    @classmethod
    def create_random(cls) -> Enchantment:
        card_type, uses = cls._random_choice_with_uses()
        return card_type.create(uses=uses)


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
