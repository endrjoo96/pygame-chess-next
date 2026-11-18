"""Serwer sygnalizacyjny WebSocket dla negocjacji WebRTC P2P."""

import asyncio
import json
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any, Optional

from network.protocol import (
    decode_message,
    encode_message,
    normalize_room_code,
)

_ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_RELAY_MESSAGE_TYPES = {"offer", "answer", "ice"}
_SEED_PATTERN = re.compile(r"^-?\d{1,20}$")


@dataclass
class Room:
    code: str
    seed: int
    host: Any
    guest: Optional[Any] = None


class SignalingServer:
    """Zarządza pokojami i przekazuje wyłącznie wiadomości negocjacji WebRTC."""

    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.connections: dict[Any, tuple[str, str]] = {}

    def _new_room_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_ROOM_ALPHABET) for _ in range(6))
            if code not in self.rooms:
                return code

    async def _send(self, websocket, message_type, **fields):
        await websocket.send(encode_message(message_type, **fields))

    async def handle(self, websocket):
        """Obsługuje jeden websocket i usuwa pokój po rozłączeniu peera."""
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
                await self._relay(websocket, raw)
        finally:
            await self._disconnect(websocket)

    async def _create_room(self, websocket, message):
        seed_value = message.get("seed")
        if isinstance(seed_value, bool):
            await self._send(websocket, "error", reason="invalid_seed")
            return
        if isinstance(seed_value, int):
            seed = seed_value
        elif (
            isinstance(seed_value, str)
            and _SEED_PATTERN.fullmatch(seed_value)
        ):
            seed = int(seed_value)
        else:
            await self._send(websocket, "error", reason="invalid_seed")
            return
        code = self._new_room_code()
        self.rooms[code] = Room(code=code, seed=seed, host=websocket)
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
        await self._send(room.host, "peer_joined", room=room.code)

    async def _relay(self, websocket, raw):
        message = decode_message(raw)
        if message is None:
            await self._send(websocket, "error", reason="invalid_message")
            return
        message_type = message["t"]
        if message_type not in _RELAY_MESSAGE_TYPES:
            await self._send(websocket, "error", reason="unsupported_message")
            return
        membership = self.connections.get(websocket)
        if membership is None:
            await self._send(websocket, "error", reason="not_in_room")
            return
        room_code, role = membership
        room = self.rooms.get(room_code)
        if room is None:
            await self._send(websocket, "error", reason="peer_not_connected")
            return
        peer = room.guest if role == "host" else room.host
        if peer is None:
            await self._send(websocket, "error", reason="peer_not_connected")
            return
        await peer.send(json.dumps(message, separators=(",", ":")))

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
            await self._send(peer, "peer_left", room=room_code)
            await peer.close()


async def serve(host=None, port=None):
    """Uruchamia serwer; host i port można ustawić zmiennymi środowiskowymi."""
    from websockets.asyncio.server import serve as websocket_serve

    bind_host = host or os.environ.get("SIGNALING_HOST", "0.0.0.0")
    bind_port = int(
        port if port is not None else os.environ.get("PORT", "8765"))
    signaling = SignalingServer()
    async with websocket_serve(
        signaling.handle,
        bind_host,
        bind_port,
        max_size=64 * 1024,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(serve())
