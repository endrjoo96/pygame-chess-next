from constants.piece_color import COLOR
from constants.pos import POS
from logic.game_rules import GameActionType
from logic.game_simulation import GameSimulation
from models.chess_pieces import Piece
from models.game_state import GameState
from models.starting_positions import pieces_starting_positions_map


_OPENING_LINES = (
    ("e2e4", "e7e5", "g1f3", "b8c6"),  # Open game
    ("e2e4", "e7e5", "f1c4", "b8c6"),  # Italian Game
    ("e2e4", "c7c5", "g1f3", "d7d6"),  # Sicilian Defense
    ("e2e4", "c7c5", "g1f3", "b8c6"),  # Sicilian Defense
    ("e2e4", "e7e6", "d2d4", "d7d5"),  # French Defense
    ("e2e4", "c7c6", "d2d4", "d7d5"),  # Caro-Kann Defense
    ("e2e4", "d7d5", "e4d5", "d8d5"),  # Scandinavian Defense
    ("d2d4", "d7d5", "c2c4", "e7e6"),  # Queen's Gambit Declined
    ("d2d4", "d7d5", "c2c4", "c7c6"),  # Slav Defense
    ("d2d4", "g8f6", "c2c4", "e7e6"),  # Indian Defense
    ("c2c4", "e7e5", "b1c3", "g8f6"),  # English Opening
    ("g1f3", "d7d5", "c2c4", "e7e6"),  # Reti Opening
)
_MAX_OPENING_HINT_TURN_SUM = max(len(line) for line in _OPENING_LINES)


def _position_key(state):
    return (
        state.current_turn,
        tuple(sorted(state.turns_started.items(), key=lambda item: item[0].value)),
        tuple(
            (position, piece.get_color(), piece.get_type(), piece.has_moved())
            for position, piece in sorted(state.pieces_locations.items())
            if piece.exists()
        ),
        state.en_passant_target,
    )


def _new_classical_state():
    pieces_locations = {
        position: Piece() for position in range(1, 65)
    }
    for position, piece in pieces_starting_positions_map.items():
        pieces_locations[position.value] = Piece(
            piece.get_color(), piece.get_type(), position.value)

    return GameState(
        pieces_locations=pieces_locations,
        current_turn=COLOR.WHITE,
        turns_started={COLOR.WHITE: 1, COLOR.BLACK: 0},
        white_cards=[],
        black_cards=[],
        captured_white=[],
        captured_black=[],
        board_card_available=False,
        board_card_position=POS.D5.value,
        board_enchantment=None,
        pending_board_card_delay=None,
    )


def _parse_move(move):
    return (
        POS[move[:2].upper()].value,
        POS[move[2:].upper()].value,
    )


def _build_opening_book():
    book = {}
    for line in _OPENING_LINES:
        state = _new_classical_state()
        for notation in line:
            source, destination = _parse_move(notation)
            action = next(
                (
                    candidate
                    for candidate in GameSimulation.available_actions(state)
                    if candidate.action_type == GameActionType.MOVE
                    and candidate.source == source
                    and candidate.destination == destination
                    and candidate.card_index == -1
                ),
                None,
            )
            if action is None:
                raise ValueError(
                    "Opening book contains an illegal classical move: "
                    + notation
                )

            key = _position_key(state)
            hints = book.setdefault(key, [])
            if (source, destination) not in hints:
                hints.append((source, destination))
            state = GameSimulation.apply(state, action)

    return {key: tuple(hints) for key, hints in book.items()}


_OPENING_BOOK = _build_opening_book()


def opening_hints(state):
    """Zwraca klasyczne ruchy książkowe dla wczesnej, zgodnej pozycji."""
    if sum(state.turns_started.values()) > _MAX_OPENING_HINT_TURN_SUM:
        return ()
    return _OPENING_BOOK.get(_position_key(state), ())
