"""Klient DataChannel P2P korzystający z mostu JavaScript przeglądarki."""

import json

from logic.game_rules import GameAction
from network.protocol import (
    PROTOCOL_VERSION,
    decode_action,
    encode_action,
    encode_message,
    normalize_room_code,
)


class WebRtcPeer:
    """Udostępnia klientowi gry zdarzenia i akcje przez WebRTC DataChannel."""

    def __init__(self):
        self._outgoing_sequence = 0
        self._incoming_sequence = 0

    @staticmethod
    def _bridge():
        from js import window

        bridge = window.chessNetwork
        if bridge is None:
            raise RuntimeError("The browser network bridge is not loaded")
        return bridge

    def start_host(self, signaling_url, seed):
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("The game seed must be an integer")
        self._bridge().startHost(signaling_url, str(seed))

    def start_guest(self, signaling_url, room_code):
        normalized_code = normalize_room_code(room_code)
        if normalized_code is None:
            raise ValueError("Invalid room code")
        self._bridge().startGuest(signaling_url, normalized_code)

    def poll_events(self):
        raw = str(self._bridge().popMessages())
        try:
            messages = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise RuntimeError("The browser network bridge returned invalid JSON") from error
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
            seq=self._outgoing_sequence,
            action=encode_action(action),
        )
        if not self._bridge().sendMessage(message):
            raise RuntimeError("The WebRTC DataChannel is not connected")
        self._outgoing_sequence += 1

    def receive_action(self, message):
        if (
            not isinstance(message, dict)
            or message.get("v") != PROTOCOL_VERSION
            or message.get("t") != "action"
        ):
            raise ValueError("Expected a network action message")
        sequence = message.get("seq")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence != self._incoming_sequence
        ):
            raise ValueError("Unexpected network action sequence")
        try:
            action = decode_action(message["action"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid network action") from error
        self._incoming_sequence += 1
        return action

    def close(self):
        self._bridge().close()
