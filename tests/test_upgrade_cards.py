import unittest

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType


class UpgradeCardTests(unittest.TestCase):
    def test_upgrade_cards_keep_their_source_target_rarity_and_stun(self):
        """Weryfikuje bazową figurę, cel, rzadkość i stun wszystkich kart awansu."""
        expected = {
            "PAWN_UPGRADE_TO_KNIGHT": (PIECE_TYPE.PAWN, PIECE_TYPE.KNIGHT, 0.1, 1),
            "PAWN_UPGRADE_TO_BISHOP": (PIECE_TYPE.PAWN, PIECE_TYPE.BISHOP, 0.025, 2),
            "PAWN_UPGRADE_TO_ROOK": (PIECE_TYPE.PAWN, PIECE_TYPE.ROOK, 0.00625, 3),
            "PAWN_UPGRADE_TO_QUEEN": (PIECE_TYPE.PAWN, PIECE_TYPE.QUEEN, 0.0015625, 4),
            "KNIGHT_UPGRADE_TO_BISHOP": (PIECE_TYPE.KNIGHT, PIECE_TYPE.BISHOP, 0.05, 1),
            "KNIGHT_UPGRADE_TO_ROOK": (PIECE_TYPE.KNIGHT, PIECE_TYPE.ROOK, 0.0125, 2),
            "KNIGHT_UPGRADE_TO_QUEEN": (PIECE_TYPE.KNIGHT, PIECE_TYPE.QUEEN, 0.003125, 3),
            "BISHOP_UPGRADE_TO_ROOK": (PIECE_TYPE.BISHOP, PIECE_TYPE.ROOK, 0.05, 1),
            "BISHOP_UPGRADE_TO_QUEEN": (PIECE_TYPE.BISHOP, PIECE_TYPE.QUEEN, 0.0125, 2),
            "ROOK_UPGRADE_TO_QUEEN": (PIECE_TYPE.ROOK, PIECE_TYPE.QUEEN, 0.01, 1),
        }

        for card_name, (source, target, rarity, stun) in expected.items():
            with self.subTest(card=card_name):
                card_type = EnchantmentCardType[card_name]
                enchantment = card_type.create()
                self.assertEqual(source, card_type.piece_type)
                self.assertEqual(target, card_type.promoted_piece_type)
                self.assertEqual(rarity, card_type.rarity)
                self.assertEqual(stun, enchantment.get_rate_stun_after_use())

    def test_piece_can_only_promote_forward_in_the_hierarchy(self):
        """Sprawdza, że awans w hierarchii działa, a cofnięcie jest odrzucane."""
        piece = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)

        self.assertTrue(piece.promote_to(PIECE_TYPE.QUEEN))
        self.assertEqual(PIECE_TYPE.QUEEN, piece.get_type())
        self.assertFalse(piece.promote_to(PIECE_TYPE.ROOK))
        self.assertEqual(PIECE_TYPE.QUEEN, piece.get_type())


if __name__ == "__main__":
    unittest.main()
