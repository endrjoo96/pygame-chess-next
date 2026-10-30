from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.game_rules import GameActionType
from logic.game_simulation import GameSimulation
from logic.stage.game_logic_loop import GameLogicLoop
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState


class FakeCardsProcessor:
    def __init__(self, cards):
        """Przechowuje testowe talie i udostępnia je według koloru."""
        self.decks = {COLOR.WHITE: cards, COLOR.BLACK: []}
        self.white_cards = self.decks[COLOR.WHITE]
        self.black_cards = self.decks[COLOR.BLACK]

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
        if piece.get_color() == COLOR.WHITE:
            self.captured_black.append(piece)
        else:
            self.captured_white.append(piece)

    def release_captured_piece(self, color, index):
        """Usuwa i zwraca figurę z testowej listy wskazanego koloru."""
        pieces = self.captured_white if color == COLOR.WHITE else self.captured_black
        return pieces.pop(index)

    def reset(self):
        self.captured_white.clear()
        self.captured_black.clear()
        self.captured.clear()


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
    game._ai_executor = ThreadPoolExecutor(max_workers=1)
    game._ai_future = None
    return game


def click_board(game, position, monkeypatch):
    """Przetwarza kliknięcie wskazanego pola planszy."""
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.input_processor.get_clicked_chessboard_field_id",
        lambda: position,
    )
    game.process_player_turn()


def test_upgrade_uses_selected_target_and_applies_card_stun(monkeypatch):
    """Sprawdza awans do celu wskazanego kartą i nałożenie ogłuszenia."""
    game = make_game(EnchantmentCardType.PAWN_UPGRADE_TO_QUEEN)
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    game.pieces_locations[1] = pawn

    click_board(game, 1, monkeypatch)

    promoted = game.pieces_locations[1]
    assert promoted.get_type() == PIECE_TYPE.QUEEN
    assert promoted.is_stunned()
    assert game.cards_processor.get_cards_for(COLOR.WHITE) == []
    assert game.current_turn == COLOR.BLACK
    assert game.turns_started[COLOR.BLACK] == 1


def test_teleport_swaps_selected_piece_with_occupied_square(monkeypatch):
    """Sprawdza zamianę dwóch figur i zużycie karty teleportacji."""
    game = make_game(EnchantmentCardType.PIECE_TELEPORT)
    first = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)
    second = Piece(COLOR.BLACK, PIECE_TYPE.BISHOP)
    game.pieces_locations[1] = first
    game.pieces_locations[2] = second

    click_board(game, 1, monkeypatch)
    click_board(game, 2, monkeypatch)

    assert game.pieces_locations[1].get_type() == PIECE_TYPE.BISHOP
    assert game.pieces_locations[2].get_type() == PIECE_TYPE.KNIGHT
    assert game.cards_processor.get_cards_for(COLOR.WHITE) == []
    assert game.current_turn == COLOR.BLACK


def test_return_to_start_moves_piece_to_an_empty_original_square(monkeypatch):
    """Sprawdza powrót figury na wolne pole startowe."""
    game = make_game(EnchantmentCardType.RETURN_TO_START, uses=1)
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK, starting_position=1)
    game.pieces_locations[20] = rook

    click_board(game, 20, monkeypatch)
    click_board(game, 1, monkeypatch)

    assert game.pieces_locations[1].get_type() == PIECE_TYPE.ROOK
    assert not game.pieces_locations[20].exists()
    assert game.current_turn == COLOR.BLACK


def test_delayed_passive_card_is_scheduled_and_consumed(monkeypatch):
    """Sprawdza zaplanowanie pasywnego efektu i zużycie jego karty."""
    game = make_game(EnchantmentCardType.PAWN_DETONATION_DELAYED_1)
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    game.pieces_locations[9] = pawn

    click_board(game, 9, monkeypatch)

    delayed_pawn = game.pieces_locations[9]
    assert delayed_pawn.get_delayed_enchantments_ready_at(1) == []
    due_effects = delayed_pawn.get_delayed_enchantments_ready_at(2)
    assert len(due_effects) == 1
    assert due_effects[0].get_card_type() == EnchantmentCardType.PAWN_DETONATION_DELAYED_1
    assert game.cards_processor.get_cards_for(COLOR.WHITE) == []
    assert game.current_turn == COLOR.BLACK


def test_resurrection_places_captured_piece_next_to_king(monkeypatch):
    """Sprawdza wybór zbitej figury i jej wskrzeszenie przy królu."""
    game = make_game(EnchantmentCardType.KING_PAWN_RESURRECTION)
    game.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.KING)
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    game.capture_processor.captured_black.append(pawn)
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.input_processor.get_clicked_chessboard_field_id",
        lambda: None,
    )
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.input_processor.get_clicked_captured_piece_index",
        lambda: (COLOR.BLACK, 0),
    )

    game.process_player_turn()

    assert game.selected_captured_piece == (COLOR.BLACK, 0)
    assert 2 in game.resurrection_moves
    click_board(game, 2, monkeypatch)

    assert game.pieces_locations[2].get_type() == PIECE_TYPE.PAWN
    assert game.capture_processor.captured_black == []
    assert game.cards_processor.get_cards_for(COLOR.WHITE) == []
    assert game.current_turn == COLOR.BLACK


def test_double_move_keeps_turn_open_between_moves(monkeypatch):
    """Sprawdza, że pierwszy ruch karty podwójnego ruchu nie kończy tury."""
    game = make_game(EnchantmentCardType.PIECE_DOUBLE_MOVE, uses=2)
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    game.pieces_locations[1] = rook
    click_board(game, 1, monkeypatch)
    click_board(game, 9, monkeypatch)

    assert game.double_move_step == 1
    assert game.selected_piece_position == 9
    assert game.current_turn == COLOR.WHITE

    click_board(game, 10, monkeypatch)

    assert game.pieces_locations[10].get_type() == PIECE_TYPE.ROOK
    assert game.current_turn == COLOR.BLACK


def test_rook_throw_captures_every_piece_on_route():
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

    assert game.pieces_locations[8].get_type() == PIECE_TYPE.ROOK
    assert not game.pieces_locations[1].exists()
    assert not game.pieces_locations[3].exists()
    assert not game.pieces_locations[5].exists()
    assert [piece.get_type() for piece in game.capture_processor.captured] == [
        PIECE_TYPE.PAWN,
        PIECE_TYPE.PAWN,
    ]


def test_move_collects_board_card_and_schedules_the_next_one():
    """Sprawdza dodanie karty z pola docelowego i zaplanowanie kolejnej."""
    game = make_game()
    game.board_card_available = True
    game.board_card_position = 2
    game.board_enchantment = EnchantmentCardType.PIECE_TELEPORT.create()
    rook = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    game.pieces_locations[1] = rook
    game.selected_piece_position = 1

    game.move_piece(2)

    assert [
        card.get_card_type()
        for card in game.cards_processor.get_cards_for(COLOR.WHITE)
    ] == [EnchantmentCardType.PIECE_TELEPORT]
    assert game.current_turn == COLOR.BLACK
    assert game.board_card_available or game.pending_board_card_delay is not None


def test_ai_turn_receives_hidden_hand_count_and_applies_legal_action():
    game = make_game()
    game.current_turn = COLOR.BLACK
    game.cards_processor.add_card_for(
        COLOR.WHITE, EnchantmentCardType.PAWN_SWORDSMAN.create())
    game.pieces_locations[57] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state = GameState.from_game(game)
    action = next(
        action for action in GameSimulation.available_actions(state)
        if action.action_type == GameActionType.MOVE
    )

    class StubAI:
        def choose_action(self, observation):
            self.observation = observation
            return SimpleNamespace(action=action)

    game.black_ai = StubAI()
    game.play_ai_turn()
    game._ai_future.result(timeout=1)
    assert game.is_ai_thinking
    game.play_ai_turn()

    assert game.black_ai.observation.own_color == COLOR.BLACK
    assert game.black_ai.observation.opponent_card_count == 1
    assert not hasattr(game.black_ai.observation, "white_cards")
    assert game.current_turn == COLOR.WHITE
    assert game.pieces_locations[action.destination].get_color() == COLOR.BLACK
