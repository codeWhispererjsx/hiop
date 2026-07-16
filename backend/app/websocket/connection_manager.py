import asyncio

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.event_loop: asyncio.AbstractEventLoop | None = None

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None):
        await websocket.accept(subprotocol=subprotocol)

        self.active_connections.append(websocket)
        self.event_loop = asyncio.get_running_loop()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected_connections = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected_connections.append(connection)

        for connection in disconnected_connections:
            self.disconnect(connection)

    def broadcast_from_thread(self, message: dict):
        if not self.event_loop or not self.active_connections:
            return

        asyncio.run_coroutine_threadsafe(
            self.broadcast(message),
            self.event_loop
        )


manager = ConnectionManager()
