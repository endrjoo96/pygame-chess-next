"""Autorytatywny serwer WebSocket zarządzający pokojami i stanem partii."""

import asyncio
import os
import secrets
from dataclasses import dataclass
from typing import Any, Optional

from constants.piece_color import COLOR
from logic.game_simulation import GameSimulation
from models.game_state import GameState
from network.protocol import (
    decode_action,
    decode_message,
    encode_action,
    encode_message,
    normalize_room_code,
)

_ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class Room:
    code: str
    seed: int
    state: GameState
    host: Any
    guest: Optional[Any] = None
    next_sequence: int = 0


class GameServer:
    """Tworzy partie, waliduje akcje i rozsyła zatwierdzone ruchy."""

    def __init__(self, seed_factory=None):
        self.rooms: dict[str, Room] = {}
        self.connections: dict[Any, tuple[str, str]] = {}
        self.seed_factory = seed_factory or (lambda: secrets.randbits(64))

    def _new_room_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_ROOM_ALPHABET) for _ in range(6))
            if code not in self.rooms:
                return code

    async def _send(self, websocket, message_type, **fields):
        await websocket.send(encode_message(message_type, **fields))

    async def handle(self, websocket):
        """Obsługuje pokój przez cały czas życia połączenia."""
        try:
            raw = await websocket.recv()
            message = decode_message(raw)
            if message is None:
                await self._send(websocket, "error", reason="invalid_message")
                return
            if message["t"] == "create_room":
                await self._create_room(websocket, message)
            elif message["t"] == "join_room":
                await self._join_room(websocket, message)
            else:
                await self._send(websocket, "error", reason="expected_room_request")
                return

            if websocket not in self.connections:
                return
            async for raw in websocket:
                await self._receive(websocket, raw)
        finally:
            await self._disconnect(websocket)

    async def _create_room(self, websocket, message):
        seed = self.seed_factory()
        code = self._new_room_code()
        room = Room(
            code=code,
            seed=seed,
            state=GameSimulation.create_initial_state(seed),
            host=websocket,
        )
        self.rooms[code] = room
        self.connections[websocket] = (code, "host")
        await self._send(websocket, "room_created", room=code, seed=str(seed))

    async def _join_room(self, websocket, message):
        code = normalize_room_code(message.get("room"))
        room = self.rooms.get(code) if code is not None else None
        if room is None:
            await self._send(websocket, "error", reason="room_not_found")
            return
        if room.guest is not None:
            await self._send(websocket, "error", reason="room_full")
            return

        room.guest = websocket
        self.connections[websocket] = (room.code, "guest")
        await self._send(
            websocket, "room_joined", room=room.code, seed=str(room.seed))
        await self._send(room.host, "player_joined", room=room.code)
        await self._send(
            room.host,
            "game_started",
            room=room.code,
            seed=str(room.seed),
            color=COLOR.WHITE.value,
        )
        await self._send(
            websocket,
            "game_started",
            room=room.code,
            seed=str(room.seed),
            color=COLOR.BLACK.value,
        )

    async def _receive(self, websocket, raw):
        message = decode_message(raw)
        if message is None:
            await self._send(websocket, "error", reason="invalid_message")
            return
        if message["t"] != "action":
            await self._send(websocket, "error", reason="unsupported_message")
            return

        membership = self.connections.get(websocket)
        if membership is None:
            await self._send(websocket, "error", reason="not_in_room")
            return
        room_code, role = membership
        room = self.rooms.get(room_code)
        if room is None or room.guest is None:
            await self._send(websocket, "error", reason="game_not_started")
            return

        sequence = message.get("seq")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence != room.next_sequence
        ):
            await self._reject_action(websocket, "unexpected_sequence")
            return

        actor_color = COLOR.WHITE if role == "host" else COLOR.BLACK
        if room.state.current_turn != actor_color:
            await self._reject_action(websocket, "not_your_turn")
            return

        try:
            action = decode_action(message.get("action"))
        except (KeyError, TypeError, ValueError):
            await self._reject_action(websocket, "invalid_action")
            return

        try:
            next_state = GameSimulation.apply(
                room.state,
                action,
                advance_board_card_clock=True,
            )
        except ValueError:
            await self._reject_action(websocket, "illegal_action")
            return

        sequence = room.next_sequence
        room.state = next_state
        room.next_sequence += 1
        accepted = encode_message(
            "action",
            seq=sequence,
            actor=actor_color.value,
            action=encode_action(action),
        )
        await room.host.send(accepted)
        await room.guest.send(accepted)

    async def _reject_action(self, websocket, reason):
        await self._send(websocket, "action_rejected", reason=reason)

    async def _disconnect(self, websocket):
        membership = self.connections.pop(websocket, None)
        if membership is None:
            return
        room_code, role = membership
        room = self.rooms.pop(room_code, None)
        if room is None:
            return

        peer = room.guest if role == "host" else room.host
        if peer is not None:
            self.connections.pop(peer, None)
            await self._send(peer, "peer_disconnected", room=room_code)
            await peer.close()


async def serve(host=None, port=None):
    """Uruchamia serwer WebSocket na adresie i porcie z konfiguracji środowiska."""
    from websockets.asyncio.server import serve as websocket_serve

    bind_host = host or os.environ.get("SIGNALING_HOST", "0.0.0.0")
    bind_port = int(
        port if port is not None else os.environ.get("PORT", "8765"))
    game_server = GameServer()
    async with websocket_serve(
        game_server.handle,
        bind_host,
        bind_port,
        max_size=64 * 1024,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(serve())
