import pygame
from pygame import Surface

from constants.piece_type import PIECE_TYPE
from constants.predefined_colors import PREDEFINED_COLOR
from models import enchantments
from models.enchantments import Enchantment
from piecesprite import PieceSprite
from utils.gamecontext import GameContext


class CardsProcessor:

    def __init__(self, screen: Surface):
        context = GameContext()

        self.white_cards = enchantments.available_cards
        self.black_cards = []

        context.white_cards_starting_point = (context.board_offset_x + (context.square_length * 8) + 20, 0)
        context.black_cards_starting_point = (0, 0)

        context.card_width = (context.board_offset_x - 20) // 2
        context.card_height = (screen.get_height() - 20) // 4

        for y in range(0, 4):
            context.white_cards_coordinates.append([])
            for x in range(0, 2):
                context.white_cards_coordinates[y].append([
                    context.white_cards_starting_point[0] + (x * context.card_width),
                    context.white_cards_starting_point[1] + (y * context.card_height)])
        for y in range(0, 4):
            context.black_cards_coordinates.append([])
            for x in range(0, 2):
                context.black_cards_coordinates[y].append([
                    context.black_cards_starting_point[0] + (x * context.card_width),
                    context.black_cards_starting_point[1] + (y * context.card_height)])
        pass

    def render(self, screen: Surface, chess_pieces: PieceSprite):
        context = GameContext()
        small_font = pygame.font.SysFont(context.comic_sans_font, 16)
        iterator = 0
        for row in context.white_cards_coordinates:
            for coord in row:
                if iterator >= len(self.white_cards): return
                card: Enchantment = self.white_cards[iterator]

                surface = Surface((context.card_width - 5, context.card_height - 5), pygame.SRCALPHA)
                surface.fill(PREDEFINED_COLOR.transparent_green)
                screen.blit(surface, coord)

                rendered_card_text = small_font.render(card.get_description(), True,
                                                       PREDEFINED_COLOR.white, wraplength=context.card_width-30)
                x,y = coord
                screen.blit(rendered_card_text, [x+15, y+(context.card_height//2)-(rendered_card_text.get_height()//2)])

                if card.get_required_piece_type() != PIECE_TYPE.EMPTY:
                    chess_pieces.draw(screen, "white_{}".format(card.get_required_piece_type().value), coord, True)

                iterator += 1

