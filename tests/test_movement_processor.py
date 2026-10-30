import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import xy_to_id
from models.chess_pieces import Piece
from processors.movement_processor import process_possible_basic_moves


def empty_board():
    """Tworzy słownik pustych pól o numerach zgodnych z indeksowaniem planszy."""
    return {position: Piece() for position in range(1, 65)}


def test_pawn_moves_forward_twice_and_captures_diagonally():
    """Sprawdza dwa początkowe pola ruchu piona i jego zbicie ukośne."""
    board = empty_board()
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN, xy_to_id(3, 1))
    board[xy_to_id(3, 1)] = pawn
    board[xy_to_id(2, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)

    moves = process_possible_basic_moves(pawn, [3, 1], board)

    assert moves == [[3, 2], [3, 3], [2, 2]]


def test_pawn_cannot_advance_when_blocked():
    """Sprawdza brak ruchu piona zablokowanego na polu przed nim."""
    board = empty_board()
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    board[xy_to_id(3, 1)] = pawn
    board[xy_to_id(3, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)

    assert process_possible_basic_moves(pawn, [3, 1], board) == []


def test_pawn_can_capture_diagonally_even_when_forward_is_blocked():
    """Sprawdza, że blokada ruchu naprzód nie odbiera możliwości zbicia."""
    board = empty_board()
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    board[xy_to_id(3, 1)] = pawn
    board[xy_to_id(3, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    board[xy_to_id(2, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)

    assert process_possible_basic_moves(pawn, [3, 1], board) == [[2, 2]]


def test_knight_moves_at_edge_and_excludes_allied_piece():
    """Sprawdza ruch skoczka przy krawędzi i odrzucenie pola sojusznika."""
    board = empty_board()
    knight = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)
    board[xy_to_id(0, 0)] = knight
    board[xy_to_id(1, 2)] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)

    moves = process_possible_basic_moves(knight, [0, 0], board)

    assert moves == [[2, 1]]


def test_sliding_piece_stops_at_first_piece_and_can_capture_enemy():
    """Sprawdza zatrzymanie wieży na pierwszej figurze i brak przejścia dalej."""
    board = empty_board()
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    board[xy_to_id(3, 3)] = rook
    board[xy_to_id(3, 5)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    board[xy_to_id(3, 6)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)

    moves = process_possible_basic_moves(rook, [3, 3], board)

    assert [3, 5] in moves
    assert [3, 6] not in moves
    assert [3, 3] not in moves


def test_queen_combines_diagonal_and_linear_moves():
    """Sprawdza połączenie ruchów po liniach i przekątnych hetmana."""
    board = empty_board()
    queen = Piece(COLOR.WHITE, PIECE_TYPE.QUEEN)
    board[xy_to_id(3, 3)] = queen

    moves = process_possible_basic_moves(queen, [3, 3], board)

    assert [4, 4] in moves
    assert [3, 4] in moves
    assert [4, 3] in moves
