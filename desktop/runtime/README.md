# HIOP Desktop runtime

This folder contains the Windows desktop runtime for HIOP.

The Electron shell loads the desktop build of the current React interface and starts a local FastAPI backend on `127.0.0.1:8765` when this computer is the Site Server. It can also connect as a client to an HTTPS Site Server without starting a local backend or database.

The packaged desktop build includes a copied, portable Python 3.12 runtime with the backend dependencies installed, and a bundled PostgreSQL runtime. It does not rely on the Python installation or filesystem paths of the computer that built the installer. On first launch, HIOP initializes its private local database under `%LOCALAPPDATA%\HIOP Desktop\postgres-data`, starts it on localhost, applies migrations, and then starts the API.

## Local development flow

1. Build the frontend desktop bundle with `npm --prefix frontend run build:desktop`.
2. Build the backend Python runtime with `npm --prefix desktop run build:backend-runtime`.
3. Build the PostgreSQL runtime with `npm --prefix desktop run build:postgres-runtime`.
4. Start the desktop shell from the `desktop` folder with `npm start`.

The runtime script starts the private local database and applies database migrations before starting the backend.

## Connecting desktop clients to a Site Server

1. Prepare one always-on Site Server and configure its API behind HTTPS. Desktop clients accept only HTTPS Site Server URLs; HTTP is allowed for localhost testing only.
2. Configure the Site Server API to allow the exact HIOP desktop origin `hiop://desktop`. Production `CORS_ORIGINS` may contain this origin alongside approved HTTPS web origins.
3. Install and open HIOP Desktop on each client PC. On the launch or sign-in screen, choose **Connect to another Site Server**, enter the HTTPS origin (for example `https://hiop.hotel.example`), and save. HIOP signs out and restarts in client mode.
4. Client mode stores only the Site Server URL and does not start local PostgreSQL or FastAPI. All clients use the Site Server API; its PostgreSQL port must not be exposed to client machines.
5. To return a computer to local Site Server mode, choose **Change Site Server** and select **Use this computer as the Site Server**.

For the first Windows LAN pilot, start the Site Server with `HIOP_SITE_SERVER_HOST=0.0.0.0` so a same-machine HTTPS reverse proxy can reach the API at `127.0.0.1:8765`. Keep the backend port blocked from client subnets and expose only the reverse proxy's HTTPS port. The packaged desktop Site Server currently runs its backend with the desktop session; keep HIOP open on the host. A managed Windows service, unattended startup, and production installer hardening are still required before treating this as a production multi-user server.

See [HIOP LAN client setup](../../docs/HIOP_LAN_CLIENT_SETUP.md) for certificate, proxy, firewall, pilot, and limitation details.

## Windows packaging flow

From the repository root:

1. Install desktop package dependencies with `npm --prefix desktop install`.
2. Build the unpacked Windows app with `npm --prefix desktop run dist:unpacked`.
3. The runnable app is created at `desktop/release/win-unpacked/HIOP Desktop.exe`.

The packaging step stages these resources into the app. The backend runtime build copies the Python 3.12 base runtime and installs the backend requirements into its local `Lib\site-packages`, rather than creating a virtual environment that points back to the builder's Python installation.

- Desktop frontend bundle
- Backend source and migrations
- Bundled backend Python runtime
- Bundled PostgreSQL runtime
- Runtime startup scripts
- Electron shell

## Troubleshooting

If the desktop window opens but HIOP cannot connect, use **Retry local startup** first. This restarts the local service if its launcher exited and waits through PostgreSQL recovery. A local installation does not need a Site Server address. Only connect to another Site Server when your HIOP administrator has provided its HTTPS address. If startup still fails, check `%LOCALAPPDATA%\HIOP Desktop\logs\backend.log`; PostgreSQL startup output is written to `%LOCALAPPDATA%\HIOP Desktop\logs\postgres.log` and `%LOCALAPPDATA%\HIOP Desktop\logs\postgres-error.log`. HIOP does not reset or delete the local database during retry.

## Production packaging still needed

This is now a self-contained Windows desktop development package for local operation. The remaining production work is installer polish: secure per-install secret generation, icon/signing, upgrade handling, backups, restore flow, and activation/licensing with the web Platform Control Center.
