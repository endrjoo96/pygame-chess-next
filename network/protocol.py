"""Serializacja akcji gry do wiadomości sieciowych. Bez zależności od Pygame i UI."""

import json
import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from logic.game_rules import GameAction, GameActionType

PROTOCOL_VERSION = 2
ROOM_CODE_LENGTH = 6
_ROOM_CODE_PATTERN = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")


def encode_action(action: GameAction) -> dict[str, Any]:
    return {
        "type": action.action_type.value,
        "source": action.source,
        "destination": action.destination,
        "card_index": action.card_index,
        "captured_color": action.captured_color.value,
        "captured_index": action.captured_index,
        "secondary_source": action.secondary_source,
        "promotion_type": (
            action.promotion_type.value if action.promotion_type is not None else None
        ),
    }


def decode_action(payload: dict[str, Any]) -> GameAction:
    if not isinstance(payload, dict):
        raise ValueError("An action payload must be an object")

    def integer(name, default=None):
        value = payload.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Invalid integer field '{}'".format(name))
        return value

    promotion = payload.get("promotion_type")
    captured_color = payload.get("captured_color", COLOR.EMPTY.value)
    if not isinstance(captured_color, str):
        raise ValueError("Invalid captured color")
    if promotion is not None and not isinstance(promotion, str):
        raise ValueError("Invalid promotion type")
    return GameAction(
        action_type=GameActionType(payload["type"]),
        source=integer("source"),
        destination=integer("destination", 0),
        card_index=integer("card_index", -1),
        captured_color=COLOR(captured_color),
        captured_index=integer("captured_index", -1),
        secondary_source=integer("secondary_source", 0),
        promotion_type=PIECE_TYPE(promotion) if promotion is not None else None,
    )


def encode_message(message_type: str, **fields: Any) -> str:
    if not isinstance(message_type, str) or not message_type:
        raise ValueError("A message type must be a non-empty string")
    if "v" in fields or "t" in fields:
        raise ValueError("Message fields cannot replace protocol metadata")
    return json.dumps(
        {"v": PROTOCOL_VERSION, "t": message_type, **fields},
        separators=(",", ":"),
    )


def decode_message(raw: str) -> Optional[dict[str, Any]]:
    """Zwraca wiadomość albo None, gdy dane są niepoprawne lub w obcej wersji."""
    try:
        message = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(message, dict):
        return None
    if message.get("v") != PROTOCOL_VERSION or not isinstance(message.get("t"), str):
        return None
    return message


def normalize_room_code(value: Any) -> Optional[str]:
    """Normalizuje prawidłowy kod pokoju albo zwraca None."""
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if _ROOM_CODE_PATTERN.fullmatch(code) else None


def room_code_from_invite_url(invite_url: str) -> Optional[str]:
    """Odczytuje kod pokoju z parametru `room` linku zaproszenia."""
    if not isinstance(invite_url, str):
        return None
    try:
        values = parse_qs(urlsplit(invite_url).query, keep_blank_values=True).get(
            "room", []
        )
    except ValueError:
        return None
    if len(values) != 1:
        return None
    return normalize_room_code(values[0])


def build_invite_url(page_url: str, room_code: str) -> str:
    """Dodaje kod pokoju do adresu strony, zachowując pozostałe parametry."""
    normalized_code = normalize_room_code(room_code)
    if normalized_code is None:
        raise ValueError("Invalid room code")
    parts = urlsplit(page_url)
    query = parse_qs(parts.query, keep_blank_values=True)
    query["room"] = [normalized_code]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment)
    )
