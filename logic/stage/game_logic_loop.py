import random

import pygame
from pygame import Surface
from pygame.font import SysFont

from constants.pos import id_to_xy, xy_to_id, POS
from constants.piece_type import PIECE_TYPE
from constants.predefined_colors import PREDEFINED_COLOR
from models.chess_pieces import pieces_starting_positions_map, Piece, COLOR
from models.enchantments import EnchantmentCardType
from piecesprite import PieceSprite
from processors import input_processor
from processors.capturing_piece_processor import CaptureProcessor
from processors.cards_processor import CardsProcessor
from processors.movement_processor import process_possible_basic_moves
from utils.gamecontext import GameContext


class GameLogicLoop(object):
    def __init__(self, screen: Surface):
        self.context = GameContext()
        # display surface
        self.screen = screen
        # create an object of class to show chess pieces on the board
        self.chess_pieces = PieceSprite(self.context.pieces_src, cols=6, rows=2)
        passive_icon = pygame.image.load(self.context.card_mod_passive_src).convert_alpha()
        self.passive_icon = pygame.transform.scale(passive_icon, (16, 16))
        delay_icon = pygame.image.load(self.context.card_mod_delay_src).convert_alpha()
        self.delay_icon = pygame.transform.scale(delay_icon, (16, 16))
        # dictionary to keeping track of player turn
        self.current_turn = COLOR.WHITE

        # Selected piece position
        self.selected_piece_position: int = 0
        # list containing possible moves for the selected piece
        self.moves = []
        self.selected_card = None
        self.selected_captured_piece = None

        # field_id: PIECE
        self.pieces_locations = {}

        # list containing captured pieces
        self.capture_processor = CaptureProcessor()
        self.cards_processor = CardsProcessor(screen)
        self.board_card_position = POS.D5.value
        self.board_card_available = True
        self.board_enchantment = EnchantmentCardType.create_random()
        self.pending_board_card_delay = None
        card_image = pygame.image.load(self.context.card_on_board_src).convert_alpha()
        self.board_card_image = pygame.transform.scale(
            card_image, (self.context.square_length, self.context.square_length))

        self.reset()

    def reset(self):
        # clear moves lists
        self.current_turn = COLOR.WHITE
        self.turns_started = {COLOR.WHITE: 1, COLOR.BLACK: 0}
        self.moves = []
        self.selected_piece_position = 0
        self.selected_card = None
        self.selected_captured_piece = None
        self.board_card_available = True
        self.board_card_position = POS.D5.value
        self.board_enchantment = EnchantmentCardType.create_random()
        self.pending_board_card_delay = None
        self.cards_processor.reset_decks()

        # two dimensonal dictionary containing details about each board location
        # storage format is [piece_name, currently_selected, x_y_coordinate]
        # # reset the board
        for i in range(1, 65):
            # [piece name, currently selected]
            self.pieces_locations[i] = Piece()
        for position, piece in pieces_starting_positions_map.items():
            self.pieces_locations[position.value] = Piece(piece.get_color(), piece.get_type())

    def play_turn(self):
        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        small_font = SysFont(self.context.comic_sans_font, 20)
        # create text to be shown on the game menu
        rendered_text = small_font.render("Turn: " + self.current_turn.value, True, white_color)
        # show welcome text
        self.screen.blit(rendered_text, ((self.screen.get_width() - rendered_text.get_width()) // 2,
                                         self.context.board_offset_y - rendered_text.get_height() - 5))
        self.print_annotations()
        self.process_player_turn()

        return self.capture_processor.is_king_captured()

    # method to draw pieces on the chess board
    def draw_pieces(self):
        if self.board_card_available:
            card_x, card_y = id_to_xy(self.board_card_position)
            self.screen.blit(
                self.board_card_image,
                self.context.chessboard_coordinates[card_x][card_y],
            )

        # loop to change background color of selected pieces
        for position, piece in self.pieces_locations.items():
            # name of the piece in the current location
            #  coordinates of the current piece

            # change background color of piece if it is selected
            if piece.exists():
                piece_coord_x, piece_coord_y = id_to_xy(position)
                if self.selected_piece_position == position:
                    self.__change_background_to_selection(position)
                if piece.is_stunned(self.turns_started[piece.get_color()]):
                    self.__change_background_to_stunned(position)
                self.chess_pieces.draw(self.screen, piece.full_name(),
                                       self.context.chessboard_coordinates[piece_coord_x][piece_coord_y])
                square_x, square_y = self.context.chessboard_coordinates[piece_coord_x][piece_coord_y]
                icon_x = square_x + self.context.square_length - 16
                if piece.has_passive_enchantment():
                    self.screen.blit(self.passive_icon, (icon_x, square_y))
                    icon_x -= 16
                if piece.has_delay_enchantment():
                    self.screen.blit(self.delay_icon, (icon_x, square_y))

        # draw captured pieces on the top and bottom of chessboard
        self.draw_captured_pieces()
        self.cards_processor.render(self.screen, self.chess_pieces, self.selected_card)
        self.__draw_board_card_preview()
        self.__draw_piece_effect_preview()

    def __draw_board_card_preview(self):
        if not self.board_card_available:
            return

        card_x, card_y = id_to_xy(self.board_card_position)
        square = pygame.Rect(
            self.context.chessboard_coordinates[card_x][card_y],
            (self.context.square_length, self.context.square_length),
        )
        mouse_x, mouse_y = pygame.mouse.get_pos()
        if not square.collidepoint(mouse_x, mouse_y):
            return

        margin = 10
        card_width = self.context.card_width
        card_height = self.context.card_height
        preview_x = mouse_x + margin
        preview_y = mouse_y + margin
        if preview_x + card_width > self.screen.get_width():
            preview_x = mouse_x - card_width - margin
        if preview_y + card_height > self.screen.get_height():
            preview_y = mouse_y - card_height - margin

        self.cards_processor.render_preview(
            self.screen, self.chess_pieces, self.board_enchantment, (preview_x, preview_y), self.current_turn)

    def __draw_piece_effect_preview(self):
        mouse_x, mouse_y = pygame.mouse.get_pos()
        for position, piece in self.pieces_locations.items():
            effects = piece.get_effects()
            if not piece.exists() or not effects:
                continue

            piece_x, piece_y = id_to_xy(position)
            square_x, square_y = self.context.chessboard_coordinates[piece_x][piece_y]
            square = pygame.Rect(
                square_x, square_y, self.context.square_length, self.context.square_length)
            if square.collidepoint(mouse_x, mouse_y):
                self.cards_processor.render_effects_preview(
                    self.screen, self.chess_pieces, effects,
                    (mouse_x + 10, mouse_y + 10), piece.get_color())
                return

    def __change_background_to_selection(self, pos):
        surface = pygame.Surface((self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        surface.fill(PREDEFINED_COLOR.transparent_blue)

        piece_coord_x, piece_coord_y = id_to_xy(pos)
        self.screen.blit(surface, self.context.chessboard_coordinates[piece_coord_x][piece_coord_y])
        if len(self.moves) > 0:
            for move in self.moves:
                x_coord = move[0]
                y_coord = move[1]
                if 0 <= x_coord < 8 and 0 <= y_coord < 8:
                    self.screen.blit(surface, self.context.chessboard_coordinates[x_coord][y_coord])

    def __change_background_to_stunned(self, pos):
        surface = pygame.Surface((self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        surface.fill(PREDEFINED_COLOR.transparent_red)
        piece_coord_x, piece_coord_y = id_to_xy(pos)
        self.screen.blit(surface, self.context.chessboard_coordinates[piece_coord_x][piece_coord_y])

    def process_player_turn(self):
        # get the coordinates of the square selected on the board
        position = input_processor.get_clicked_chessboard_field_id()
        # if a square was selected
        if position:
            piece = self.pieces_locations[position]
            if (piece.exists()) and (piece.get_color() == self.current_turn):
                if piece.is_stunned(self.turns_started[self.current_turn]):
                    self.selected_piece_position = 0
                    self.moves = []
                    return

                if position == self.selected_piece_position:
                    self.selected_piece_position = 0
                    self.moves = []
                    return

                active_enchantment = None
                if self.selected_card is not None:
                    card_color, card_index = self.selected_card
                    card_deck = self.cards_processor.get_cards_for(card_color)
                    if card_index >= len(card_deck):
                        self.selected_card = None
                        self.moves = []
                        self.selected_piece_position = 0
                        return
                    active_enchantment = card_deck[card_index]
                    required_piece_type = active_enchantment.get_required_piece_type()
                    if required_piece_type != piece.get_type() and required_piece_type != PIECE_TYPE.EMPTY:
                        self.moves = []
                        self.selected_piece_position = 0
                        return

                    if active_enchantment.is_passive():
                        delay = active_enchantment.get_rate_delay_before_use()
                        if delay > 0:
                            piece.add_delayed_enchantment(
                                active_enchantment,
                                self.turns_started[self.current_turn] + delay,
                            )
                        else:
                            self.__apply_passive_enchantment(position, active_enchantment)
                        card_deck.pop(card_index)
                        self.selected_card = None
                        self.selected_piece_position = 0
                        self.moves = []
                        self.__end_turn()
                        return

                self.selected_piece_position = position
                self.moves = process_possible_basic_moves(
                    piece, id_to_xy(position), self.pieces_locations, active_enchantment)

            else:
                for i in self.moves:
                    # if selected square is a valid move
                    if xy_to_id(i[0], i[1]) == position:
                        # if selected square is not occupied by any piece
                        if not piece.exists():
                            # move piece
                            self.move_piece(position)
                        # if piece selected is the opponents piece
                        else:
                            # capture piece
                            self.capture_piece(position)

        else:
            color, index = input_processor.get_clicked_captured_piece_index()
            if color is not None and index is not None:
                captured_pieces = (
                    self.capture_processor.get_captured_white()
                    if color == COLOR.WHITE
                    else self.capture_processor.get_captured_black()
                )
                if 0 <= index < len(captured_pieces):
                    piece = captured_pieces[index]
                    print(
                        "Clicked captured piece: type={}, color={}, list_position={}".format(
                            piece.get_type().value, piece.get_color().value, index
                        )
                    )
                    clicked_piece = (color, index)
                    self.selected_captured_piece = (
                        None if self.selected_captured_piece == clicked_piece else clicked_piece
                    )
            else:
                color, index = input_processor.get_clicked_card_index()
                if color == self.current_turn:
                    card_deck = self.cards_processor.get_cards_for(color)
                    if index is not None and 0 <= index < len(card_deck):
                        clicked_card = (color, index)
                        self.selected_card = None if self.selected_card == clicked_card else clicked_card
                        self.selected_piece_position = 0
                        self.moves = []

    def __detonate_pawn(self, position):
        x, y = id_to_xy(position)
        for target_y in range(max(0, y - 1), min(7, y + 1) + 1):
            for target_x in range(max(0, x - 1), min(7, x + 1) + 1):
                if target_x == x and target_y == y:
                    continue

                target_position = xy_to_id(target_x, target_y)
                target_piece = self.pieces_locations[target_position]
                if target_piece.exists():
                    self.capture_processor.capture_piece(target_piece)
                    self.pieces_locations[target_position] = Piece()

        self.pieces_locations[position] = Piece()
        self.selected_piece_position = 0
        self.moves = []

    def __apply_passive_enchantment(self, position, enchantment):
        if enchantment.get_card_type() == EnchantmentCardType.PAWN_DETONATION:
            self.__detonate_pawn(position)
        else:
            self.pieces_locations[position].set_enchantment(enchantment)

    def __apply_ready_passive_enchantments(self, color):
        turn = self.turns_started[color]
        for position, piece in self.pieces_locations.items():
            if not piece.exists() or piece.get_color() != color:
                continue
            for enchantment in piece.get_delayed_enchantments_ready_at(turn):
                if not piece.exists():
                    break
                self.__apply_passive_enchantment(position, enchantment)

    def __end_turn(self):
        self.current_turn = COLOR.BLACK if self.current_turn == COLOR.WHITE else COLOR.WHITE
        self.turns_started[self.current_turn] += 1
        self.__apply_ready_passive_enchantments(self.current_turn)

    def capture_piece(self, destination):
        p: Piece = self.pieces_locations[destination]
        self.capture_processor.capture_piece(p)
        # add the captured piece to list
        # if p.get_color() == COLOR.WHITE:
        #     self.captured_black.append(p)
        # else:
        #     self.captured_white.append(p)
        # move source piece to its destination
        self.move_piece(destination, beats=True)

    def move_piece(self, destination, beats=False):
        if self.selected_piece_position > 0:
            collected_board_card = self.board_card_available and destination == self.board_card_position
            moving_color = self.current_turn
            used_card = None
            if self.selected_card is not None and self.selected_card[0] == moving_color:
                card_color, card_index = self.selected_card
                card_deck = self.cards_processor.get_cards_for(card_color)
                if card_index < len(card_deck):
                    used_card = card_deck[card_index]

            piece: Piece = self.pieces_locations[self.selected_piece_position]
            self.pieces_locations[self.selected_piece_position] = Piece()
            self.pieces_locations[destination] = piece

            if collected_board_card:
                card_deck = self.cards_processor.get_cards_for(moving_color)
                if self.board_enchantment.is_reusable():
                    matching_card = next(
                        (
                            card for card in card_deck
                            if card.get_card_type() == self.board_enchantment.get_card_type()
                            and card.is_reusable()
                        ),
                        None,
                    )
                    if matching_card is not None:
                        matching_card.add_uses(self.board_enchantment.get_remaining_uses())
                    else:
                        card_deck.append(self.board_enchantment)
                else:
                    card_deck.append(self.board_enchantment)
                self.board_card_available = False

            if used_card is not None and used_card.consume_use() == 0:
                card_deck.pop(card_index)

            stun_turns = (
                used_card.get_rate_stun_after_use()
                if used_card is not None
                else sum(
                    enchantment.get_rate_stun_after_use()
                    for enchantment in piece.get_passive_enchantments()
                )
            )
            if stun_turns > 0:
                piece.set_stunned_until_turn(
                    self.turns_started[moving_color] + stun_turns + 1
                )

            self.__end_turn()

            if collected_board_card:
                self.pending_board_card_delay = random.randint(0, 4)
                print("Next board card will appear in {} turns".format(self.pending_board_card_delay))
                if self.pending_board_card_delay == 0:
                    self.__place_next_board_card()
            elif self.pending_board_card_delay is not None:
                self.pending_board_card_delay -= 1
                if self.pending_board_card_delay == 0:
                    self.__place_next_board_card()

            beats_or_moves = "moves"
            if beats:
                beats_or_moves = "beats"
            print(
                "{} {} from {} to {}".format(piece.full_name(), beats_or_moves, POS(self.selected_piece_position).name,
                                             POS(destination).name))
            self.selected_piece_position = 0
            self.moves = []
            self.selected_card = None

    def __place_next_board_card(self):
        empty_positions = [
            position for position in range(1, 65)
            if not self.pieces_locations[position].exists()
        ]
        self.board_card_position = random.choice(empty_positions)
        self.board_enchantment = EnchantmentCardType.create_random()
        self.board_card_available = True
        self.pending_board_card_delay = None

    def print_annotations(self):
        font_size = int(self.context.square_length / 3)
        font = pygame.font.SysFont(self.context.comic_sans_font, font_size)
        color = (120, 120, 120)
        top_margin = self.context.board_offset_y + self.context.square_length / 2
        number_to_display = 8
        # display numbers on the left
        for row in range(0, 8):
            rendered = font.render(str(number_to_display), True, color)
            self.screen.blit(rendered,
                             (int(self.context.board_offset_x - rendered.get_width() - 10),
                              int(top_margin + (row * self.context.square_length - rendered.get_height() / 2))))
            number_to_display -= 1

        # display letters on the bottom
        left_margin = self.context.board_offset_x + self.context.square_length / 2
        for column in range(0, 8):
            rendered = font.render(chr(65 + column), True, color)
            self.screen.blit(rendered,
                             (int(left_margin + (column * self.context.square_length - rendered.get_width() / 2)),
                              int(self.context.board_offset_y + (self.context.square_length * 8) + 5)))

    def draw_captured_pieces(self):
        if not (self.context.captured_white_starting_point and self.context.captured_black_starting_point):
            self.context.captured_white_starting_point = (self.context.board_offset_x,
                                                          self.context.board_offset_y * 2 + (
                                                                  self.context.square_length * 8) - (
                                                                  2 * self.context.piece_cell_thumbnail_height))
            self.context.captured_black_starting_point = (self.context.board_offset_x, 0)

        self.__draw_captured_group(
            self.capture_processor.get_captured_black(),
            COLOR.BLACK,
            self.context.captured_black_starting_point,
        )
        self.__draw_captured_group(
            self.capture_processor.get_captured_white(),
            COLOR.WHITE,
            self.context.captured_white_starting_point,
        )

    def __draw_captured_group(self, pieces, color, starting_point):
        width = self.context.piece_cell_thumbnail_width
        height = self.context.piece_cell_thumbnail_height
        for index, piece in enumerate(pieces):
            coords = (
                starting_point[0] + (index // 2) * width,
                starting_point[1] + (index % 2) * height,
            )
            self.chess_pieces.draw(self.screen, piece.full_name(), coords, True)
            if self.selected_captured_piece == (color, index):
                pygame.draw.rect(
                    self.screen,
                    (255, 255, 255),
                    pygame.Rect(coords, (width, height)),
                    2,
                )
