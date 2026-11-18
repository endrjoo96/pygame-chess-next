"""Testy protokołu sieciowego: kodowanie akcji i walidacja wiadomości."""

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.game_rules import GameAction, GameActionType
from network.protocol import (
    PROTOCOL_VERSION,
    build_invite_url,
    decode_action,
    decode_message,
    encode_action,
    encode_message,
    normalize_room_code,
    room_code_from_invite_url,
)


def test_action_roundtrip_preserves_all_fields():
    action = GameAction(
        action_type=GameActionType.PROMOTE,
        source=12,
        destination=4,
        card_index=2,
        captured_color=COLOR.BLACK,
        captured_index=7,
        secondary_source=9,
        promotion_type=PIECE_TYPE.QUEEN,
    )

    assert decode_action(encode_action(action)) == action


def test_action_without_optional_fields_decodes_to_defaults():
    action = decode_action({"type": "move", "source": 1, "destination": 2})

    assert action.action_type is GameActionType.MOVE
    assert action.card_index == -1
    assert action.captured_color is COLOR.EMPTY
    assert action.promotion_type is None


def test_action_decoder_rejects_boolean_in_integer_fields():
    import pytest

    with pytest.raises(ValueError, match="integer"):
        decode_action({"type": "move", "source": True, "destination": 2})


def test_message_roundtrip():
    raw = encode_message("action", action={"type": "move"})
    message = decode_message(raw)

    assert message == {"v": PROTOCOL_VERSION, "t": "action", "action": {"type": "move"}}


def test_invalid_json_is_rejected():
    assert decode_message("{nie json") is None


def test_non_object_json_is_rejected():
    assert decode_message("[1, 2]") is None


def test_wrong_protocol_version_is_rejected():
    assert decode_message('{"v": 999, "t": "action"}') is None


def test_missing_message_type_is_rejected():
    assert decode_message('{"v": 1}') is None


def test_room_code_is_normalized_and_validated():
    assert normalize_room_code(" abcd23 ") == "ABCD23"
    assert normalize_room_code("ABC123") is None
    assert normalize_room_code("ABCDE") is None


def test_room_code_is_parsed_from_invite_url():
    assert room_code_from_invite_url(
        "https://example.github.io/game/?theme=dark&room=abcd23"
    ) == "ABCD23"
    assert room_code_from_invite_url(
        "https://example.github.io/game/?room=ABCD23&room=EFGH45"
    ) is None
    assert room_code_from_invite_url("https://example.github.io/game/") is None


def test_invite_url_preserves_path_fragment_and_other_parameters():
    assert build_invite_url(
        "https://example.github.io/game/?theme=dark#board", "abcd23"
    ) == "https://example.github.io/game/?theme=dark&room=ABCD23#board"


def test_message_metadata_cannot_be_overwritten():
    import pytest

    with pytest.raises(ValueError, match="cannot replace"):
        encode_message("action", v=999)
