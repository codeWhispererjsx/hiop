# HIOP Desktop runtime

This folder is the first Windows desktop runtime for HIOP.

The Electron shell loads the desktop build of the current React interface and starts a local FastAPI backend on `127.0.0.1:8765`.

For this development version, the backend expects a local PostgreSQL database named `hiop_desktop` with user `postgres` and password `postgres`, unless `DATABASE_URL` is already set before launch.

## Local development flow

1. Create a local PostgreSQL database called `hiop_desktop`.
2. Install backend dependencies in the Python environment.
3. Build the frontend desktop bundle with `npm --prefix frontend run build:desktop`.
4. Start the desktop shell from the `desktop` folder with `npm start`.

The runtime script applies database migrations before starting the backend.

## Production packaging still needed

This is not yet the final customer installer. The installer still needs to bundle or install PostgreSQL, Python runtime/backend, the desktop app, startup shortcuts, upgrade handling, backup paths, and activation/licensing from the web Platform Control Center.
## Troubleshooting

If the desktop window opens but HIOP cannot connect, check `%LOCALAPPDATA%\HIOP Desktop\logs\backend.log`. The app writes migration and backend startup errors there, including missing PostgreSQL, bad database credentials, or Python dependency problems.
