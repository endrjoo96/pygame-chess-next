import math
import random
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from threading import Event, Lock
from typing import Optional

import pygame
from pygame import Surface
from pygame.font import SysFont

from constants.pos import id_to_xy, xy_to_id, POS
from constants.piece_type import PIECE_TYPE
from constants.predefined_colors import PREDEFINED_COLOR
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from logic.stage.action_animation import ActionAnimation
from models.game_state import GameState
from models.chess_pieces import Piece, COLOR
from models.enchantment_cards import EnchantmentCardType
from models.starting_positions import pieces_starting_positions_map
from piecesprite import PieceSprite
from processors import input_processor
from processors.capturing_piece_processor import CaptureProcessor
from processors.cards_processor import CardsProcessor
from processors.movement_processor import process_possible_basic_moves
from utils import utils
from utils.gamecontext import GameContext
from utils.logging import log_debug, log_error, log_info, log_logic, log_warn
from utils.run_config import (
    LOG_LEVEL,
    RUN_MODE,
    RunMode,
    UI_ACTION_ANIMATION_DURATION_MS,
    resolve_game_seed,
)

class GameLogicLoop(object):
    def __init__(
        self, screen: Surface, black_ai=None, seed=None, *,
        local_player_color=None, action_callback=None,
    ):
        """Tworzy stan rozgrywki, procesory i zasoby wizualne dla powierzchni ekranu."""
        if local_player_color is not None and black_ai is not None:
            raise ValueError("Network games cannot use an AI opponent")
        self.context = GameContext()
        # display surface
        self.screen = screen
        self.black_ai = black_ai
        self.local_player_color = local_player_color
        self.action_callback = action_callback
        self._applying_network_action = False
        self._network_action_pending = False
        self.seed = resolve_game_seed() if seed is None else seed
        self.rng = random.Random(self.seed)
        self._ai_executor = (
            ThreadPoolExecutor(max_workers=1) if black_ai is not None else None
        )
        self._ai_future: Optional[Future] = None
        self._ai_best_move = None
        self._ai_best_move_from_learning = None
        self._ai_searching = False
        self._ai_final_result = None
        self._ai_final_move_from_learning = None
        self._ai_progress_lock = Lock()
        self._ai_generation = 0
        self._ai_active_generation = None
        self._ponder_future: Optional[Future] = None
        self._ponder_cancel_event = Event()
        self._action_animation: Optional[ActionAnimation] = None
        self._position_evaluation = 0.0
        self._position_evaluation_stale = True
        # create an object of class to show chess pieces on the board
        self.chess_pieces = PieceSprite(self.context.pieces_src, cols=6, rows=2)
        passive_icon = pygame.image.load(self.context.card_mod_passive_src).convert_alpha()
        self.passive_icon = pygame.transform.scale(passive_icon, (16, 16))
        delay_icon = pygame.image.load(self.context.card_mod_delay_src).convert_alpha()
        self.delay_icon = pygame.transform.scale(delay_icon, (16, 16))
        stun_icon = pygame.image.load(self.context.card_mod_stun_src).convert_alpha()
        self.stun_icon = pygame.transform.scale(stun_icon, (16, 16))
        # dictionary to keeping track of player turn
        self.current_turn = COLOR.WHITE

        # Selected piece position
        self.selected_piece_position: int = 0
        # list containing possible moves for the selected piece
        self.moves = []
        self.resurrection_moves = []
        self.selected_card = None
        self.selected_captured_piece = None
        self.selected_trebuchet_pawn_position = 0
        self.double_move_step = 0
        self.double_move_collected_board_card = False

        # field_id: PIECE
        self.pieces_locations = {}

        # list containing captured pieces
        self.capture_processor = CaptureProcessor()
        self.cards_processor = CardsProcessor(screen, self.rng)
        self.board_card_position = POS.D5.value
        self.board_card_available = False
        self.board_enchantment = None
        self.board_cards = []
        self.rune_traps = []
        self.pending_board_card_delay = None
        self.en_passant_target = None
        self.en_passant_targets = []
        card_image = pygame.image.load(self.context.card_on_board_src).convert_alpha()
        self.board_card_image = pygame.transform.scale(
            card_image, (self.context.square_length, self.context.square_length))

        self.reset()

    @property
    def position_evaluation(self) -> float:
        """Zwraca ocenę bieżącej pozycji w perspektywie białych."""
        if self._position_evaluation_stale:
            self._position_evaluation = -self._chess_ai_class().evaluate(
                GameState.from_game(self))
            self._position_evaluation_stale = False
        return self._position_evaluation

    @staticmethod
    def _chess_ai_class():
        return __import__(
            "logic.chess_ai", fromlist=["ChessAI"]).ChessAI

    @classmethod
    def _is_chess_ai(cls, candidate):
        return candidate is not None and isinstance(
            candidate, cls._chess_ai_class())

    @property
    def is_action_animation_active(self) -> bool:
        if self._action_animation is None:
            return False
        if self._action_animation.is_active:
            return True
        self._action_animation = None
        return False

    def reset(self):
        """Przywraca planszę, talie i liczniki do stanu początkowego nowej partii."""
        self._cancel_pondering()
        self._action_animation = None
        self._network_action_pending = False
        self._position_evaluation_stale = True
        log_info(
            "Initializing game state: seed={}, mode={}, log_level={}, black_ai={}".format(
                self.seed,
                RUN_MODE.value,
                LOG_LEVEL.name,
                self.black_ai is not None,
            )
        )
        # clear moves lists
        self.current_turn = COLOR.WHITE
        self.turns_started = {COLOR.WHITE: 1, COLOR.BLACK: 0}
        self.moves = []
        self.resurrection_moves = []
        self.pending_promotion_actions = None
        self.selected_piece_position = 0
        self.selected_card = None
        self.selected_captured_piece = None
        self.selected_trebuchet_pawn_position = 0
        self.double_move_step = 0
        self.double_move_collected_board_card = False
        self.board_card_available = False
        self.board_card_position = POS.D5.value
        self.board_enchantment = None
        self.board_cards = []
        self.rune_traps = []
        self.pending_board_card_delay = None
        self.en_passant_target = None
        self.en_passant_targets = []
        if self._ai_future is not None:
            self._ai_future.cancel()
            self._ai_future = None
        if self._is_chess_ai(self.black_ai):
            self.black_ai.clear_search_cache()
        with self._ai_progress_lock:
            self._ai_generation += 1
            self._ai_active_generation = None
            self._ai_best_move = None
            self._ai_best_move_from_learning = None
            self._ai_searching = False
            self._ai_final_result = None
            self._ai_final_move_from_learning = None
        self.capture_processor.reset()
        self.cards_processor.reset_decks()

        initial_state = GameSimulation.create_initial_state(self.seed)
        self.pieces_locations = initial_state.pieces_locations
        self.current_turn = initial_state.current_turn
        self.turns_started = initial_state.turns_started
        self.board_card_available = initial_state.board_card_available
        self.board_card_position = initial_state.board_card_position
        self.board_enchantment = initial_state.board_enchantment
        self.board_cards = initial_state.board_cards
        self.rune_traps = initial_state.rune_traps
        self.pending_board_card_delay = initial_state.pending_board_card_delay
        self.en_passant_target = initial_state.en_passant_target
        self.en_passant_targets = initial_state.en_passant_targets
        self.selected_card = initial_state.selected_card
        self.selected_piece_position = initial_state.selected_piece_position
        self.selected_captured_piece = initial_state.selected_captured_piece
        self.double_move_step = initial_state.double_move_step
        self.double_move_collected_board_card = (
            initial_state.double_move_collected_board_card)
        self.resurrection_moves = initial_state.resurrection_moves
        self.rng.setstate(initial_state.random_state)

    def close(self):
        """Kończy wyszukiwanie i zamyka zasoby AI przy zamykaniu aplikacji."""
        self._cancel_pondering()
        if self._ai_future is not None and not self._ai_future.done():
            self._ai_future.cancel()
        if self._ponder_future is not None and self._ponder_future.done():
            self._reap_pondering()
        if self._ai_executor is not None:
            self._ai_executor.shutdown(wait=True, cancel_futures=True)
        self._reap_pondering()
        if self._ai_future is not None:
            try:
                self._ai_future.result()
            except CancelledError:
                pass
            except Exception as error:
                log_error("AI search failed during shutdown: {}".format(error))
        if self._is_chess_ai(self.black_ai):
            self.black_ai.close()

    def play_turn(self):
        """Rysuje informacje o turze, obsługuje jej wejście i zwraca zwycięzcę, jeśli jest."""
        self._reap_pondering()
        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        small_font = SysFont(self.context.comic_sans_font, 20)
        # create text to be shown on the game menu
        rendered_text = small_font.render("Turn: " + self.current_turn.value, True, white_color)
        # show welcome text
        self.screen.blit(rendered_text, ((self.screen.get_width() - rendered_text.get_width()) // 2,
                                         self.context.board_offset_y - rendered_text.get_height() - 5))
        self.print_annotations()
        winner = self.capture_processor.get_winner()
        if winner is None:
            if self.current_turn == COLOR.BLACK and self.black_ai is not None:
                self.play_ai_turn()
            elif (
                getattr(self, "local_player_color", None) is None
                or self.current_turn == self.local_player_color
            ) and not self._network_action_pending:
                self.process_player_turn()
            winner = self.capture_processor.get_winner()
        if winner is not None:
            log_info("Game winner: {}".format(winner.value))

        return winner

    def play_ai_turn(self):
        """Asynchronicznie wyszukuje ruch i zatwierdza go po zakończeniu obliczeń."""
        if self.black_ai is None or self.current_turn != COLOR.BLACK:
            return

        if self._ai_future is None:
            GameObservation = __import__(
                "models.game_observation", fromlist=["GameObservation"]
            ).GameObservation
            state = GameState.from_game(self)
            observation = GameObservation.from_state(state, COLOR.BLACK)
            with self._ai_progress_lock:
                self._ai_generation += 1
                generation = self._ai_generation
                self._ai_active_generation = generation
                self._ai_best_move = None
                self._ai_best_move_from_learning = None
                self._ai_searching = True
                self._ai_final_result = None
                self._ai_final_move_from_learning = None

            def report_candidate(action, depth, score):
                notation = self._format_ai_action_notation(state, action)
                learning_hint_used = (
                    self.black_ai.action_has_learning_hint(action)
                    if self._is_chess_ai(self.black_ai) else None
                )
                with self._ai_progress_lock:
                    if generation == self._ai_generation:
                        self._ai_best_move = (notation, depth, score)
                        self._ai_best_move_from_learning = learning_hint_used

            log_info("Starting AI search for black")
            search_options = {}
            if self._is_chess_ai(self.black_ai):
                search_options["cache_generation"] = (
                    self.black_ai.search_cache_generation()
                )
            self._ai_future = self._ai_executor.submit(
                self.black_ai.choose_action,
                observation,
                candidate_callback=report_candidate,
                **search_options,
            )
            return
        if not self._ai_future.done():
            return
        if self.is_action_animation_active:
            return

        try:
            decision = self._ai_future.result()
        except Exception as error:
            self._ai_future = None
            with self._ai_progress_lock:
                if self._ai_active_generation == self._ai_generation:
                    self._ai_searching = False
            log_error("AI search failed: {}".format(error))
            raise
        self._ai_future = None
        if decision.action is None:
            with self._ai_progress_lock:
                if self._ai_active_generation == self._ai_generation:
                    self._ai_searching = False
            log_warn("AI search returned no legal action")
            return
        final_notation = self._format_ai_action_notation(
            GameState.from_game(self), decision.action)
        with self._ai_progress_lock:
            if self._ai_active_generation == self._ai_generation:
                self._ai_searching = False
                self._ai_final_result = (
                    final_notation,
                    decision.score,
                    decision.completed_depth,
                    decision.visited_nodes,
                )
                self._ai_final_move_from_learning = getattr(
                    decision, "learning_hint_used", None)
        log_info(
            "AI selected {} (score={:+.2f}, depth={}, nodes={})".format(
                final_notation,
                decision.score,
                decision.completed_depth,
                decision.visited_nodes,
            )
        )
        self.apply_ai_action(decision.action)
        self._start_pondering()

    def _start_pondering(self):
        if (
            not self._is_chess_ai(self.black_ai)
            or not self.black_ai.ponder_enabled
            or self.current_turn != COLOR.WHITE
            or self.capture_processor.get_winner() is not None
        ):
            return
        self._reap_pondering()
        if self._ponder_future is not None:
            return
        self._ponder_cancel_event.clear()
        state = GameState.from_game(self)
        log_info("Starting AI pondering during white turn")
        self._ponder_future = self._ai_executor.submit(
            self.black_ai.ponder, state, self._ponder_cancel_event)

    def _cancel_pondering(self):
        future = getattr(self, "_ponder_future", None)
        if future is None:
            return
        self._ponder_cancel_event.set()
        if self._is_chess_ai(self.black_ai):
            self.black_ai.cancel_ponder()
        if future.cancel():
            self._ponder_future = None

    def _reap_pondering(self):
        future = getattr(self, "_ponder_future", None)
        if future is None or not future.done():
            return
        try:
            future.result()
        except CancelledError:
            pass
        except Exception as error:
            log_error("AI pondering failed: {}".format(error))
        self._ponder_future = None

    @property
    def is_ai_thinking(self):
        thinking = (
            self.black_ai is not None
            and self.current_turn == COLOR.BLACK
            and self._ai_future is not None
        )
        return thinking

    @property
    def ai_search_stats(self):
        AISearchStats = __import__(
            "models.ai_search_stats", fromlist=["AISearchStats"]
        ).AISearchStats

        with self._ai_progress_lock:
            best_move = self._ai_best_move
            best_move_from_learning = self._ai_best_move_from_learning
            final_result = self._ai_final_result
            final_move_from_learning = self._ai_final_move_from_learning
            is_searching = self._ai_searching
        cache_stats = None
        cache_deepest_entry_depth = None
        workers = ()
        learning_database_size_bytes = None
        learning_database_limit_bytes = None
        progress_stats = (
            None, None, None, None, None, None, None, None, None, (), None,
            (),
        )
        if self._is_chess_ai(self.black_ai):
            cache_stats = self.black_ai.cache_diagnostics()
            cache_deepest_entry_depth = cache_stats[4]
            workers = self.black_ai.worker_stats()
            progress_stats = self.black_ai.search_progress_stats(workers)
            learning_database_size_bytes = (
                self.black_ai.learning_database_file_size())
            learning_database_limit_bytes = (
                self.black_ai.config.learning_max_file_size_bytes)
        return AISearchStats(
            is_searching=is_searching,
            candidate_move=best_move[0] if best_move is not None else None,
            candidate_score=best_move[2] if best_move is not None else None,
            candidate_depth=best_move[1] if best_move is not None else None,
            final_move=final_result[0] if final_result is not None else None,
            final_score=final_result[1] if final_result is not None else None,
            completed_depth=(
                final_result[2] if final_result is not None else None
            ),
            visited_nodes=(
                final_result[3] if final_result is not None else None
            ),
            cache_enabled=cache_stats[0] if cache_stats is not None else None,
            cache_entries=cache_stats[1] if cache_stats is not None else None,
            cache_limit=cache_stats[2] if cache_stats is not None else None,
            cache_evictions=cache_stats[3] if cache_stats is not None else None,
            cache_deepest_entry_depth=cache_deepest_entry_depth,
            learning_database_size_bytes=learning_database_size_bytes,
            learning_database_limit_bytes=learning_database_limit_bytes,
            candidate_move_from_learning_database=best_move_from_learning,
            final_move_from_learning_database=final_move_from_learning,
            workers=workers,
            search_phase=progress_stats[0],
            current_depth=progress_stats[1],
            completed_search_depth=progress_stats[2],
            live_visited_nodes=progress_stats[3],
            ponder_white_actions_completed=progress_stats[4],
            ponder_white_actions_total=progress_stats[5],
            ponder_branches_generated=progress_stats[6],
            ponder_root_actions_completed=progress_stats[7],
            ponder_root_actions_discovered=progress_stats[8],
            ponder_depth_counts=progress_stats[9],
            ponder_max_branch_depth=progress_stats[10],
            ponder_dangerous_white_candidates=progress_stats[11],
        )

    def draw_ai_thinking_overlay(self):
        """Rysuje półprzezroczyste, czarne tło ze spinnerem podczas obliczeń bota."""
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        self.screen.blit(overlay, (0, 0))

        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2
        spinner_radius = 24
        phase = pygame.time.get_ticks() / 100.0
        for index in range(8):
            angle = phase - index * math.tau / 8
            position = (
                round(center_x + math.cos(angle) * spinner_radius),
                round(center_y - 28 + math.sin(angle) * spinner_radius),
            )
            shade = 255 - index * 22
            pygame.draw.circle(self.screen, (shade, shade, shade), position, 4)

        font = SysFont(self.context.comic_sans_font, 25)
        message = font.render("Czarny wykonuje ruch...", True, (255, 255, 255))
        self.screen.blit(
            message,
            (center_x - message.get_width() // 2, center_y + 18),
        )

    @staticmethod
    def _format_ai_action_notation(state, action):
        if action.action_type == GameActionType.RECRUIT_PAWN:
            return "P@{}".format(POS(action.destination).name.lower())
        piece = state.pieces_locations.get(action.source)
        destination = action.destination
        if piece is None or not piece.exists():
            return "?"

        piece_symbols = {
            PIECE_TYPE.KING: "K",
            PIECE_TYPE.QUEEN: "H",
            PIECE_TYPE.ROOK: "W",
            PIECE_TYPE.BISHOP: "G",
            PIECE_TYPE.KNIGHT: "S",
            PIECE_TYPE.PAWN: "",
        }
        source_square = POS(action.source).name.lower()

        if action.action_type in (
            GameActionType.APPLY_PASSIVE,
            GameActionType.APPLY_BUFF,
        ):
            return "{}@{}".format(piece_symbols.get(piece.get_type(), "?"), source_square)
        if action.action_type == GameActionType.PLACE_RUNE:
            return "S{}^{}".format(
                source_square, POS(destination).name.lower())
        if action.action_type == GameActionType.TREBUCHET:
            return "W{}:{}>{}".format(
                source_square,
                POS(action.secondary_source).name.lower(),
                POS(destination).name.lower(),
            )
        if action.action_type == GameActionType.TELEPORT and destination in range(1, 65):
            return "{}{}↔{}".format(
                piece_symbols.get(piece.get_type(), "?"),
                source_square,
                POS(destination).name.lower(),
            )
        if action.action_type == GameActionType.PROMOTE:
            cards = state.get_cards_for(state.current_turn)
            if 0 <= action.card_index < len(cards):
                promoted_type = cards[action.card_index].get_card_type().promoted_piece_type
                promoted_symbol = piece_symbols.get(promoted_type, "?")
                return "{}={}".format(source_square, promoted_symbol)
            return "{}=?".format(source_square)
        if action.action_type == GameActionType.RESURRECT:
            captured = state.get_captured_for(action.captured_color)
            if 0 <= action.captured_index < len(captured):
                resurrected_type = captured[action.captured_index].get_type()
                symbol = piece_symbols.get(resurrected_type, "?")
                return "{}@{}".format(symbol, POS(destination).name.lower())
            return "@{}".format(POS(destination).name.lower())
        if destination not in range(1, 65):
            return source_square

        destination_square = POS(destination).name.lower()
        target = state.pieces_locations.get(destination)
        is_capture = target is not None and target.exists()
        if (
            action.action_type == GameActionType.MOVE
            and 0 <= action.card_index < len(state.get_cards_for(state.current_turn))
            and state.get_cards_for(state.current_turn)[action.card_index].get_card_type()
            == EnchantmentCardType.ROOK_TOWER_THROW
        ):
            source_x, source_y = id_to_xy(action.source)
            destination_x, destination_y = id_to_xy(destination)
            step_x = (destination_x > source_x) - (destination_x < source_x)
            step_y = (destination_y > source_y) - (destination_y < source_y)
            x, y = source_x + step_x, source_y + step_y
            while (x, y) != (destination_x, destination_y):
                if state.pieces_locations[xy_to_id(x, y)].exists():
                    is_capture = True
                    break
                x += step_x
                y += step_y
        symbol = piece_symbols.get(piece.get_type(), "?")
        promotion_suffix = (
            "={}".format(piece_symbols.get(action.promotion_type, "?"))
            if action.promotion_type is not None else ""
        )
        if piece.get_type() == PIECE_TYPE.PAWN and is_capture:
            return "{}x{}{}".format(
                source_square[0], destination_square, promotion_suffix)
        return "{}{}{}".format(
            symbol,
            "x" if is_capture else "",
            destination_square + promotion_suffix,
        )

    def apply_ai_action(self, action):
        """Zatwierdza kompletną akcję AI przez te same reguły co symulacja."""
        log_logic("Applying AI action {}".format(action))
        self.__apply_domain_action(action)

    def apply_network_action(self, action):
        """Stosuje akcję przeciwnika odebraną z serwera."""
        if self.local_player_color is None:
            raise RuntimeError("Network actions require a network game")
        if self.current_turn == self.local_player_color:
            raise ValueError("Received a network action during the local player's turn")
        self.apply_authoritative_action(action)

    def apply_authoritative_action(self, action):
        """Stosuje zatwierdzoną przez serwer akcję obu graczy."""
        if self.local_player_color is None:
            raise RuntimeError("Network actions require a network game")
        if (
            self.current_turn == self.local_player_color
            and not self._network_action_pending
        ):
            raise ValueError("Received an unexpected action during the local player's turn")
        if (
            self.current_turn != self.local_player_color
            and self._network_action_pending
        ):
            raise ValueError("Received an action while a local action is pending")
        if self.is_action_animation_active:
            raise RuntimeError("Cannot apply an authoritative action during an animation")
        self._applying_network_action = True
        try:
            self.__apply_domain_action(action)
        finally:
            self._applying_network_action = False
            self._network_action_pending = False

    def reject_pending_network_action(self):
        """Odrzuca oczekującą akcję i czyści wybór interfejsu."""
        self._network_action_pending = False
        if self.double_move_step == 0:
            self.selected_card = None
            self.selected_piece_position = 0
            self.selected_captured_piece = None
            self.selected_trebuchet_pawn_position = 0
            self.resurrection_moves = []
            self.moves = []

    def __apply_domain_action(self, action):
        callback = getattr(self, "action_callback", None)
        if callback is not None and not getattr(
            self, "_applying_network_action", False
        ):
            if self._network_action_pending:
                raise RuntimeError("A network action is already awaiting confirmation")
            if callback(action) is False:
                raise RuntimeError("The game server is not connected")
            self._network_action_pending = True
            return

        state = GameState.from_game(self)
        result = GameSimulation.apply(
            state, action, advance_board_card_clock=True)
        action_animation = None
        if UI_ACTION_ANIMATION_DURATION_MS > 0:
            action_animation = ActionAnimation.from_transition(
                state,
                result,
                action,
                self.context,
                self.cards_processor,
                self.chess_pieces,
                UI_ACTION_ANIMATION_DURATION_MS,
            )

        self.pieces_locations = result.pieces_locations
        self.current_turn = result.current_turn
        self.turns_started = result.turns_started
        self.cards_processor.white_cards[:] = result.white_cards
        self.cards_processor.black_cards[:] = result.black_cards
        self.capture_processor.reset()
        for piece in result.captured_white + result.captured_black:
            self.capture_processor.capture_piece(piece)
        self.board_card_available = result.board_card_available
        self.board_card_position = result.board_card_position
        self.board_enchantment = result.board_enchantment
        self.board_cards = result.board_cards
        self.rune_traps = result.rune_traps
        self.pending_board_card_delay = result.pending_board_card_delay
        self.en_passant_target = result.en_passant_target
        self.en_passant_targets = result.en_passant_targets
        self.selected_card = result.selected_card
        self.selected_piece_position = result.selected_piece_position
        self.selected_trebuchet_pawn_position = 0
        self.selected_captured_piece = result.selected_captured_piece
        self.double_move_step = result.double_move_step
        self.double_move_collected_board_card = result.double_move_collected_board_card
        self.resurrection_moves = result.resurrection_moves
        if self.double_move_step > 0:
            piece = self.pieces_locations[self.selected_piece_position]
            self.moves = GameSimulation.destinations_for(
                piece,
                self.selected_piece_position,
                self.pieces_locations,
            )
        else:
            self.moves = []
        self.rng.setstate(result.random_state)
        if result.current_turn == COLOR.BLACK:
            self._cancel_pondering()
        self._action_animation = action_animation
        self._position_evaluation_stale = True

    # method to draw pieces on the chess board
    def draw_pieces(self):
        """Rysuje karty planszowe, figury, ich efekty oraz panele kart i zbić."""
        animation_time = pygame.time.get_ticks()
        animation = self._action_animation
        if (
            animation is not None
            and not animation.is_active_at(animation_time)
        ):
            self._action_animation = None
            animation = None
        hidden_piece_positions = (
            set(animation.hidden_piece_positions(animation_time))
            if animation is not None else set()
        )
        board_cards = getattr(self, "board_cards", []) or (
            [(self.board_card_position, self.board_enchantment)]
            if self.board_card_available and self.board_enchantment is not None
            else []
        )
        for card_position, _ in board_cards:
            card_x, card_y = id_to_xy(card_position)
            self.screen.blit(
                self.board_card_image,
                self.context.chessboard_coordinates[card_x][card_y],
            )

        for trap in self.rune_traps:
            x, y = id_to_xy(trap.position)
            square_x, square_y = self.context.chessboard_coordinates[x][y]
            center = (
                square_x + self.context.square_length // 2,
                square_y + self.context.square_length // 2,
            )
            radius = max(5, self.context.square_length // 5)
            pygame.draw.polygon(
                self.screen,
                (126, 54, 166),
                ((center[0], center[1] - radius),
                 (center[0] + radius, center[1]),
                 (center[0], center[1] + radius),
                 (center[0] - radius, center[1])),
            )
            pygame.draw.circle(self.screen, (235, 215, 255), center, max(2, radius // 4))

        self.__draw_recruit_targets()

        self.__draw_promotion_targets()
        self.__draw_return_to_start_targets()

        # loop to change background color of selected pieces
        for position, piece in self.pieces_locations.items():
            # name of the piece in the current location
            #  coordinates of the current piece

            # change background color of piece if it is selected
            if piece.exists() and position not in hidden_piece_positions:
                piece_coord_x, piece_coord_y = id_to_xy(position)
                if self.selected_piece_position == position:
                    self.__change_background_to_selection(position)
                if piece.is_stunned():
                    self.__change_background_to_stunned(position)
                self.chess_pieces.draw(self.screen, piece.full_name(),
                                       self.context.chessboard_coordinates[piece_coord_x][piece_coord_y])
                square_x, square_y = self.context.chessboard_coordinates[piece_coord_x][piece_coord_y]
                icon_x = square_x + self.context.square_length - 16
                if piece.has_passive_enchantment():
                    self.screen.blit(self.passive_icon, (icon_x, square_y))
                    icon_x -= 16
                if piece.has_delay_enchantment():
                    self.screen.blit(self.delay_icon, (icon_x, square_y))
                    icon_x -= 16
                if piece.is_stunned():
                    self.screen.blit(self.stun_icon, (icon_x, square_y))

        self.__draw_resurrection_moves()

        # draw captured pieces on the top and bottom of chessboard
        self.draw_captured_pieces(animation, animation_time)
        self.cards_processor.render(
            self.screen,
            self.chess_pieces,
            self.selected_card,
            hidden_card_slot=(
                animation.hidden_card_slot_at(animation_time)
                if animation is not None else None),
        )
        self.__draw_board_card_preview()
        self.__draw_piece_effect_preview()
        if animation is not None and not animation.draw(
            self.screen, self.chess_pieces, animation_time):
            self._action_animation = None
        self.__draw_promotion_popup()

    def __get_promotion_popup_layout(self):
        """Zwraca prostokąt okna promocji oraz przyciski jego wyborów."""
        button_width = 100
        button_height = 94
        button_gap = 12
        padding = 24
        panel_width = (
            padding * 2
            + len(self.pending_promotion_actions) * button_width
            + (len(self.pending_promotion_actions) - 1) * button_gap
        )
        panel_height = 190
        panel = pygame.Rect(
            (self.screen.get_width() - panel_width) // 2,
            (self.screen.get_height() - panel_height) // 2,
            panel_width,
            panel_height,
        )
        buttons = []
        for index, action in enumerate(self.pending_promotion_actions):
            button = pygame.Rect(
                panel.x + padding + index * (button_width + button_gap),
                panel.y + 72,
                button_width,
                button_height,
            )
            buttons.append((action, button))
        return panel, buttons

    def __draw_promotion_popup(self):
        """Wyświetla modalny wybór figury po dotarciu piona do końca planszy."""
        if not self.pending_promotion_actions:
            return

        panel, buttons = self.__get_promotion_popup_layout()
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (36, 39, 48), panel, border_radius=10)
        pygame.draw.rect(self.screen, (218, 196, 132), panel, 2, border_radius=10)

        title_font = SysFont(self.context.comic_sans_font, 24)
        title = title_font.render("Wybierz figurę do promocji", True, (245, 245, 245))
        self.screen.blit(
            title,
            (panel.centerx - title.get_width() // 2, panel.y + 18),
        )

        labels = {
            PIECE_TYPE.QUEEN: "Hetman",
            PIECE_TYPE.ROOK: "Wieża",
            PIECE_TYPE.BISHOP: "Goniec",
            PIECE_TYPE.KNIGHT: "Skoczek",
        }
        source_piece = self.pieces_locations[buttons[0][0].source]
        mouse_position = pygame.mouse.get_pos()
        label_font = SysFont(self.context.comic_sans_font, 17)
        for action, button in buttons:
            color = (
                (91, 98, 112)
                if button.collidepoint(mouse_position)
                else (57, 62, 73)
            )
            pygame.draw.rect(self.screen, color, button, border_radius=7)
            pygame.draw.rect(
                self.screen, (145, 150, 162), button, 1, border_radius=7)
            piece_name = "{}_{}".format(
                source_piece.get_color().value, action.promotion_type.value)
            thumbnail_width = int(self.context.piece_cell_thumbnail_width)
            thumbnail_height = int(self.context.piece_cell_thumbnail_height)
            self.chess_pieces.draw(
                self.screen,
                piece_name,
                (
                    button.centerx - thumbnail_width // 2,
                    button.y + 5,
                ),
                True,
            )
            label = label_font.render(
                labels[action.promotion_type], True, (245, 245, 245))
            self.screen.blit(
                label,
                (button.centerx - label.get_width() // 2, button.bottom - 24),
            )

    def __draw_promotion_targets(self):
        """Podświetla własne figury możliwe do ulepszenia wybraną kartą."""
        if not self.__selected_card_is_piece_upgrade():
            return

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        required_piece_type = card_deck[card_index].get_required_piece_type()
        surface = pygame.Surface((self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        surface.fill(PREDEFINED_COLOR.transparent_green)
        for position, piece in self.pieces_locations.items():
            if (
                piece.exists()
                and piece.get_color() == self.current_turn
                and piece.get_type() == required_piece_type
            ):
                x, y = id_to_xy(position)
                self.screen.blit(surface, self.context.chessboard_coordinates[x][y])

    def __draw_return_to_start_targets(self):
        """Podświetla wolne pola startowe dostępne dla wybranej figury."""
        if not self.__selected_card_is_return_to_start():
            return

        surface = pygame.Surface((self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        surface.fill(PREDEFINED_COLOR.transparent_green)
        for position in self.__get_return_to_start_targets():
            x, y = id_to_xy(position)
            self.screen.blit(surface, self.context.chessboard_coordinates[x][y])

    def __draw_board_card_preview(self):
        """Wyświetla podgląd karty planszowej, gdy kursor znajduje się nad nią."""
        mouse_x, mouse_y = pygame.mouse.get_pos()
        hovered_card = None
        hovered_color = self.current_turn
        remaining_turns = None
        board_cards = getattr(self, "board_cards", []) or (
            [(self.board_card_position, self.board_enchantment)]
            if self.board_card_available and self.board_enchantment is not None
            else []
        )
        for card_position, enchantment in board_cards:
            card_x, card_y = id_to_xy(card_position)
            square = pygame.Rect(
                self.context.chessboard_coordinates[card_x][card_y],
                (self.context.square_length, self.context.square_length),
            )
            if square.collidepoint(mouse_x, mouse_y):
                hovered_card = enchantment
                break
        if hovered_card is None:
            for trap in self.rune_traps:
                trap_x, trap_y = id_to_xy(trap.position)
                square = pygame.Rect(
                    self.context.chessboard_coordinates[trap_x][trap_y],
                    (self.context.square_length, self.context.square_length),
                )
                if square.collidepoint(mouse_x, mouse_y):
                    hovered_card = trap.enchantment
                    hovered_color = trap.owner
                    remaining_turns = trap.remaining_owner_turns
                    break
        if hovered_card is None:
            return

        margin = 10
        card_width = self.context.card_width
        card_height = self.context.card_height
        preview_x = mouse_x + margin
        preview_y = mouse_y + margin
        if preview_x + card_width > self.screen.get_width():
            preview_x = mouse_x - card_width - margin
        if preview_y + card_height > self.screen.get_height():
            preview_y = mouse_y - card_height - margin

        self.cards_processor.render_preview(
            self.screen, self.chess_pieces, hovered_card, (preview_x, preview_y),
            hovered_color, remaining_turns)

    def __draw_piece_effect_preview(self):
        """Pokazuje podgląd efektów figury wskazanej kursorem."""
        mouse_x, mouse_y = pygame.mouse.get_pos()
        for position, piece in self.pieces_locations.items():
            if not piece.exists():
                continue
            effects = piece.get_effects(self.turns_started[piece.get_color()])
            if not effects:
                continue

            piece_x, piece_y = id_to_xy(position)
            square_x, square_y = self.context.chessboard_coordinates[piece_x][piece_y]
            square = pygame.Rect(
                square_x, square_y, self.context.square_length, self.context.square_length)
            if square.collidepoint(mouse_x, mouse_y):
                self.cards_processor.render_effects_preview(
                    self.screen, self.chess_pieces, effects,
                    (mouse_x + 10, mouse_y + 10), piece.get_color())
                return

    def __change_background_to_selection(self, pos):
        """Podświetla wybraną figurę oraz jej wyznaczone pola ruchu."""
        surface = pygame.Surface((self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        surface.fill(PREDEFINED_COLOR.transparent_blue)

        piece_coord_x, piece_coord_y = id_to_xy(pos)
        self.screen.blit(surface, self.context.chessboard_coordinates[piece_coord_x][piece_coord_y])
        if len(self.moves) > 0:
            for move in self.moves:
                x_coord = move[0]
                y_coord = move[1]
                if 0 <= x_coord < 8 and 0 <= y_coord < 8:
                    self.screen.blit(surface, self.context.chessboard_coordinates[x_coord][y_coord])

    def __change_background_to_stunned(self, pos):
        """Nakłada czerwone podświetlenie na pole ogłuszonej figury."""
        surface = pygame.Surface((self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        surface.fill(PREDEFINED_COLOR.transparent_red)
        piece_coord_x, piece_coord_y = id_to_xy(pos)
        self.screen.blit(surface, self.context.chessboard_coordinates[piece_coord_x][piece_coord_y])

    def __draw_resurrection_moves(self):
        """Podświetla pola, na których można umieścić wybraną zmartwychwstającą figurę."""
        surface = pygame.Surface((self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        surface.fill(PREDEFINED_COLOR.transparent_green)
        for position in self.resurrection_moves:
            x, y = id_to_xy(position)
            self.screen.blit(surface, self.context.chessboard_coordinates[x][y])

    def process_player_turn(self):
        """Pobiera jedno kliknięcie i przekazuje je do obsługi odpowiedniego obszaru."""
        if self.is_action_animation_active:
            return

        if self.pending_promotion_actions is not None:
            self.__handle_promotion_choice()
            return

        if not self.__selected_card_allows_captured_piece_selection():
            self.selected_captured_piece = None
            self.resurrection_moves = []

        position = input_processor.get_clicked_chessboard_field_id()
        if position:
            self.__handle_board_click(position)
            return

        self.__handle_sidebar_click()

    def __handle_promotion_choice(self):
        """Zatwierdza wybraną figurę z modalnego okna promocji."""
        if not utils.left_click_event():
            return
        mouse_position = utils.get_mouse_event()
        _, buttons = self.__get_promotion_popup_layout()
        action = next(
            (action for action, button in buttons if button.collidepoint(mouse_position)),
            None,
        )
        if action is None:
            return
        self.pending_promotion_actions = None
        self.__apply_domain_action(action)

    def __handle_board_click(self, position):
        """Obsługuje planszowe kliknięcie zależnie od wybranej karty i figury."""
        if self.__selected_card_is_resurrection():
            if position in self.resurrection_moves:
                self.__resurrect_selected_piece(position)
            return

        piece = self.pieces_locations[position]
        selected_card_type = self.__get_selected_card_type()
        if selected_card_type == EnchantmentCardType.KNIGHT_RUNIC_TRAP:
            self.__handle_rune_trap_click(position, piece)
            return
        if selected_card_type == EnchantmentCardType.ROOK_TREBUCHET:
            self.__handle_trebuchet_click(position, piece)
            return
        if selected_card_type == EnchantmentCardType.RECRUIT_PAWN:
            self.__handle_recruit_click(position)
            return
        if self.__selected_card_is_piece_teleport():
            self.__handle_piece_teleport(position, piece)
            return
        if self.__selected_card_is_piece_upgrade():
            self.__handle_piece_upgrade(position, piece)
            return
        if self.__selected_card_is_return_to_start():
            self.__handle_return_to_start_click(position, piece)
            return

        if piece.exists() and piece.get_color() == self.current_turn:
            self.__select_piece_for_movement(position, piece)
        else:
            self.__move_to_clicked_destination(position, piece)

    def __handle_piece_teleport(self, position, piece):
        """Wybiera pierwszą figurę teleportacji lub zamienia ją z drugą i kończy turę."""
        if self.selected_piece_position == 0:
            if piece.exists() and piece.get_color() == self.current_turn:
                self.selected_piece_position = position
            return
        if position == self.selected_piece_position or not piece.exists():
            return

        card_color, card_index = self.selected_card
        self.__apply_domain_action(GameAction(
            GameActionType.TELEPORT,
            self.selected_piece_position,
            position,
            card_index,
        ))

    def __handle_piece_upgrade(self, position, piece):
        """Awansuje wskazaną figurę, zużywa kartę i ustawia jej ogłuszenie."""
        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        used_card = card_deck[card_index]
        if (
            not piece.exists()
            or piece.get_color() != self.current_turn
            or piece.get_type() != used_card.get_required_piece_type()
            or not piece.get_promotion_stun_turns_to(
                used_card.get_card_type().promoted_piece_type)
        ):
            return

        self.__apply_domain_action(GameAction(
            GameActionType.PROMOTE, position, card_index=card_index))

    def __handle_return_to_start_click(self, position, piece):
        """Wybiera figurę do przeniesienia albo wykonuje jej powrót na pole startowe."""
        if self.selected_piece_position == 0:
            if (
                piece.exists()
                and piece.get_color() == self.current_turn
                and piece.can_receive_enchantment()
            ):
                self.selected_piece_position = position
            return
        if position == self.selected_piece_position:
            self.selected_piece_position = 0
            return
        if piece.exists() and piece.get_color() == self.current_turn:
            self.selected_piece_position = position
            return
        if position in self.__get_return_to_start_targets():
            self.__apply_domain_action(GameAction(
                GameActionType.RETURN_TO_START,
                self.selected_piece_position,
                position,
                self.selected_card[1],
            ))

    def __select_piece_for_movement(self, position, piece):
        """Waliduje własną figurę i oblicza jej ruchy z wybraną kartą."""
        if self.__selected_card_is_piece_double_move() and self.double_move_step > 0:
            return
        if not piece.can_receive_enchantment():
            self.selected_piece_position = 0
            self.moves = []
            return
        if position == self.selected_piece_position:
            self.selected_piece_position = 0
            self.moves = []
            return

        active_enchantment = self.__get_selected_enchantment()
        if self.selected_card is not None and active_enchantment is None:
            self.selected_card = None
            self.moves = []
            self.selected_piece_position = 0
            return
        if active_enchantment is not None:
            required_piece_type = active_enchantment.get_required_piece_type()
            if required_piece_type not in (PIECE_TYPE.EMPTY, piece.get_type()):
                self.moves = []
                self.selected_piece_position = 0
                return
            if active_enchantment.is_passive():
                self.__apply_selected_piece_enchantment(position, active_enchantment)
                return

        self.selected_piece_position = position
        self.moves = GameSimulation.destinations_for(
            piece, position, self.pieces_locations,
            None if self.__selected_card_is_piece_double_move() else active_enchantment)
        if self.selected_card is None and self.double_move_step == 0:
            state = GameState.from_game(self)
            self.moves.extend(
                id_to_xy(destination)
                for destination in GameSimulation.special_move_destinations(
                    state, position)
            )

    def __get_selected_enchantment(self):
        """Zwraca aktualnie wybraną kartę albo None, jeśli nie ma prawidłowej selekcji."""
        if self.selected_card is None:
            return None
        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        if 0 <= card_index < len(card_deck):
            return card_deck[card_index]
        return None

    def __apply_selected_piece_enchantment(self, position, enchantment):
        """Nakłada efekt przypisany do figury i zużywa wybraną kartę."""
        _, card_index = self.selected_card
        action_type = (
            GameActionType.APPLY_BUFF
            if enchantment.is_buff()
            else GameActionType.APPLY_PASSIVE
        )
        self.__apply_domain_action(GameAction(
            action_type,
            position,
            card_index=card_index,
        ))

    def __move_to_clicked_destination(self, position, piece):
        """Wykonuje legalny ruch na wybrane puste pole lub zbija figurę przeciwnika."""
        for move in self.moves:
            if xy_to_id(move[0], move[1]) != position:
                continue
            source = self.selected_piece_position
            moving_piece = self.pieces_locations[source]
            promotion_rank = 7 if self.current_turn == COLOR.WHITE else 0
            if (
                moving_piece.get_type() == PIECE_TYPE.PAWN
                and id_to_xy(position)[1] == promotion_rank
            ):
                selected_card_index = (
                    self.selected_card[1]
                    if self.selected_card is not None
                    and self.selected_card[0] == self.current_turn
                    else -1
                )
                promotion_actions = tuple(
                    action
                    for action in GameSimulation.available_actions(
                        GameState.from_game(self))
                    if (
                        action.action_type == GameActionType.MOVE
                        and action.source == source
                        and action.destination == position
                        and action.card_index == selected_card_index
                        and action.promotion_type is not None
                    )
                )
                if promotion_actions:
                    self.pending_promotion_actions = promotion_actions
                    return
                log_error(
                    "No legal promotion choice found for pawn at {}".format(
                        POS(source).name)
                )
                return
            if piece.exists():
                self.capture_piece(position)
            else:
                self.move_piece(position)
            return

    def __handle_sidebar_click(self):
        """Obsługuje wybór figury zbitej; gdy jej nie kliknięto, przełącza kartę."""
        color, index = input_processor.get_clicked_captured_piece_index()
        if color is not None and index is not None:
            self.__select_captured_piece(color, index)
            return

        color, index = input_processor.get_clicked_card_index()
        if color != self.current_turn or self.double_move_step > 0:
            return
        card_deck = self.cards_processor.get_cards_for(color)
        if index is None or not 0 <= index < len(card_deck):
            return
        clicked_card = (color, index)
        self.selected_card = None if self.selected_card == clicked_card else clicked_card
        self.double_move_step = 0
        self.double_move_collected_board_card = False
        self.selected_captured_piece = None
        self.selected_trebuchet_pawn_position = 0
        self.resurrection_moves = []
        self.selected_piece_position = 0
        self.moves = []
        if self.__get_selected_card_type() == EnchantmentCardType.RECRUIT_PAWN:
            self.moves = [
                id_to_xy(action.destination)
                for action in self.__get_selected_card_actions(
                    GameActionType.RECRUIT_PAWN)
            ]

    def __get_selected_card_type(self):
        """Zwraca typ aktywnie wskazanej karty, jeśli nadal istnieje w talii."""
        enchantment = self.__get_selected_enchantment()
        return enchantment.get_card_type() if enchantment is not None else None

    def __get_selected_card_actions(
        self, action_type, *, source=None, secondary_source=None,
    ):
        """Pobiera legalne akcje bieżącej karty ze współdzielonego generatora symulacji."""
        if self.selected_card is None:
            return []
        card_index = self.selected_card[1]
        return [
            action for action in GameSimulation.available_actions(GameState.from_game(self))
            if action.action_type == action_type
            and action.card_index == card_index
            and (source is None or action.source == source)
            and (secondary_source is None or action.secondary_source == secondary_source)
        ]

    def __handle_rune_trap_click(self, position, piece):
        """Wybiera skoczka i legalne pole runy albo zatwierdza jej położenie."""
        if self.selected_piece_position == 0:
            actions = self.__get_selected_card_actions(
                GameActionType.PLACE_RUNE, source=position)
            if actions and piece.exists() and piece.get_color() == self.current_turn:
                self.selected_piece_position = position
                self.moves = [id_to_xy(action.destination) for action in actions]
            return

        if position == self.selected_piece_position:
            self.selected_piece_position = 0
            self.moves = []
            return
        action = next(
            (action for action in self.__get_selected_card_actions(
                GameActionType.PLACE_RUNE, source=self.selected_piece_position)
             if action.destination == position),
            None,
        )
        if action is not None:
            self.__apply_domain_action(action)
        elif piece.exists() and piece.get_color() == self.current_turn:
            actions = self.__get_selected_card_actions(
                GameActionType.PLACE_RUNE, source=position)
            if actions:
                self.selected_piece_position = position
                self.moves = [id_to_xy(action.destination) for action in actions]

    def __handle_trebuchet_click(self, position, piece):
        """Wybiera wieżę, wystrzeliwanego piona i puste pole docelowe."""
        if self.selected_piece_position == 0:
            actions = self.__get_selected_card_actions(
                GameActionType.TREBUCHET, source=position)
            if actions and piece.exists() and piece.get_color() == self.current_turn:
                self.selected_piece_position = position
                self.moves = [
                    id_to_xy(pawn_position)
                    for pawn_position in dict.fromkeys(
                        action.secondary_source for action in actions)
                ]
            return

        if self.selected_trebuchet_pawn_position == 0:
            actions = self.__get_selected_card_actions(
                GameActionType.TREBUCHET,
                source=self.selected_piece_position,
                secondary_source=position,
            )
            if actions:
                self.selected_trebuchet_pawn_position = position
                self.moves = [id_to_xy(action.destination) for action in actions]
            elif (
                piece.exists() and piece.get_type() == PIECE_TYPE.ROOK
                and piece.get_color() == self.current_turn
            ):
                self.selected_piece_position = 0
                self.__handle_trebuchet_click(position, piece)
            return

        action = next(
            (action for action in self.__get_selected_card_actions(
                GameActionType.TREBUCHET,
                source=self.selected_piece_position,
                secondary_source=self.selected_trebuchet_pawn_position,
            ) if action.destination == position),
            None,
        )
        if action is not None:
            self.__apply_domain_action(action)
            self.selected_trebuchet_pawn_position = 0
        elif piece.exists() and piece.get_type() == PIECE_TYPE.PAWN:
            actions = self.__get_selected_card_actions(
                GameActionType.TREBUCHET,
                source=self.selected_piece_position,
                secondary_source=position,
            )
            if actions:
                self.selected_trebuchet_pawn_position = position
                self.moves = [id_to_xy(action.destination) for action in actions]
        elif piece.exists() and piece.get_type() == PIECE_TYPE.ROOK:
            actions = self.__get_selected_card_actions(
                GameActionType.TREBUCHET, source=position)
            if actions and piece.get_color() == self.current_turn:
                self.selected_piece_position = position
                self.selected_trebuchet_pawn_position = 0
                self.moves = [
                    id_to_xy(pawn_position)
                    for pawn_position in dict.fromkeys(
                        action.secondary_source for action in actions)
                ]

    def __handle_recruit_click(self, position):
        """Stawia rekruta na jednym z legalnych pól pierwszej linii."""
        action = next(
            (action for action in self.__get_selected_card_actions(
                GameActionType.RECRUIT_PAWN)
             if action.destination == position),
            None,
        )
        if action is not None:
            self.__apply_domain_action(action)

    def __draw_recruit_targets(self):
        """Podświetla pola rekruta, które można wybrać bez uprzedniego wyboru figury."""
        if self.__get_selected_card_type() != EnchantmentCardType.RECRUIT_PAWN:
            return
        overlay = pygame.Surface(
            (self.context.square_length, self.context.square_length), pygame.SRCALPHA)
        overlay.fill(PREDEFINED_COLOR.transparent_blue)
        for move_x, move_y in self.moves:
            self.screen.blit(
                overlay, self.context.chessboard_coordinates[move_x][move_y])

    def __select_captured_piece(self, color, index):
        """Przełącza wybór kwalifikującej się zbitej figury i aktualizuje pola wskrzeszenia."""
        if (
            not self.__selected_card_allows_captured_piece_selection()
            or not self.__is_valid_captured_piece_list_for_selected_card(color)
        ):
            return
        captured_pieces = (
            self.capture_processor.get_captured_white()
            if color == COLOR.WHITE
            else self.capture_processor.get_captured_black()
        )
        if (
            not 0 <= index < len(captured_pieces)
            or not self.__is_valid_captured_piece_for_selected_card(captured_pieces[index])
        ):
            return

        piece = captured_pieces[index]
        log_debug(
            "Clicked captured piece: type={}, color={}, list_position={}".format(
                piece.get_type().value, piece.get_color().value, index
            )
        )
        clicked_piece = (color, index)
        self.selected_captured_piece = (
            None if self.selected_captured_piece == clicked_piece else clicked_piece
        )
        self.resurrection_moves = (
            self.__get_resurrection_moves()
            if self.selected_captured_piece is not None
            and self.__selected_card_is_resurrection()
            else []
        )

    def __is_valid_captured_piece_for_selected_card(self, piece):
        """Sprawdza, czy zbita figura spełnia ograniczenia wybranej karty."""
        if self.__selected_card_is_resurrection():
            return (
                piece.get_color() == self.current_turn
                and piece.get_type() == self.__selected_resurrection_piece_type()
                and self.__get_resurrection_king_position() is not None
            )
        return True

    def __is_valid_captured_piece_list_for_selected_card(self, color):
        """Sprawdza, czy można wybierać zbitą figurę z panelu podanego koloru."""
        if self.__selected_card_is_resurrection():
            return color != self.current_turn
        return True

    def __selected_card_is_resurrection(self):
        """Rozpoznaje, czy wybrana karta bieżącego gracza wskrzesza figurę."""
        if self.selected_card is None or self.selected_card[0] != self.current_turn:
            return False

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        return 0 <= card_index < len(card_deck) and self.__selected_resurrection_piece_type() is not None

    def __selected_card_is_piece_upgrade(self):
        """Rozpoznaje kartę awansu wskazującą docelowy typ figury."""
        if self.selected_card is None or self.selected_card[0] != self.current_turn:
            return False

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        return (
            0 <= card_index < len(card_deck)
            and card_deck[card_index].get_card_type().promoted_piece_type is not None
        )

    def __selected_card_is_return_to_start(self):
        """Sprawdza, czy wybrana karta przenosi figurę na wolne pole startowe."""
        if self.selected_card is None or self.selected_card[0] != self.current_turn:
            return False

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        return (
            0 <= card_index < len(card_deck)
            and card_deck[card_index].get_card_type() == EnchantmentCardType.RETURN_TO_START
        )

    def __selected_card_is_piece_teleport(self):
        """Sprawdza, czy wybrana karta pozwala zamienić miejscami dwie figury."""
        if self.selected_card is None or self.selected_card[0] != self.current_turn:
            return False

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        return (
            0 <= card_index < len(card_deck)
            and card_deck[card_index].get_card_type() == EnchantmentCardType.PIECE_TELEPORT
        )

    def __selected_card_is_piece_double_move(self):
        """Sprawdza, czy bieżąca karta umożliwia wykonanie dwóch ruchów jedną figurą."""
        if self.selected_card is None or self.selected_card[0] != self.current_turn:
            return False

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        return (
            0 <= card_index < len(card_deck)
            and card_deck[card_index].get_card_type() == EnchantmentCardType.PIECE_DOUBLE_MOVE
        )

    def __get_return_to_start_targets(self):
        """Zwraca wolne pola startowe tej samej barwy i typu co wybrana figura."""
        if self.selected_piece_position == 0:
            return []

        selected_piece = self.pieces_locations[self.selected_piece_position]
        origin = selected_piece.get_starting_position()
        if origin is None:
            return []

        original_piece = next(
            (
                piece for starting_position, piece in pieces_starting_positions_map.items()
                if starting_position.value == origin
            ),
            None,
        )
        if original_piece is None:
            return []

        return [
            starting_position.value
            for starting_position, piece in pieces_starting_positions_map.items()
            if piece.get_color() == original_piece.get_color()
            and piece.get_type() == original_piece.get_type()
            and starting_position.value != self.selected_piece_position
            and not self.pieces_locations[starting_position.value].exists()
        ]

    def __selected_resurrection_piece_type(self):
        """Zwraca typ figury wymagany do wskrzeszenia albo None dla innej karty."""
        if self.selected_card is None:
            return None

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        if not 0 <= card_index < len(card_deck):
            return None
        return card_deck[card_index].get_card_type().resurrected_piece_type

    def __get_resurrection_moves(self):
        """Zwraca wolne pola sąsiadujące z królem dla wybranej, kwalifikującej się figury."""
        if self.selected_captured_piece is None:
            return []

        color, index = self.selected_captured_piece
        captured_pieces = (
            self.capture_processor.get_captured_white()
            if color == COLOR.WHITE
            else self.capture_processor.get_captured_black()
        )
        if (
            color == self.current_turn
            or not 0 <= index < len(captured_pieces)
            or captured_pieces[index].get_color() != self.current_turn
            or not self.__is_valid_captured_piece_for_selected_card(captured_pieces[index])
        ):
            return []

        king_position = self.__get_resurrection_king_position()
        if king_position is None:
            return []

        king_x, king_y = id_to_xy(king_position)
        return [
            xy_to_id(x, y)
            for y in range(max(0, king_y - 1), min(7, king_y + 1) + 1)
            for x in range(max(0, king_x - 1), min(7, king_x + 1) + 1)
            if (x, y) != (king_x, king_y)
            and not self.pieces_locations[xy_to_id(x, y)].exists()
        ]

    def __get_resurrection_king_position(self):
        """Wyszukuje pozycję nieogłuszonego króla bieżącego gracza lub zwraca None."""
        return next(
            (
                position for position, piece in self.pieces_locations.items()
                if piece.exists() and piece.get_color() == self.current_turn
                and piece.get_type() == PIECE_TYPE.KING and piece.can_receive_enchantment()
            ),
            None,
        )

    def __resurrect_selected_piece(self, position):
        """Przywraca wybraną zbitą figurę na dozwolone pole i kończy turę."""
        if self.selected_captured_piece is None or position not in self.resurrection_moves:
            return

        color, index = self.selected_captured_piece
        king_position = self.__get_resurrection_king_position()
        if king_position is None:
            return
        card_color, card_index = self.selected_card
        self.__apply_domain_action(GameAction(
            GameActionType.RESURRECT,
            king_position,
            position,
            card_index,
            color,
            index,
        ))

    def __selected_card_allows_captured_piece_selection(self):
        """Sprawdza, czy wybrana karta bieżącego gracza wymaga wskazania zbitej figury."""
        if self.selected_card is None or self.selected_card[0] != self.current_turn:
            return False

        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        return (
            0 <= card_index < len(card_deck)
            and card_deck[card_index].allows_captured_piece_selection()
        )

    def __detonate_pawn(self, position):
        """Zbija figury w sąsiedztwie pionka, usuwa pionka i czyści wybór ruchu."""
        x, y = id_to_xy(position)
        for target_y in range(max(0, y - 1), min(7, y + 1) + 1):
            for target_x in range(max(0, x - 1), min(7, x + 1) + 1):
                if target_x == x and target_y == y:
                    continue

                target_position = xy_to_id(target_x, target_y)
                target_piece = self.pieces_locations[target_position]
                if target_piece.exists():
                    self.capture_processor.capture_piece(target_piece)
                    self.pieces_locations[target_position] = Piece()

        self.pieces_locations[position] = Piece()
        self.selected_piece_position = 0
        self.moves = []

    def __apply_passive_enchantment(self, position, enchantment):
        """Uruchamia specjalną detonację lub przypisuje efekt pasywny do figury."""
        if enchantment.get_card_type() in (
            EnchantmentCardType.PAWN_DETONATION,
            EnchantmentCardType.PAWN_DETONATION_DELAYED_1,
            EnchantmentCardType.PAWN_DETONATION_DELAYED_2,
        ):
            self.__detonate_pawn(position)
        else:
            self.pieces_locations[position].set_enchantment(enchantment)

    def __apply_ready_passive_enchantments(self, color):
        """Aktywuje efekty oczekujące dla figur danego koloru na rozpoczętej turze."""
        turn = self.turns_started[color]
        for position, piece in self.pieces_locations.items():
            if not piece.exists() or piece.get_color() != color:
                continue
            for enchantment in piece.get_delayed_enchantments_ready_at(turn):
                if not piece.exists():
                    break
                self.__apply_passive_enchantment(position, enchantment)

    def __end_turn(self):
        """Przełącza gracza, zwiększa jego licznik tur i uruchamia gotowe efekty."""
        self.current_turn = COLOR.BLACK if self.current_turn == COLOR.WHITE else COLOR.WHITE
        self.turns_started[self.current_turn] += 1
        self.__apply_ready_passive_enchantments(self.current_turn)

    def capture_piece(self, destination):
        """Zbija figurę na polu docelowym i wykonuje ruch, uwzględniając rzut wieżą."""
        self.move_piece(destination, beats=True)

    def __is_rook_tower_throw_selected(self):
        """Sprawdza, czy wybrano kartę specjalnego ruchu wieży."""
        if self.selected_card is None or self.selected_card[0] != self.current_turn:
            return False
        card_deck = self.cards_processor.get_cards_for(self.current_turn)
        card_index = self.selected_card[1]
        return (
            0 <= card_index < len(card_deck)
            and card_deck[card_index].get_card_type() == EnchantmentCardType.ROOK_TOWER_THROW
        )

    def move_piece(self, destination, beats=False):
        """Przenosi wybraną figurę i koordynuje rozliczenie skutków ruchu."""
        if self.selected_piece_position <= 0:
            return

        source_position = self.selected_piece_position
        card_index = (
            self.selected_card[1]
            if self.selected_card is not None
            and self.selected_card[0] == self.current_turn
            else -1
        )
        piece_name = self.pieces_locations[source_position].full_name()
        action = GameAction(
            GameActionType.MOVE, source_position, destination, card_index)
        self.__apply_domain_action(action)
        log_logic(
            "{} {} from {} to {}".format(
                piece_name, "beats" if beats else "moves",
                POS(source_position).name, POS(destination).name)
        )

    def __get_used_card(self, moving_color):
        """Zwraca kartę bieżącego ruchu wraz z jej talią i indeksem, jeśli jest wybrana."""
        if self.selected_card is None or self.selected_card[0] != moving_color:
            return None, None, None, None
        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        if not 0 <= card_index < len(card_deck):
            return card_color, card_index, card_deck, None
        return card_color, card_index, card_deck, card_deck[card_index]

    def __capture_rook_throw_route(self, source_position, destination):
        """Zbija wszystkie figury na trasie specjalnego ruchu wieży."""
        source_x, source_y = id_to_xy(source_position)
        destination_x, destination_y = id_to_xy(destination)
        step_x = (destination_x > source_x) - (destination_x < source_x)
        step_y = (destination_y > source_y) - (destination_y < source_y)
        target_x, target_y = source_x + step_x, source_y + step_y
        while (target_x, target_y) != (destination_x, destination_y):
            target_position = xy_to_id(target_x, target_y)
            target_piece = self.pieces_locations[target_position]
            if target_piece.exists():
                self.capture_processor.capture_piece(target_piece)
                self.pieces_locations[target_position] = Piece()
            target_x += step_x
            target_y += step_y

        target_piece = self.pieces_locations[destination]
        if target_piece.exists():
            self.capture_processor.capture_piece(target_piece)

    def __collect_board_card(self, destination, moving_color):
        """Dodaje kartę zebraną na polu docelowym i zwraca, czy została zebrana."""
        board_cards = getattr(self, "board_cards", [])
        card = next(
            (card for card in board_cards if card[0] == destination),
            None,
        )
        if card is None and self.board_card_available and destination == self.board_card_position:
            card = (self.board_card_position, self.board_enchantment)
            board_cards = [card]
            self.board_cards = board_cards
        if card is None:
            return False
        self.cards_processor.add_card_for(moving_color, card[1])
        board_cards.remove(card)
        self.board_cards = board_cards
        self.__sync_board_card_fields()
        return True

    def __sync_board_card_fields(self):
        """Synchronizuje starsze pola pojedynczej karty z kolekcją kart planszowych."""
        self.board_card_available = bool(getattr(self, "board_cards", []))
        if self.board_card_available:
            self.board_card_position, self.board_enchantment = self.board_cards[0]
        else:
            self.board_enchantment = None

    def __apply_move_stun(self, piece, used_card):
        """Nakłada ogłuszenie po ruchu z karty lub po aktywnych efektach pasywnych."""
        passive_enchantments = piece.get_passive_enchantments()
        stun_turns = (
            used_card.get_rate_stun_after_use()
            if used_card is not None
            else sum(
                enchantment.get_rate_stun_after_use()
                for enchantment in passive_enchantments
            )
        )
        if stun_turns <= 0:
            return

        piece.set_stunned_for_turns(stun_turns)
        stun_enchantments = (
            [used_card]
            if used_card is not None and used_card.get_rate_stun_after_use() > 0
            else passive_enchantments
        )
        for enchantment in stun_enchantments:
            if enchantment.get_rate_stun_after_use() > 0:
                piece.add_stun_effect(enchantment, stun_turns)

    def __continue_double_move(
        self, piece, destination, used_card, card_deck, card_index, collected_board_card,
    ):
        """Pozwala wykonać drugi ruch kartą podwójnego ruchu, jeśli są legalne pola."""
        self.double_move_step = 1
        self.double_move_collected_board_card = collected_board_card
        self.selected_piece_position = destination
        self.moves = process_possible_basic_moves(
            piece, id_to_xy(destination), self.pieces_locations)
        if self.moves:
            return True
        if used_card is not None and used_card.consume_use() == 0:
            card_deck.pop(card_index)
        return False

    def __finish_piece_move(
        self, piece, source_position, destination, beats, collected_board_card,
    ):
        """Zamyka turę, aktualizuje pojawienie się kart, loguje ruch i czyści wybór."""
        self.__end_turn()
        if collected_board_card and self.pending_board_card_delay is None:
            self.__schedule_next_board_card()
        self.__advance_board_card_clock()

        beats_or_moves = "beats" if beats else "moves"
        log_logic(
            "{} {} from {} to {}".format(
                piece.full_name(), beats_or_moves, POS(source_position).name,
                POS(destination).name)
        )
        self.selected_piece_position = 0
        self.moves = []
        self.selected_card = None
        self.selected_captured_piece = None
        self.double_move_step = 0
        self.double_move_collected_board_card = False

    def __advance_stun_effects(self, color):
        """Zmniejsza liczniki ogłuszenia wszystkich istniejących figur wskazanego koloru."""
        for piece in self.pieces_locations.values():
            if piece.exists() and piece.get_color() == color:
                piece.advance_stun_effects()

    def __place_next_board_card(self):
        """Losuje wolne pole i kartę, po czym oznacza kartę planszową jako dostępną."""
        existing_cards = getattr(self, "board_cards", []) or (
            [(self.board_card_position, self.board_enchantment)]
            if self.board_card_available and self.board_enchantment is not None
            else []
        )
        occupied_card_positions = {position for position, _ in existing_cards}
        empty_positions = [
            position for position in range(1, 65)
            if not self.pieces_locations[position].exists()
            and position not in occupied_card_positions
            and all(
                trap.position != position
                for trap in getattr(self, "rune_traps", ())
            )
        ]
        log_debug(
            "Board card placement: found {} empty square(s)".format(len(empty_positions))
        )
        if not empty_positions:
            return
        rng = self.rng
        card_position = rng.choice(empty_positions)
        log_debug(
            "Board card placement: selected square {}".format(POS(card_position).name)
        )
        enchantment = EnchantmentCardType.create_random(rng)
        existing_cards.append((card_position, enchantment))
        self.board_cards = existing_cards
        self.__sync_board_card_fields()
        self.pending_board_card_delay = (
            0 if RUN_MODE is RunMode.DEBUG else rng.randint(1, 5)
        )
        log_logic(
            "Board card placement: '{}' is now available on {}; next-card countdown starts at {} turn(s)".format(
                enchantment.get_title(),
                POS(card_position).name,
                self.pending_board_card_delay,
            )
        )

    def __advance_board_card_clock(self):
        """Odlicza do następnego wyłożenia niezależnie od kart już leżących."""
        if self.pending_board_card_delay is None:
            return
        previous_delay = self.pending_board_card_delay
        if previous_delay > 0:
            self.pending_board_card_delay -= 1
            log_debug(
                "Board card placement: countdown decreased from {} to {} turn(s)".format(
                    previous_delay, self.pending_board_card_delay)
            )
        if self.pending_board_card_delay == 0:
            self.__place_next_board_card()

    def __schedule_next_board_card(self):
        """Planuje pojawienie się następnej karty, z natychmiastowym losowaniem w debug."""
        self.pending_board_card_delay = (
            0 if RUN_MODE is RunMode.DEBUG else self.rng.randint(1, 5)
        )
        log_logic(
            "Board card placement: scheduled; delay={} turn(s) (run mode={})".format(
                self.pending_board_card_delay, RUN_MODE.value)
        )
        if self.pending_board_card_delay == 0:
            self.__place_next_board_card()

    def print_annotations(self):
        """Rysuje oznaczenia rzędów i kolumn wokół planszy."""
        font_size = int(self.context.square_length / 3)
        font = pygame.font.SysFont(self.context.comic_sans_font, font_size)
        color = (120, 120, 120)
        top_margin = self.context.board_offset_y + self.context.square_length / 2
        number_to_display = 8
        # display numbers on the left
        for row in range(0, 8):
            rendered = font.render(str(number_to_display), True, color)
            self.screen.blit(rendered,
                             (int(self.context.board_offset_x - rendered.get_width() - 10),
                              int(top_margin + (row * self.context.square_length - rendered.get_height() / 2))))
            number_to_display -= 1

        # display letters on the bottom
        left_margin = self.context.board_offset_x + self.context.square_length / 2
        for column in range(0, 8):
            rendered = font.render(chr(65 + column), True, color)
            self.screen.blit(rendered,
                             (int(left_margin + (column * self.context.square_length - rendered.get_width() / 2)),
                              int(self.context.board_offset_y + (self.context.square_length * 8) + 5)))

    def draw_captured_pieces(self, animation=None, animation_time=None):
        """Ustala położenie paneli zbitych figur i rysuje obie grupy."""
        if not (self.context.captured_white_starting_point and self.context.captured_black_starting_point):
            self.context.captured_white_starting_point = (self.context.board_offset_x,
                                                          self.context.board_offset_y * 2 + (
                                                                  self.context.square_length * 8) - (
                                                                  2 * self.context.piece_cell_thumbnail_height))
            self.context.captured_black_starting_point = (self.context.board_offset_x, 0)

        if animation_time is None:
            animation_time = pygame.time.get_ticks()
        if animation is None:
            animation = self._action_animation
        if (
            animation is not None
            and not animation.is_active_at(animation_time)
        ):
            animation = None
        captured_slot = (
            animation.hidden_captured_slot_at(animation_time)
            if animation is not None else None
        )
        self.__draw_captured_group(
            self.capture_processor.get_captured_black(),
            COLOR.BLACK,
            self.context.captured_black_starting_point,
            captured_slot[1]
            if captured_slot is not None and captured_slot[0] == COLOR.BLACK
            else None,
        )
        self.__draw_captured_group(
            self.capture_processor.get_captured_white(),
            COLOR.WHITE,
            self.context.captured_white_starting_point,
            captured_slot[1]
            if captured_slot is not None and captured_slot[0] == COLOR.WHITE
            else None,
        )

    def __draw_captured_group(
        self, pieces, color, starting_point, hidden_index=None,
    ):
        """Rysuje miniatury zbitych figur w panelu i obramowuje aktualny wybór."""
        width = self.context.piece_cell_thumbnail_width
        height = self.context.piece_cell_thumbnail_height
        for index, piece in enumerate(pieces):
            if index == hidden_index:
                continue
            coords = (
                starting_point[0] + (index // 2) * width,
                starting_point[1] + (index % 2) * height,
            )
            self.chess_pieces.draw(self.screen, piece.full_name(), coords, True)
            if self.selected_captured_piece == (color, index):
                pygame.draw.rect(
                    self.screen,
                    (255, 255, 255),
                    pygame.Rect(coords, (width, height)),
                    2,
                )
