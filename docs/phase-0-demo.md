# Phase 0 demo script

Password for all demo users: value of `DEMO_SEED_PASSWORD` in `.env` (default `ChangeMeDemo!2026`).

## Prep

Native Windows (no Docker needed). See [README.md](../README.md) for one-time setup.

```powershell
# from repo root, with PostgreSQL running and .venv set up
cd backend
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py seed_demo
cd ..
.\scripts\dev.ps1
```

Open http://127.0.0.1:5173

## Walkthrough

1. **Health** — `GET http://localhost:8000/api/v1/health` returns `database: true`, `redis: true`.
2. **Sign in as `facadmin`** — land on Home. Roles include Facility Admin.
3. **Facility Settings** — open Settings. Confirm amber banners for unconfirmed GSTIN and TDS. Change letterhead text and Save. Confirm success.
4. **Users** — create a receptionist user (username `demo_recv`, role Receptionist). Confirm they appear in the directory.
5. **Roles** — open Roles, select Receptionist, confirm only `home.view` and Home screen (or adjust and Save).
6. **Number Sequences** — confirm UHID sequence under organization and BILL/RCPT/… under facility for the current FY.
7. **Audit Logs** — filter action `settings` or actor `facadmin`. Confirm the settings update row.
8. **Sign out.** Sign in as `cashier`. Home works. Navigate to `/users` — expect permission denied.
9. **Sign in as `doctor`** — Home shows 2FA setup required banner (policy requires TOTP for Doctor). Optional: enroll via Settings after granting that screen, or leave for later.
10. **Sign in as `superadmin`** — full admin screens available.

## API docs

http://localhost:8000/api/docs/

## Done criteria checklist

- [ ] Demo script steps 1–10 complete
- [ ] `..\.venv\Scripts\python.exe -m pytest tests -q` passes (from `backend/`)
- [ ] Frontend `npm test -- --run` passes
- [ ] Permissions and audit enforced
- [ ] Migrations reverse: `python manage.py migrate numbering zero` (then re-migrate)
