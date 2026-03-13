# Samba Admin Console

LDAP-first admin console for AD/Samba environments.

## 1. What This Project Does

Current mode is **LDAP-focused user/OU management** with local JWT auth + RBAC.

Implemented:
- LDAP health check
- Dashboard user activity view
- Users list/search/pagination
- OU tree browse/create/rename/delete
- User create/edit/delete
- Group-based filtering
- Legacy TXT import and CSV export
- Local RBAC management (users/roles/permissions)

Not implemented (intentional placeholders):
- Samba config apply/validate endpoints (`/api/config/*` -> 501 in current mode)
- Version rollback endpoints (`/api/versions/{id}/rollback` -> 501)

## 2. Project Structure

```text
samba-admin/
├─ backend/
│  ├─ app/
│  │  ├─ core/                 # settings, logging, app startup infra
│  │  ├─ routers/              # FastAPI routes
│  │  ├─ schemas/              # Pydantic models (auth / ldap / samba / users)
│  │  ├─ services/             # business logic
│  │  │  └─ users/             # user-specific service layer
│  │  ├─ data/                 # runtime data (rbac.json, logs, versions)
│  │  └─ main.py
│  ├─ templates/               # Samba template files
│  └─ tests/                   # backend tests
├─ frontend/
│  ├─ src/
│  │  ├─ api/
│  │  ├─ auth/
│  │  ├─ components/
│  │  ├─ router/
│  │  └─ views/
│  │     ├─ auth/
│  │     ├─ dashboard/
│  │     ├─ ous/
│  │     ├─ system/
│  │     ├─ users/
│  │     └─ legacy/
│  └─ public/
└─ samples/
```

## 3. Architecture

```text
Browser (Vue 3 + Vite)
  -> FastAPI backend
  -> ldap3
  -> Active Directory / Samba AD DC
```

## 4. Requirements

- Python `3.10+`
- Node.js `20.19+` or `22.12+`

## 5. Backend Quick Start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/ldap/health
```

OpenAPI:
- `http://127.0.0.1:8000/docs`

## 6. Frontend Quick Start

```bash
cd frontend
npm install
cp .env.example .env.development
npm run dev
```

Build:

```bash
npm run build
npm run preview
```

## 7. Key Runtime Files

- RBAC store: `backend/app/data/rbac.json`
- Backend logs: `backend/app/data/logs/backend.log`

When migrating servers, keep:
- `backend/app/data/rbac.json`
- your `APP_JWT_SECRET`

## 8. Important Behavior Rules

### OU behavior
- **Search/list pages** (`Users`, `Dashboard`): OU filter supports multi-select.
- **Create/Edit user**: OU path is **single physical target only** (LDAP-compliant).

### Group behavior
- Group filters support multi-select.
- Edit user uses exact group sync mode (`sync_groups=true`).

### Protected account
- `krbtgt` cannot be deleted from UI workflows.

## 9. Logging

Configured in backend env:
- `APP_LOG_DIR` default `backend/app/data/logs`
- `APP_LOG_FILE` default `backend.log`
- `APP_LOG_MAX_BYTES` default `10485760` (10MB per rotated file)
- `APP_LOG_RETAIN_DAYS` default `7`

## 10. Development Conventions

- Keep data contracts in `backend/app/schemas/*`.
- Keep HTTP concerns in `backend/app/routers/*`.
- Keep LDAP/domain logic in `backend/app/services/*`.
- Frontend views are grouped by domain under `frontend/src/views/*`.
- Prefer explicit, minimal side effects in watchers and request flows.

## 11. Test Commands

Backend tests:

```bash
cd backend
source .venv/bin/activate
python -m unittest discover -s tests -p 'test_*.py' -v
```

Frontend build validation:

```bash
cd frontend
npm run build
```

## 12. Default Local Admin

Created automatically on first startup:
- username: `admin`
- password: `admin123`

Change password immediately in System Management.
