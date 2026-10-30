import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.core.config import settings
from app.websocket.routes import dashboard_socket


def _websocket(origin: str):
    return SimpleNamespace(
        headers={"origin": origin, "host": "hiop.hotel.example"},
        url=SimpleNamespace(scheme="https"),
        scope={"subprotocols": []},
        close=AsyncMock(),
    )


def test_dashboard_websocket_rejects_untrusted_origins():
    websocket = _websocket("https://untrusted.example")

    asyncio.run(dashboard_socket(websocket))

    websocket.close.assert_awaited_once_with(code=4403, reason="Origin not allowed")


def test_dashboard_websocket_accepts_the_configured_desktop_origin_for_auth_check():
    websocket = _websocket("hiop://desktop")
    database = Mock()
    with patch.object(settings, "cors_origins", ["hiop://desktop"]), \
         patch("app.websocket.routes.SessionLocal", return_value=database), \
         patch("app.websocket.routes.user_from_token", return_value=None):
        asyncio.run(dashboard_socket(websocket))

    websocket.close.assert_awaited_once_with(code=4401, reason="Authentication required")
    database.close.assert_called_once()
