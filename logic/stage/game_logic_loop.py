import random

import pygame
from pygame import Surface
from pygame.font import SysFont

from constants.pos import id_to_xy, xy_to_id, POS
from constants.piece_type import PIECE_TYPE
from constants.predefined_colors import PREDEFINED_COLOR
from logic.chess_ai import ChessAI
from logic.game_rules import GameAction, GameActionType, GameRules
from logic.game_simulation import GameSimulation
from models.game_observation import GameObservation
from models.game_state import GameState
from models.chess_pieces import Piece, COLOR
from models.enchantment_cards import EnchantmentCardType
from models.starting_positions import pieces_starting_positions_map
from piecesprite import PieceSprite
from processors import input_processor
from processors.capturing_piece_processor import CaptureProcessor
from processors.cards_processor import CardsProcessor
from processors.movement_processor import process_possible_basic_moves
from utils.gamecontext import GameContext
from utils.logging import debug_log
from utils.run_config import RUN_MODE, RunMode


class GameLogicLoop(object):
    def __init__(self, screen: Surface, black_ai=None):
        """Tworzy stan rozgrywki, procesory i zasoby wizualne dla powierzchni ekranu."""
        self.context = GameContext()
        # display surface
        self.screen = screen
        self.black_ai = black_ai
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
        self.double_move_step = 0
        self.double_move_collected_board_card = False

        # field_id: PIECE
        self.pieces_locations = {}

        # list containing captured pieces
        self.capture_processor = CaptureProcessor()
        self.cards_processor = CardsProcessor(screen)
        self.board_card_position = POS.D5.value
        self.board_card_available = False
        self.board_enchantment = None
        self.pending_board_card_delay = None
        card_image = pygame.image.load(self.context.card_on_board_src).convert_alpha()
        self.board_card_image = pygame.transform.scale(
            card_image, (self.context.square_length, self.context.square_length))

        self.reset()

    def reset(self):
        """Przywraca planszę, talie i liczniki do stanu początkowego nowej partii."""
        # clear moves lists
        self.current_turn = COLOR.WHITE
        self.turns_started = {COLOR.WHITE: 1, COLOR.BLACK: 0}
        self.moves = []
        self.resurrection_moves = []
        self.selected_piece_position = 0
        self.selected_card = None
        self.selected_captured_piece = None
        self.double_move_step = 0
        self.double_move_collected_board_card = False
        self.board_card_available = False
        self.board_card_position = POS.D5.value
        self.board_enchantment = None
        self.pending_board_card_delay = None
        self.capture_processor.reset()
        self.cards_processor.reset_decks()

        # two dimensonal dictionary containing details about each board location
        # storage format is [piece_name, currently_selected, x_y_coordinate]
        # # reset the board
        for i in range(1, 65):
            # [piece name, currently selected]
            self.pieces_locations[i] = Piece()
        for position, piece in pieces_starting_positions_map.items():
            self.pieces_locations[position.value] = Piece(
                piece.get_color(), piece.get_type(), position.value)
        self.__schedule_next_board_card()

    def play_turn(self):
        """Rysuje informacje o turze, obsługuje jej wejście i zwraca zwycięzcę, jeśli jest."""
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
            else:
                self.process_player_turn()
            winner = self.capture_processor.get_winner()

        return winner

    def play_ai_turn(self):
        """Wykonuje jedną akcję bota czarnych na podstawie wyłącznie jego obserwacji."""
        if self.black_ai is None or self.current_turn != COLOR.BLACK:
            return

        state = GameState.from_game(self)
        observation = GameObservation.from_state(state, COLOR.BLACK)
        decision = self.black_ai.choose_action(observation)
        if decision.action is None:
            return
        self.apply_ai_action(decision.action)

    def apply_ai_action(self, action):
        """Zatwierdza kompletną akcję AI przez te same reguły co symulacja."""
        self.__apply_domain_action(action)

    def __apply_domain_action(self, action):
        state = GameState.from_game(self)
        result = GameSimulation.apply(state, action)

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
        self.pending_board_card_delay = result.pending_board_card_delay
        self.selected_card = result.selected_card
        self.selected_piece_position = result.selected_piece_position
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
        random.setstate(result.random_state)

    # method to draw pieces on the chess board
    def draw_pieces(self):
        """Rysuje karty planszowe, figury, ich efekty oraz panele kart i zbić."""
        if self.board_card_available:
            card_x, card_y = id_to_xy(self.board_card_position)
            self.screen.blit(
                self.board_card_image,
                self.context.chessboard_coordinates[card_x][card_y],
            )

        self.__draw_promotion_targets()
        self.__draw_return_to_start_targets()

        # loop to change background color of selected pieces
        for position, piece in self.pieces_locations.items():
            # name of the piece in the current location
            #  coordinates of the current piece

            # change background color of piece if it is selected
            if piece.exists():
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
        self.draw_captured_pieces()
        self.cards_processor.render(self.screen, self.chess_pieces, self.selected_card)
        self.__draw_board_card_preview()
        self.__draw_piece_effect_preview()

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
        if not self.board_card_available:
            return

        card_x, card_y = id_to_xy(self.board_card_position)
        square = pygame.Rect(
            self.context.chessboard_coordinates[card_x][card_y],
            (self.context.square_length, self.context.square_length),
        )
        mouse_x, mouse_y = pygame.mouse.get_pos()
        if not square.collidepoint(mouse_x, mouse_y):
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
            self.screen, self.chess_pieces, self.board_enchantment, (preview_x, preview_y), self.current_turn)

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
        if not self.__selected_card_allows_captured_piece_selection():
            self.selected_captured_piece = None
            self.resurrection_moves = []

        position = input_processor.get_clicked_chessboard_field_id()
        if position:
            self.__handle_board_click(position)
            return

        self.__handle_sidebar_click()

    def __handle_board_click(self, position):
        """Obsługuje planszowe kliknięcie zależnie od wybranej karty i figury."""
        if self.__selected_card_is_resurrection():
            if position in self.resurrection_moves:
                self.__resurrect_selected_piece(position)
            return

        piece = self.pieces_locations[position]
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
                self.__apply_selected_passive_enchantment(
                    position, piece, active_enchantment)
                return

        self.selected_piece_position = position
        self.moves = GameSimulation.destinations_for(
            piece, position, self.pieces_locations,
            None if self.__selected_card_is_piece_double_move() else active_enchantment)

    def __get_selected_enchantment(self):
        """Zwraca aktualnie wybraną kartę albo None, jeśli nie ma prawidłowej selekcji."""
        if self.selected_card is None:
            return None
        card_color, card_index = self.selected_card
        card_deck = self.cards_processor.get_cards_for(card_color)
        if 0 <= card_index < len(card_deck):
            return card_deck[card_index]
        return None

    def __apply_selected_passive_enchantment(self, position, piece, enchantment):
        """Przypisuje efekt pasywny lub planuje go, zużywa kartę i kończy turę."""
        card_color, card_index = self.selected_card
        self.__apply_domain_action(GameAction(
            GameActionType.APPLY_PASSIVE, position, card_index=card_index))

    def __move_to_clicked_destination(self, position, piece):
        """Wykonuje legalny ruch na wybrane puste pole lub zbija figurę przeciwnika."""
        for move in self.moves:
            if xy_to_id(move[0], move[1]) != position:
                continue
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
        self.resurrection_moves = []
        self.selected_piece_position = 0
        self.moves = []

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
        debug_log(
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
        debug_log(
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
        collected = self.board_card_available and destination == self.board_card_position
        if collected:
            self.cards_processor.add_card_for(moving_color, self.board_enchantment)
            self.board_card_available = False
        return collected

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
        if collected_board_card:
            self.__schedule_next_board_card()
        elif self.pending_board_card_delay is not None:
            previous_delay = self.pending_board_card_delay
            self.pending_board_card_delay -= 1
            debug_log(
                "Board card placement: countdown decreased from {} to {} turn(s)".format(
                    previous_delay, self.pending_board_card_delay)
            )
            if self.pending_board_card_delay == 0:
                self.__place_next_board_card()

        beats_or_moves = "beats" if beats else "moves"
        debug_log(
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
        empty_positions = [
            position for position in range(1, 65)
            if not self.pieces_locations[position].exists()
        ]
        debug_log(
            "Board card placement: found {} empty square(s)".format(len(empty_positions))
        )
        rng = getattr(self, "rng", random)
        self.board_card_position = rng.choice(empty_positions)
        debug_log(
            "Board card placement: selected square {}".format(POS(self.board_card_position).name)
        )
        self.board_enchantment = EnchantmentCardType.create_random(rng)
        self.board_card_available = True
        self.pending_board_card_delay = None
        debug_log(
            "Board card placement: '{}' is now available on {}".format(
                self.board_enchantment.get_title(), POS(self.board_card_position).name)
        )

    def __schedule_next_board_card(self):
        """Planuje pojawienie się następnej karty, z natychmiastowym losowaniem w debug."""
        self.board_card_available = False
        self.pending_board_card_delay = (
            0 if RUN_MODE is RunMode.DEBUG else getattr(self, "rng", random).randint(0, 4)
        )
        debug_log(
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

    def draw_captured_pieces(self):
        """Ustala położenie paneli zbitych figur i rysuje obie grupy."""
        if not (self.context.captured_white_starting_point and self.context.captured_black_starting_point):
            self.context.captured_white_starting_point = (self.context.board_offset_x,
                                                          self.context.board_offset_y * 2 + (
                                                                  self.context.square_length * 8) - (
                                                                  2 * self.context.piece_cell_thumbnail_height))
            self.context.captured_black_starting_point = (self.context.board_offset_x, 0)

        self.__draw_captured_group(
            self.capture_processor.get_captured_black(),
            COLOR.BLACK,
            self.context.captured_black_starting_point,
        )
        self.__draw_captured_group(
            self.capture_processor.get_captured_white(),
            COLOR.WHITE,
            self.context.captured_white_starting_point,
        )

    def __draw_captured_group(self, pieces, color, starting_point):
        """Rysuje miniatury zbitych figur w panelu i obramowuje aktualny wybór."""
        width = self.context.piece_cell_thumbnail_width
        height = self.context.piece_cell_thumbnail_height
        for index, piece in enumerate(pieces):
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
