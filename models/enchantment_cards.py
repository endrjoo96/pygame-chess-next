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
from utils.logging import debug_log
from utils.run_config import RUN_MODE, RunMode


def _resolve_remaining_uses_range(enchantment_types, remaining_uses):
    """Waliduje zakres użyć karty i zwraca go dla kart wielokrotnego użytku."""
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
    """Sprawdza, czy rzadkość mieści się w przedziale od 0 do 1, i zwraca float."""
    if isinstance(rarity, bool) or not isinstance(rarity, (int, float)) or not 0 <= rarity <= 1:
        raise ValueError("An enchantment rarity must be a number between 0 and 1")
    return float(rarity)


def _sample_card_candidates(card_types):
    """Tworzy kandydatów losowania, próbkując liczbę użyć kart wielokrotnych."""
    return [
        (
            card_type,
            random.randint(*card_type.remaining_uses_range)
            if card_type.remaining_uses_range is not None
            else None,
        )
        for card_type in card_types
    ]


def _calculate_effective_weights(card_types_with_uses):
    """Wylicza wagi rzadkości i proporcjonalnie ogranicza je liczbą pozostałych użyć."""
    return [
        card_type.rarity
        * (
            uses / card_type.remaining_uses_range[1]
            if uses is not None
            else 1
        )
        for card_type, uses in card_types_with_uses
    ]


def _log_candidate_uses(card_types_with_uses):
    """Zapisuje rzadkość i wylosowaną liczbę użyć każdej karty-kandydata."""
    debug_log("Board card draw: sampled uses for candidate cards:")
    for card_type, uses in card_types_with_uses:
        debug_log(
            "  {}: rarity={}, sampled uses={}".format(
                card_type.name, card_type.rarity,
                uses if uses is not None else "not reusable")
        )


def _log_effective_weights(card_types_with_uses, weights):
    """Loguje kandydatów posortowanych malejąco po wadze, bez zmiany ich kolejności losowania."""
    debug_log("Board card draw: effective candidate weights:")
    sorted_candidates = sorted(
        zip(card_types_with_uses, weights),
        key=lambda candidate: candidate[1],
        reverse=True,
    )
    for (card_type, _), weight in sorted_candidates:
        debug_log("  {}: {}".format(card_type.name, weight))


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
    PAWN_UPGRADE_TO_KNIGHT = (
        [EnchantmentType.STUN_AFTER_USE], 0.1, "Awans piona: skoczek",
        "Awansuje piona na skoczka i ogłusza go na 1 turę.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.KNIGHT)
    PAWN_UPGRADE_TO_BISHOP = (
        [EnchantmentType.STUN_AFTER_USE] * 2, 0.025, "Awans piona: goniec",
        "Awansuje piona na gońca i ogłusza go na 2 tury.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.BISHOP)
    PAWN_UPGRADE_TO_ROOK = (
        [EnchantmentType.STUN_AFTER_USE] * 3, 0.00625, "Awans piona: wieża",
        "Awansuje piona na wieżę i ogłusza go na 3 tury.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.ROOK)
    PAWN_UPGRADE_TO_QUEEN = (
        [EnchantmentType.STUN_AFTER_USE] * 4, 0.0015625, "Awans piona: hetman",
        "Awansuje piona na hetmana i ogłusza go na 4 tury.",
        PIECE_TYPE.PAWN, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.QUEEN)
    KNIGHT_UPGRADE_TO_BISHOP = (
        [EnchantmentType.STUN_AFTER_USE], 0.05, "Awans skoczka: goniec",
        "Awansuje skoczka na gońca i ogłusza go na 1 turę.",
        PIECE_TYPE.KNIGHT, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.BISHOP)
    KNIGHT_UPGRADE_TO_ROOK = (
        [EnchantmentType.STUN_AFTER_USE] * 2, 0.0125, "Awans skoczka: wieża",
        "Awansuje skoczka na wieżę i ogłusza go na 2 tury.",
        PIECE_TYPE.KNIGHT, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.ROOK)
    KNIGHT_UPGRADE_TO_QUEEN = (
        [EnchantmentType.STUN_AFTER_USE] * 3, 0.003125, "Awans skoczka: hetman",
        "Awansuje skoczka na hetmana i ogłusza go na 3 tury.",
        PIECE_TYPE.KNIGHT, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.QUEEN)
    BISHOP_UPGRADE_TO_ROOK = (
        [EnchantmentType.STUN_AFTER_USE], 0.05, "Awans gońca: wieża",
        "Awansuje gońca na wieżę i ogłusza go na 1 turę.",
        PIECE_TYPE.BISHOP, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.ROOK)
    BISHOP_UPGRADE_TO_QUEEN = (
        [EnchantmentType.STUN_AFTER_USE] * 2, 0.0125, "Awans gońca: hetman",
        "Awansuje gońca na hetmana i ogłusza go na 2 tury.",
        PIECE_TYPE.BISHOP, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.QUEEN)
    ROOK_UPGRADE_TO_QUEEN = (
        [EnchantmentType.STUN_AFTER_USE], 0.01, "Awans wieży: hetman",
        "Awansuje wieżę na hetmana i ogłusza ją na 1 turę.",
        PIECE_TYPE.ROOK, any_piece_behaviors.no_additional_moves,
        None, None, False, None, PIECE_TYPE.QUEEN)
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
        resurrected_piece_type=None, promoted_piece_type=None,
    ):
        """Opisuje wariant karty i waliduje jej parametry użycia oraz losowania."""
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
        self.promoted_piece_type = promoted_piece_type

    def create(self, uses=None) -> Enchantment:
        """Tworzy instancję zaklęcia; dla kart z zakresem losuje lub waliduje liczbę użyć."""
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
        """Zwraca konfigurację karty z podaną, zweryfikowaną liczbą użyć."""
        _resolve_remaining_uses(self.enchantment_types, uses)
        if self.remaining_uses_range is not None:
            minimum, maximum = self.remaining_uses_range
            if not minimum <= uses <= maximum:
                raise ValueError("The selected number of uses is outside the card's configured range")
        return ConfiguredEnchantmentCard(self, uses)

    @classmethod
    def _random_choice_with_uses(cls):
        """Losuje kartę i liczbę użyć, delegując obliczanie wag i logowanie."""
        card_types_with_uses = _sample_card_candidates(cls)
        _log_candidate_uses(card_types_with_uses)

        if RUN_MODE is RunMode.DEBUG:
            selected = random.choice(card_types_with_uses)
            debug_log(
                "Board card draw: DEBUG mode selected {} uniformly (rarity weights ignored)".format(
                    selected[0].name)
            )
            return selected

        weights = _calculate_effective_weights(card_types_with_uses)
        _log_effective_weights(card_types_with_uses, weights)
        if not any(weights):
            raise ValueError("At least one enchantment must have a non-zero rarity")
        selected = random.choices(card_types_with_uses, weights=weights, k=1)[0]
        debug_log(
            "Board card draw: selected {} with {} use(s)".format(
                selected[0].name, selected[1] if selected[1] is not None else 1)
        )
        return selected

    @classmethod
    def random_choice(cls) -> "EnchantmentCardType":
        """Losuje i zwraca typ karty, nie tworząc jeszcze zaklęcia."""
        return cls._random_choice_with_uses()[0]

    @classmethod
    def create_random(cls) -> Enchantment:
        """Losuje kartę i tworzy jej zaklęcie z wybraną liczbą użyć."""
        card_type, uses = cls._random_choice_with_uses()
        enchantment = card_type.create(uses=uses)
        debug_log(
            "Board card draw: created '{}' with {} use(s)".format(
                enchantment.get_title(), enchantment.get_remaining_uses())
        )
        return enchantment


class ConfiguredEnchantmentCard:
    def __init__(self, card_type: EnchantmentCardType, uses: int):
        """Zapamiętuje typ karty i ustaloną liczbę użyć do późniejszego utworzenia."""
        self.card_type = card_type
        self.uses = uses

    def create(self) -> Enchantment:
        """Tworzy zaklęcie skonfigurowane z zapisaną liczbą użyć."""
        return self.card_type.create(uses=self.uses)


rook_jump_card = EnchantmentCardType.ROOK_JUMP_ALLIES.create()
available_cards = [
    card_type.create() if card_type != EnchantmentCardType.ROOK_JUMP_ALLIES else rook_jump_card
    for card_type in EnchantmentCardType
]
