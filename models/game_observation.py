import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from constants.piece_color import COLOR
from models.chess_pieces import Piece
from models.enchantments import Enchantment
from models.game_state import GameState


@dataclass
class GameObservation:
    """Pełna migawka informacji przekazywana do wyszukiwania AI."""

    own_color: COLOR
    pieces_locations: Dict[int, Piece]
    current_turn: COLOR
    turns_started: Dict[COLOR, int]
    own_cards: List[Enchantment]
    opponent_cards: List[Enchantment]
    captured_white: List[Piece]
    captured_black: List[Piece]
    board_card_available: bool
    board_card_position: int
    board_enchantment: Optional[Enchantment]
    pending_board_card_delay: Optional[int]
    selected_card: Optional[Tuple[COLOR, int]]
    selected_piece_position: int
    selected_captured_piece: Optional[Tuple[COLOR, int]]
    double_move_step: int
    double_move_collected_board_card: bool
    resurrection_moves: List[int]
    random_state: tuple
    board_cards: List[Tuple[int, Enchantment]] = field(default_factory=list)

    @classmethod
    def from_state(cls, state: GameState, own_color: COLOR):
        """Buduje obserwację zawierającą dokładne ręce obu graczy."""
        opponent_color = COLOR.BLACK if own_color == COLOR.WHITE else COLOR.WHITE
        observation = cls(
            own_color=own_color,
            pieces_locations=state.pieces_locations,
            current_turn=state.current_turn,
            turns_started=state.turns_started,
            own_cards=state.get_cards_for(own_color),
            opponent_cards=state.get_cards_for(opponent_color),
            captured_white=state.captured_white,
            captured_black=state.captured_black,
            board_card_available=state.board_card_available,
            board_card_position=state.board_card_position,
            board_enchantment=state.board_enchantment,
            pending_board_card_delay=state.pending_board_card_delay,
            selected_card=state.selected_card,
            selected_piece_position=state.selected_piece_position,
            selected_captured_piece=state.selected_captured_piece,
            double_move_step=state.double_move_step,
            double_move_collected_board_card=state.double_move_collected_board_card,
            resurrection_moves=state.resurrection_moves,
            random_state=state.random_state,
            board_cards=state.board_cards,
        )
        return copy.deepcopy(observation)

    def to_state(self) -> GameState:
        """Tworzy odizolowany stan symulacji z dokładnymi rękami obu graczy."""
        memo = {}
        white_cards = (
            copy.deepcopy(self.own_cards, memo)
            if self.own_color == COLOR.WHITE
            else copy.deepcopy(self.opponent_cards, memo)
        )
        black_cards = (
            copy.deepcopy(self.own_cards, memo)
            if self.own_color == COLOR.BLACK
            else copy.deepcopy(self.opponent_cards, memo)
        )
        return GameState(
            pieces_locations=copy.deepcopy(self.pieces_locations, memo),
            current_turn=self.current_turn,
            turns_started=copy.deepcopy(self.turns_started, memo),
            white_cards=white_cards,
            black_cards=black_cards,
            captured_white=copy.deepcopy(self.captured_white, memo),
            captured_black=copy.deepcopy(self.captured_black, memo),
            board_card_available=self.board_card_available,
            board_card_position=self.board_card_position,
            board_enchantment=copy.deepcopy(self.board_enchantment, memo),
            pending_board_card_delay=self.pending_board_card_delay,
            selected_card=self.selected_card,
            selected_piece_position=self.selected_piece_position,
            selected_captured_piece=self.selected_captured_piece,
            double_move_step=self.double_move_step,
            double_move_collected_board_card=self.double_move_collected_board_card,
            resurrection_moves=copy.deepcopy(self.resurrection_moves, memo),
            random_state=self.random_state,
            board_cards=copy.deepcopy(self.board_cards, memo),
        )
