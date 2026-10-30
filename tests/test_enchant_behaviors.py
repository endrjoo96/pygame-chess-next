import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import xy_to_id
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from processors.movement_processor import process_possible_basic_moves


def empty_board():
    return {position: Piece() for position in range(1, 65)}


def test_pawn_two_field_move_requires_both_squares_to_be_empty():
    board = empty_board()
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)

    assert process_possible_basic_moves(
        pawn, [3, 1], board, EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create()
    ) == [[3, 3]]

    board[xy_to_id(3, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)
    assert process_possible_basic_moves(
        pawn, [3, 1], board, EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create()
    ) == []

    board[xy_to_id(3, 2)] = Piece()
    board[xy_to_id(3, 3)] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)
    assert process_possible_basic_moves(
        pawn, [3, 1], board, EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD.create()
    ) == []


def test_pawn_backward_move_captures_only_diagonal_enemies():
    board = empty_board()
    board[xy_to_id(2, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)
    board[xy_to_id(4, 2)] = Piece(COLOR.WHITE, PIECE_TYPE.BISHOP)
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)

    moves = process_possible_basic_moves(
        pawn, [3, 3], board, EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD.create(uses=1)
    )

    assert moves == [[3, 2], [2, 2]]

    board[xy_to_id(3, 2)] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    assert process_possible_basic_moves(
        pawn, [3, 3], board, EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD.create(uses=1)
    ) == [[2, 2]]


def test_pawn_horizontal_move_stays_on_board_and_excludes_occupied_allied_square():
    board = empty_board()
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    enchantment = EnchantmentCardType.PAWN_SWORDSMAN.create()

    assert process_possible_basic_moves(pawn, [0, 4], board, enchantment) == [[1, 4]]

    board[xy_to_id(1, 4)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    assert process_possible_basic_moves(pawn, [0, 4], board, enchantment) == []

    board[xy_to_id(1, 4)] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    assert process_possible_basic_moves(pawn, [0, 4], board, enchantment) == []


def test_knight_adjacent_move_is_bounded_and_cannot_end_on_ally():
    board = empty_board()
    board[xy_to_id(1, 0)] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    board[xy_to_id(0, 1)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    knight = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)

    moves = process_possible_basic_moves(
        knight, [0, 0], board,
        EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION.create(uses=1),
    )

    assert moves == [[0, 1], [1, 1]]


def test_rook_move_passes_allies_but_stops_before_enemy():
    board = empty_board()
    board[xy_to_id(3, 4)] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    board[xy_to_id(3, 6)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)

    moves = process_possible_basic_moves(
        rook, [3, 3], board, EnchantmentCardType.ROOK_JUMP_ALLIES.create()
    )

    assert [3, 5] in moves
    assert [3, 4] not in moves
    assert [3, 6] not in moves
    assert [3, 7] not in moves
    assert [2, 3] in moves


def test_rook_tower_throw_reaches_board_edges_through_any_pieces():
    board = empty_board()
    board[xy_to_id(3, 4)] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    board[xy_to_id(3, 6)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)

    moves = process_possible_basic_moves(
        rook, [3, 3], board, EnchantmentCardType.ROOK_TOWER_THROW.create()
    )

    assert moves == [[3, 0], [3, 7], [0, 3], [7, 3]]


def test_queen_passes_allies_caps_range_and_stops_before_enemy():
    board = empty_board()
    board[xy_to_id(4, 3)] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    board[xy_to_id(6, 3)] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    queen = Piece(COLOR.WHITE, PIECE_TYPE.QUEEN)
    enchantment = EnchantmentCardType.QUEEN_JUMP_ALLIES.create()

    moves = process_possible_basic_moves(queen, [3, 3], board, enchantment)

    assert [5, 3] in moves
    assert [4, 3] not in moves
    assert [6, 3] not in moves
    assert [7, 3] not in moves
    assert [3, 7] in moves

    corner_moves = process_possible_basic_moves(queen, [0, 0], empty_board(), enchantment)
    assert [4, 4] in corner_moves
    assert [5, 5] not in corner_moves
