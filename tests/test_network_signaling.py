"""Testy autorytatywnego serwera partii i zarzadzania pokojami."""

import asyncio

from logic.game_simulation import GameSimulation
from network.protocol import decode_message, encode_action, encode_message
from server.signaling import GameServer


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, message):
        self.sent.append(message)

    async def close(self):
        self.closed = True


async def _create_and_join(server, seed=7):
    server.seed_factory = lambda: seed
    host, guest = FakeWebSocket(), FakeWebSocket()
    await server._create_room(
        host, decode_message(encode_message("create_room"))
    )
    code = decode_message(host.sent[-1])["room"]
    await server._join_room(
        guest, decode_message(encode_message("join_room", room=code))
    )
    return host, guest, code


def test_room_creation_starts_game_when_guest_joins():
    async def scenario():
        server = GameServer(seed_factory=lambda: 987654)
        host, guest = FakeWebSocket(), FakeWebSocket()
        await server._create_room(
            host, decode_message(encode_message("create_room", seed=1))
        )
        created = decode_message(host.sent[-1])
        code = created["room"]
        await server._join_room(
            guest, decode_message(encode_message("join_room", room=code.lower()))
        )

        assert created["t"] == "room_created"
        assert created["seed"] == "987654"
        assert decode_message(guest.sent[0]) == {
            "v": 2, "t": "room_joined", "room": code, "seed": "987654"
        }
        assert decode_message(host.sent[-1]) == {
            "v": 2, "t": "game_started", "room": code,
            "seed": "987654", "color": "white",
        }
        assert decode_message(guest.sent[-1]) == {
            "v": 2, "t": "game_started", "room": code,
            "seed": "987654", "color": "black",
        }
        assert server.connections[host] == (code, "host")
        assert server.connections[guest] == (code, "guest")
        assert server.rooms[code].state.cache_key() == (
            GameSimulation.create_initial_state(987654).cache_key()
        )

    asyncio.run(scenario())


def test_server_accepts_only_legal_turn_actions_and_broadcasts_them():
    server = GameServer()
    async def scenario():
        host, guest, code = await _create_and_join(server, seed=7)
        room = server.rooms[code]
        action = GameSimulation.available_actions(room.state)[0]
        request = encode_message(
            "action", seq=0, action=encode_action(action))

        await server._receive(host, request)

        assert room.next_sequence == 1
        assert room.state.current_turn.value == "black"
        host_action = decode_message(host.sent[-1])
        guest_action = decode_message(guest.sent[-1])
        assert host_action == guest_action
        assert host_action == {
            "v": 2,
            "t": "action",
            "seq": 0,
            "actor": "white",
            "action": encode_action(action),
        }

    asyncio.run(scenario())


def test_server_and_clients_stay_in_sync_across_both_turns():
    server = GameServer()

    async def scenario():
        host, guest, code = await _create_and_join(server, seed=41)
        room = server.rooms[code]
        client_state = GameSimulation.create_initial_state(41)

        for sequence, websocket in enumerate((host, guest)):
            action = GameSimulation.available_actions(client_state)[0]
            client_state = GameSimulation.apply(
                client_state, action, advance_board_card_clock=True)
            await server._receive(
                websocket,
                encode_message(
                    "action",
                    seq=sequence,
                    action=encode_action(action),
                ),
            )
            assert room.state.cache_key() == client_state.cache_key()

        assert room.next_sequence == 2

    asyncio.run(scenario())


def test_server_rejects_wrong_turn_illegal_and_out_of_order_actions():
    server = GameServer()
    async def send_requests():
        host, guest, _ = await _create_and_join(server)
        action = GameSimulation.available_actions(
            server.rooms[decode_message(host.sent[0])["room"]].state
        )[0]
        encoded_action = encode_action(action)
        await server._receive(
            guest, encode_message("action", seq=0, action=encoded_action))
        await server._receive(
            host, encode_message("action", seq=1, action=encoded_action))
        await server._receive(
            host, encode_message("action", seq=0, action={
                **encoded_action, "source": 999,
            }))
        return host, guest

    host, guest = asyncio.run(send_requests())

    assert [
        decode_message(raw)["reason"] for raw in guest.sent
        if decode_message(raw)["t"] == "action_rejected"
    ] == ["not_your_turn"]
    assert [
        decode_message(raw)["reason"] for raw in host.sent
        if decode_message(raw)["t"] == "action_rejected"
    ] == ["unexpected_sequence", "illegal_action"]
    assert server.rooms[decode_message(host.sent[0])["room"]].next_sequence == 0


def test_full_unknown_rooms_and_webrtc_messages_are_rejected():
    async def scenario():
        server = GameServer()
        host, guest, code = await _create_and_join(server)
        another_guest = FakeWebSocket()
        await server._join_room(
            another_guest, decode_message(encode_message("join_room", room=code)))
        await server._join_room(
            another_guest, decode_message(encode_message("join_room", room="ZZZZZZ")))
        await server._receive(host, encode_message("offer", description={"sdp": "x"}))

        assert decode_message(another_guest.sent[-2])["reason"] == "room_full"
        assert decode_message(another_guest.sent[-1])["reason"] == "room_not_found"
        assert decode_message(host.sent[-1])["reason"] == "unsupported_message"
        assert guest.closed is False

    asyncio.run(scenario())


def test_disconnect_closes_room_peer_and_removes_room():
    server = GameServer()
    async def scenario():
        host, guest, code = await _create_and_join(server)
        await server._disconnect(host)
        return guest, code

    guest, code = asyncio.run(scenario())

    assert code not in server.rooms
    assert guest.closed
    assert decode_message(guest.sent[-1])["t"] == "peer_disconnected"
    assert not server.connections


def test_websocket_clients_receive_only_server_accepted_actions():
    import pytest

    async def scenario():
        pytest.importorskip("websockets.asyncio.server")
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        game_server = GameServer(seed_factory=lambda: 41)
        async with serve(game_server.handle, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            url = "ws://127.0.0.1:{}".format(port)
            async with connect(url) as host, connect(url) as guest:
                await host.send(encode_message("create_room"))
                created = decode_message(await host.recv())
                await guest.send(
                    encode_message("join_room", room=created["room"]))
                joined = decode_message(await guest.recv())
                host_notice = decode_message(await host.recv())
                host_started = decode_message(await host.recv())
                guest_started = decode_message(await guest.recv())

                state = GameSimulation.create_initial_state(41)
                action = GameSimulation.available_actions(state)[0]
                await host.send(encode_message(
                    "action", seq=0, action=encode_action(action)))
                host_action = decode_message(await host.recv())
                guest_action = decode_message(await guest.recv())

                assert joined["t"] == "room_joined"
                assert host_notice["t"] == "player_joined"
                assert host_started["color"] == "white"
                assert guest_started["color"] == "black"
                assert host_action == guest_action
                assert host_action["action"] == encode_action(action)

    asyncio.run(scenario())
