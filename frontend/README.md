# HIOP frontend

React, TypeScript and Vite client for the Hotel IT Operations Portal.

## Configuration

Optional `.env.local` values:

```env
VITE_API_URL=http://127.0.0.1:8000/api/v1
VITE_WS_URL=ws://127.0.0.1:8000/ws/dashboard
```

## Run

```bash
npm install
npm run dev
```

## Verify

```bash
npm run lint
npm run build
```

The active screens use FastAPI for authentication, dashboard metrics, devices, network scans, alerts, tickets, users, audit logs and settings. Empty states mean the database has no corresponding records; they are not replaced by sample content. See [MISSING_API.md](MISSING_API.md) for deliberately deferred backend contracts.
