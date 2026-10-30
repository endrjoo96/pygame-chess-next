import unittest
from unittest.mock import Mock, patch

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from logic.stage.game_logic_loop import GameLogicLoop


class FakeCardsProcessor:
    def __init__(self, cards):
        """Przechowuje testowe talie i udostępnia je według koloru."""
        self.decks = {COLOR.WHITE: cards, COLOR.BLACK: []}

    def get_cards_for(self, color):
        """Zwraca testową talię wskazanego gracza."""
        return self.decks[color]

    def add_card_for(self, color, card):
        """Dodaje kartę do testowej talii i sygnalizuje powodzenie."""
        self.decks[color].append(card)
        return True


class FakeCaptureProcessor:
    def __init__(self):
        """Przygotowuje testowe listy zbitych figur i rejestr zbić."""
        self.captured_white = []
        self.captured_black = []
        self.captured = []

    def get_captured_white(self):
        """Zwraca testową listę białych zbitych figur."""
        return self.captured_white

    def get_captured_black(self):
        """Zwraca testową listę czarnych zbitych figur."""
        return self.captured_black

    def capture_piece(self, piece):
        """Zapisuje figurę zgłoszoną jako zbita."""
        self.captured.append(piece)

    def release_captured_piece(self, color, index):
        """Usuwa i zwraca figurę z testowej listy wskazanego koloru."""
        pieces = self.captured_white if color == COLOR.WHITE else self.captured_black
        return pieces.pop(index)


def make_game(card_type=None, uses=None):
    """Tworzy minimalny stan gry z atrapami procesorów dla testów logiki."""
    cards = []
    if card_type is not None:
        cards.append(card_type.create(uses=uses))

    game = GameLogicLoop.__new__(GameLogicLoop)
    game.current_turn = COLOR.WHITE
    game.selected_piece_position = 0
    game.moves = []
    game.resurrection_moves = []
    game.selected_card = (COLOR.WHITE, 0) if cards else None
    game.selected_captured_piece = None
    game.double_move_step = 0
    game.double_move_collected_board_card = False
    game.pieces_locations = {position: Piece() for position in range(1, 65)}
    game.capture_processor = FakeCaptureProcessor()
    game.cards_processor = FakeCardsProcessor(cards)
    game.turns_started = {COLOR.WHITE: 1, COLOR.BLACK: 0}
    game.board_card_available = False
    game.board_card_position = 36
    game.board_enchantment = None
    game.pending_board_card_delay = None
    game._GameLogicLoop__end_turn = Mock()
    return game


class GameLogicLoopTests(unittest.TestCase):
    def click_board(self, game, position):
        """Uruchamia przetwarzanie tury z jednym kliknięciem danego pola."""
        with patch(
            "logic.stage.game_logic_loop.input_processor.get_clicked_chessboard_field_id",
            return_value=position,
        ):
            game.process_player_turn()

    def test_upgrade_uses_selected_target_and_applies_card_stun(self):
        """Sprawdza awans do celu wskazanego kartą i nałożenie ogłuszenia."""
        game = make_game(EnchantmentCardType.PAWN_UPGRADE_TO_QUEEN)
        pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
        game.pieces_locations[1] = pawn

        self.click_board(game, 1)

        self.assertEqual(PIECE_TYPE.QUEEN, pawn.get_type())
        self.assertTrue(pawn.is_stunned())
        self.assertEqual([], game.cards_processor.get_cards_for(COLOR.WHITE))
        game._GameLogicLoop__end_turn.assert_called_once_with()

    def test_teleport_swaps_selected_piece_with_occupied_square(self):
        """Sprawdza zamianę dwóch figur i zużycie karty teleportacji."""
        game = make_game(EnchantmentCardType.PIECE_TELEPORT)
        first = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)
        second = Piece(COLOR.BLACK, PIECE_TYPE.BISHOP)
        game.pieces_locations[1] = first
        game.pieces_locations[2] = second

        self.click_board(game, 1)
        self.click_board(game, 2)

        self.assertIs(second, game.pieces_locations[1])
        self.assertIs(first, game.pieces_locations[2])
        self.assertEqual([], game.cards_processor.get_cards_for(COLOR.WHITE))
        game._GameLogicLoop__end_turn.assert_called_once_with()

    def test_return_to_start_moves_piece_to_an_empty_original_square(self):
        """Sprawdza powrót figury na wolne pole startowe."""
        game = make_game(EnchantmentCardType.RETURN_TO_START, uses=1)
        rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK, starting_position=1)
        game.pieces_locations[20] = rook

        self.click_board(game, 20)
        self.click_board(game, 1)

        self.assertIs(rook, game.pieces_locations[1])
        self.assertFalse(game.pieces_locations[20].exists())
        game._GameLogicLoop__end_turn.assert_called_once_with()

    def test_delayed_passive_card_is_scheduled_and_consumed(self):
        """Sprawdza zaplanowanie pasywnego efektu i zużycie jego karty."""
        game = make_game(EnchantmentCardType.PAWN_DETONATION_DELAYED_1)
        pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
        game.pieces_locations[9] = pawn

        self.click_board(game, 9)

        self.assertEqual([], pawn.get_delayed_enchantments_ready_at(1))
        due_effects = pawn.get_delayed_enchantments_ready_at(2)
        self.assertEqual(1, len(due_effects))
        self.assertEqual(
            EnchantmentCardType.PAWN_DETONATION_DELAYED_1,
            due_effects[0].get_card_type(),
        )
        self.assertEqual([], game.cards_processor.get_cards_for(COLOR.WHITE))
        game._GameLogicLoop__end_turn.assert_called_once_with()

    def test_resurrection_places_captured_piece_next_to_king(self):
        """Sprawdza wybór zbitej figury i jej wskrzeszenie przy królu."""
        game = make_game(EnchantmentCardType.KING_PAWN_RESURRECTION)
        game.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
        pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
        game.capture_processor.captured_black.append(pawn)

        with patch(
            "logic.stage.game_logic_loop.input_processor.get_clicked_chessboard_field_id",
            return_value=None,
        ), patch(
            "logic.stage.game_logic_loop.input_processor.get_clicked_captured_piece_index",
            return_value=(COLOR.BLACK, 0),
        ):
            game.process_player_turn()

        self.assertEqual((COLOR.BLACK, 0), game.selected_captured_piece)
        self.assertIn(2, game.resurrection_moves)
        self.click_board(game, 2)

        self.assertIs(pawn, game.pieces_locations[2])
        self.assertEqual([], game.capture_processor.captured_black)
        self.assertEqual([], game.cards_processor.get_cards_for(COLOR.WHITE))
        game._GameLogicLoop__end_turn.assert_called_once_with()

    def test_double_move_keeps_turn_open_between_moves(self):
        """Sprawdza, że pierwszy ruch karty podwójnego ruchu nie kończy tury."""
        game = make_game(EnchantmentCardType.PIECE_DOUBLE_MOVE, uses=2)
        rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
        game.pieces_locations[1] = rook
        self.click_board(game, 1)
        self.click_board(game, 9)

        self.assertEqual(1, game.double_move_step)
        self.assertEqual(9, game.selected_piece_position)
        game._GameLogicLoop__end_turn.assert_not_called()

        self.click_board(game, 10)

        self.assertIs(rook, game.pieces_locations[10])
        game._GameLogicLoop__end_turn.assert_called_once_with()

    def test_rook_throw_captures_every_piece_on_route(self):
        """Sprawdza zbijanie własnych i przeciwnych figur na trasie rzutu wieżą."""
        game = make_game(EnchantmentCardType.ROOK_TOWER_THROW)
        rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
        allied = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
        enemy = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
        game.pieces_locations[1] = rook
        game.pieces_locations[3] = allied
        game.pieces_locations[5] = enemy
        game.selected_piece_position = 1

        game.move_piece(8, beats=True)

        self.assertIs(rook, game.pieces_locations[8])
        self.assertFalse(game.pieces_locations[1].exists())
        self.assertFalse(game.pieces_locations[3].exists())
        self.assertFalse(game.pieces_locations[5].exists())
        self.assertEqual([allied, enemy], game.capture_processor.captured)

    def test_move_collects_board_card_and_schedules_the_next_one(self):
        """Sprawdza dodanie karty z pola docelowego i zaplanowanie kolejnej."""
        game = make_game()
        game._GameLogicLoop__schedule_next_board_card = Mock()
        game.board_card_available = True
        game.board_card_position = 2
        game.board_enchantment = EnchantmentCardType.PIECE_TELEPORT.create()
        rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
        game.pieces_locations[1] = rook
        game.selected_piece_position = 1

        game.move_piece(2)

        self.assertIn(
            game.board_enchantment,
            game.cards_processor.get_cards_for(COLOR.WHITE),
        )
        self.assertFalse(game.board_card_available)
        game._GameLogicLoop__schedule_next_board_card.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
