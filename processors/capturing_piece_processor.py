from typing import List

from gamecontext import GameContext
from models.chess_pieces import Piece, COLOR, PIECE_TYPE


class CaptureProcessor:
    __captured_black = [Piece(COLOR.WHITE, PIECE_TYPE.BISHOP), Piece(COLOR.WHITE, PIECE_TYPE.PAWN)]
    __captured_white = [Piece(COLOR.BLACK, PIECE_TYPE.ROOK), Piece(COLOR.BLACK, PIECE_TYPE.PAWN),
                        Piece(COLOR.WHITE, PIECE_TYPE.BISHOP)]

    def capture_piece(self, piece: Piece):
        if piece.get_color() == COLOR.WHITE:
            self.__captured_black.append(piece)
        else:
            self.__captured_white.append(piece)

        self.__recalculate_clickable_coordinates()

    def get_captured_black(self) -> List[Piece]: return self.__captured_black
    def get_captured_white(self) -> List[Piece]: return self.__captured_white

    def __recalculate_clickable_coordinates(self):
        context = GameContext()
        bottom_row = False
        column = 0
        for piece in self.__captured_white:
            context.captured_white_coordinates[bottom_row].append([
                context.captured_white_starting_point[0] + column * context.piece_cell_thumbnail_width,
                context.captured_white_starting_point[1] + bottom_row * context.piece_cell_thumbnail_height
            ])
            bottom_row = not bottom_row
            if not bottom_row:
                column += 1

        bottom_row = False
        column = 0
        for piece in self.__captured_black:
            context.captured_black_coordinates[bottom_row].append([
                context.captured_black_starting_point[0] + column * context.piece_cell_thumbnail_width,
                context.captured_black_starting_point[1] + bottom_row * context.piece_cell_thumbnail_height
            ])
            bottom_row = not bottom_row
            if not bottom_row:
                column += 1

        pass
