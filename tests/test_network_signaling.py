"""Testy zarządzania pokojami i przekazywania sygnalizacji WebRTC."""

import asyncio
import json

from network.protocol import decode_message, encode_message
from server.signaling import SignalingServer


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, message):
        self.sent.append(message)

    async def close(self):
        self.closed = True


def test_room_creation_and_join_share_the_host_seed():
    async def scenario():
        server = SignalingServer()
        host = FakeWebSocket()
        guest = FakeWebSocket()

        await server._create_room(
            host, decode_message(encode_message("create_room", seed=987654))
        )
        created = decode_message(host.sent[-1])
        code = created["room"]
        await server._join_room(
            guest, decode_message(encode_message("join_room", room=code.lower()))
        )

        assert created["t"] == "room_created"
        assert created["seed"] == "987654"
        assert decode_message(guest.sent[-1]) == {
            "v": 1, "t": "room_joined", "room": code, "seed": "987654"
        }
        assert decode_message(host.sent[-1])["t"] == "peer_joined"
        assert server.connections[host] == (code, "host")
        assert server.connections[guest] == (code, "guest")

    asyncio.run(scenario())


def test_full_or_unknown_rooms_are_rejected():
    async def scenario():
        server = SignalingServer()
        host, guest, another_guest = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
        await server._create_room(
            host, decode_message(encode_message("create_room", seed=1))
        )
        code = decode_message(host.sent[-1])["room"]
        await server._join_room(
            guest, decode_message(encode_message("join_room", room=code))
        )
        await server._join_room(
            another_guest, decode_message(encode_message("join_room", room=code))
        )
        await server._join_room(
            another_guest, decode_message(encode_message("join_room", room="ZZZZZZ"))
        )

        assert decode_message(another_guest.sent[-2])["reason"] == "room_full"
        assert decode_message(another_guest.sent[-1])["reason"] == "room_not_found"

    asyncio.run(scenario())


def test_only_webrtc_negotiation_messages_are_relayed():
    async def scenario():
        server = SignalingServer()
        host, guest = FakeWebSocket(), FakeWebSocket()
        await server._create_room(
            host, decode_message(encode_message("create_room", seed=7))
        )
        code = decode_message(host.sent[-1])["room"]
        await server._join_room(
            guest, decode_message(encode_message("join_room", room=code))
        )

        offer = {"type": "offer", "sdp": "offer-sdp"}
        await server._relay(host, encode_message("offer", description=offer))
        await server._relay(host, encode_message("action", action={"type": "move"}))

        assert json.loads(guest.sent[-1]) == {
            "v": 1, "t": "offer", "description": offer
        }
        assert decode_message(host.sent[-1])["reason"] == "unsupported_message"

    asyncio.run(scenario())


def test_disconnect_closes_room_peer_and_removes_room():
    async def scenario():
        server = SignalingServer()
        host, guest = FakeWebSocket(), FakeWebSocket()
        await server._create_room(
            host, decode_message(encode_message("create_room", seed=1))
        )
        code = decode_message(host.sent[-1])["room"]
        await server._join_room(
            guest, decode_message(encode_message("join_room", room=code))
        )

        await server._disconnect(host)

        assert code not in server.rooms
        assert guest.closed
        assert decode_message(guest.sent[-1])["t"] == "peer_left"
        assert not server.connections

    asyncio.run(scenario())


def test_websocket_server_handles_room_and_relay_lifecycle():
    import pytest

    async def scenario():
        pytest.importorskip("websockets.asyncio.server")
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        signaling = SignalingServer()
        async with serve(signaling.handle, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            url = "ws://127.0.0.1:{}".format(port)
            async with connect(url) as host, connect(url) as guest:
                await host.send(encode_message("create_room", seed="18446744073709551615"))
                created = decode_message(await host.recv())
                await guest.send(
                    encode_message("join_room", room=created["room"]))
                joined = decode_message(await guest.recv())
                host_notice = decode_message(await host.recv())
                await host.send(
                    encode_message("offer", description={"sdp": "offer"}))
                relayed = decode_message(await guest.recv())

                assert created["seed"] == "18446744073709551615"
                assert joined["seed"] == created["seed"]
                assert host_notice["t"] == "peer_joined"
                assert relayed == {
                    "v": 1,
                    "t": "offer",
                    "description": {"sdp": "offer"},
                }

    asyncio.run(scenario())
