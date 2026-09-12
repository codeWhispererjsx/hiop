# Move HIOP off Railway without paid hosting

Use this when Railway is about to expire. The target free stack is:

- Frontend: Vercel
- Backend: Render free web service
- Database: Neon free Postgres or Supabase free Postgres

## 1. Create the free database

Create a new Postgres database in Neon or Supabase and copy its pooled connection string.

The value must start with `postgresql://` or `postgresql+psycopg2://`.

Save it as:

```text
DATABASE_URL=<your Postgres connection string>
```

## 2. Create the Render backend

In Render, create a new Blueprint or Web Service from the GitHub repository.

If using Blueprint, select the repository and let Render read `render.yaml`.

If creating manually:

- Root directory: `backend`
- Runtime: Docker
- Plan: Free
- Health check path: `/healthz`

Set these environment variables:

```text
APP_NAME=Hospitality IT Operations Platform
APP_VERSION=4.0.0
DEBUG=false
ENVIRONMENT=production
API_PREFIX=/api/v1
DISCOVERY_EXECUTION_MODE=agent
SCHEDULER_ENABLED=true
COMMERCIAL_ENFORCEMENT_ENABLED=false
REQUIRE_EMAIL_VERIFICATION=false
CORS_ORIGINS=["https://hiop-ivory.vercel.app"]
PUBLIC_APP_URL=https://hiop-ivory.vercel.app
DATABASE_URL=<Neon or Supabase Postgres URL>
SECRET_KEY=<generate at least 32 random characters>
HIOP_AD_SECRET_KEY=<generate at least 32 random characters>
HIOP_SNMP_SECRET_KEY=<generate at least 32 random characters>
HIOP_DISCOVERY_CREDENTIAL_KEY=<generate at least 32 random characters>
```

Email can stay unconfigured during testing. Invites will show a copyable invitation link in the UI when email delivery is not configured.

## 3. Run database migrations

After Render deploys the backend once, open Render Shell or a one-off job and run:

```bash
alembic upgrade head
```

Then open:

```text
https://<your-render-backend>.onrender.com/health
```

Expected result: `status` should be `healthy`.

## 4. Point Vercel frontend to Render

In Vercel, update the frontend environment variable:

```text
VITE_API_URL=https://<your-render-backend>.onrender.com/api/v1
```

Redeploy Vercel after changing it.

## 5. Create the first platform admin

Run this once against the new Render database from Render Shell:

```bash
python scripts/bootstrap_platform_admin.py --username <username> --email <email>
```

It will ask for a password securely.

Use that account to open:

```text
https://hiop-ivory.vercel.app/platform
```

## 6. What to test after migration

- Login
- Dashboard
- Organization creation
- Invite user copyable link
- Local agent download
- Local agent connection code
- Discovery scan through local agent
- Audit export
- Billing platform exemption

## Free hosting limitation

Render free services can sleep when idle. The first request after sleep can be slow. That is acceptable for testing, but production should move to an always-on paid backend later.
