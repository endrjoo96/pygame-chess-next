import pygame
from pygame import Surface

from constants.pos import id_to_xy, xy_to_id, POS
from constants.predefined_colors import PREDEFINED_COLOR
from processors.cards_processor import CardsProcessor
from utils.gamecontext import GameContext
from models import enchantments
from models.chess_pieces import pieces_starting_positions_map, Piece, COLOR
from piecesprite import PieceSprite
from processors import input_processor
from processors.capturing_piece_processor import CaptureProcessor
from processors.movement_processor import process_possible_basic_moves


class Chess(object):
    def __init__(self, screen: Surface):
        self.context = GameContext()
        # display surface
        self.screen = screen
        # create an object of class to show chess pieces on the board
        self.chess_pieces = PieceSprite(self.context.pieces_src, cols=6, rows=2)
        # dictionary to keeping track of player turn
        self.current_turn = COLOR.WHITE

        # Selected piece position
        self.selected_piece_position: int = 0
        # list containing possible moves for the selected piece
        self.moves = []

        # field_id: PIECE
        self.pieces_locations = {}

        # list containing captured pieces
        self.capture_processor = CaptureProcessor()
        self.cards_processor = CardsProcessor(screen)

        self.reset()

    def reset(self):
        # clear moves lists
        self.moves = []

        # two dimensonal dictionary containing details about each board location
        # storage format is [piece_name, currently_selected, x_y_coordinate]
        # # reset the board
        for i in range(1, 64):
            # [piece name, currently selected]
            self.pieces_locations[i] = Piece()

        for position, piece in pieces_starting_positions_map.items():
                self.pieces_locations[position.value] = piece

    def play_turn(self):
        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        small_font = pygame.font.SysFont(self.context.comic_sans_font, 20)
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
        # loop to change background color of selected pieces
        for position, piece in self.pieces_locations.items():
            # name of the piece in the current location
            #  coordinates of the current piece

            # change background color of piece if it is selected
            if piece.exists():
                piece_coord_x, piece_coord_y = id_to_xy(position)
                if self.selected_piece_position == position:
                    self.__change_background_to_selection(position)
                self.chess_pieces.draw(self.screen, piece.full_name(),
                                       self.context.chessboard_coordinates[piece_coord_x][piece_coord_y])

        # draw captured pieces on the top and bottom of chessboard
        self.draw_captured_pieces()
        self.cards_processor.render(self.screen, self.chess_pieces)

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

    def process_player_turn(self):
        # get the coordinates of the square selected on the board
        position = input_processor.get_clicked_chessboard_field_id()
        # if a square was selected
        if position:
            piece = self.pieces_locations[position]
            if piece.exists() and piece.get_color() == self.current_turn:
                self.selected_piece_position = position

            # if there's a piece on the selected square
            if (piece.exists()) and (piece.get_color() == self.current_turn):
                # find possible moves for thr piece
                self.moves = process_possible_basic_moves(piece, id_to_xy(position), self.pieces_locations)

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

        # TODO will be necessary for special ability cards, not for usual gameplay
        # else:
        #     color, index = input_processor.get_clicked_captured_piece_index()
        #     if color == COLOR.WHITE:
        #         print("clicked {} captured by {}".format(self.capture_processor.get_captured_white()[index].full_name(),
        #                                                  color.value))
        #     if color == COLOR.BLACK:
        #         print("clicked {} captured by {}".format(self.capture_processor.get_captured_black()[index].full_name(),
        #                                                  color.value))

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
            piece: Piece = self.pieces_locations[self.selected_piece_position]
            self.pieces_locations[self.selected_piece_position] = Piece()
            self.pieces_locations[destination] = piece

            if self.current_turn == COLOR.WHITE:
                self.current_turn = COLOR.BLACK
            else:
                self.current_turn = COLOR.WHITE

            beats_or_moves = "moves"
            if beats:
                beats_or_moves = "beats"
            print(
                "{} {} from {} to {}".format(piece.full_name(), beats_or_moves, POS(self.selected_piece_position).name,
                                             POS(destination).name))
            self.selected_piece_position = 0
            self.moves = []

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
        iterator = 0
        row = 0

        if not (self.context.captured_white_starting_point and self.context.captured_black_starting_point):
            self.context.captured_white_starting_point = (self.context.board_offset_x,
                                                          self.context.board_offset_y * 2 + (
                                                                      self.context.square_length * 8) - (
                                                                      2 * self.context.piece_cell_thumbnail_height))
            self.context.captured_black_starting_point = (self.context.board_offset_x, 0)

        for piece in self.capture_processor.get_captured_black():
            self.chess_pieces.draw(self.screen, piece.full_name(), (
                self.context.captured_black_starting_point[0] + (
                            iterator * int(self.context.piece_cell_thumbnail_width)),
                self.context.captured_black_starting_point[1] + row * self.context.piece_cell_thumbnail_height
            ), True)
            if row == 1:
                row = 0
                iterator += 1
            else:
                row = 1

        iterator = 0
        row = 0
        for piece in self.capture_processor.get_captured_white():
            self.chess_pieces.draw(self.screen, piece.full_name(), (
                self.context.captured_white_starting_point[0] + (
                            iterator * int(self.context.piece_cell_thumbnail_width)),
                self.context.captured_white_starting_point[1] + (row * self.context.piece_cell_thumbnail_height)
            ), True)
            if row == 1:
                row = 0
                iterator += 1
            else:
                row = 1
