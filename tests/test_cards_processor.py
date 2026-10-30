import random

import pygame
import pytest

from constants.enchantment_type import EnchantmentType
from constants.predefined_colors import PREDEFINED_COLOR
from models.enchantment_cards import EnchantmentCardType
from processors.cards_processor import CardsProcessor


class FakePieceSprite:
    def draw(self, surface, piece_name, coords, thumbnail=False):
        """Miejsce zastępcze dla grafiki figury używanej podczas testu."""
        return None


@pytest.fixture(scope="module", autouse=True)
def initialize_pygame_font():
    pygame.font.init()


def test_card_renderer_composes_icons_piece_and_text():
    """Sprawdza, czy pojedyncza karta może zostać narysowana na powierzchni."""
    processor = CardsProcessor.__new__(CardsProcessor)
    processor.title_font = pygame.font.SysFont("Arial", 16, bold=True)
    processor.small_font = pygame.font.SysFont("Arial", 13)
    processor.use_count_font = pygame.font.SysFont("Arial", 12, bold=True)
    processor.enchantment_icons = {
        EnchantmentType.STUN_AFTER_USE: pygame.Surface((24, 24), pygame.SRCALPHA),
    }
    screen = pygame.Surface((180, 240), pygame.SRCALPHA)
    card = EnchantmentCardType.PAWN_UPGRADE_TO_KNIGHT.create()

    processor._CardsProcessor__render_card(
        screen, (0, 0), FakePieceSprite(), card, (180, 240),
        PREDEFINED_COLOR.transparent_green, "white",
    )

    assert screen.get_at((10, 10)) != (0, 0, 0, 0)


def test_reset_decks_gives_both_players_the_same_two_random_cards(monkeypatch):
    draws = iter([
        (EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD, 2),
        (EnchantmentCardType.PIECE_TELEPORT, None),
    ])
    monkeypatch.setattr(
        EnchantmentCardType,
        "sample_with_uses",
        staticmethod(lambda rng=None: next(draws)),
    )
    processor = CardsProcessor.__new__(CardsProcessor)
    processor.rng = random.Random(23)
    processor.white_cards = []
    processor.black_cards = []

    processor.reset_decks()

    white = processor.white_cards
    black = processor.black_cards
    assert len(white) == len(black) == 2
    assert [
        (card.get_card_type(), card.get_remaining_uses()) for card in white
    ] == [
        (card.get_card_type(), card.get_remaining_uses()) for card in black
    ]
    assert all(white_card is not black_card for white_card, black_card in zip(white, black))


def test_same_seed_reproduces_starting_cards():
    processors = []
    for _ in range(2):
        processor = CardsProcessor.__new__(CardsProcessor)
        processor.rng = random.Random(20261030)
        processor.white_cards = []
        processor.black_cards = []
        processor.reset_decks()
        processors.append(processor)

    def card_signature(cards):
        return [
            (card.get_card_type(), card.get_remaining_uses())
            for card in cards
        ]

    assert card_signature(processors[0].white_cards) == card_signature(
        processors[1].white_cards)
