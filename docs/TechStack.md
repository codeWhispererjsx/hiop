# HIOP 1.0.0 technology stack

| Layer | Implemented technology |
| --- | --- |
| Frontend | React 19, TypeScript 6, Vite 8, React Router 7, CSS design tokens, inline SVG icon component |
| Backend | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Uvicorn |
| Data | PostgreSQL 16, psycopg2 |
| Authentication | JWT (`python-jose`), bcrypt/passlib, backend role dependencies |
| Monitoring | `ping3`, approved-CIDR range scanning, APScheduler, authenticated WebSockets |
| Reporting | Server-side SQLAlchemy aggregation/pagination and formula-safe CSV export; dependency-free SVG/CSS charts |
| Production | Multi-stage Docker builds, Docker Compose, Nginx, JSON logs, health checks |
| Quality | ESLint, TypeScript compiler, Python `unittest`, compile/import checks, Alembic verification |

HIOP does not use Tailwind, Axios, TanStack Query, Recharts, or python-nmap in Version 1.0.0. External secrets, TLS certificates, PostgreSQL, and production observability remain deployment responsibilities.
