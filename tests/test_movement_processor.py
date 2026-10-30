import unittest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import xy_to_id
from models.chess_pieces import Piece
from processors.movement_processor import process_possible_basic_moves


def empty_board():
    """Tworzy słownik pustych pól o numerach zgodnych z indeksowaniem planszy."""
    return {position: Piece() for position in range(1, 65)}


class MovementProcessorTests(unittest.TestCase):
    def test_pawn_moves_forward_twice_and_captures_diagonally(self):
        """Sprawdza dwa początkowe pola ruchu piona i jego zbicie ukośne."""
        board = empty_board()
        pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN, xy_to_id(3, 1))
        board[xy_to_id(3, 1)] = pawn
        board[xy_to_id(2, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)

        moves = process_possible_basic_moves(pawn, [3, 1], board)

        self.assertEqual([[3, 2], [3, 3], [2, 2]], moves)

    def test_pawn_cannot_advance_when_blocked(self):
        """Sprawdza brak ruchu piona zablokowanego na polu przed nim."""
        board = empty_board()
        pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
        board[xy_to_id(3, 1)] = pawn
        board[xy_to_id(3, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)

        self.assertEqual([], process_possible_basic_moves(pawn, [3, 1], board))

    def test_pawn_can_capture_diagonally_even_when_forward_is_blocked(self):
        """Sprawdza, że blokada ruchu naprzód nie odbiera możliwości zbicia."""
        board = empty_board()
        pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
        board[xy_to_id(3, 1)] = pawn
        board[xy_to_id(3, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
        board[xy_to_id(2, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)

        self.assertEqual(
            [[2, 2]],
            process_possible_basic_moves(pawn, [3, 1], board),
        )

    def test_knight_moves_at_edge_and_excludes_allied_piece(self):
        """Sprawdza ruch skoczka przy krawędzi i odrzucenie pola sojusznika."""
        board = empty_board()
        knight = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)
        board[xy_to_id(0, 0)] = knight
        board[xy_to_id(1, 2)] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)

        moves = process_possible_basic_moves(knight, [0, 0], board)

        self.assertEqual([[2, 1]], moves)

    def test_sliding_piece_stops_at_first_piece_and_can_capture_enemy(self):
        """Sprawdza zatrzymanie wieży na pierwszej figurze i brak przejścia dalej."""
        board = empty_board()
        rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
        board[xy_to_id(3, 3)] = rook
        board[xy_to_id(3, 5)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
        board[xy_to_id(3, 6)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)

        moves = process_possible_basic_moves(rook, [3, 3], board)

        self.assertIn([3, 5], moves)
        self.assertNotIn([3, 6], moves)
        self.assertNotIn([3, 3], moves)

    def test_queen_combines_diagonal_and_linear_moves(self):
        """Sprawdza połączenie ruchów po liniach i przekątnych hetmana."""
        board = empty_board()
        queen = Piece(COLOR.WHITE, PIECE_TYPE.QUEEN)
        board[xy_to_id(3, 3)] = queen

        moves = process_possible_basic_moves(queen, [3, 3], board)

        self.assertIn([4, 4], moves)
        self.assertIn([3, 4], moves)
        self.assertIn([4, 3], moves)


if __name__ == "__main__":
    unittest.main()
