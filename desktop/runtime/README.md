# HIOP Desktop runtime

This folder contains the Windows desktop runtime for HIOP.

The Electron shell loads the desktop build of the current React interface and starts a local FastAPI backend on `127.0.0.1:8765`.

For this development packaging version, the backend expects a local PostgreSQL database named `hiop_desktop` with user `postgres` and password `postgres`, unless `DATABASE_URL` is already set before launch.

## Local development flow

1. Create a local PostgreSQL database called `hiop_desktop`.
2. Install backend dependencies in the Python environment.
3. Build the frontend desktop bundle with `npm --prefix frontend run build:desktop`.
4. Start the desktop shell from the `desktop` folder with `npm start`.

The runtime script applies database migrations before starting the backend.

## Windows installer flow

From the repository root:

1. Install desktop package dependencies with `npm --prefix desktop install`.
2. Build the installer with `npm --prefix desktop run dist:win`.
3. The installer is created in `desktop/release`.

The packaging step stages these resources into the installer:

- Desktop frontend bundle
- Backend source and migrations
- Runtime startup scripts
- Electron shell

## Troubleshooting

If the desktop window opens but HIOP cannot connect, check `%LOCALAPPDATA%\HIOP Desktop\logs\backend.log`. The app writes migration and backend startup errors there, including missing PostgreSQL, bad database credentials, Python dependency problems, and backend import errors.

## Production packaging still needed

This is close to a Windows installable development build, but it is not yet the final customer installer. The installer still needs to bundle or install PostgreSQL, bundle a Python runtime/backend environment, set secure per-install secrets, manage upgrades, configure backups, and connect activation/licensing to the web Platform Control Center.
