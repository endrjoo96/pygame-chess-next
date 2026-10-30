import copy
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from constants.piece_color import COLOR
from models.chess_pieces import Piece
from models.enchantment_cards import EnchantmentCardType
from models.enchantments import Enchantment
from models.game_state import GameState


@dataclass
class GameObservation:
    """Informacje dostępne dla AI, bez ujawniania typów kart przeciwnika."""

    own_color: COLOR
    pieces_locations: Dict[int, Piece]
    current_turn: COLOR
    turns_started: Dict[COLOR, int]
    own_cards: List[Enchantment]
    opponent_card_count: int
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
        """Buduje obserwację publiczną i prywatną rękę gracza, pomijając rękę wroga."""
        opponent_color = _opponent_of(own_color)
        observation = cls(
            own_color=own_color,
            pieces_locations=state.pieces_locations,
            current_turn=state.current_turn,
            turns_started=state.turns_started,
            own_cards=state.get_cards_for(own_color),
            opponent_card_count=len(state.get_cards_for(opponent_color)),
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

    def determinize(self, rng: random.Random) -> GameState:
        """Tworzy możliwy pełny stan z ukrytą ręką wylosowaną wg prawdziwych szans."""
        opponent_cards = _sample_opponent_hand(self.opponent_card_count, rng)
        white_cards = (
            copy.deepcopy(self.own_cards)
            if self.own_color == COLOR.WHITE
            else opponent_cards
        )
        black_cards = (
            copy.deepcopy(self.own_cards)
            if self.own_color == COLOR.BLACK
            else opponent_cards
        )
        return GameState(
            pieces_locations=copy.deepcopy(self.pieces_locations),
            current_turn=self.current_turn,
            turns_started=copy.deepcopy(self.turns_started),
            white_cards=white_cards,
            black_cards=black_cards,
            captured_white=copy.deepcopy(self.captured_white),
            captured_black=copy.deepcopy(self.captured_black),
            board_card_available=self.board_card_available,
            board_card_position=self.board_card_position,
            board_enchantment=copy.deepcopy(self.board_enchantment),
            pending_board_card_delay=self.pending_board_card_delay,
            selected_card=self.selected_card,
            selected_piece_position=self.selected_piece_position,
            selected_captured_piece=self.selected_captured_piece,
            double_move_step=self.double_move_step,
            double_move_collected_board_card=self.double_move_collected_board_card,
            resurrection_moves=copy.deepcopy(self.resurrection_moves),
            random_state=rng.getstate(),
            board_cards=copy.deepcopy(self.board_cards),
        )

    @staticmethod
    def opponent_card_probabilities():
        """Pobiera bieżący rozkład losowania z konfiguracji talii gry."""
        return EnchantmentCardType.draw_probability_distribution()


def _opponent_of(color):
    return COLOR.BLACK if color == COLOR.WHITE else COLOR.WHITE


def _sample_opponent_hand(card_count, rng):
    if not 0 <= card_count <= 8:
        raise ValueError("Opponent card count must be between 0 and 8")

    cards = []
    while len(cards) < card_count:
        card_type, uses = EnchantmentCardType.sample_with_uses(rng)
        card = card_type.create(uses=uses)
        matching_reusable = next(
            (
                existing for existing in cards
                if card.is_reusable()
                and existing.is_reusable()
                and existing.get_card_type() == card_type
            ),
            None,
        )
        if matching_reusable is not None:
            matching_reusable.add_uses(card.get_remaining_uses())
        else:
            cards.append(card)
    return cards
