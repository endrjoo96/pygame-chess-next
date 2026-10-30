import unittest

import pygame

from constants.enchantment_type import EnchantmentType
from constants.predefined_colors import PREDEFINED_COLOR
from models.enchantment_cards import EnchantmentCardType
from processors.cards_processor import CardsProcessor


class FakePieceSprite:
    def draw(self, surface, piece_name, coords, thumbnail=False):
        """Miejsce zastępcze dla grafiki figury używanej podczas testu."""
        return None


class CardsProcessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Inicjalizuje czcionki Pygame potrzebne do renderowania testowego."""
        pygame.font.init()

    def test_card_renderer_composes_icons_piece_and_text(self):
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

        self.assertNotEqual((0, 0, 0, 0), screen.get_at((10, 10)))


if __name__ == "__main__":
    unittest.main()
