# Alembic Migrations

This directory stores database migration scripts generated via Alembic.

Create new incremental migrations with:

```bash
alembic revision --autogenerate -m "describe changes"
```

Apply the latest schema to your database:

```bash
alembic upgrade head
```
