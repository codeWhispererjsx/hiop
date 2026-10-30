# HIOP LAN client setup

This guide covers the first desktop-client path to one hotel Site Server. It is suitable for a controlled LAN pilot, not yet an unattended production Windows server deployment.

## Target topology

```text
Client HIOP Desktop PCs
        | HTTPS / WSS (443)
        v
Site Server reverse proxy
        | HTTP / WS on loopback only
        v
One HIOP FastAPI backend
        |
        v
Private PostgreSQL (not exposed to clients)
```

Only the Site Server connects to PostgreSQL. Client PCs authenticate to the API; do not copy the database directory or database credentials to clients and do not publish PostgreSQL's port.

## Site Server preparation

1. Choose one always-on, supported Windows host or a server running the existing Docker Compose deployment.
2. Assign a DHCP reservation or stable DNS name to the host.
3. Back up the current Site Server data and verify the restore procedure before a pilot.
4. Configure a trusted TLS certificate for the hotel DNS name. Install any private certificate authority on client PCs through the hotel's managed device process.
5. Configure the reverse proxy to terminate TLS and forward API and WebSocket traffic to the backend. For a Windows desktop Site Server, the upstream is `http://127.0.0.1:8765`. For Docker Compose, use its published frontend/reverse-proxy path and keep the backend and database services internal to the Compose network.
6. Set `CORS_ORIGINS` to include `hiop://desktop` and any exact HTTPS browser origins the hotel uses. Do not use wildcard origins.
7. For the Windows desktop host only, set `HIOP_SITE_SERVER_HOST=0.0.0.0` before launching HIOP so the backend can be reached by a same-machine proxy. The launcher accepts only `127.0.0.1` or `0.0.0.0`; its default remains loopback. Keep port 8765 blocked from client networks. Do not expose PostgreSQL port 55432.
8. Keep the desktop Site Server app open during this pilot. Its backend and bundled PostgreSQL currently follow the interactive desktop process and are not installed as a Windows service.

The LAN must trust the TLS certificate; the desktop client rejects non-local HTTP URLs. Avoid internet port forwarding. For remote users, use the hotel's approved VPN.

### Reverse proxy requirements

Configure the proxy for:

- HTTPS requests under `/api/` forwarded unchanged to the backend.
- WebSocket upgrades under `/ws/` forwarded to the backend with HTTP/1.1 upgrade headers.
- `Host` and forwarded-protocol headers preserved.
- A certificate valid for the Site Server DNS name.

Keep PostgreSQL bound to loopback or the private Compose network. Firewall rules should expose HTTPS only to approved hotel client subnets; the backend port should be reachable only from a same-host proxy (or a tightly scoped proxy host).

## Connect each desktop client

1. Install the same HIOP Desktop release on each client PC.
2. Open HIOP. On the launch screen or sign-in page, choose **Connect to another Site Server** or **Change Site Server**.
3. Enter only the HTTPS origin, for example `https://hiop.hotel.example` (no path, credentials, query string, or trailing API path).
4. Save the connection. HIOP clears the prior sign-in, stores the server origin in the current Windows user profile, restarts in client mode, and signs in against that Site Server.
5. Create individual hotel accounts on the Site Server and assign the least-privilege roles required.

Client mode does not start PostgreSQL or FastAPI locally. It stores no database credentials. Changing the server signs out so cached organization, property, and authentication context is not reused against another installation.

To turn a client PC back into a local Site Server, use **Change Site Server** and select **Use this computer as the Site Server**. That mode uses the PC's own local database; it does not migrate or merge data from the remote Site Server.

## Pilot acceptance checks

- Two client PCs can sign in to the same Site Server with separate accounts.
- A permitted change from one client is visible after refresh on the other.
- A denied role action stays denied on the server.
- Live dashboard updates work through the WebSocket proxy.
- Scheduled scans run once on the Site Server, not on clients.
- Clients cannot connect to PostgreSQL or the backend's unencrypted port.
- HTTPS certificate validation succeeds on every client.
- Site Server backup and restore are verified, and server restart recovery is tested.

## Current limitations

- The Windows Site Server backend and bundled PostgreSQL are tied to the interactive desktop app lifecycle. Closing HIOP stops the backend. Do not deploy it as a 24/7 production host until it has managed service lifecycle, unattended startup, health monitoring, and installer upgrade/recovery handling.
- The desktop client URL and connection flow are implemented, but a client setup wizard is not yet available in the installer itself; users choose the server from the launch/sign-in UI.
- LAN access requires an administrator-managed TLS reverse proxy and firewall/certificate configuration. The desktop app does not configure those host services automatically.
- No automatic data migration or synchronization between separate local Site Server databases is provided.
- Docker Compose is a separate Site Server deployment option; it still needs a hotel-managed HTTPS reverse proxy/certificate and operational deployment procedure.
