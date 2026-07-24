# HIOP Developer Guide

## Hotel IT Operations Portal — Version 1.0.0

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Folder Structure](#folder-structure)
3. [Coding Standards](#coding-standards)
4. [Backend Development](#backend-development)
5. [Frontend Development](#frontend-development)
6. [Database](#database)
7. [Adding Modules](#adding-modules)
8. [Testing](#testing)
9. [Deployment](#deployment)

---

## Architecture Overview

HIOP is a three-tier internal operations application:

```
Browser (React + TypeScript)     ← Frontend
        | HTTPS REST + WebSocket
FastAPI application               ← Backend
        | SQLAlchemy / Alembic
PostgreSQL                        ← Database
```

### Key Design Decisions

- **Frontend**: React 19 with TypeScript, Vite build tool, React Router v7 for navigation
- **Backend**: FastAPI with Pydantic v2 validation, SQLAlchemy 2.0 ORM, Alembic migrations
- **Authentication**: JWT with bcrypt password hashing, session-scoped tokens
- **Real-time**: WebSocket for live device status updates
- **Scanner**: ICMP-based network scanning with CIDR authorization
- **Scheduler**: APScheduler for background scan jobs

---

## Folder Structure

```
hiop/
├── backend/
│   ├── alembic/              # Database migrations
│   ├── app/
│   │   ├── core/             # Config, security, dependencies
│   │   ├── db/               # Database session management
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── routers/          # API route handlers
│   │   ├── services/         # Business logic
│   │   ├── repositories/     # Data access layer
│   │   └── main.py           # Application entry point
│   └── tests/                # Backend tests
├── frontend/
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   ├── hooks/            # Custom React hooks
│   │   ├── layouts/          # Page layouts
│   │   ├── lib/              # API client, auth, types
│   │   ├── pages/            # Route page components
│   │   └── styles/           # CSS stylesheets
│   └── public/               # Static assets
├── docs/                     # Documentation
├── deploy/                   # Deployment configuration
├── scripts/                  # Utility scripts
└── docker-compose.yml        # Production orchestration
```

---

## Coding Standards

### General

- Use 2-space indentation for all code
- Follow PEP 8 (Python) and ESLint (TypeScript) conventions
- Write descriptive variable and function names
- Include type hints in Python and TypeScript
- Keep functions focused and under 50 lines where possible
- Document public APIs with docstrings

### Python (Backend)

```python
# Good example
async def get_device(device_id: str, db: AsyncSession) -> Device:
    """Retrieve a device by its UUID.

    Args:
        device_id: The device's unique identifier.
        db: An active database session.

    Returns:
        The Device record, or raises 404 if not found.
    """
    device = await device_repository.get_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device
```

### TypeScript (Frontend)

```typescript
// Good example
interface DeviceFilters {
  search?: string;
  status?: string;
  department?: string;
  page?: number;
  pageSize?: number;
}

function useDevices(filters: DeviceFilters) {
  return useRequest(
    () => endpoints.devices(filters),
    [filters.search, filters.status, filters.department, filters.page],
  );
}
```

### CSS

- Use CSS custom properties for theming
- Follow BEM-like naming for components
- Keep selectors flat (avoid deep nesting)
- Use responsive breakpoints consistently

---

## Backend Development

### Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env for your environment
```

### Running the Server

```bash
uvicorn app.main:app --reload --port 8001
```

The API will be available at `http://127.0.0.1:8001/api/v1`.

### Project Structure

**Models** (`app/models/`): SQLAlchemy ORM models defining database tables and relationships.

**Schemas** (`app/schemas/`): Pydantic models for request/response validation.

**Routers** (`app/routers/`): FastAPI route definitions grouped by module.

**Services** (`app/services/`): Business logic layer between routers and repositories.

**Repositories** (`app/repositories/`): Data access layer with database queries.

### Adding a New Endpoint

1. Create or update the Pydantic schema in `app/schemas/`
2. Add the route handler in the appropriate router file
3. Implement business logic in a service
4. Add database queries to a repository
5. Register the router in `app/main.py`

---

## Frontend Development

### Setup

```bash
cd frontend
npm install
```

### Development Server

```bash
npm run dev
```

The app will be available at `http://localhost:5173`.

### Project Structure

**Pages** (`src/pages/`): Route-level components, one per route.

**Components** (`src/components/`): Reusable UI elements.

**Hooks** (`src/hooks/`): Custom React hooks (`useRequest`, etc.).

**Lib** (`src/lib/`): API client, authentication, type definitions.

**Styles** (`src/styles/`): Global CSS and component-specific styles.

### Key Patterns

**Data Fetching:**
```typescript
const devices = useRequest(() => endpoints.devices(), []);
// devices.data, devices.loading, devices.error, devices.reload
```

**Protected Routes:**
```typescript
<Route path="/devices" element={protectedPage(<DevicesPage />)} />
```

**API Client:**
```typescript
const result = await endpoints.device(id);
// Automatic JWT attachment, error handling, GET coalescing
```

### Adding a New Page

1. Create the page component in `src/pages/`
2. Add the import and route in `src/App.tsx`
3. Add navigation link in `src/components/Sidebar.tsx`
4. Add any new API endpoints in `src/lib/api.ts`

---

## Database

### Migrations

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Adding a New Table

1. Create the SQLAlchemy model in `app/models/`
2. Add the Pydantic schema in `app/schemas/`
3. Generate a migration: `alembic revision --autogenerate -m "add table"`
4. Review and apply the migration: `alembic upgrade head`

### Key Models

- `User` — System users with roles
- `Device` — Inventory devices
- `NetworkScan` — Scan results
- `Alert` — Status change alerts
- `Ticket` — Operational tickets
- `AuditLog` — Audit trail
- `SystemSetting` — Application settings
- `HierarchyItem` — Organization hierarchy
- `DiscoveredDevice` — Discovery results
- `ImportSession` — Import sessions
- `ImportedDevice` — Staged device records
- `ImportMatchCandidate` — Match candidates

---

## Adding Modules

### Step-by-Step Guide

1. **Database Layer**: Add models and generate migration
2. **Backend API**: Add schemas, repository, service, and router
3. **Register Router**: Add to `app/main.py` include list
4. **Frontend Types**: Add TypeScript types in `src/lib/types.ts`
5. **API Endpoints**: Add endpoint functions in `src/lib/api.ts`
6. **UI Page**: Create page component in `src/pages/`
7. **Routing**: Add route in `src/App.tsx`
8. **Navigation**: Add sidebar link in `src/components/Sidebar.tsx`
9. **Tests**: Add backend tests in `backend/tests/`

---

## Testing

### Backend Tests

```bash
cd backend
python -m unittest discover -s tests -v
```

### Test Structure

Tests are in `backend/tests/` and follow the module structure:
- `test_auth.py` — Authentication tests
- `test_devices.py` — Device CRUD tests
- `test_network.py` — Scanner tests
- etc.

### Writing Tests

```python
class TestDevices(unittest.TestCase):
    def setUp(self):
        # Setup test client and database
        pass

    async def test_create_device(self):
        # Test device creation
        pass
```

---

## Deployment

### Production Build

```bash
# Frontend
cd frontend
npm run build
# Output: frontend/dist/

# Backend
cd backend
# Ensure .env is configured for production
```

### Docker Deployment

```bash
docker compose build
docker compose up -d
```

### Environment Configuration

See `backend/.env.example` for all required variables. Production requires:
- `ENVIRONMENT=production`
- `DEBUG=false`
- Secure `SECRET_KEY` (32+ characters)
- Production HTTPS `CORS_ORIGINS`
- Proper PostgreSQL credentials

---

## Git Workflow

### Branch Strategy

- `main` — Production-ready code
- `develop` — Integration branch
- `feature/*` — Feature branches
- `release/*` — Release candidates
- `hotfix/*` — Urgent production fixes

### Commit Messages

Follow conventional commits:
```
feat: add device bulk import
fix: resolve WebSocket reconnection loop
docs: update API documentation
refactor: simplify scan result handling
test: add device scan tests
chore: update dependencies
```

---

## Troubleshooting

### Common Issues

**Backend won't start:**
- Check PostgreSQL is running
- Verify `.env` configuration
- Run `alembic upgrade head`

**Frontend build fails:**
- Check Node.js version (22+)
- Run `npm install` to update dependencies
- Clear Vite cache: delete `node_modules/.vite`

**Database migration conflicts:**
- Review migration chain: `alembic history`
- Check for overlapping branch migrations
- Merge or recreate conflicting revisions

---

## Additional Resources

- `docs/Architecture.md` — Detailed architecture documentation
- `docs/API.md` — Full API reference
- `docs/Database.md` — Database schema documentation
- `docs/DEPLOYMENT.md` — Deployment guide
- `docs/OPERATIONS.md` — Operations runbook