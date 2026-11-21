# HIMS — Hospital Information Management System

Production-oriented HIMS for small and mid-size hospitals. India-first (GST, TDS), multi-facility ready.

See [ARCHITECTURE.md](ARCHITECTURE.md) for stack, module boundaries, billing design, and numbering rules.

**Current phase:** Through Phase 7. Masters, OPD, billing, clinical EMR at `/emr`, pharmacy at `/pharmacy`, laboratory at `/laboratory`, and radiology at `/radiology` (test master, scheduling, report templates, authorization, consumables, PDF reports, billing).

Development runs natively on Windows (no Docker required). Docker files are optional and kept for later hosting work.

## Prerequisites

- PostgreSQL 16 or 17 installed locally, with a running service (tested: PostgreSQL 17 on Windows)
- Python 3.12+ (tested on 3.14)
- Node 20+
- Redis is **not** required locally (`USE_REDIS_CACHE=false` uses an in-process cache)

## One-time setup

1. Create the database role and database (run as the `postgres` superuser, e.g. in `psql`):

   ```sql
   CREATE ROLE hims LOGIN PASSWORD 'hims_dev_password' CREATEDB;
   CREATE DATABASE hims OWNER hims;
   ```

2. Copy the environment file and review it:

   ```powershell
   Copy-Item .env.example .env
   ```

   Local defaults in `.env.example`: `POSTGRES_HOST=127.0.0.1`, `USE_REDIS_CACHE=false`.  
   Set `SECRET_KEY` and `DEMO_SEED_PASSWORD` before first use.

3. Install dependencies and set up the database:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   cd frontend; npm install; cd ..
   cd backend
   ..\.venv\Scripts\python.exe manage.py migrate
   ..\.venv\Scripts\python.exe manage.py seed_demo
   cd ..
   ```

## Run the app

Start backend and frontend together:

```powershell
.\scripts\dev.ps1
```

Or in two terminals:

```powershell
# terminal 1
cd backend; ..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000

# terminal 2
cd frontend; npm run dev
```

- UI: http://127.0.0.1:5173  
- API health: http://127.0.0.1:8000/api/v1/health  
- OpenAPI docs: http://127.0.0.1:8000/api/docs/  

Demo users (password from `DEMO_SEED_PASSWORD`):

| Username | Role |
|---|---|
| `superadmin` | Super Admin |
| `facadmin` | Facility Admin |
| `receptionist` | Receptionist |
| `cashier` | Cashier |
| `doctor` | Doctor |
| `pharmacist` | Pharmacist |
| `labtech` | Lab Technician |
| `pathologist` | Lab Pathologist/Authorizer |
| `radtech` | Radiology Technician |
| `radiologist` | Radiologist |

Demo walkthroughs: [docs/phase-0-demo.md](docs/phase-0-demo.md) … [docs/phase-7-demo.md](docs/phase-7-demo.md).

## Tests

```powershell
# Backend (from backend/)
..\.venv\Scripts\python.exe -m pytest tests -q

# Lint (from backend/)
..\.venv\Scripts\python.exe -m ruff check apps hims tests

# Frontend unit + typecheck (from frontend/)
npm test -- --run
npx tsc --noEmit

# End-to-end (needs backend and frontend running; from frontend/)
npx playwright install chromium   # first time only
npx playwright test
```

## Backup restore drill

Needs PostgreSQL client tools (`pg_dump`, `psql`) on `PATH`, e.g. `C:\Program Files\PostgreSQL\17\bin`.

```powershell
cd backend
..\.venv\Scripts\python.exe manage.py backup_restore_drill
```

The `hims` role needs `CREATEDB` for the drill (it creates and drops a scratch database).

## Optional: Docker

Only if Docker Desktop is available on your machine. Not required for Phase 0 development.

```bash
docker compose up --build -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
```

Use `POSTGRES_HOST=db` and `USE_REDIS_CACHE=true` in `.env` for Compose.

## Phase policy

Do not start the next phase until the current phase is approved. Money, stock, and clinical flows must not contain placeholder logic.
