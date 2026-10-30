from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import user_from_token
from app.db.database import SessionLocal
from app.websocket.connection_manager import manager

router = APIRouter()


@router.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host", "")
    request_origin = f"{websocket.url.scheme}://{host}"
    if origin and origin not in settings.cors_origins and origin != request_origin:
        await websocket.close(code=4403, reason="Origin not allowed")
        return
    protocols = websocket.scope.get("subprotocols", [])
    token = protocols[1] if len(protocols) == 2 and protocols[0] == "hiop" else ""
    db = SessionLocal()
    try:
        authenticated = bool(token and user_from_token(db, token))
    finally:
        db.close()
    if not authenticated:
        await websocket.close(code=4401, reason="Authentication required")
        return

    await manager.connect(websocket, subprotocol="hiop")

    await websocket.send_json({
        "event": "connected",
        "message": "Welcome to HIOP Live Dashboard"
    })

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
