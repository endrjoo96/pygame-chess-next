import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from processors.capturing_piece_processor import CaptureProcessor
from utils.gamecontext import GameContext


@pytest.fixture
def capture_context(monkeypatch):
    """Izoluje współrzędne paneli zbitych figur od singletona GameContext."""
    monkeypatch.setattr(GameContext, "captured_white_coordinates", [])
    monkeypatch.setattr(GameContext, "captured_black_coordinates", [])
    monkeypatch.setattr(GameContext, "captured_white_starting_point", (10, 20))
    monkeypatch.setattr(GameContext, "captured_black_starting_point", (100, 200))
    monkeypatch.setattr(GameContext, "piece_cell_thumbnail_width", 12)
    monkeypatch.setattr(GameContext, "piece_cell_thumbnail_height", 16)
    return GameContext()


def test_capture_groups_by_piece_color_updates_coordinates_and_clears_effects(capture_context):
    processor = CaptureProcessor()
    white_piece = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    white_piece.set_enchantment(EnchantmentCardType.PAWN_SWORDSMAN.create())
    white_piece.add_delayed_enchantment(
        EnchantmentCardType.PAWN_DETONATION_DELAYED_1.create(), 3
    )
    stun = EnchantmentCardType.PAWN_UPGRADE_TO_KNIGHT.create()
    white_piece.add_stun_effect(stun, 2)
    white_piece.set_stunned_for_turns(2)
    black_piece = Piece(COLOR.BLACK, PIECE_TYPE.KNIGHT)

    processor.capture_piece(white_piece)
    processor.capture_piece(black_piece)

    assert processor.get_captured_white() == [black_piece]
    assert processor.get_captured_black() == [white_piece]
    assert not white_piece.has_passive_enchantment()
    assert not white_piece.has_delay_enchantment()
    assert not white_piece.is_stunned()
    assert white_piece.get_effects(current_turn=1) == []
    assert capture_context.captured_white_coordinates == [[[10, 20]], []]
    assert capture_context.captured_black_coordinates == [[[100, 200]], []]


def test_release_removes_selected_piece_and_reflows_remaining_coordinates(capture_context):
    processor = CaptureProcessor()
    first = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    second = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    processor.capture_piece(first)
    processor.capture_piece(second)

    released = processor.release_captured_piece(COLOR.BLACK, 0)

    assert released is first
    assert processor.get_captured_black() == [second]
    assert capture_context.captured_black_coordinates == [[[100, 200]], []]


@pytest.mark.parametrize(
    ("king_color", "expected_winner"),
    [(COLOR.WHITE, COLOR.BLACK), (COLOR.BLACK, COLOR.WHITE)],
)
def test_capturing_king_sets_winner_to_opposite_color(
    capture_context, king_color, expected_winner
):
    processor = CaptureProcessor()

    assert processor.get_winner() is None

    processor.capture_piece(Piece(king_color, PIECE_TYPE.KING))

    assert processor.get_winner() == expected_winner


def test_reset_clears_capture_lists_winner_and_rebuilds_empty_rows(capture_context):
    processor = CaptureProcessor()
    processor.capture_piece(Piece(COLOR.WHITE, PIECE_TYPE.KING))
    processor.capture_piece(Piece(COLOR.BLACK, PIECE_TYPE.PAWN))

    processor.reset()

    assert processor.get_captured_white() == []
    assert processor.get_captured_black() == []
    assert processor.get_winner() is None
    assert capture_context.captured_white_coordinates == [[], []]
    assert capture_context.captured_black_coordinates == [[], []]
