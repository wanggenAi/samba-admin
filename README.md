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
- `APP_LOG_BACKUP_COUNT` default `20` (number of rotated backup files to keep)
- `APP_LOG_RETAIN_DAYS` default `7`

Behavior:
- Log rotation by file size is automatic at runtime via `RotatingFileHandler`.
- Old-log cleanup by `APP_LOG_RETAIN_DAYS` runs on backend startup (not a periodic background task).

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

Backend lint:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
ruff check app tests
```

Backend coverage (default fail-under `80`, configurable):

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
COVERAGE_THRESHOLD=80 coverage run -m unittest discover -s tests -p 'test_*.py'
coverage report -m --fail-under="${COVERAGE_THRESHOLD:-80}"
```

Frontend build validation:

```bash
cd frontend
npm run build
```

GitHub CI:
- Workflow file: `.github/workflows/backend-ci.yml`
- Stages: `lint -> test -> coverage`
- Coverage threshold priority: manual dispatch input `coverage_threshold` > repo variable `COVERAGE_THRESHOLD` > default `80`
- Default threshold: `80`

Disable CI stages:
- Manual run (`workflow_dispatch`): set inputs `run_lint=false`, `run_tests=false`, or `run_coverage=false`.
- Repo-level (all push/PR): set GitHub Actions Variables
  - `ENABLE_LINT=false`
  - `ENABLE_TESTS=false`
  - `ENABLE_COVERAGE=false`

Recommended CI-based development workflow:
1. Sync `main` first, then create a feature branch (avoid direct commits to `main`).
2. Implement changes on the feature branch.
3. Run local checks before pushing:

```bash
cd backend
source .venv/bin/activate
ruff check app tests
python -m unittest discover -s tests -p 'test_*.py'
coverage run -m unittest discover -s tests -p 'test_*.py'
coverage report -m --fail-under=80
```

4. Push branch and open a Pull Request to `main`.
5. Wait for GitHub Actions (`lint -> test -> coverage`) to pass.
6. Merge into `main` only after all required CI checks are green.
7. Optionally delete merged feature branch to keep repository clean.

Repo cleanliness (recommended):
- Ignore local-only files and caches via `.gitignore` (see section below).
- If a file was tracked before being ignored, untrack it once:

```bash
git rm --cached .python-version
git rm --cached backend/app/data/rbac.json
git rm --cached -r backend/.ruff_cache backend/**/__pycache__ 2>/dev/null || true
```

Then commit the `.gitignore` update.

## 12. Default Local Admin

Created automatically on first startup:
- username: `admin`
- password: `admin123`

Change password immediately in System Management.

## 13. Server Deployment with systemd

Use separate units for backend/frontend, plus one general wrapper unit to manage both together.

### 1) Backend service

Create `/etc/systemd/system/samba-admin-backend.service`:

```ini
[Unit]
Description=Samba Admin Backend (FastAPI)
After=network-online.target
Wants=network-online.target
PartOf=samba-admin.service

[Service]
Type=simple
# CHANGE: runtime user/group that has access to project files
User=sambaadmin
Group=sambaadmin
# CHANGE: absolute backend path on your server
WorkingDirectory=/opt/samba-admin/backend
# CHANGE: env file location (must be readable by systemd)
EnvironmentFile=/etc/samba-admin/backend.env
# CHANGE: uvicorn path (venv), bind host/port as needed
ExecStart=/opt/samba-admin/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

Recommended env-file workflow (use project template, do not hand-write from scratch):

```bash
# 1) Start from backend/.env.example in this repo (single source of truth).
# 2) Adjust values for your production environment (LDAP host, bind user, secrets, etc.).
# 3) Install it as systemd EnvironmentFile.
sudo install -d -m 755 /etc/samba-admin
sudo cp /opt/samba-admin/backend/.env.example /etc/samba-admin/backend.env
sudo chmod 600 /etc/samba-admin/backend.env
sudo nano /etc/samba-admin/backend.env
```

Notes:
- `backend/.env.example` should contain all supported variables and comments.
- Normal operation is: maintain `.env.example` in repo, then copy/rename it to `/etc/samba-admin/backend.env` on server.
- Do not commit real secrets into git; keep production secrets only in `/etc/samba-admin/backend.env`.

### 2) Frontend service

Create `/etc/systemd/system/samba-admin-frontend.service`:

```ini
[Unit]
Description=Samba Admin Frontend (Vite Preview)
After=network-online.target
Wants=network-online.target
PartOf=samba-admin.service

[Service]
Type=simple
# CHANGE: runtime user/group
User=sambaadmin
Group=sambaadmin
# CHANGE: absolute frontend path on your server
WorkingDirectory=/opt/samba-admin/frontend
# CHANGE: backend URL reachable from frontend service host
Environment=VITE_API_TARGET=http://127.0.0.1:8000
# CHANGE: npm path/port if your environment differs
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port 4173
Restart=on-failure
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

### 3) General stack service

Create `/etc/systemd/system/samba-admin.service`:

```ini
[Unit]
Description=Samba Admin Stack (Backend + Frontend)
# Keep these names aligned with the two unit files above.
Requires=samba-admin-backend.service samba-admin-frontend.service
After=network-online.target samba-admin-backend.service samba-admin-frontend.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
# Keep as-is: wrapper unit only, no long-running process here.
ExecStart=/usr/bin/true
ExecStop=/usr/bin/true

[Install]
WantedBy=multi-user.target
```

### 4) Enable and manage

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now samba-admin.service

sudo systemctl status samba-admin.service samba-admin-backend.service samba-admin-frontend.service
sudo systemctl restart samba-admin.service
sudo systemctl stop samba-admin.service
sudo systemctl start samba-admin.service
```

Service logs:

```bash
sudo journalctl -u samba-admin-backend.service -f
sudo journalctl -u samba-admin-frontend.service -f
```
