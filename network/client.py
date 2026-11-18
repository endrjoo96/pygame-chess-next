"""Klient WebSocket do wysyłania akcji do autorytatywnego serwera gry."""

import json

from logic.game_rules import GameAction
from network.protocol import (
    PROTOCOL_VERSION,
    decode_action,
    encode_action,
    encode_message,
    normalize_room_code,
)


class WebSocketGameClient:
    """Udostępnia klientowi gry zdarzenia i akcje przez most JavaScript."""

    def __init__(self):
        self._next_sequence = 0

    @staticmethod
    def _bridge():
        from js import window

        bridge = window.chessNetwork
        if bridge is None:
            raise RuntimeError("The browser network bridge is not loaded")
        return bridge

    def start_host(self, game_server_url):
        self._next_sequence = 0
        self._bridge().startHost(game_server_url)

    def start_guest(self, game_server_url, room_code):
        normalized_code = normalize_room_code(room_code)
        if normalized_code is None:
            raise ValueError("Invalid room code")
        self._next_sequence = 0
        self._bridge().startGuest(game_server_url, normalized_code)

    def poll_events(self):
        raw = str(self._bridge().popMessages())
        try:
            messages = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "The browser network bridge returned invalid JSON") from error
        if not isinstance(messages, list) or any(
            not isinstance(message, dict)
            or not isinstance(message.get("t"), str)
            for message in messages
        ):
            raise RuntimeError("The browser network bridge returned invalid events")
        return messages

    def send_action(self, action: GameAction):
        message = encode_message(
            "action",
            seq=self._next_sequence,
            action=encode_action(action),
        )
        return bool(self._bridge().sendMessage(message))

    def receive_action(self, message):
        if (
            not isinstance(message, dict)
            or message.get("v") != PROTOCOL_VERSION
            or message.get("t") != "action"
        ):
            raise ValueError("Expected an authoritative action message")
        sequence = message.get("seq")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence != self._next_sequence
        ):
            raise ValueError("Unexpected authoritative action sequence")
        try:
            action = decode_action(message["action"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid authoritative action") from error
        self._next_sequence += 1
        return action

    def close(self):
        self._bridge().close()
