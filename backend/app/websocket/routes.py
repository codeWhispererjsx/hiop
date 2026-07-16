from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import user_from_token
from app.db.database import SessionLocal
from app.websocket.connection_manager import manager

router = APIRouter()


@router.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket):
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
