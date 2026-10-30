import pytest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType


@pytest.mark.parametrize(
    ("card_name", "source", "target", "rarity", "stun"),
    [
        ("PAWN_UPGRADE_TO_KNIGHT", PIECE_TYPE.PAWN, PIECE_TYPE.KNIGHT, 0.1, 1),
        ("PAWN_UPGRADE_TO_BISHOP", PIECE_TYPE.PAWN, PIECE_TYPE.BISHOP, 0.025, 2),
        ("PAWN_UPGRADE_TO_ROOK", PIECE_TYPE.PAWN, PIECE_TYPE.ROOK, 0.00625, 3),
        ("PAWN_UPGRADE_TO_QUEEN", PIECE_TYPE.PAWN, PIECE_TYPE.QUEEN, 0.0015625, 4),
        ("KNIGHT_UPGRADE_TO_BISHOP", PIECE_TYPE.KNIGHT, PIECE_TYPE.BISHOP, 0.05, 1),
        ("KNIGHT_UPGRADE_TO_ROOK", PIECE_TYPE.KNIGHT, PIECE_TYPE.ROOK, 0.0125, 2),
        ("KNIGHT_UPGRADE_TO_QUEEN", PIECE_TYPE.KNIGHT, PIECE_TYPE.QUEEN, 0.003125, 3),
        ("BISHOP_UPGRADE_TO_ROOK", PIECE_TYPE.BISHOP, PIECE_TYPE.ROOK, 0.05, 1),
        ("BISHOP_UPGRADE_TO_QUEEN", PIECE_TYPE.BISHOP, PIECE_TYPE.QUEEN, 0.0125, 2),
        ("ROOK_UPGRADE_TO_QUEEN", PIECE_TYPE.ROOK, PIECE_TYPE.QUEEN, 0.01, 1),
    ],
)
def test_upgrade_cards_keep_their_source_target_rarity_and_stun(
    card_name, source, target, rarity, stun
):
    """Weryfikuje bazową figurę, cel, rzadkość i stun kart awansu."""
    card_type = EnchantmentCardType[card_name]
    enchantment = card_type.create()

    assert card_type.piece_type == source
    assert card_type.promoted_piece_type == target
    assert card_type.rarity == rarity
    assert enchantment.get_rate_stun_after_use() == stun


def test_piece_can_only_promote_forward_in_the_hierarchy():
    """Sprawdza, że awans w hierarchii działa, a cofnięcie jest odrzucane."""
    piece = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)

    assert piece.promote_to(PIECE_TYPE.QUEEN)
    assert piece.get_type() == PIECE_TYPE.QUEEN
    assert not piece.promote_to(PIECE_TYPE.ROOK)
    assert piece.get_type() == PIECE_TYPE.QUEEN
