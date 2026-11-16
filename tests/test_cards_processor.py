import random

import pygame
import pytest

from constants.enchantment_type import EnchantmentType
from constants.predefined_colors import PREDEFINED_COLOR
from models.enchantment_cards import EnchantmentCardType
from processors.cards_processor import CardsProcessor
from utils.gamecontext import GameContext


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


def test_buff_card_icon_is_loaded_from_its_resource(monkeypatch):
    loaded_paths = []

    class FakeImage:
        def convert_alpha(self):
            return pygame.Surface((24, 24), pygame.SRCALPHA)

    def fake_load(path):
        loaded_paths.append(path)
        return FakeImage()

    monkeypatch.setattr(pygame.image, "load", fake_load)
    monkeypatch.setattr(GameContext(), "square_length", 80, raising=False)
    processor = CardsProcessor(pygame.Surface((1200, 880)))

    assert EnchantmentType.BUFF in processor.enchantment_icons
    assert GameContext().card_mod_buff_src in loaded_paths


def test_reset_decks_leaves_both_players_with_empty_hands():
    processor = CardsProcessor.__new__(CardsProcessor)
    processor.rng = random.Random(23)
    processor.white_cards = [
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create(uses=2),
    ]
    processor.black_cards = [
        EnchantmentCardType.PIECE_TELEPORT.create(),
    ]
    rng_state = processor.rng.getstate()

    processor.reset_decks()

    assert processor.white_cards == []
    assert processor.black_cards == []
    assert processor.rng.getstate() == rng_state


def test_reset_decks_clears_hands_again_without_randomizing():
    processor = CardsProcessor.__new__(CardsProcessor)
    processor.rng = random.Random(20261030)
    processor.white_cards = []
    processor.black_cards = []
    processor.reset_decks()
    rng_state = processor.rng.getstate()

    processor.white_cards.append(
        EnchantmentCardType.PAWN_UPGRADE_TO_KNIGHT.create())
    processor.black_cards.append(
        EnchantmentCardType.PAWN_UPGRADE_TO_ROOK.create())
    processor.reset_decks()

    assert processor.white_cards == []
    assert processor.black_cards == []
    assert processor.rng.getstate() == rng_state
