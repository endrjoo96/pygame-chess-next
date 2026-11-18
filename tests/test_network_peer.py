"""Testy kontroli kolejności akcji przekazywanych przez DataChannel."""

import pytest

from constants.piece_color import COLOR
from logic.game_rules import GameAction, GameActionType
from network.peer import WebRtcPeer
from network.protocol import encode_action, encode_message


def test_received_actions_require_an_in_order_sequence():
    peer = WebRtcPeer()
    action = GameAction(GameActionType.MOVE, 1, 2)

    assert peer.receive_action(
        {"v": 1, "t": "action", "seq": 0, "action": encode_action(action)}
    ) == action
    with pytest.raises(ValueError, match="sequence"):
        peer.receive_action(
            {"v": 1, "t": "action", "seq": 0, "action": encode_action(action)}
        )


@pytest.mark.parametrize("sequence", [True, -1, "0"])
def test_received_actions_reject_invalid_sequences(sequence):
    peer = WebRtcPeer()

    with pytest.raises(ValueError, match="sequence"):
        peer.receive_action(
            {"v": 1, "t": "action", "seq": sequence, "action": encode_action(
                GameAction(GameActionType.MOVE, 1, 2)
            )}
        )


def test_received_actions_reject_malformed_action_payloads():
    peer = WebRtcPeer()

    with pytest.raises(ValueError, match="Invalid network action"):
        peer.receive_action(
            {"v": 1, "t": "action", "seq": 0, "action": {"type": "bad"}}
        )


def test_received_actions_reject_messages_of_another_type():
    peer = WebRtcPeer()

    with pytest.raises(ValueError, match="Expected a network action"):
        peer.receive_action(encode_message("offer", color=COLOR.WHITE.value))
