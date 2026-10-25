from typing import List

import pygame
from pygame import Surface

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.predefined_colors import PREDEFINED_COLOR
from models import enchantments
from models.enchantments import Enchantment
from piecesprite import PieceSprite
from utils.gamecontext import GameContext


class CardsProcessor:

    def __init__(self, screen: Surface):
        context = GameContext()

        self.small_font = pygame.font.SysFont(context.comic_sans_font, 16)
        self.white_cards = list(enchantments.available_cards)
        self.black_cards = list(enchantments.available_cards)

        context.white_cards_starting_point = (context.board_offset_x + (context.square_length * 8) + 20, 0)
        context.black_cards_starting_point = (0, 0)

        columns = 2
        max_card_count = max(len(self.white_cards), len(self.black_cards))
        rows = max(4, (max_card_count + columns - 1) // columns)

        context.card_width = (context.board_offset_x - 20) // columns
        context.card_height = (screen.get_height() - 20) // rows

        context.white_cards_coordinates.clear()
        context.black_cards_coordinates.clear()

        for coordinates, starting_point in (
            (context.white_cards_coordinates, context.white_cards_starting_point),
            (context.black_cards_coordinates, context.black_cards_starting_point),
        ):
            for row in range(rows):
                coordinates.append([])
                for column in range(columns):
                    coordinates[row].append([
                        starting_point[0] + column * context.card_width,
                        starting_point[1] + row * context.card_height,
                    ])

    def get_cards_for(self, color: COLOR) -> List[Enchantment]:
        if color == COLOR.WHITE:
            return self.white_cards
        return self.black_cards

    def render(self, screen: Surface, chess_pieces: PieceSprite, selected_card=None):
        context = GameContext()
        card_size = (context.card_width, context.card_height)
        self.__render_cards(
            screen, context.white_cards_coordinates, chess_pieces, self.white_cards,
            card_size, PREDEFINED_COLOR.transparent_green, COLOR.WHITE.value, COLOR.WHITE, selected_card)
        self.__render_cards(
            screen, context.black_cards_coordinates, chess_pieces, self.black_cards,
            card_size, PREDEFINED_COLOR.transparent_blue, COLOR.BLACK.value, COLOR.BLACK, selected_card)

    def __render_cards(self, screen, coordinates, chess_pieces, card_deck, card_size, bg_color, color_name, color, selected_card):
        iterator = 0
        for row in coordinates:
            for coord in row:
                if iterator >= len(card_deck): return
                card: Enchantment = card_deck[iterator]

                surface = Surface((card_size[0] - 5, card_size[1] - 5), pygame.SRCALPHA)
                surface.fill(bg_color)
                screen.blit(surface, coord)

                rendered_card_text = self.small_font.render(card.get_description(), True,
                                                       PREDEFINED_COLOR.white, wraplength=card_size[0]-30)
                x,y = coord
                screen.blit(rendered_card_text, [x+15, y+(card_size[1]//2)-(rendered_card_text.get_height()//2)])

                if card.get_required_piece_type() != PIECE_TYPE.EMPTY:
                    chess_pieces.draw(screen, "{}_{}".format(color_name, card.get_required_piece_type().value), coord, True)

                if selected_card == (color, iterator):
                    pygame.draw.rect(
                        screen, PREDEFINED_COLOR.white,
                        pygame.Rect(coord[0], coord[1], card_size[0] - 5, card_size[1] - 5), 4)

                iterator += 1
