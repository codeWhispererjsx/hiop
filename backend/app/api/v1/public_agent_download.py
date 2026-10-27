import ipaddress
import json
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from zipfile import ZIP_STORED, ZipFile

from app.core.security import get_db
from app.models.local_agent import AgentDownloadEvent

router = APIRouter(prefix="/download", tags=["Public Downloads"])


def _client_ip(request: Request) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    forwarded = request.headers.get("x-real-ip")
    candidate = forwarded or (request.client.host if request.client else "")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise HTTPException(403, "Agent downloads are available only from the hotel admin network") from exc
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise HTTPException(403, "Agent downloads are available only from the hotel admin network")
    return address


@router.get("/status")
def download_status(request: Request, db: Session = Depends(get_db)):
    _client_ip(request)
    return {
        "status": "online",
        "server_ip": request.url.hostname,
        "downloads": db.query(AgentDownloadEvent).count(),
    }


@router.get("/agent")
def download_agent(request: Request, db: Session = Depends(get_db)):
    client_ip = _client_ip(request)
    distribution = Path(__file__).resolve().parents[2] / "distributions"
    installer = distribution / "HIOP-Agent-Windows.exe"
    if not installer.is_file():
        raise HTTPException(503, "The Windows agent installer is unavailable. Contact your HIOP administrator.")

    db.add(AgentDownloadEvent(client_ip=str(client_ip)))
    db.commit()
    return FileResponse(
        installer,
        media_type="application/vnd.microsoft.portable-executable",
        filename="HIOP-Agent-Windows.exe",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/agent/package")
def download_agent_package(request: Request, db: Session = Depends(get_db)):
    client_ip = _client_ip(request)
    distribution = Path(__file__).resolve().parents[2] / "distributions"
    bundle = distribution / "hiop-agent-windows.zip"
    if not bundle.is_file():
        raise HTTPException(503, "The Windows agent package is unavailable. Contact your HIOP administrator.")

    output = BytesIO()
    with ZipFile(bundle, "r") as source, ZipFile(output, "w", ZIP_STORED) as archive:
        for entry in source.infolist():
            if entry.filename in {
                "setup.json", "install-user.ps1", "uninstall-user.ps1",
                "Install HIOP Agent.cmd", "Remove HIOP Agent.cmd", "Connect HIOP.cmd",
            } or entry.filename.startswith("hiop_agent/"):
                continue
            archive.writestr(entry, source.read(entry.filename))
        for filename in ("install-user.ps1", "uninstall-user.ps1", "Install HIOP Agent.cmd", "Remove HIOP Agent.cmd"):
            script = distribution / filename
            if not script.is_file():
                raise HTTPException(503, "The Windows agent setup files are incomplete.")
            archive.write(script, filename)
        archive.writestr("setup.json", json.dumps({"backend_url": str(request.base_url).rstrip("/")}))

    db.add(AgentDownloadEvent(client_ip=str(client_ip)))
    db.commit()
    return Response(
        output.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="HIOP-Agent-Windows-Package.zip"',
            "Cache-Control": "no-store",
        },
    )
