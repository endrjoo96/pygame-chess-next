from typing import List

from utils.gamecontext import GameContext
from models.chess_pieces import Piece, COLOR, PIECE_TYPE


class CaptureProcessor:
    __captured_black = []
    __captured_white = []
    __captured_king = None
    def capture_piece(self, piece: Piece):
        if piece.get_type() == PIECE_TYPE.KING:
            self.__captured_king = piece
        if piece.get_color() == COLOR.WHITE:
            self.__captured_black.append(piece)
        else:
            self.__captured_white.append(piece)

        self.__recalculate_clickable_coordinates()

    def get_captured_black(self) -> List[Piece]: return self.__captured_black
    def get_captured_white(self) -> List[Piece]: return self.__captured_white
    def is_king_captured(self): return self.__captured_king

    def __recalculate_clickable_coordinates(self):
        context = GameContext()
        self.__calculate_coordinates_for(context.captured_white_coordinates, context.captured_white_starting_point, self.__captured_white)
        self.__calculate_coordinates_for(context.captured_black_coordinates, context.captured_black_starting_point, self.__captured_black)

    def __calculate_coordinates_for(self, captured_coordinates_array, captured_coordinates_starting_point, captured_list):
        context = GameContext()
        bottom_row = False
        column = 0
        captured_coordinates_array.clear()
        captured_coordinates_array.append([])
        captured_coordinates_array.append([])
        for piece in captured_list:
            captured_coordinates_array[int(bottom_row)].append([
                captured_coordinates_starting_point[0] + column * context.piece_cell_thumbnail_width,
                captured_coordinates_starting_point[1] + int(bottom_row) * context.piece_cell_thumbnail_height
            ])
            bottom_row = not bottom_row
            if not bottom_row:
                column += 1
