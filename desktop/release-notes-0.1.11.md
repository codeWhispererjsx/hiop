# HIOP Desktop 0.1.11

Fixes desktop startup after a PostgreSQL recovery or stale local backend process. The startup service now runs migrations and the API through a stable command path and reports conflicts clearly.