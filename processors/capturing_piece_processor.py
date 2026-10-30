from typing import List

from utils.gamecontext import GameContext
from models.chess_pieces import Piece, COLOR, PIECE_TYPE


class CaptureProcessor:
    def __init__(self):
        """Tworzy osobne listy zbitych figur i rejestr zwycięskiego zbicia króla."""
        self.__captured_black = []
        self.__captured_white = []
        self.__captured_king = None

    def capture_piece(self, piece: Piece):
        """Usuwa efekty figury, zapisuje ją jako zbitą i odświeża jej pozycję w panelu."""
        piece.clear_effects()
        if piece.get_type() == PIECE_TYPE.KING:
            self.__captured_king = piece
        if piece.get_color() == COLOR.WHITE:
            self.__captured_black.append(piece)
        else:
            self.__captured_white.append(piece)

        self.__recalculate_clickable_coordinates()

    def get_captured_black(self) -> List[Piece]:
        """Zwraca listę figur czarnych zbitych przez białego gracza."""
        return self.__captured_black

    def get_captured_white(self) -> List[Piece]:
        """Zwraca listę figur białych zbitych przez czarnego gracza."""
        return self.__captured_white

    def release_captured_piece(self, color: COLOR, index: int) -> Piece:
        """Usuwa i zwraca figurę o indeksie z panelu wskazanego koloru."""
        captured_pieces = self.__captured_white if color == COLOR.WHITE else self.__captured_black
        piece = captured_pieces.pop(index)
        self.__recalculate_clickable_coordinates()
        return piece

    def get_winner(self):
        """Zwraca kolor zwycięzcy po zbiciu króla albo None, jeśli gra trwa."""
        if self.__captured_king is None:
            return None
        return COLOR.BLACK if self.__captured_king.get_color() == COLOR.WHITE else COLOR.WHITE

    def reset(self):
        """Czyści zbiory figur i wynik, po czym przelicza współrzędne paneli."""
        self.__captured_black.clear()
        self.__captured_white.clear()
        self.__captured_king = None
        self.__recalculate_clickable_coordinates()

    def __recalculate_clickable_coordinates(self):
        """Aktualizuje pola klikalne obu paneli zbitych figur w kontekście gry."""
        context = GameContext()
        self.__calculate_coordinates_for(context.captured_white_coordinates, context.captured_white_starting_point, self.__captured_white)
        self.__calculate_coordinates_for(context.captured_black_coordinates, context.captured_black_starting_point, self.__captured_black)

    def __calculate_coordinates_for(self, captured_coordinates_array, captured_coordinates_starting_point, captured_list):
        """Układa współrzędne miniaturek naprzemiennie w dwóch rzędach panelu."""
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
