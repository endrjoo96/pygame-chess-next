import math
import random
import time
from dataclasses import dataclass
from typing import Optional

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import id_to_xy, xy_to_id
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState


PIECE_VALUES = {
    PIECE_TYPE.PAWN: 1.0,
    PIECE_TYPE.KNIGHT: 3.0,
    PIECE_TYPE.BISHOP: 3.25,
    PIECE_TYPE.ROOK: 5.0,
    PIECE_TYPE.QUEEN: 9.0,
    PIECE_TYPE.KING: 0.0,
    PIECE_TYPE.EMPTY: 0.0,
}

CARD_VALUES = {
    EnchantmentCardType.PAWN_TWO_FIELDS_FORWARD: 1.0,
    EnchantmentCardType.PAWN_ONE_FIELD_BACKWARD: 1.0,
    EnchantmentCardType.KNIGHT_ONE_FIELD_ANY_DIRECTION: 1.25,
    EnchantmentCardType.ROOK_JUMP_ALLIES: 1.0,
    EnchantmentCardType.QUEEN_JUMP_ALLIES: 1.75,
    EnchantmentCardType.PAWN_DETONATION: 1.0,
    EnchantmentCardType.PAWN_DETONATION_DELAYED_1: 1.0,
    EnchantmentCardType.PAWN_DETONATION_DELAYED_2: 1.0,
    EnchantmentCardType.PAWN_SWORDSMAN: 1.0,
    EnchantmentCardType.KING_PAWN_RESURRECTION: 1.5,
    EnchantmentCardType.KING_KNIGHT_RESURRECTION: 1.75,
    EnchantmentCardType.KING_BISHOP_RESURRECTION: 1.75,
    EnchantmentCardType.KING_ROOK_RESURRECTION: 2.5,
    EnchantmentCardType.KING_QUEEN_RESURRECTION: 3.5,
    EnchantmentCardType.ROOK_TOWER_THROW: 2.0,
    EnchantmentCardType.PIECE_TELEPORT: 1.5,
    EnchantmentCardType.PIECE_DOUBLE_MOVE: 2.0,
}


@dataclass(frozen=True)
class SearchConfig:
    """Limity obliczeń i próbkowania ukrytej ręki dla jednego wyboru ruchu."""

    time_limit_seconds: float = 0.75
    max_depth: int = 4
    hidden_hand_samples: int = 4

    def __post_init__(self):
        if self.time_limit_seconds <= 0:
            raise ValueError("The search time limit must be positive")
        if self.max_depth < 1:
            raise ValueError("The search depth must be at least one")
        if self.hidden_hand_samples < 1:
            raise ValueError("At least one hidden-hand sample is required")


@dataclass(frozen=True)
class SearchResult:
    action: Optional[GameAction]
    score: float
    completed_depth: int
    visited_nodes: int


class _SearchTimeout(Exception):
    pass


class ChessAI:
    """Wybiera akcje z perspektywy czarnych, nie otrzymując kart wroga."""

    def __init__(self, config: SearchConfig = SearchConfig()):
        self.config = config
        self.rng = random.Random()
        self._deadline = 0.0
        self._nodes = 0

    def choose_action(
        self,
        observation: GameObservation,
        rng: Optional[random.Random] = None,
    ) -> SearchResult:
        """Szuka ruchu w próbkach ukrytych rąk i zwraca wynik ostatniej pełnej głębokości."""
        if observation.own_color != COLOR.BLACK:
            raise ValueError("ChessAI is configured to play as black")
        if observation.current_turn != COLOR.BLACK:
            raise ValueError("It is not the AI player's turn")

        rng = rng or self.rng
        samples = [
            observation.determinize(rng)
            for _ in range(self.config.hidden_hand_samples)
        ]
        root_actions = GameSimulation.available_actions(samples[0])
        if not root_actions:
            return SearchResult(None, self.evaluate(samples[0]), 0, 0)
        if any(GameSimulation.available_actions(sample) != root_actions for sample in samples[1:]):
            raise ValueError("The AI's legal actions differ across hidden-hand samples")

        self._deadline = time.monotonic() + self.config.time_limit_seconds
        self._nodes = 0
        ordered_actions = self._order_actions(samples[0], root_actions)
        best_action = ordered_actions[0]
        best_score = self._quick_action_score(samples[0], best_action)
        completed_depth = 0

        for depth in range(1, self.config.max_depth + 1):
            try:
                depth_scores = []
                for action in ordered_actions:
                    self._check_deadline()
                    scores = []
                    for sample in samples:
                        child = GameSimulation.apply(sample, action)
                        scores.append(self._search(child, depth - 1, -math.inf, math.inf))
                    depth_scores.append((sum(scores) / len(scores), action))
            except _SearchTimeout:
                break

            best_score, best_action = max(depth_scores, key=lambda item: item[0])
            completed_depth = depth
            ordered_actions = [
                action for _, action in sorted(depth_scores, key=lambda item: item[0], reverse=True)
            ]

        return SearchResult(best_action, best_score, completed_depth, self._nodes)

    def _search(self, state: GameState, depth: int, alpha: float, beta: float) -> float:
        self._check_deadline()
        self._nodes += 1

        winner = state.get_winner()
        if winner is not None:
            return 100_000.0 if winner == COLOR.BLACK else -100_000.0
        if depth <= 0:
            return self.evaluate(state)

        actions = GameSimulation.available_actions(state)
        if not actions:
            return self.evaluate(state)
        actions = self._order_actions(state, actions)

        if state.current_turn == COLOR.BLACK:
            value = -math.inf
            for action in actions:
                child = GameSimulation.apply(state, action)
                value = max(value, self._search(child, depth - 1, alpha, beta))
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
            return value

        value = math.inf
        for action in actions:
            child = GameSimulation.apply(state, action)
            value = min(value, self._search(child, depth - 1, alpha, beta))
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value

    @staticmethod
    def evaluate(state: GameState) -> float:
        """Ocenia materiał, ruchliwość, ogłuszenia, widoczne efekty i karty."""
        winner = state.get_winner()
        if winner is not None:
            return 100_000.0 if winner == COLOR.BLACK else -100_000.0

        score = 0.0
        for position, piece in state.pieces_locations.items():
            if not piece.exists():
                continue
            sign = 1 if piece.get_color() == COLOR.BLACK else -1
            value = PIECE_VALUES[piece.get_type()]
            if piece.is_stunned():
                value *= 0.75
            value += 0.15 * len(piece.get_enchantments_to_alter_behavior())
            value -= 0.05 * sum(
                remaining or 0
                for _, _, remaining in piece.get_effects(
                    state.turns_started[piece.get_color()])
            )
            score += sign * value

            if piece.can_receive_enchantment():
                mobility = len(GameSimulation.destinations_for(
                    piece, position, state.pieces_locations))
                score += sign * min(mobility, 12) * 0.025

        for color in (COLOR.BLACK, COLOR.WHITE):
            sign = 1 if color == COLOR.BLACK else -1
            for card in state.get_cards_for(color):
                card_type = card.get_card_type()
                card_value = CARD_VALUES.get(card_type, 0.75)
                if card.is_reusable():
                    card_value *= min(1.0, card.get_remaining_uses() / 2)
                score += sign * card_value

        return score

    def _order_actions(self, state, actions):
        return sorted(
            actions,
            key=lambda action: self._quick_action_score(state, action),
            reverse=state.current_turn == COLOR.BLACK,
        )

    @staticmethod
    def _quick_action_score(state, action):
        score = 0.0
        target = state.pieces_locations.get(action.destination)
        if target is not None and target.exists():
            score += PIECE_VALUES[target.get_type()] * 10
        if action.action_type == GameActionType.PROMOTE:
            score += 60
        elif action.action_type == GameActionType.RESURRECT:
            score += 35
        elif action.action_type == GameActionType.TELEPORT:
            score += 20
        elif action.action_type == GameActionType.APPLY_PASSIVE:
            score += 5

        if (
            action.card_index >= 0
            and action.card_index < len(state.get_cards_for(state.current_turn))
        ):
            card = state.get_cards_for(state.current_turn)[action.card_index]
            score += CARD_VALUES.get(card.get_card_type(), 0.75)

        if target is not None and target.get_type() == PIECE_TYPE.KING:
            score += 100_000
        if action.destination and action.source != action.destination:
            score += abs(action.destination - action.source) * 0.001
        return score

    def _check_deadline(self):
        if time.monotonic() >= self._deadline:
            raise _SearchTimeout
