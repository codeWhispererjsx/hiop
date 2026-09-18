# HIOP Desktop runtime

This folder contains the Windows desktop runtime for HIOP.

The Electron shell loads the desktop build of the current React interface and starts a local FastAPI backend on `127.0.0.1:8765`.

The packaged desktop build includes the backend Python runtime, installed backend dependencies, and a bundled PostgreSQL runtime. On first launch, HIOP initializes its private local database under `%LOCALAPPDATA%\HIOP Desktop\postgres-data`, starts it on localhost, applies migrations, and then starts the API.

## Local development flow

1. Build the frontend desktop bundle with `npm --prefix frontend run build:desktop`.
2. Build the backend Python runtime with `npm --prefix desktop run build:backend-runtime`.
3. Build the PostgreSQL runtime with `npm --prefix desktop run build:postgres-runtime`.
4. Start the desktop shell from the `desktop` folder with `npm start`.

The runtime script starts the private local database and applies database migrations before starting the backend.

## Windows packaging flow

From the repository root:

1. Install desktop package dependencies with `npm --prefix desktop install`.
2. Build the unpacked Windows app with `npm --prefix desktop run dist:unpacked`.
3. The runnable app is created at `desktop/release/win-unpacked/HIOP Desktop.exe`.

The packaging step stages these resources into the app:

- Desktop frontend bundle
- Backend source and migrations
- Bundled backend Python runtime
- Bundled PostgreSQL runtime
- Runtime startup scripts
- Electron shell

## Troubleshooting

If the desktop window opens but HIOP cannot connect, check `%LOCALAPPDATA%\HIOP Desktop\logs\backend.log`. PostgreSQL startup output is written to `%LOCALAPPDATA%\HIOP Desktop\logs\postgres.log` and `%LOCALAPPDATA%\HIOP Desktop\logs\postgres-error.log`.

## Production packaging still needed

This is now a self-contained Windows desktop development package for local operation. The remaining production work is installer polish: secure per-install secret generation, icon/signing, upgrade handling, backups, restore flow, and activation/licensing with the web Platform Control Center.
