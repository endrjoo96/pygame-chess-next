from types import SimpleNamespace

import pygame

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.game_rules import GameAction, GameActionType
from logic.stage.action_animation import ActionAnimation
from models.chess_pieces import Piece
from processors.cards_processor import CardsProcessor


class AnimationState:
    def __init__(self, pieces, cards=None, captured=None):
        self.pieces_locations = pieces
        self.current_turn = COLOR.WHITE
        self._cards = cards or {COLOR.WHITE: [], COLOR.BLACK: []}
        self._captured = captured or {
            COLOR.WHITE: [],
            COLOR.BLACK: [],
        }

    def get_cards_for(self, color):
        return self._cards[color]

    def get_captured_for(self, color):
        return self._captured[color]


class FakeCardsProcessor:
    CARD_COLUMNS = 2

    @staticmethod
    def render_preview(surface, _chess_pieces, _card, _position, _color):
        surface.fill((30, 180, 230))


class RecordingPieceSprite:
    def __init__(self):
        self.draws = []

    def draw(self, _surface, piece_name, position):
        self.draws.append((piece_name, position))


def make_context():
    square_length = 80
    coordinates = [
        [
            (300 + x * square_length, 120 + y * square_length)
            for y in range(8)
        ]
        for x in range(8)
    ]
    return SimpleNamespace(
        square_length=square_length,
        chessboard_coordinates=coordinates,
        board_starting_point=(300, 120),
        card_width=140,
        card_height=210,
        white_cards_coordinates=[[(960, 0), (1100, 0)]],
        black_cards_coordinates=[[(0, 0), (140, 0)]],
        captured_white_starting_point=(300, 760),
        captured_black_starting_point=(300, 0),
        piece_cell_thumbnail_width=40,
        piece_cell_thumbnail_height=40,
    )


def test_move_and_used_card_animate_together(monkeypatch):
    ticks = [100]
    monkeypatch.setattr(
        "logic.stage.action_animation.pygame.time.get_ticks",
        lambda: ticks[0],
    )
    source = 1
    destination = 2
    before = AnimationState(
        {source: Piece(COLOR.WHITE, PIECE_TYPE.PAWN), destination: Piece()},
        cards={COLOR.WHITE: [object()], COLOR.BLACK: []},
    )
    after = AnimationState(
        {source: Piece(), destination: Piece(COLOR.WHITE, PIECE_TYPE.PAWN)},
        cards={COLOR.WHITE: [], COLOR.BLACK: []},
    )
    animation = ActionAnimation.from_transition(
        before,
        after,
        GameAction(GameActionType.MOVE, source, destination, card_index=0),
        make_context(),
        FakeCardsProcessor(),
        object(),
        300,
    )

    assert animation is not None
    assert animation.hidden_piece_positions() == (destination,)
    assert animation.hidden_card_slot == (COLOR.WHITE, 0)

    sprite = RecordingPieceSprite()
    surface = pygame.Surface((1240, 880))
    ticks[0] = 250
    assert animation.draw(surface, sprite)
    assert sprite.draws == [("white_pawn", (340, 120))]
    assert animation.is_active

    ticks[0] = 400
    assert not animation.is_active
    assert animation.hidden_piece_positions() == ()
    assert animation.hidden_card_slot is None


def test_teleport_animates_both_swapped_pieces(monkeypatch):
    monkeypatch.setattr(
        "logic.stage.action_animation.pygame.time.get_ticks", lambda: 0)
    before = AnimationState({
        1: Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT),
        2: Piece(COLOR.WHITE, PIECE_TYPE.ROOK),
    })
    after = AnimationState({
        1: Piece(COLOR.WHITE, PIECE_TYPE.ROOK),
        2: Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT),
    })

    animation = ActionAnimation.from_transition(
        before,
        after,
        GameAction(GameActionType.TELEPORT, 1, 2),
        make_context(),
        FakeCardsProcessor(),
        object(),
        300,
    )

    assert animation is not None
    assert animation.hidden_piece_positions() == (2, 1)
    sprite = RecordingPieceSprite()
    assert animation.draw(pygame.Surface((1240, 880)), sprite)
    assert sprite.draws == [
        ("white_knight", (300, 120)),
        ("white_rook", (380, 120)),
    ]


def test_resurrection_animates_a_captured_piece_out_of_its_panel(monkeypatch):
    monkeypatch.setattr(
        "logic.stage.action_animation.pygame.time.get_ticks", lambda: 0)
    resurrected_piece = Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)
    before = AnimationState(
        {1: Piece(), 3: Piece()},
        cards={COLOR.WHITE: [object()], COLOR.BLACK: []},
        captured={COLOR.WHITE: [resurrected_piece], COLOR.BLACK: []},
    )
    after = AnimationState(
        {1: Piece(), 3: Piece(COLOR.WHITE, PIECE_TYPE.KNIGHT)},
        cards={COLOR.WHITE: [], COLOR.BLACK: []},
        captured={COLOR.WHITE: [], COLOR.BLACK: []},
    )

    animation = ActionAnimation.from_transition(
        before,
        after,
        GameAction(
            GameActionType.RESURRECT,
            1,
            3,
            card_index=0,
            captured_color=COLOR.WHITE,
            captured_index=0,
        ),
        make_context(),
        FakeCardsProcessor(),
        object(),
        300,
    )

    assert animation is not None
    assert animation.hidden_piece_positions() == (3,)
    assert animation.hidden_captured_slot == (COLOR.WHITE, 0)
    assert animation.piece_motions[0].start_size == (40, 40)
    assert animation.piece_motions[0].end_size == (80, 80)


def test_zero_duration_disables_action_animation():
    before = AnimationState({1: Piece(COLOR.WHITE, PIECE_TYPE.PAWN)})
    after = AnimationState({2: Piece(COLOR.WHITE, PIECE_TYPE.PAWN)})

    assert ActionAnimation.from_transition(
        before,
        after,
        GameAction(GameActionType.MOVE, 1, 2),
        make_context(),
        FakeCardsProcessor(),
        object(),
        0,
    ) is None


def test_cards_processor_hides_the_hand_slot_being_animated(monkeypatch):
    processor = CardsProcessor.__new__(CardsProcessor)
    rendered_positions = []
    setattr(
        processor,
        "_CardsProcessor__render_card",
        lambda _screen, coords, *_args: rendered_positions.append(tuple(coords)),
    )

    processor._CardsProcessor__render_cards(
        object(),
        [[(0, 0), (40, 0)], [(0, 40), (40, 40)]],
        object(),
        [object(), object(), object()],
        (40, 40),
        (0, 0, 0, 0),
        "white",
        COLOR.WHITE,
        None,
        (COLOR.WHITE, 1),
    )

    assert rendered_positions == [(0, 0), (0, 40)]
