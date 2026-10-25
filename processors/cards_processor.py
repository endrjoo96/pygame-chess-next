from typing import List

import pygame
from pygame import Surface

from constants.enchantment_type import EnchantmentType
from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.predefined_colors import PREDEFINED_COLOR
from models.enchantments import Enchantment, EnchantmentCardType
from piecesprite import PieceSprite
from utils.gamecontext import GameContext


class CardsProcessor:
    STARTING_CARD_TYPES = (
        EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD,
        EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD,
        EnchantmentCardType.PAWN_DETONATION,
        EnchantmentCardType.PAWN_DETONATION_DELAYED,
    )

    def __init__(self, screen: Surface):
        context = GameContext()

        self.small_font = pygame.font.SysFont(context.comic_sans_font, 14)
        self.use_count_font = pygame.font.SysFont(context.comic_sans_font, 12, bold=True)
        self.enchantment_icons = {
            EnchantmentType.PASSIVE: pygame.transform.scale(
                pygame.image.load(context.card_mod_passive_src).convert_alpha(), (24, 24)),
            EnchantmentType.REUSABLE: pygame.transform.scale(
                pygame.image.load(context.card_mod_reusable_src).convert_alpha(), (24, 24)),
            EnchantmentType.DELAY_BEFORE_USE: pygame.transform.scale(
                pygame.image.load(context.card_mod_delay_src).convert_alpha(), (24, 24)),
        }
        self.white_cards = []
        self.black_cards = []
        self.reset_decks()

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

    def reset_decks(self):
        deck = [card_type.create() for card_type in self.STARTING_CARD_TYPES]
        self.white_cards[:] = deck
        self.black_cards[:] = [card_type.create() for card_type in self.STARTING_CARD_TYPES]

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

    def render_preview(self, screen: Surface, chess_pieces: PieceSprite, card: Enchantment, coords, color: COLOR):
        context = GameContext()
        self.__render_card(
            screen, coords, chess_pieces, card, (context.card_width, context.card_height),
            PREDEFINED_COLOR.transparent_brown, card_color=color.value)

    def render_effects_preview(self, screen: Surface, chess_pieces: PieceSprite, effects, coords, color: COLOR):
        if not effects:
            return

        context = GameContext()
        columns = min(3, len(effects))
        rows = (len(effects) + columns - 1) // columns
        card_width = context.card_width
        card_height = min(context.card_height, max(60, (screen.get_height() - 20) // rows))
        preview_width = columns * card_width
        preview_height = rows * card_height
        x, y = coords
        if x + preview_width > screen.get_width():
            x -= preview_width + 20
        if y + preview_height > screen.get_height():
            y -= preview_height + 20
        x = max(0, min(x, screen.get_width() - preview_width))
        y = max(0, min(y, screen.get_height() - preview_height))

        for index, effect in enumerate(effects):
            card_coords = (
                x + (index % 3) * card_width,
                y + (index // 3) * card_height,
            )
            self.__render_card(
                screen, card_coords, chess_pieces, effect, (card_width, card_height),
                PREDEFINED_COLOR.transparent_red, card_color=color.value)

    def __render_cards(self, screen, coordinates, chess_pieces, card_deck, card_size, bg_color, color_name, color, selected_card):
        iterator = 0
        for row in coordinates:
            for coord in row:
                if iterator >= len(card_deck):
                    return
                card: Enchantment = card_deck[iterator]
                self.__render_card(
                    screen, coord, chess_pieces, card, card_size, bg_color, color_name)
                if selected_card == (color, iterator):
                    pygame.draw.rect(
                        screen, PREDEFINED_COLOR.white,
                        pygame.Rect(coord[0], coord[1], card_size[0] - 5, card_size[1] - 5), 4)
                iterator += 1

    def __render_card(self, screen, coords, chess_pieces, card, card_size, bg_color, card_color):
        surface = Surface((card_size[0] - 5, card_size[1] - 5), pygame.SRCALPHA)
        surface.fill(bg_color)
        screen.blit(surface, coords)

        x, y = coords
        icon_types = [
            enchantment_type for enchantment_type in card.get_enchantment_types()
            if enchantment_type in self.enchantment_icons
        ]
        has_piece_icon = card.get_required_piece_type() != PIECE_TYPE.EMPTY
        reusable_icon_x = None
        for index, enchantment_type in enumerate(icon_types):
            icon_x = x + card_size[0] - 5 - 24 * (index + 1)
            screen.blit(self.enchantment_icons[enchantment_type], (icon_x, y + 5))
            if enchantment_type == EnchantmentType.REUSABLE:
                reusable_icon_x = icon_x
            if enchantment_type == EnchantmentType.DELAY_BEFORE_USE:
                delay = self.use_count_font.render(
                    str(card.get_rate_delay_before_use()), True, PREDEFINED_COLOR.white)
                screen.blit(
                    delay,
                    (icon_x + (24 - delay.get_width()) // 2, y + 30))

        if reusable_icon_x is not None:
            use_count = self.use_count_font.render(
                str(card.get_remaining_uses()), True, PREDEFINED_COLOR.white)
            screen.blit(
                use_count,
                (reusable_icon_x + (24 - use_count.get_width()) // 2, y + 30))

        if has_piece_icon:
            chess_pieces.draw(
                screen, "{}_{}".format(card_color, card.get_required_piece_type().value), coords, True)

        margin = 6
        graphics_height = max(
            46 if reusable_icon_x is not None or EnchantmentType.DELAY_BEFORE_USE in icon_types
            else (29 if icon_types else 0),
            GameContext().piece_cell_thumbnail_height if has_piece_icon else 0,
        )
        text_top = y + margin + graphics_height + (margin if graphics_height else 0)
        text_height = y + card_size[1] - margin - text_top
        text_width = card_size[0] - 2 * margin
        for font_size in range(14, 0, -1):
            card_font = self.small_font if font_size == 14 else pygame.font.SysFont(
                GameContext().comic_sans_font, font_size)
            rendered_card_text = card_font.render(
                card.get_description(), True, PREDEFINED_COLOR.white, wraplength=text_width)
            if rendered_card_text.get_height() <= text_height:
                break

        screen.blit(
            rendered_card_text,
            (x + margin, text_top + max(0, (text_height - rendered_card_text.get_height()) // 2)))
