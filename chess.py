import pygame

from constants.chess_pieces import pieces_starting_positions_map, PIECE, PIECE_COLOR, PIECE_TYPE
from constants.colors import COLOR
from constants.pos import id_to_xy, xy_to_id, POS
from piece import Piece
from processors.movement_processor import process_possible_basic_moves
from utils import Utils


class Chess(object):
    def __init__(self, screen, pieces_src, square_coords, square_length, context):
        self.context = context
        # display surface
        self.screen = screen
        # create an object of class to show chess pieces on the board
        self.chess_pieces = Piece(pieces_src, cols=6, rows=2)
        # store coordinates of the chess board squares
        self.drawing_coordinates = square_coords
        # length of the side of a chess board square
        self.square_length = square_length
        # dictionary to keeping track of player turn
        self.current_turn = PIECE_COLOR.WHITE

        # Selected piece position
        self.selected_piece_position: int = 0
        # list containing possible moves for the selected piece
        self.moves = []
        #
        self.utils = Utils()

        # mapping of piece names to index of list containing piece coordinates on spritesheet
        self.pieces = pieces_starting_positions_map

        # field_id: PIECE
        self.pieces_locations = {}

        # list containing captured pieces
        self.captured_black = []
        self.captured_white = []

        self.reset()

    def reset(self):
        # clear moves lists
        self.moves = []

        # two dimensonal dictionary containing details about each board location
        # storage format is [piece_name, currently_selected, x_y_coordinate]
        # # reset the board
        for i in range(1, 64):
            # [piece name, currently selected]
            self.pieces_locations[i] = PIECE()

        for piece, positions_list in pieces_starting_positions_map.items():
            for position in positions_list:
                self.pieces_locations[position.value] = piece

    #
    def play_turn(self):
        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        small_font = pygame.font.SysFont("comicsansms", 20)
        # create text to be shown on the game menu
        rendered_text = small_font.render("Turn: " + self.current_turn.value, True, white_color)
        # show welcome text
        self.screen.blit(rendered_text, ((self.screen.get_width() - rendered_text.get_width()) // 2,
                                         self.context.board_offset_y - rendered_text.get_height() - 5))
        self.print_annotations()
        self.process_player_turn()

        if len(self.captured_white) > 1 and self.captured_white[
            len(self.captured_white) - 1].get_type() == PIECE_TYPE.KING:
            return PIECE_COLOR.WHITE.value
        elif len(self.captured_black) > 1 and self.captured_black[
            len(self.captured_black) - 1].get_type() == PIECE_TYPE.KING:
            return PIECE_COLOR.BLACK.value
        else:
            return None

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
                                       self.drawing_coordinates[piece_coord_x][piece_coord_y])

    def __change_background_to_selection(self, pos):
        surface = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
        surface.fill(COLOR.transparent_blue)

        piece_coord_x, piece_coord_y = id_to_xy(pos)
        self.screen.blit(surface, self.drawing_coordinates[piece_coord_x][piece_coord_y])
        if len(self.moves) > 0:
            for move in self.moves:
                x_coord = move[0]
                y_coord = move[1]
                if 0 <= x_coord < 8 and 0 <= y_coord < 8:
                    self.screen.blit(surface, self.drawing_coordinates[x_coord][y_coord])

    def process_player_turn(self):
        # get the coordinates of the square selected on the board
        # [piece name, position]
        square = self.get_selected_square()

        # if a square was selected
        if square:
            # get name of piece on the selected square
            piece: PIECE = square[0]
            position = square[1]

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

                # # only the player with the turn gets to play
                # if piece.get_color() == self.current_turn:
                #     # change selection flag from all other pieces
                #     for k in self.piece_location.keys():
                #         for key in self.piece_location[k].keys():
                #             self.piece_location[k][key][1] = False
                #
                #     # change selection flag of the selected piece
                #     self.piece_location[columnChar][rowNo][1] = True

    # returns: [PIECE, piece location]
    def get_selected_square(self):
        # get mouse event
        mouse_event = self.utils.get_mouse_event()

        # if there's a mouse event
        if mouse_event and self.utils.left_click_event():
            for i in range(len(self.drawing_coordinates)):
                for j in range(len(self.drawing_coordinates)):
                    rect = pygame.Rect(self.drawing_coordinates[i][j][0], self.drawing_coordinates[i][j][1],
                                       self.square_length, self.square_length)
                    collision = rect.collidepoint(mouse_event[0], mouse_event[1])
                    if collision:
                        selected = [rect.x, rect.y]
                        # find x, y coordinates the selected square
                        for k in range(len(self.drawing_coordinates)):
                            #
                            try:
                                l = None
                                l = self.drawing_coordinates[k].index(selected)
                                if l is not None:
                                    # reset color of all selected pieces
                                    # for position, piece in self.pieces_locations.items():
                                    #     # [piece name, currently selected, board coordinates]
                                    #     if not info[1]:
                                    #         info[1] = False
                                    pos = xy_to_id(k, l)
                                    piece = self.pieces_locations[pos]
                                    if piece.exists() and piece.get_color() == self.current_turn:
                                        self.selected_piece_position = pos
                                    return [piece, pos]
                            except:
                                pass
        else:
            return None

    def capture_piece(self, destination):
        p: PIECE = self.pieces_locations[destination]
        # add the captured piece to list
        if p.get_color() == PIECE_COLOR.WHITE:
            self.captured_black.append(p)
        else:
            self.captured_white.append(p)
        # move source piece to its destination
        self.move_piece(destination, beats=True)

    def move_piece(self, destination, beats=False):
        if self.selected_piece_position > 0:
            piece: PIECE = self.pieces_locations[self.selected_piece_position]
            self.pieces_locations[self.selected_piece_position] = PIECE()
            self.pieces_locations[destination] = piece

            if self.current_turn == PIECE_COLOR.WHITE:
                self.current_turn = PIECE_COLOR.BLACK
            else:
                self.current_turn = PIECE_COLOR.WHITE

            beats_or_moves = "moves"
            if beats:
                beats_or_moves = "beats"
            print(
                "{} {} from {} to {}".format(piece.full_name(), beats_or_moves, POS(self.selected_piece_position).name,
                                             POS(destination).name))
            self.selected_piece_position = 0
            self.moves = []

    def print_annotations(self):
        font_size = int(self.square_length / 3)
        font = pygame.font.SysFont("comicsansms", font_size)
        color = (120, 120, 120)
        top_margin = self.context.board_offset_y + self.square_length / 2
        number_to_display = 8
        for row in range(0, 8):
            rendered = font.render(str(number_to_display), True, color)
            self.screen.blit(rendered,
                             (int(self.context.board_offset_x / 2 - rendered.get_width() / 2),
                              int(top_margin + (row * self.square_length - rendered.get_height() / 2))))
            number_to_display -= 1

        left_margin = self.context.board_offset_x + self.square_length / 2
        for column in range(0, 8):
            rendered = font.render(chr(65 + column), True, color)
            self.screen.blit(rendered,
                             (int(left_margin + (column * self.square_length - rendered.get_width() / 2)),
                              int(self.context.board_offset_y + (self.square_length * 8) + 5)))
