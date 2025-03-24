import pygame

from constants.chess_pieces import pieces_starting_positions_map, PIECE, PIECE_COLOR
from constants.colors import COLOR
from constants.pos import notation_to_xy, xy_to_notation
from piece import Piece
from utils import Utils


class Chess(object):
    def __init__(self, screen, pieces_src, square_coords, square_length):
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

        # list containing possible moves for the selected piece
        self.moves = []
        #
        self.utils = Utils()

        # mapping of piece names to index of list containing piece coordinates on spritesheet
        self.pieces = pieces_starting_positions_map
        self.piece_location = {}
        # list containing captured pieces
        self.winner = ""
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
            self.piece_location[i] = [PIECE(), False]

        for piece, positions_list in pieces_starting_positions_map.items():
            for position in positions_list:
                self.piece_location[position] = [piece, False]

    #
    def play_turn(self):
        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        small_font = pygame.font.SysFont("comicsansms", 20)
        # create text to be shown on the game menu
        rendered_text = small_font.render("Turn: " + self.current_turn, True, white_color)
        # show welcome text
        self.screen.blit(rendered_text, ((self.screen.get_width() - rendered_text.get_width()) // 2, 10))
        self.move_piece()

    # method to draw pieces on the chess board
    def draw_pieces(self):
        # loop to change background color of selected pieces
        for position, values in self.piece_location.items():
            piece: PIECE = values[0]
            selection = values[1]
            # name of the piece in the current location
            #  coordinates of the current piece

            # change background color of piece if it is selected
            if not piece.is_empty():
                if selection:
                    self.__change_background_to_selection(position)
                piece_coord_x, piece_coord_y = notation_to_xy(position)
                self.chess_pieces.draw(self.screen, piece, self.drawing_coordinates[piece_coord_x][piece_coord_y])


    def __change_background_to_selection(self, pos):
        surface = pygame.Surface((self.square_length, self.square_length), pygame.SRCALPHA)
        surface.fill(COLOR.transparent_blue)

        piece_coord_x, piece_coord_y = notation_to_xy(pos)
        self.screen.blit(surface, self.drawing_coordinates[piece_coord_x][piece_coord_y])
        if len(self.moves) > 0:
            for move in self.moves:
                x_coord = move[0]
                y_coord = move[1]
                if 0 <= x_coord < 8 and 0 <= y_coord < 8:
                    self.screen.blit(surface, self.drawing_coordinates[x_coord][y_coord])


    # method to find the possible moves of the selected piece
    def possible_moves(self, piece_name, piece_coord):
        # list to store possible moves of the selected piece
        positions = []
        # find the possible locations to put a piece
        if len(piece_name) > 0:
            # get x, y coordinate
            x_coord, y_coord = piece_coord
            # calculate moves for bishop
            if piece_name[6:] == "bishop":
                positions = self.diagonal_moves(positions, piece_name, piece_coord)

            # calculate moves for pawn
            elif piece_name[6:] == "pawn":
                # convert list index to dictionary key
                # calculate moves for white pawn
                if piece_name == "black_pawn":
                    if y_coord + 1 < 8:
                        # get row in front of black pawn
                        front_piece = self.piece_location[xy_to_notation(x_coord, y_coord - 1)][0]

                        # pawns cannot move when blocked by another another pawn
                        if (front_piece[6:] != "pawn"):
                            positions.append([x_coord, y_coord - 1])
                            # black pawns can move two positions ahead for first move
                            if y_coord == 7:
                                positions.append([x_coord, y_coord - 2])

                        # EM PASSANT
                        # diagonal to the left
                        if x_coord - 1 >= 0 and y_coord - 1 < 8:
                            x = x_coord - 1
                            y = y_coord - 1

                            # convert list index to dictionary key
                            to_capture = self.piece_location[xy_to_notation(x, y)][0]

                            if to_capture.startswith("white"):
                                positions.append([x, y])

                        # diagonal to the right
                        if x_coord + 1 < 8 and y_coord - 1 < 8:
                            x = x_coord + 1
                            y = y_coord - 1

                            # convert list index to dictionary key
                            to_capture = self.piece_location[xy_to_notation(x, y)][0]

                            if to_capture.startswith("white"):
                                positions.append([x, y])

                # calculate moves for white pawn
                elif piece_name == "white_pawn":
                    if y_coord - 1 >= 0:
                        # get row in front of black pawn
                        front_piece = self.piece_location[xy_to_notation(x_coord, y_coord + 1)][0]

                        # pawns cannot move when blocked by another another pawn
                        if (front_piece[6:] != "pawn"):
                            positions.append([x_coord, y_coord + 1])
                            # black pawns can move two positions ahead for first move
                            if y_coord > 5:
                                positions.append([x_coord, y_coord + 2])

                        # EM PASSANT
                        # diagonal to the left
                        if x_coord - 1 >= 0 and y_coord + 1 >= 0:
                            x = x_coord - 1
                            y = y_coord + 1

                            # convert list index to dictionary key
                            to_capture = self.piece_location[xy_to_notation(x, y)][0]

                            if to_capture.startswith("black"):
                                positions.append([x, y])

                        # diagonal to the right
                        if x_coord + 1 < 8 and y_coord + 1 >= 0:
                            x = x_coord + 1
                            y = y_coord + 1

                            # convert list index to dictionary key
                            to_capture = self.piece_location[xy_to_notation(x, y)][0]

                            if to_capture.startswith("black"):
                                positions.append([x, y])


            # calculate moves for rook
            elif piece_name[6:] == "rook":
                # find linear moves
                positions = self.linear_moves(positions, piece_name, piece_coord)

            # calculate moves for knight
            elif piece_name[6:] == "knight":
                # left positions
                if (x_coord - 2) >= 0:
                    if (y_coord - 1) >= 0:
                        positions.append([x_coord - 2, y_coord - 1])
                    if (y_coord + 1) < 8:
                        positions.append([x_coord - 2, y_coord + 1])
                # top positions
                if (y_coord - 2) >= 0:
                    if (x_coord - 1) >= 0:
                        positions.append([x_coord - 1, y_coord - 2])
                    if (x_coord + 1) < 8:
                        positions.append([x_coord + 1, y_coord - 2])
                # right positions
                if (x_coord + 2) < 8:
                    if (y_coord - 1) >= 0:
                        positions.append([x_coord + 2, y_coord - 1])
                    if (y_coord + 1) < 8:
                        positions.append([x_coord + 2, y_coord + 1])
                # bottom positions
                if (y_coord + 2) < 8:
                    if (x_coord - 1) >= 0:
                        positions.append([x_coord - 1, y_coord + 2])
                    if (x_coord + 1) < 8:
                        positions.append([x_coord + 1, y_coord + 2])

            # calculate movs for king
            elif piece_name[6:] == "king":
                if (y_coord - 1) >= 0:
                    # top spot
                    positions.append([x_coord, y_coord - 1])

                if (y_coord + 1) < 8:
                    # bottom spot
                    positions.append([x_coord, y_coord + 1])

                if (x_coord - 1) >= 0:
                    # left spot
                    positions.append([x_coord - 1, y_coord])
                    # top left spot
                    if (y_coord - 1) >= 0:
                        positions.append([x_coord - 1, y_coord - 1])
                    # bottom left spot
                    if (y_coord + 1) < 8:
                        positions.append([x_coord - 1, y_coord + 1])

                if (x_coord + 1) < 8:
                    # right spot
                    positions.append([x_coord + 1, y_coord])
                    # top right spot
                    if (y_coord - 1) >= 0:
                        positions.append([x_coord + 1, y_coord - 1])
                    # bottom right spot
                    if (y_coord + 1) < 8:
                        positions.append([x_coord + 1, y_coord + 1])

            # calculate movs for queen
            elif piece_name[6:] == "queen":
                # find diagonal positions
                positions = self.diagonal_moves(positions, piece_name, piece_coord)

                # find linear moves
                positions = self.linear_moves(positions, piece_name, piece_coord)

            # list of positions to be removed
            to_remove = []

            # remove positions that overlap other pieces of the current player
            for xy in positions:
                pos = xy_to_notation(xy[0], xy[1])

                # find the pieces to remove
                des_piece_name = self.piece_location[pos][0]
                if (des_piece_name[:5] == piece_name[:5]):
                    to_remove.append(xy)

            # remove position from positions list
            for xy in to_remove:
                positions.remove(xy)

        # return list containing possible moves for the selected piece
        return positions


    def move_piece(self):
        # get the coordinates of the square selected on the board
        # [piece name, position]
        square = self.get_selected_square()

        # if a square was selected
        if square:
            # get name of piece on the selected square
            piece_name = square[0]
            # color of piece on the selected square
            piece_color = piece_name[:5]

            # if there's a piece on the selected square
            if (piece_name) and (str.lower(piece_color) == str.lower(self.current_turn)):
                # find possible moves for thr piece
                self.moves = self.possible_moves(piece_name, notation_to_xy(square[1]))

            # TODO checkmate mechanism
            # p = self.piece_location[columnChar][rowNo]
            #
            # #
            # for i in self.moves:
            #     # if selected square is a valid move
            #     if i == [x, y]:
            #         # if selected square is not occupied by any piece
            #         if (p[0][:5] == turn) or len(p[0]) == 0:
            #             # move piece
            #             self.validate_move([x, y])
            #         # if piece selected is the opponents piece
            #         else:
            #             # capture piece
            #             self.capture_piece(turn, [columnChar, rowNo], [x, y])
            #
            # # only the player with the turn gets to play
            # if (piece_color == turn):
            #     # change selection flag from all other pieces
            #     for k in self.piece_location.keys():
            #         for key in self.piece_location[k].keys():
            #             self.piece_location[k][key][1] = False
            #
            #     # change selection flag of the selected piece
            #     self.piece_location[columnChar][rowNo][1] = True


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
                                    for position, info in self.piece_location.items():
                                        # [piece name, currently selected, board coordinates]
                                        if not info[1]:
                                            info[1] = False
                                    pos = xy_to_notation(k, l)
                                    self.piece_location[pos][1] = True
                                    return [self.piece_location[pos][0], pos]
                            except:
                                pass
        else:
            return None


    def capture_piece(self, turn, chess_board_coord, piece_coord):
        # get x, y coordinate of the destination piece
        x, y = piece_coord

        # get chess board coordinate
        columnChar, rowNo = chess_board_coord

        p = self.piece_location[columnChar][rowNo]
        # add the captured piece to list
        self.captured_black.append(p)
        # move source piece to its destination
        self.validate_move(piece_coord)


    def validate_move(self, destination):
        desColChar = chr(97 + destination[0])
        desRowNo = 8 - destination[1]

        for k in self.piece_location.keys():
            for key in self.piece_location[k].keys():
                board_piece = self.piece_location[k][key]

                if board_piece[1]:
                    # unselect the source piece
                    self.piece_location[k][key][1] = False
                    # get the name of the source piece
                    piece_name = self.piece_location[k][key][0]
                    # move the source piece to the destination piece
                    self.piece_location[desColChar][desRowNo][0] = piece_name

                    src_name = self.piece_location[k][key][0]
                    # remove source piece from its current position
                    self.piece_location[k][key][0] = ""

                    # change turn
                    if (self.turn["black"]):
                        self.turn["black"] = 0
                        self.turn["white"] = 1
                    elif ("white"):
                        self.turn["black"] = 1
                        self.turn["white"] = 0

                    src_location = k + str(key)
                    des_location = desColChar + str(desRowNo)
                    print("{} moved from {} to {}".format(src_name, src_location, des_location))


    # helper function to find diagonal moves
    def diagonal_moves(self, positions, piece_name, piece_coord):
        # reset x and y coordinate values
        x, y = piece_coord
        # find top left diagonal spots
        while (True):
            x = x - 1
            y = y - 1
            if (x < 0 or y < 0):
                break
            else:
                positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

        # reset x and y coordinate values
        x, y = piece_coord
        # find bottom right diagonal spots
        while (True):
            x = x + 1
            y = y + 1
            if (x > 7 or y > 7):
                break
            else:
                positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

        # reset x and y coordinate values
        x, y = piece_coord
        # find bottom left diagonal spots
        while (True):
            x = x - 1
            y = y + 1
            if (x < 0 or y > 7):
                break
            else:
                positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

        # reset x and y coordinate values
        x, y = piece_coord
        # find top right diagonal spots
        while (True):
            x = x + 1
            y = y - 1
            if (x > 7 or y < 0):
                break
            else:
                positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

        return positions


    # helper function to find horizontal and vertical moves
    def linear_moves(self, positions, piece_name, piece_coord):
        # reset x, y coordniate value
        x, y = piece_coord
        # horizontal moves to the left
        while (x > 0):
            x = x - 1
            positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

        # reset x, y coordniate value
        x, y = piece_coord
        # horizontal moves to the right
        while (x < 7):
            x = x + 1
            positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

                # reset x, y coordniate value
        x, y = piece_coord
        # vertical moves upwards
        while (y > 0):
            y = y - 1
            positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

        # reset x, y coordniate value
        x, y = piece_coord
        # vertical moves downwards
        while (y < 7):
            y = y + 1
            positions.append([x, y])

            # convert list index to dictionary key
            columnChar = chr(97 + x)
            rowNo = 8 - y
            p = self.piece_location[columnChar][rowNo]

            # stop finding possible moves if blocked by a piece
            if len(p[0]) > 0 and piece_name[:5] != p[:5]:
                break

        return positions
