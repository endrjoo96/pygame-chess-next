"""Testy klienta WebSocket i kolejnosci akcji zatwierdzanych przez serwer."""

import json

import pytest

from logic.game_rules import GameAction, GameActionType
from network.client import WebSocketGameClient
from network.protocol import decode_message, encode_action, encode_message


class FakeBridge:
    def __init__(self):
        self.sent = []
        self.events = []

    def sendMessage(self, message):
        self.sent.append(message)
        return True

    def popMessages(self):
        return json.dumps(self.events)

    def close(self):
        pass


def test_client_sends_action_with_next_server_sequence(monkeypatch):
    bridge = FakeBridge()
    monkeypatch.setattr(
        WebSocketGameClient, "_bridge", staticmethod(lambda: bridge))
    client = WebSocketGameClient()
    action = GameAction(GameActionType.MOVE, 1, 2)

    assert client.send_action(action)
    sent = decode_message(bridge.sent[-1])

    assert sent["t"] == "action"
    assert sent["seq"] == 0
    assert sent["action"] == encode_action(action)
    assert client.receive_action({
        "v": 2, "t": "action", "seq": 0, "action": encode_action(action)
    }) == action
    assert client.send_action(action)
    assert decode_message(bridge.sent[-1])["seq"] == 1


@pytest.mark.parametrize("sequence", [True, -1, "0"])
def test_client_rejects_invalid_server_sequences(sequence):
    client = WebSocketGameClient()

    with pytest.raises(ValueError, match="sequence"):
        client.receive_action({
            "v": 2,
            "t": "action",
            "seq": sequence,
            "action": encode_action(GameAction(GameActionType.MOVE, 1, 2)),
        })


def test_client_rejects_malformed_authoritative_actions():
    client = WebSocketGameClient()

    with pytest.raises(ValueError, match="Invalid authoritative action"):
        client.receive_action(
            {"v": 2, "t": "action", "seq": 0, "action": {"type": "bad"}}
        )


def test_client_rejects_other_message_types():
    client = WebSocketGameClient()

    with pytest.raises(ValueError, match="authoritative action"):
        client.receive_action(encode_message("offer"))


def test_client_starts_room_requests_through_the_browser_bridge(monkeypatch):
    bridge = FakeBridge()
    starts = []

    def start_host(url):
        starts.append(("host", url))

    def start_guest(url, room):
        starts.append(("guest", url, room))

    bridge.startHost = start_host
    bridge.startGuest = start_guest
    monkeypatch.setattr(
        WebSocketGameClient, "_bridge", staticmethod(lambda: bridge))
    client = WebSocketGameClient()

    client.start_host("wss://game.example")
    client.start_guest("wss://game.example", "abcd23")

    assert starts == [
        ("host", "wss://game.example"),
        ("guest", "wss://game.example", "ABCD23"),
    ]
