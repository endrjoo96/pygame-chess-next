import math
import os
import random
import time
from concurrent.futures import ALL_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from typing import Callable, Optional

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from constants.pos import id_to_xy, xy_to_id
from logic.game_rules import GameAction, GameActionType
from logic.game_simulation import GameSimulation
from models.enchantment_cards import EnchantmentCardType
from models.game_observation import GameObservation
from models.game_state import GameState
from utils.run_config import (
    AI_SEARCH_CPU_PERCENT,
    AI_SEARCH_MAX_DEPTH,
    AI_SEARCH_TIME_LIMIT_SECONDS,
    GAME_SEED,
)


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
CARD_MOVEMENT_TYPES = GameSimulation.MOVEMENT_CARDS


@dataclass(frozen=True)
class SearchConfig:
    """Limity obliczeń i próbkowania ukrytej ręki dla jednego wyboru ruchu."""

    time_limit_seconds: float = AI_SEARCH_TIME_LIMIT_SECONDS
    max_depth: int = AI_SEARCH_MAX_DEPTH
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


def _evaluate_root_action(sample, action, depth, config, deadline):
    """Ocenia jeden ruch startowy w izolowanym workerze."""
    worker = ChessAI(config, max_workers=1)
    worker._deadline = deadline
    worker._nodes = 0
    try:
        worker._check_deadline()
        child = GameSimulation.apply(sample, action)
        score = worker._search(child, depth - 1, -math.inf, math.inf)
    except _SearchTimeout:
        return None, worker._nodes
    return score, worker._nodes


class ChessAI:
    """Wybiera akcje z perspektywy czarnych, nie otrzymując kart wroga."""

    def __init__(
        self,
        config: SearchConfig = SearchConfig(),
        max_workers: Optional[int] = None,
        cpu_percent: int = AI_SEARCH_CPU_PERCENT,
    ):
        if max_workers is not None and max_workers < 1:
            raise ValueError("The worker count must be at least one")
        if not 1 <= cpu_percent <= 100:
            raise ValueError("The CPU usage percentage must be between 1 and 100")
        self.config = config
        logical_cpu_count = os.cpu_count() or 1
        self.max_workers = (
            max_workers
            if max_workers is not None
            else max(1, logical_cpu_count * cpu_percent // 100)
        )
        self._deadline = 0.0
        self._nodes = 0

    def choose_action(
        self,
        observation: GameObservation,
        rng: Optional[random.Random] = None,
        progress_callback: Optional[Callable[[GameAction, int], None]] = None,
    ) -> SearchResult:
        """Szuka ruchu w próbkach ukrytych rąk i zwraca wynik ostatniej pełnej głębokości."""
        if observation.own_color != COLOR.BLACK:
            raise ValueError("ChessAI is configured to play as black")
        if observation.current_turn != COLOR.BLACK:
            raise ValueError("It is not the AI player's turn")

        if rng is None:
            rng = random.Random(GAME_SEED if GAME_SEED is not None else 0)
            rng.setstate(observation.random_state)
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
        if progress_callback is not None:
            progress_callback(best_action, completed_depth)

        worker_count = self._worker_count_for_tasks(
            len(ordered_actions) * len(samples))
        executor = (
            ProcessPoolExecutor(max_workers=worker_count)
            if worker_count > 1
            else None
        )
        try:
            for depth in range(1, self.config.max_depth + 1):
                if time.monotonic() >= self._deadline:
                    break
                depth_scores = []
                if executor is None:
                    for action in ordered_actions:
                        scores = []
                        for sample in samples:
                            score, nodes = _evaluate_root_action(
                                sample, action, depth, self.config, self._deadline)
                            self._nodes += nodes
                            if score is None:
                                break
                            scores.append(score)
                        if len(scores) != len(samples):
                            break
                        depth_scores.append((sum(scores) / len(scores), action))
                    if len(depth_scores) != len(ordered_actions):
                        break
                else:
                    tasks_per_depth = [
                        (action, sample)
                        for action in ordered_actions
                        for sample in samples
                    ]
                    futures = [
                        executor.submit(
                            _evaluate_root_action,
                            sample,
                            action,
                            depth,
                            self.config,
                            self._deadline,
                        )
                        for action, sample in tasks_per_depth
                    ]
                    remaining = max(0.0, self._deadline - time.monotonic())
                    _, pending = wait(
                        futures, timeout=remaining, return_when=ALL_COMPLETED)
                    if pending:
                        for future in pending:
                            future.cancel()
                        executor.shutdown(wait=True, cancel_futures=True)
                        executor = None
                        for future in futures:
                            if not future.cancelled():
                                _, nodes = future.result()
                                self._nodes += nodes
                        break

                    # Preserve action order for deterministic tie-breaking.
                    results = [future.result() for future in futures]
                    self._nodes += sum(nodes for _, nodes in results)
                    if any(score is None for score, _ in results):
                        break
                    index = 0
                    for action in ordered_actions:
                        action_scores = [
                            score
                            for score, _ in results[index:index + len(samples)]
                        ]
                        index += len(samples)
                        depth_scores.append(
                            (sum(action_scores) / len(action_scores), action))

                best_score, best_action = max(
                    depth_scores, key=lambda item: item[0])
                completed_depth = depth
                if progress_callback is not None:
                    progress_callback(best_action, completed_depth)
                ordered_actions = [
                    action
                    for _, action in sorted(
                        depth_scores, key=lambda item: item[0], reverse=True)
                ]
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)

        return SearchResult(best_action, best_score, completed_depth, self._nodes)

    def _worker_count_for_tasks(self, task_count):
        return min(self.max_workers, task_count)

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
            score += sign * ChessAI._development_value(piece, position)

            if piece.can_receive_enchantment():
                mobility = len(GameSimulation.destinations_for(
                    piece, position, state.pieces_locations))
                score += sign * min(mobility, 12) * 0.025

        score += ChessAI._threat_score(state)

        for color in (COLOR.BLACK, COLOR.WHITE):
            sign = 1 if color == COLOR.BLACK else -1
            for card in state.get_cards_for(color):
                card_value = ChessAI._card_value(card)
                if card.is_reusable():
                    card_value *= min(1.0, card.get_remaining_uses() / 2)
                score += sign * card_value

        score += ChessAI._board_card_opportunity_score(state)
        return score

    @staticmethod
    def _card_value(card):
        card_type = card.get_card_type()
        if card_type.promoted_piece_type is not None:
            piece_value = PIECE_VALUES.get(card_type.piece_type, 0.0)
            upgrade_value = (
                PIECE_VALUES[card_type.promoted_piece_type] - piece_value
            )
            return max(0.0, upgrade_value * 0.45)
        return CARD_VALUES.get(card_type, 0.75)

    @staticmethod
    def _development_value(piece, position):
        piece_type = piece.get_type()
        x, y = id_to_xy(position)
        if piece_type in (PIECE_TYPE.KNIGHT, PIECE_TYPE.BISHOP):
            back_rank = 0 if piece.get_color() == COLOR.WHITE else 7
            progress = abs(y - back_rank)
            centrality = 3.5 - abs(x - 3.5)
            return min(progress, 3) * 0.07 + centrality * 0.035
        if piece_type == PIECE_TYPE.PAWN:
            progress = y if piece.get_color() == COLOR.WHITE else 7 - y
            return min(progress, 5) * 0.025
        return 0.0

    @staticmethod
    def _threat_score(state):
        """Penalizes valuable pieces that the opponent can capture next."""
        score = 0.0
        attack_map = ChessAI._attack_map(state)
        for target_position, target in state.pieces_locations.items():
            if not target.exists():
                continue
            attacker_color = (
                COLOR.BLACK if target.get_color() == COLOR.WHITE else COLOR.WHITE
            )
            attackers = attack_map[attacker_color].get(target_position, set())
            if not attackers:
                continue

            target_value = (
                80.0 if target.get_type() == PIECE_TYPE.KING
                else PIECE_VALUES[target.get_type()]
            )
            urgency = 0.75 if attacker_color == state.current_turn else 0.4
            exposure = min(1.0, 0.55 + 0.15 * (len(attackers) - 1))
            target_sign = 1 if target.get_color() == COLOR.BLACK else -1
            score -= target_sign * target_value * urgency * exposure
        return score

    @staticmethod
    def _attack_map(state):
        attack_map = {COLOR.BLACK: {}, COLOR.WHITE: {}}
        for source, piece in state.pieces_locations.items():
            if not piece.exists() or not piece.can_receive_enchantment():
                continue
            color = piece.get_color()
            destinations = GameSimulation.destinations_for(
                piece, source, state.pieces_locations)
            ChessAI._record_attacks(attack_map[color], source, destinations)

            for card in state.get_cards_for(color):
                card_type = card.get_card_type()
                if (
                    card_type not in CARD_MOVEMENT_TYPES
                    or card_type.piece_type not in (PIECE_TYPE.EMPTY, piece.get_type())
                ):
                    continue
                card_destinations = GameSimulation.destinations_for(
                    piece, source, state.pieces_locations, card)
                ChessAI._record_attacks(
                    attack_map[color],
                    source,
                    card_destinations,
                    rook_throw=(
                        card_type == EnchantmentCardType.ROOK_TOWER_THROW
                    ),
                )
        return attack_map

    @staticmethod
    def _record_attacks(attack_map, source, destinations, rook_throw=False):
        source_x, source_y = id_to_xy(source)
        for destination in destinations:
            target_x, target_y = destination
            if rook_throw:
                step_x = (target_x > source_x) - (target_x < source_x)
                step_y = (target_y > source_y) - (target_y < source_y)
                x, y = source_x + step_x, source_y + step_y
                while True:
                    position = xy_to_id(x, y)
                    attack_map.setdefault(position, set()).add(source)
                    if (x, y) == (target_x, target_y):
                        break
                    x += step_x
                    y += step_y
            else:
                position = xy_to_id(target_x, target_y)
                attack_map.setdefault(position, set()).add(source)

    @staticmethod
    def _board_card_opportunity_score(state):
        cards = state.board_cards or (
            [(state.board_card_position, state.board_enchantment)]
            if state.board_card_available and state.board_enchantment is not None
            else []
        )
        score = 0.0
        for card_position, enchantment in cards:
            x, y = id_to_xy(card_position)
            distances = {}
            for color in (COLOR.BLACK, COLOR.WHITE):
                eligible_distances = []
                for position, piece in state.pieces_locations.items():
                    if (
                        not piece.exists()
                        or piece.get_color() != color
                        or not piece.can_receive_enchantment()
                    ):
                        continue
                    piece_x, piece_y = id_to_xy(position)
                    eligible_distances.append(
                        max(abs(x - piece_x), abs(y - piece_y)))
                distances[color] = min(eligible_distances, default=8)

            card_value = ChessAI._card_value(enchantment)
            black_access = max(0.0, 1.0 - distances[COLOR.BLACK] / 8)
            white_access = max(0.0, 1.0 - distances[COLOR.WHITE] / 8)
            score += 0.3 * card_value * (black_access - white_access)
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
            score += PIECE_VALUES[target.get_type()] * 1.5
        if action.action_type == GameActionType.PROMOTE:
            score += 3
        elif action.action_type == GameActionType.RESURRECT:
            score += 2
        elif action.action_type == GameActionType.TELEPORT:
            score += 1
        elif action.action_type == GameActionType.APPLY_PASSIVE:
            score += 0.5

        if (
            action.card_index >= 0
            and action.card_index < len(state.get_cards_for(state.current_turn))
        ):
            card = state.get_cards_for(state.current_turn)[action.card_index]
            score += ChessAI._card_value(card)

        if target is not None and target.get_type() == PIECE_TYPE.KING:
            score += 100_000
        board_cards = state.board_cards or (
            [(state.board_card_position, state.board_enchantment)]
            if state.board_card_available and state.board_enchantment is not None
            else []
        )
        board_card = next(
            (card for card in board_cards if card[0] == action.destination),
            None,
        )
        if board_card is not None:
            score += ChessAI._card_value(board_card[1]) * 2
        if action.destination and action.source != action.destination:
            score += abs(action.destination - action.source) * 0.001
        return score

    def _check_deadline(self):
        if time.monotonic() >= self._deadline:
            raise _SearchTimeout
