# HIOP frontend

React, TypeScript and Vite client for the Hotel IT Operations Portal.

## Configuration

Optional `.env.local` values:

```env
VITE_API_URL=http://127.0.0.1:8001/api/v1
VITE_WS_URL=ws://127.0.0.1:8001/ws/dashboard
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

The active screens use FastAPI for authentication, dashboard metrics, devices, network scans, alerts, tickets, users, audit logs, reports, hierarchy management, and settings. Empty states mean the database has no corresponding records; they are never replaced by sample content. Release limitations are maintained in the root `PROJECT_STATUS.md` and `RELEASE_CANDIDATE.md` files.
