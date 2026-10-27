from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import public_agent_download
from app.core.security import get_db


def test_public_agent_download_serves_single_file_installer(tmp_path, monkeypatch):
    module_file = tmp_path / "backend" / "app" / "api" / "v1" / "public_agent_download.py"
    distribution = tmp_path / "backend" / "app" / "distributions"
    distribution.mkdir(parents=True)
    installer = distribution / "HIOP-Agent-Windows.exe"
    installer.write_bytes(b"test-agent-installer")
    monkeypatch.setattr(public_agent_download, "__file__", str(module_file))

    database = SimpleNamespace(add=lambda _event: None, commit=lambda: None)
    app = FastAPI()
    app.include_router(public_agent_download.router)
    app.dependency_overrides[get_db] = lambda: database

    response = TestClient(app).get(
        "/download/agent",
        headers={"x-real-ip": "10.20.30.40"},
    )

    assert response.status_code == 200
    assert response.content == b"test-agent-installer"
    assert response.headers["content-type"] == "application/vnd.microsoft.portable-executable"
    assert response.headers["content-disposition"] == 'attachment; filename="HIOP-Agent-Windows.exe"'


def test_installer_package_route_injects_its_hotel_server_address(tmp_path, monkeypatch):
    module_file = tmp_path / "backend" / "app" / "api" / "v1" / "public_agent_download.py"
    distribution = tmp_path / "backend" / "app" / "distributions"
    distribution.mkdir(parents=True)
    with ZipFile(distribution / "hiop-agent-windows.zip", "w") as archive:
        archive.writestr("service/Hiop.Agent.Service.exe", b"service")
        archive.writestr("tray/Hiop.Agent.Tray.exe", b"tray")
        archive.writestr("setup.json", b"old setup")
    for name in ("install-user.ps1", "uninstall-user.ps1", "Install HIOP Agent.cmd", "Remove HIOP Agent.cmd"):
        (distribution / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(public_agent_download, "__file__", str(module_file))

    database = SimpleNamespace(add=lambda _event: None, commit=lambda: None)
    app = FastAPI()
    app.include_router(public_agent_download.router)
    app.dependency_overrides[get_db] = lambda: database

    response = TestClient(app).get(
        "/download/agent/package",
        headers={"x-real-ip": "10.20.30.40"},
    )

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.read("setup.json") == b'{"backend_url": "http://testserver"}'
        assert archive.read("service/Hiop.Agent.Service.exe") == b"service"
    assert response.headers["content-disposition"] == 'attachment; filename="HIOP-Agent-Windows-Package.zip"'
