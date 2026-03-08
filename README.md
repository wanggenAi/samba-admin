# Samba Admin Console

A lightweight web-based management system for Samba (including AD DC mode).

## What it does

- Check Samba service status
- Validate generated `smb.conf` with `testparm`
- Apply config with automatic backup and rollback support
- Manage AD users/groups via `samba-tool` and LDAP

## Architecture

```
Browser (Vue + Vite)
    -> FastAPI backend
    -> systemctl / testparm / samba-tool / LDAP
    -> Samba
```

## Requirements

- Ubuntu 24.04 LTS (server)
- Python 3.10+
- Node.js 18+ (frontend build)
- Git

## 1. Install Samba on server

```bash
sudo apt update
sudo apt install samba -y
```

For AD DC mode (default in this backend), service name is usually `samba-ad-dc`:

```bash
sudo systemctl enable samba-ad-dc
sudo systemctl start samba-ad-dc
sudo systemctl status samba-ad-dc
```

If your server uses classic file service mode, set `SAMBA_SERVICE=smbd` in environment.

## 2. Backend setup

```bash
cd backend
sudo apt install python3-venv -y
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Backend environment variables

Create `backend/.env` (example):

```env
# Samba
SAMBA_SERVICE=samba-ad-dc
SAMBA_CONF=/etc/samba/smb.conf
SAMBA_TESTPARM=testparm
ALLOW_APPLY=false

# LDAP
LDAP_HOST=10.211.55.10
LDAP_PORT=389
LDAP_USE_SSL=false
LDAP_START_TLS=false
LDAP_TLS_SKIP_VERIFY=true
LDAP_BIND_USER=Administrator@EXAMPLE.COM
LDAP_BIND_PASSWORD=change_me
LDAP_BASE_DN=DC=example,DC=com
```

## 4. Run backend manually

From `backend/`:

```bash
sudo -E .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://SERVER_IP:8000/health
```

## 5. Deploy as systemd service (recommended)

Create `/etc/systemd/system/samba-admin.service`:

```ini
[Unit]
Description=Samba Admin FastAPI Service
After=network.target

[Service]
User=root
WorkingDirectory=/home/YOUR_USER/samba-admin/backend
EnvironmentFile=/home/YOUR_USER/samba-admin/backend/.env
ExecStart=/home/YOUR_USER/samba-admin/backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable samba-admin
sudo systemctl start samba-admin
sudo systemctl status samba-admin
```

## 6. Frontend build

```bash
cd frontend
npm install
npm run build
```

This produces `frontend/dist/`. Deploy it with your preferred web serving strategy.

## Security notes (important)

- Do not expose this API directly to the public internet.
- Keep `ALLOW_APPLY=false` by default; enable only on trusted admin hosts.
- Restrict CORS origins in production (avoid wildcard origins).
- Set strong `LDAP_BIND_PASSWORD` via environment, never hardcode in code.
- Run behind a reverse proxy with TLS and authentication.

## Data and backups

- Config backups: `backend/app/data/versions/`
- Last apply payload snapshot: `backend/app/data/last_apply.json`

## API quick check

- `GET /health`
- `GET /api/system/status`
- `POST /api/config/validate`
- `POST /api/config/apply` (requires `ALLOW_APPLY=true`)
- `GET /api/versions/`
- `POST /api/versions/{id}/rollback`
- `GET /api/ldap/health`
- `POST /api/users`
