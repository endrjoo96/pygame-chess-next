import random
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import POS, id_to_xy
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from logic.stage.action_animation import ActionAnimation, PieceMotion
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

    def reset_decks(self):
        for deck in self.decks.values():
            deck.clear()


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

    def get_winner(self):
        return None


def make_game(card_type=None, uses=None):
    """Tworzy minimalny stan gry z atrapami procesorów dla testów logiki."""
    cards = []
    if card_type is not None:
        cards.append(card_type.create(uses=uses))

    game = GameLogicLoop.__new__(GameLogicLoop)
    game.black_ai = None
    game.seed = 23
    game.current_turn = COLOR.WHITE
    game.selected_piece_position = 0
    game.moves = []
    game.resurrection_moves = []
    game.pending_promotion_actions = None
    game.selected_card = (COLOR.WHITE, 0) if cards else None
    game.selected_captured_piece = None
    game.selected_trebuchet_pawn_position = 0
    game.double_move_step = 0
    game.double_move_collected_board_card = False
    game.pieces_locations = {position: Piece() for position in range(1, 65)}
    game.capture_processor = FakeCaptureProcessor()
    game.cards_processor = FakeCardsProcessor(cards)
    game.turns_started = {COLOR.WHITE: 1, COLOR.BLACK: 0}
    game.board_card_available = False
    game.board_card_position = 36
    game.board_enchantment = None
    game.board_cards = []
    game.rune_traps = []
    game.pending_board_card_delay = None
    game.en_passant_target = None
    game.en_passant_targets = []
    game._ai_executor = ThreadPoolExecutor(max_workers=1)
    game._ai_future = None
    game._ai_best_move = None
    game._ai_best_move_from_learning = None
    game._ai_searching = False
    game._ai_final_result = None
    game._ai_final_move_from_learning = None
    game._ai_progress_lock = Lock()
    game._ai_generation = 0
    game._ai_active_generation = None
    game._ponder_future = None
    game._ponder_cancel_event = Event()
    game._action_animation = None
    game._applying_network_action = False
    game._network_action_pending = False
    game._position_evaluation = 0.0
    game._position_evaluation_stale = True
    game.rng = random.Random(23)
    return game


def test_player_can_apply_buff_and_select_its_new_piece_move():
    game = make_game(EnchantmentCardType.PAWN_SWORDSMAN)
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    source = 28
    game.pieces_locations[source] = pawn

    game._GameLogicLoop__select_piece_for_movement(source, pawn)

    assert game.current_turn == COLOR.WHITE
    assert game.cards_processor.white_cards == []
    buffed_pawn = game.pieces_locations[source]
    assert buffed_pawn.has_passive_enchantment()
    assert game.selected_card is None

    game._GameLogicLoop__select_piece_for_movement(source, buffed_pawn)

    source_x, source_y = id_to_xy(source)
    assert [source_x - 1, source_y] in game.moves
    assert [source_x + 1, source_y] in game.moves
    game._ai_executor.shutdown(wait=True)


def test_position_evaluation_is_cached_and_refreshed_after_action(monkeypatch):
    game = make_game()
    game.pieces_locations[POS.E1.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.KING)
    game.pieces_locations[POS.E8.value] = Piece(
        COLOR.BLACK, PIECE_TYPE.KING)
    game.pieces_locations[POS.E2.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.PAWN)
    score_values = iter((1.25, -0.75))
    evaluated_states = []

    def evaluate(evaluated_state):
        evaluated_states.append(evaluated_state.cache_key())
        return next(score_values)

    monkeypatch.setattr(
        "logic.chess_ai.ChessAI.evaluate", evaluate)

    assert game.position_evaluation == -1.25
    assert game.position_evaluation == -1.25
    assert len(evaluated_states) == 1

    state = GameState.from_game(game)
    action = next(
        action
        for action in GameSimulation.available_actions(state)
        if (
            action.action_type == GameActionType.MOVE
            and action.source == POS.E2.value
        )
    )
    game._GameLogicLoop__apply_domain_action(action)

    assert game.position_evaluation == 0.75
    assert len(evaluated_states) == 2


def test_position_evaluation_cache_is_invalidated_by_reset(monkeypatch):
    game = make_game()
    scores = iter((1.0, 2.0))
    monkeypatch.setattr(
        "logic.chess_ai.ChessAI.evaluate",
        lambda state: next(scores),
    )
    monkeypatch.setattr(
        game, "_GameLogicLoop__schedule_next_board_card", lambda: None)

    assert game.position_evaluation == -1.0
    game.reset()

    assert game._position_evaluation_stale
    assert game.position_evaluation == -2.0
    game._ai_executor.shutdown(wait=True)


def test_reset_uses_the_shared_simulation_initial_state():
    game = make_game()
    game.seed = 1789

    game.reset()

    assert GameState.from_game(game).cache_key() == (
        GameSimulation.create_initial_state(1789).cache_key()
    )
    game._ai_executor.shutdown(wait=True)


def test_domain_action_starts_a_piece_animation_when_configured(monkeypatch):
    game = make_game()
    game.pieces_locations[POS.E1.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.KING)
    game.pieces_locations[POS.E8.value] = Piece(
        COLOR.BLACK, PIECE_TYPE.KING)
    game.pieces_locations[POS.E2.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.PAWN)
    game.context = SimpleNamespace(
        chessboard_coordinates=[
            [(x * 80, y * 80) for y in range(8)]
            for x in range(8)
        ],
    )
    game.chess_pieces = object()
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.UI_ACTION_ANIMATION_DURATION_MS", 300)
    monkeypatch.setattr(
        "logic.stage.action_animation.pygame.time.get_ticks", lambda: 0)
    state = GameState.from_game(game)
    action = next(
        action
        for action in GameSimulation.available_actions(state)
        if (
            action.action_type == GameActionType.MOVE
            and action.source == POS.E2.value
        )
    )

    game._GameLogicLoop__apply_domain_action(action)

    assert game._action_animation is not None
    assert game._action_animation.duration_ms == 300
    assert game._action_animation.hidden_piece_positions() == (
        action.destination,)


def test_player_input_is_blocked_while_action_animation_is_active(monkeypatch):
    game = make_game()
    monkeypatch.setattr(
        "logic.stage.action_animation.pygame.time.get_ticks", lambda: 100)
    game._action_animation = ActionAnimation(
        300,
        (PieceMotion("white_pawn", (0, 0), (80, 0), POS.A1.value),),
        started_at=0,
    )
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.input_processor.get_clicked_chessboard_field_id",
        lambda: (_ for _ in ()).throw(AssertionError("input should be blocked")),
    )

    game.process_player_turn()


def test_ai_thinking_overlay_keeps_translucent_black_background(monkeypatch):
    import pygame

    game = GameLogicLoop.__new__(GameLogicLoop)
    game.screen = pygame.Surface((160, 120))
    game.context = SimpleNamespace(comic_sans_font=None)
    game.screen.fill((0, 0, 0))
    game.screen.set_at((5, 5), (255, 0, 0))
    game.screen.set_at((6, 5), (0, 255, 0))

    class FakeFont:
        @staticmethod
        def render(_text, _antialias, _color):
            return pygame.Surface((80, 20), pygame.SRCALPHA)

    monkeypatch.setattr(
        "logic.stage.game_logic_loop.SysFont",
        lambda *_args, **_kwargs: FakeFont(),
    )

    game.draw_ai_thinking_overlay()
    red_pixel = game.screen.get_at((5, 5))
    green_pixel = game.screen.get_at((6, 5))

    assert red_pixel.r > 0
    assert red_pixel.g == 0
    assert green_pixel.r == 0
    assert green_pixel.g > 0


def click_board(game, position, monkeypatch):
    """Przetwarza kliknięcie wskazanego pola planszy."""
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.input_processor.get_clicked_chessboard_field_id",
        lambda: position,
    )
    game.process_player_turn()


def test_player_selection_highlights_en_passant_and_castling_moves():
    game = make_game()
    game.current_turn = COLOR.BLACK
    game.en_passant_target = POS.E3.value
    game.pieces_locations[POS.D4.value] = Piece(
        COLOR.BLACK, PIECE_TYPE.PAWN, POS.D7.value)
    game.pieces_locations[POS.D4.value].set_has_moved()
    game.pieces_locations[POS.E4.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.PAWN, POS.E2.value)

    game._GameLogicLoop__select_piece_for_movement(
        POS.D4.value, game.pieces_locations[POS.D4.value])

    assert id_to_xy(POS.E3.value) in game.moves

    castling_game = make_game()
    castling_game.pieces_locations[POS.E1.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.KING, POS.E1.value)
    castling_game.pieces_locations[POS.A1.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.ROOK, POS.A1.value)
    castling_game.pieces_locations[POS.H1.value] = Piece(
        COLOR.WHITE, PIECE_TYPE.ROOK, POS.H1.value)

    castling_game._GameLogicLoop__select_piece_for_movement(
        POS.E1.value, castling_game.pieces_locations[POS.E1.value])

    assert id_to_xy(POS.C1.value) in castling_game.moves
    assert id_to_xy(POS.G1.value) in castling_game.moves
    game._ai_executor.shutdown(wait=True)
    castling_game._ai_executor.shutdown(wait=True)


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


def test_pawn_move_to_final_rank_opens_promotion_popup_and_applies_choice(monkeypatch):
    game = make_game()
    game.screen = SimpleNamespace(
        get_width=lambda: 1240,
        get_height=lambda: 880,
    )
    pawn = Piece(COLOR.WHITE, PIECE_TYPE.PAWN, POS.A7.value)
    game.pieces_locations[POS.A7.value] = pawn

    game._GameLogicLoop__select_piece_for_movement(POS.A7.value, pawn)
    click_board(game, POS.A8.value, monkeypatch)

    assert game.pending_promotion_actions is not None
    assert game.pieces_locations[POS.A7.value] is pawn
    assert {
        action.promotion_type for action in game.pending_promotion_actions
    } == {
        PIECE_TYPE.QUEEN,
        PIECE_TYPE.ROOK,
        PIECE_TYPE.BISHOP,
        PIECE_TYPE.KNIGHT,
    }

    _, buttons = game._GameLogicLoop__get_promotion_popup_layout()
    selected_button = next(
        button for action, button in buttons
        if action.promotion_type == PIECE_TYPE.ROOK
    )
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.utils.left_click_event", lambda: True)
    monkeypatch.setattr(
        "logic.stage.game_logic_loop.utils.get_mouse_event",
        lambda: selected_button.center,
    )
    game.process_player_turn()

    assert game.pending_promotion_actions is None
    assert game.pieces_locations[POS.A8.value].get_type() == PIECE_TYPE.ROOK
    assert game.current_turn == COLOR.BLACK


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
    board_card = EnchantmentCardType.PIECE_TELEPORT.create()
    game.board_cards = [(2, board_card)]
    game.board_card_available = True
    game.board_card_position = 2
    game.board_enchantment = board_card
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
    assert [
        card.get_card_type()
        for card in game.cards_processor.get_cards_for(COLOR.WHITE)
    ] == [EnchantmentCardType.PIECE_TELEPORT]
    assert game.board_cards == []
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


def test_ai_turn_receives_both_hands_and_applies_legal_action():
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
        def choose_action(self, observation, candidate_callback=None):
            self.observation = observation
            if candidate_callback is not None:
                candidate_callback(action, 1, 2.5)
            return SimpleNamespace(
                action=action,
                score=2.5,
                completed_depth=1,
                visited_nodes=1,
            )

    game.black_ai = StubAI()
    game.play_ai_turn()
    game._ai_future.result(timeout=1)
    assert game.is_ai_thinking
    assert game._ai_best_move == ("Wb8", 1, 2.5)
    assert game.ai_search_stats.is_searching
    assert game.ai_search_stats.candidate_move == "Wb8"
    assert game.ai_search_stats.candidate_score == 2.5
    assert game.ai_search_stats.candidate_depth == 1
    assert game.ai_search_stats.candidate_move_from_learning_database is None
    game.play_ai_turn()

    assert game.black_ai.observation.own_color == COLOR.BLACK
    assert len(game.black_ai.observation.opponent_cards) == 1
    assert (
        game.black_ai.observation.opponent_cards[0].get_card_type()
        == EnchantmentCardType.PAWN_SWORDSMAN
    )
    assert not hasattr(game.black_ai.observation, "white_cards")
    assert game.current_turn == COLOR.WHITE
    assert game.pieces_locations[action.destination].get_color() == COLOR.BLACK
    assert not game.ai_search_stats.is_searching
    assert game.ai_search_stats.final_move == "Wb8"
    assert game.ai_search_stats.final_score == 2.5
    assert game.ai_search_stats.completed_depth == 1
    assert game.ai_search_stats.visited_nodes == 1
    assert game.ai_search_stats.final_move_from_learning_database is None


def test_ai_search_stats_include_cache_and_individual_worker_states(tmp_path):
    from logic.chess_ai import ChessAI, SearchConfig
    from logic.search_cache import Bound, CacheEntry

    game = make_game()
    database_path = tmp_path / "move-learning.sqlite3"
    database_path.write_bytes(b"abc")
    game.black_ai = ChessAI(
        SearchConfig(
            cache_enabled=True,
            cache_max_entries=4,
            learning_max_file_size_bytes=32 * 1024,
        ),
        max_workers=1,
        initialize_move_learning=False,
    )
    game.black_ai._learning_database_path = database_path
    game.black_ai._cache.put(
        CacheEntry(("diagnostic",), 3, None, 1.0, Bound.EXACT))
    game.black_ai._begin_search_progress("pondering")
    game.black_ai._set_current_search_depth(4)
    game.black_ai._set_completed_search_depth(3)
    game.black_ai._add_completed_nodes(900)
    game.black_ai._begin_ponder_progress(12)
    game.black_ai._record_ponder_progress(
        white_actions_completed=4,
        branches_generated=7,
        root_actions_completed=8,
        root_actions_discovered=10,
    )
    game.black_ai._set_ponder_depth_progress([0, 2, 2])
    game.black_ai._set_dangerous_white_candidates((
        (
            GameAction(GameActionType.MOVE, POS.E2.value, POS.E4.value),
            -1.25,
            2,
        ),
    ))

    stats = game.ai_search_stats

    assert stats.cache_enabled
    assert stats.cache_entries == 1
    assert stats.cache_deepest_entry_depth == 3
    assert stats.cache_limit == 4
    assert stats.cache_evictions == 0
    assert stats.learning_database_size_bytes == 3
    assert stats.learning_database_limit_bytes == 32 * 1024
    assert len(stats.workers) == 1
    assert stats.workers[0].is_local
    assert stats.workers[0].state == "idle"
    assert stats.search_phase == "pondering"
    assert stats.current_depth == 4
    assert stats.completed_search_depth == 3
    assert stats.live_visited_nodes == 900
    assert stats.ponder_white_actions_completed == 4
    assert stats.ponder_white_actions_total == 12
    assert stats.ponder_branches_generated == 7
    assert stats.ponder_root_actions_completed == 8
    assert stats.ponder_root_actions_discovered == 10
    assert stats.ponder_depth_counts == ((0, 1), (2, 2))
    assert stats.ponder_max_branch_depth == 2
    assert stats.ponder_dangerous_white_candidates == (
        ("e2-e4", -1.25, 2),
    )


def test_ai_starts_pondering_after_its_move():
    from logic.chess_ai import ChessAI, PonderResult

    class StubAI(ChessAI):
        def __init__(self):
            super().__init__(max_workers=1, ponder_cpu_worker_usage=50)

        def ponder(self, state, cancellation_event):
            self.pondered_state = state
            return PonderResult(1, 1, 2, "max-depth")

    game = make_game()
    game.black_ai = StubAI()

    game._start_pondering()
    result = game._ponder_future.result(timeout=1)
    game._reap_pondering()

    assert result.stopped_reason == "max-depth"
    assert game.black_ai.pondered_state.current_turn == COLOR.WHITE
    assert game._ponder_future is None
    game._ai_executor.shutdown(wait=True)


def test_ai_can_disable_pondering():
    from logic.chess_ai import ChessAI

    game = make_game()
    game.black_ai = ChessAI(max_workers=1, ponder_enabled=False)

    game._start_pondering()

    assert game._ponder_future is None
    game._ai_executor.shutdown(wait=True)


def test_completed_white_action_cancels_active_pondering():
    from concurrent.futures import Future
    from logic.chess_ai import ChessAI

    class StubAI(ChessAI):
        def __init__(self):
            super().__init__(max_workers=1)
            self.cancelled = False

        def cancel_ponder(self):
            self.cancelled = True

    game = make_game()
    game.black_ai = StubAI()
    game._ponder_future = Future()
    game.pieces_locations[9] = Piece(COLOR.WHITE, PIECE_TYPE.PAWN)
    state = GameState.from_game(game)
    action = next(
        candidate
        for candidate in GameSimulation.available_actions(state)
        if candidate.action_type == GameActionType.MOVE
    )

    game._GameLogicLoop__apply_domain_action(action)

    assert game.current_turn == COLOR.BLACK
    assert game._ponder_cancel_event.is_set()
    assert game.black_ai.cancelled
    assert game._ponder_future is None
    game._ai_executor.shutdown(wait=True)


def test_reset_clears_search_cache_and_invalidates_active_generation(monkeypatch):
    from logic.chess_ai import ChessAI, SearchConfig
    from logic.search_cache import Bound, CacheEntry

    game = make_game()
    game.seed = 23
    game.black_ai = ChessAI(SearchConfig(cache_max_entries=8), max_workers=1)
    game._ai_best_move = ("Wb8", 2, 1.5)
    game._ai_searching = True
    game._ai_final_result = ("Wb8", 2, 1.5, 24)
    game.black_ai._cache.put(CacheEntry(("old",), 1, None, 1.0, Bound.EXACT))
    old_generation = game.black_ai.search_cache_generation()
    monkeypatch.setattr(game.cards_processor, "reset_decks", lambda: None, raising=False)
    monkeypatch.setattr(game, "_GameLogicLoop__schedule_next_board_card", lambda: None)

    game.reset()

    assert len(game.black_ai._cache) == 0
    assert game.black_ai.search_cache_generation() != old_generation
    assert not game.ai_search_stats.is_searching
    assert game.ai_search_stats.candidate_move is None
    assert game.ai_search_stats.final_move is None


def test_ai_move_notation_uses_polish_piece_symbol_and_capture_marker():
    game = make_game()
    game.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    game.pieces_locations[9] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)
    state = GameState.from_game(game)
    action = GameAction(GameActionType.MOVE, 1, 9)

    assert GameLogicLoop._format_ai_action_notation(state, action) == "Wxa2"


def test_board_card_countdown_places_another_card_while_one_is_available(monkeypatch):
    from utils.run_config import RunMode
    import logic.stage.game_logic_loop as game_logic_loop

    monkeypatch.setattr(game_logic_loop, "RUN_MODE", RunMode.PROD)
    game = make_game()
    game.rng = SimpleNamespace(
        choice=lambda positions: positions[0],
        randint=lambda minimum, maximum: 3,
    )
    monkeypatch.setattr(
        game_logic_loop.EnchantmentCardType,
        "create_random",
        staticmethod(lambda rng: EnchantmentCardType.PIECE_TELEPORT.create()),
    )
    game.pieces_locations[1] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    game._GameLogicLoop__place_next_board_card()
    assert game.pending_board_card_delay == 3

    game._GameLogicLoop__finish_piece_move(
        game.pieces_locations[1], 1, 2, False, False)

    assert game.board_card_available
    assert game.pending_board_card_delay == 2

    game._GameLogicLoop__finish_piece_move(
        game.pieces_locations[1], 1, 2, False, False)
    game._GameLogicLoop__finish_piece_move(
        game.pieces_locations[1], 1, 2, False, False)

    assert game.board_card_available
    assert game.pending_board_card_delay == 3
    assert len(game.board_cards) == 2


def test_player_can_place_rune_by_selecting_a_knight_and_empty_square():
    game = make_game(EnchantmentCardType.KNIGHT_RUNIC_TRAP)
    knight_position = POS.E4.value
    trap_position = POS.D4.value
    game.pieces_locations[knight_position] = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)

    game._GameLogicLoop__handle_board_click(knight_position)
    assert game.selected_piece_position == knight_position
    assert [3, 4] in game.moves

    game._GameLogicLoop__handle_board_click(trap_position)

    assert [trap.position for trap in game.rune_traps] == [trap_position]
    assert game.rune_traps[0].caster_position == knight_position
    assert game.current_turn == COLOR.BLACK
    assert game.cards_processor.white_cards == []


def test_player_can_fire_trebuchet_with_three_board_clicks():
    game = make_game(EnchantmentCardType.ROOK_TREBUCHET, uses=2)
    rook_position = POS.E4.value
    pawn_position = POS.D4.value
    destination = POS.H6.value
    game.pieces_locations[rook_position] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    game.pieces_locations[pawn_position] = Piece(COLOR.BLACK, PIECE_TYPE.PAWN)

    game._GameLogicLoop__handle_board_click(rook_position)
    assert game.selected_piece_position == rook_position
    game._GameLogicLoop__handle_board_click(pawn_position)
    assert game.selected_trebuchet_pawn_position == pawn_position
    game._GameLogicLoop__handle_board_click(destination)

    assert game.pieces_locations[destination].get_color() == COLOR.BLACK
    assert game.pieces_locations[destination].get_type() == PIECE_TYPE.PAWN
    assert game.pieces_locations[rook_position].is_stunned()
    assert game.cards_processor.white_cards[0].get_remaining_uses() == 1
    assert game.current_turn == COLOR.BLACK


def test_player_can_recruit_a_pawn_on_the_home_rank():
    game = make_game(EnchantmentCardType.RECRUIT_PAWN, uses=2)
    destination = POS.A1.value

    game._GameLogicLoop__handle_board_click(destination)

    assert game.pieces_locations[destination].get_color() == COLOR.WHITE
    assert game.pieces_locations[destination].get_type() == PIECE_TYPE.PAWN
    assert game.cards_processor.white_cards[0].get_remaining_uses() == 1
    assert game.current_turn == COLOR.BLACK


def test_network_game_waits_for_server_before_applying_local_action(monkeypatch):
    import logic.stage.game_logic_loop as game_logic_loop

    monkeypatch.setattr(game_logic_loop, "UI_ACTION_ANIMATION_DURATION_MS", 0)
    sent_actions = []
    game = make_game()
    game.local_player_color = COLOR.WHITE
    game.action_callback = sent_actions.append
    game.pieces_locations[POS.A1.value] = Piece(COLOR.WHITE, PIECE_TYPE.ROOK)
    action = GameAction(GameActionType.MOVE, POS.A1.value, POS.B1.value)

    game._GameLogicLoop__apply_domain_action(action)

    assert sent_actions == [action]
    assert game.current_turn is COLOR.WHITE
    assert game.pieces_locations[POS.A1.value].get_type() is PIECE_TYPE.ROOK
    assert not game.pieces_locations[POS.B1.value].exists()
    assert game._network_action_pending

    game.apply_authoritative_action(action)

    assert game.current_turn is COLOR.BLACK
    assert not game.pieces_locations[POS.A1.value].exists()
    assert game.pieces_locations[POS.B1.value].get_color() is COLOR.WHITE
    assert not game._network_action_pending


def test_network_game_applies_peer_actions_without_echoing_them(monkeypatch):
    import logic.stage.game_logic_loop as game_logic_loop

    monkeypatch.setattr(game_logic_loop, "UI_ACTION_ANIMATION_DURATION_MS", 0)
    sent_actions = []
    game = make_game()
    game.local_player_color = COLOR.WHITE
    game.action_callback = sent_actions.append
    game.current_turn = COLOR.BLACK
    game.pieces_locations[POS.H8.value] = Piece(COLOR.BLACK, PIECE_TYPE.ROOK)
    state = GameState.from_game(game)
    action = next(
        action
        for action in GameSimulation.available_actions(state)
        if action.action_type == GameActionType.MOVE
    )

    game.apply_network_action(action)

    assert game.current_turn is COLOR.WHITE
    assert not game.pieces_locations[action.source].exists()
    assert game.pieces_locations[action.destination].get_color() is COLOR.BLACK
    assert sent_actions == []


def test_network_game_rejects_peer_action_during_local_turn():
    game = make_game()
    game.local_player_color = COLOR.WHITE

    try:
        game.apply_network_action(GameAction(GameActionType.MOVE, 1, 2))
    except ValueError as error:
        assert "local player's turn" in str(error)
    else:
        raise AssertionError("A peer action was accepted during the local turn")


def test_network_game_can_reject_pending_action_without_changing_position():
    game = make_game()
    game.local_player_color = COLOR.WHITE
    game._network_action_pending = True
    game.selected_piece_position = POS.A1.value
    game.moves = [(0, 1)]

    game.reject_pending_network_action()

    assert not game._network_action_pending
    assert game.selected_piece_position == 0
    assert game.moves == []
