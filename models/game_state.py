import copy
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.chess_pieces import Piece
from models.enchantments import Enchantment
from utils.run_config import GAME_SEED


def _initial_random_state():
    return random.Random(GAME_SEED if GAME_SEED is not None else 0).getstate()


@dataclass
class GameState:
    """Stan domenowy partii, niezależny od ekranu i zasobów Pygame."""

    pieces_locations: Dict[int, Piece]
    current_turn: COLOR
    turns_started: Dict[COLOR, int]
    white_cards: List[Enchantment]
    black_cards: List[Enchantment]
    captured_white: List[Piece]
    captured_black: List[Piece]
    board_card_available: bool
    board_card_position: int
    board_enchantment: Optional[Enchantment]
    pending_board_card_delay: Optional[int]
    selected_card: Optional[Tuple[COLOR, int]] = None
    selected_piece_position: int = 0
    selected_captured_piece: Optional[Tuple[COLOR, int]] = None
    double_move_step: int = 0
    double_move_collected_board_card: bool = False
    resurrection_moves: List[int] = field(default_factory=list)
    random_state: tuple = field(default_factory=_initial_random_state)
    board_cards: List[Tuple[int, Enchantment]] = field(default_factory=list)

    @classmethod
    def from_game(cls, game) -> "GameState":
        """Tworzy odizolowaną migawkę stanu domenowego z aktywnej partii."""
        state = cls(
            pieces_locations=game.pieces_locations,
            current_turn=game.current_turn,
            turns_started=game.turns_started,
            white_cards=game.cards_processor.white_cards,
            black_cards=game.cards_processor.black_cards,
            captured_white=game.capture_processor.get_captured_white(),
            captured_black=game.capture_processor.get_captured_black(),
            board_card_available=game.board_card_available,
            board_card_position=game.board_card_position,
            board_enchantment=game.board_enchantment,
            pending_board_card_delay=game.pending_board_card_delay,
            selected_card=game.selected_card,
            selected_piece_position=game.selected_piece_position,
            selected_captured_piece=game.selected_captured_piece,
            double_move_step=game.double_move_step,
            double_move_collected_board_card=game.double_move_collected_board_card,
            resurrection_moves=game.resurrection_moves,
            board_cards=(
                game.board_cards
                if getattr(game, "board_cards", None)
                else (
                    [(game.board_card_position, game.board_enchantment)]
                    if game.board_card_available and game.board_enchantment is not None
                    else []
                )
            ),
            random_state=(
                game.rng.getstate()
                if hasattr(game, "rng")
                else _initial_random_state()
            ),
        )
        return state.clone()

    def clone(self) -> "GameState":
        """Kopiuje rekurencyjnie mutowalny stan figur, efektów i kart."""
        return copy.deepcopy(self)

    def get_cards_for(self, color: COLOR) -> List[Enchantment]:
        """Zwraca talię wskazanego gracza."""
        return self.white_cards if color == COLOR.WHITE else self.black_cards

    def get_captured_for(self, color: COLOR) -> List[Piece]:
        """Zwraca panel figur zbitych przez wskazany kolor."""
        return self.captured_white if color == COLOR.WHITE else self.captured_black

    def get_winner(self) -> Optional[COLOR]:
        """Zwraca zwycięzcę, jeśli wśród zbitych figur jest król."""
        if any(piece.get_type() == PIECE_TYPE.KING for piece in self.captured_black):
            return COLOR.BLACK
        if any(piece.get_type() == PIECE_TYPE.KING for piece in self.captured_white):
            return COLOR.WHITE
        return None
