# Docker Deployment

This guide explains how to deploy and operate `samba-admin` with Docker on Ubuntu/Linux.

## 0. Scope And Goals

This document covers:
- Docker installation and verification
- First-time project startup
- Day-to-day operations (start/stop/logs/rebuild)
- systemd management from any working directory
- Fast runtime restart vs full deploy rebuild
- Server-local configuration without Git pull conflicts
- Common deployment pitfalls and exact recovery commands

## 1. Project Docker Files

```text
samba-admin/
├─ docker/
│  ├─ backend.Dockerfile
│  ├─ frontend.Dockerfile
│  ├─ backend.env.example
│  ├─ backend.env                # local, ignored by Git
│  ├─ nginx.conf
│  └─ systemd/
│     ├─ samba-admin@.service
│     ├─ samba-admin-deploy@.service
│     └─ install-systemd.sh
├─ docker-compose.yml            # baseline tracked in Git
├─ docker-compose.override.yml   # local override, ignored by Git
├─ docker-compose.override.example.yml
└─ data/                         # persistent runtime data on host
```

## 2. Install Docker On Ubuntu

Quick install:

```bash
curl -fsSL https://get.docker.com | sh
```

Verify:

```bash
docker --version
docker compose version
sudo systemctl status docker
```

Manage Docker service:

```bash
sudo systemctl start docker
sudo systemctl stop docker
sudo systemctl restart docker
sudo systemctl enable docker
sudo systemctl disable docker
```

Optional: run Docker without `sudo`:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Remove non-sudo access later:

```bash
sudo gpasswd -d $USER docker
```

## 3. First-Time Project Startup

1. Create backend env file:

```bash
cp docker/backend.env.example docker/backend.env
```

2. Edit `docker/backend.env` and set at least:
- `APP_JWT_SECRET`
- `LDAP_HOST`
- `LDAP_BIND_USER`
- `LDAP_BIND_PASSWORD`
- `LDAP_BASE_DN`

3. Build and start all services:

```bash
docker compose up -d --build
```

Default endpoints:
- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## 4. Daily Operations

Start stack:

```bash
docker compose up -d
```

Stop stack:

```bash
docker compose down
```

Rebuild and restart:

```bash
docker compose up -d --build --force-recreate
```

View status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

Host-side log file:

```bash
tail -f data/logs/backend.log
```

## 5. Resource Usage And Data

Real-time container usage:

```bash
docker stats
docker stats samba-admin-backend samba-admin-frontend
```

Disk usage summary:

```bash
docker system df
docker system df -v
```

Data persistence mapping:

```yaml
services:
  backend:
    volumes:
      - ./data:/app/backend/app/data
```

Backup important runtime data:
- `data/rbac.json`
- `data/logs/`

## 6. Ports, Paths, And Env Paths

### 6.1 Change host ports

Use host:container format in `ports`.

Current:
- backend: `8000:8000`
- frontend: `5173:80`

Example:

```yaml
services:
  backend:
    ports:
      - "18000:8000"

  frontend:
    ports:
      - "15173:80"
```

Apply:

```bash
docker compose up -d --build
```

### 6.2 Change persistent data path

Example:

```yaml
services:
  backend:
    volumes:
      - /srv/samba-admin/data:/app/backend/app/data
```

Or project-relative:

```yaml
services:
  backend:
    volumes:
      - ./runtime-data:/app/backend/app/data
```

### 6.3 Change backend env file path

Example:

```yaml
services:
  backend:
    env_file:
      - /etc/samba-admin/backend.env
```

## 7. Server-Local Overrides (Recommended)

To avoid server `git pull` conflicts, do not edit tracked `docker-compose.yml` directly.
Put machine-specific settings in `docker-compose.override.yml`.

Create local override:

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

Use override for:
- host ports
- host bind paths
- server-specific CPU/memory limits

Compose auto-merges:
- `docker-compose.yml` (Git baseline)
- `docker-compose.override.yml` (local server config)

Benefits:
- stable `git pull --ff-only` during deploy
- server-only config stays local

## 8. CPU And Memory Limits

Current limits are defined in `docker-compose.yml`.

Parameters:
- `cpus`: CPU quota (e.g. `"0.50"`, `"1.00"`, `"2.00"`)
- `mem_limit`: hard memory cap (e.g. `"512m"`, `"1g"`)
- `mem_reservation`: soft target under pressure (must be lower than `mem_limit`)

Apply changes:

```bash
docker compose up -d
```

Verify effective limits:

```bash
docker inspect samba-admin-backend --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}'
docker inspect samba-admin-frontend --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}'
```

## 9. systemd Management (Any Directory)

Install units (idempotent; safe to run multiple times):

```bash
./docker/systemd/install-systemd.sh
```

Installed units:
- `samba-admin@.service` (runtime service)
- `samba-admin-deploy@.service` (deploy/rebuild task)

### 9.1 Runtime service (`samba-admin@...`)

Use for fast start/stop/restart (no build).

```bash
sudo systemctl start samba-admin@backend
sudo systemctl start samba-admin@frontend
sudo systemctl start samba-admin@all

sudo systemctl stop samba-admin@backend
sudo systemctl stop samba-admin@frontend
sudo systemctl stop samba-admin@all

sudo systemctl restart samba-admin@all
sudo systemctl status samba-admin@all
journalctl -u samba-admin@all -f
```

Enable at boot (recommended):

```bash
sudo systemctl enable samba-admin@all
sudo systemctl disable samba-admin@all
```

### 9.2 Deploy service (`samba-admin-deploy@...`)

Use for code deploy and image rebuild.

What it does:
1. `git pull --ff-only`
2. `docker compose up -d --build --force-recreate ...`

Commands:

```bash
sudo systemctl start samba-admin-deploy@backend
sudo systemctl start samba-admin-deploy@frontend
sudo systemctl start samba-admin-deploy@all
sudo systemctl status samba-admin-deploy@all
```

Important:
- deploy is a `oneshot` task; use `start` (not `restart`)
- runtime `restart` is still for `samba-admin@all`

## 10. Common Pitfalls And Recovery

### 10.1 `fatal: detected dubious ownership`

Symptom:

```text
fatal: detected dubious ownership in repository at '/home/<user>/samba-admin'
```

Cause:
- deploy unit runs as `root`, and root Git does not trust repo ownership

Fix:

```bash
sudo git config --global --add safe.directory /home/parallels/samba-admin
sudo git config --system --add safe.directory /home/parallels/samba-admin
```

Verify:

```bash
sudo git config --global --get-all safe.directory
sudo git config --system --get-all safe.directory
```

### 10.2 Unit points to old project path

Check:

```bash
systemctl cat samba-admin@all | grep WorkingDirectory
systemctl cat samba-admin-deploy@all | grep WorkingDirectory
```

If wrong, reinstall from current repo path:

```bash
cd /absolute/path/to/current/samba-admin
./docker/systemd/install-systemd.sh
sudo systemctl daemon-reload
```

### 10.3 Deploy fails on `git pull --ff-only`

Possible reasons:
- local uncommitted changes in tracked files
- branch not fast-forward
- Git credential/network issue

Check manually:

```bash
cd /absolute/path/to/samba-admin
git status --porcelain
git pull --ff-only
```

If this manual pull fails, fix Git state first, then run deploy again.

### 10.4 Port already in use

If host port conflicts:
- change ports in `docker-compose.override.yml`
- redeploy

### 10.5 Full recovery sequence

```bash
cd /home/parallels/samba-admin
./docker/systemd/install-systemd.sh
sudo git config --global --add safe.directory /home/parallels/samba-admin
sudo git config --system --add safe.directory /home/parallels/samba-admin
sudo systemctl daemon-reload
sudo systemctl reset-failed samba-admin-deploy@all
sudo systemctl start samba-admin-deploy@all
sudo systemctl status samba-admin-deploy@all --no-pager -l
```

## 11. Command Mapping Reference

Runtime unit mapping:
- `samba-admin@backend` -> `docker compose up -d backend`
- `samba-admin@frontend` -> `docker compose up -d --no-deps frontend`
- `samba-admin@all` -> `docker compose up -d`
- `samba-admin@all` stop -> `docker compose down`

Deploy unit mapping:
- `samba-admin-deploy@backend` -> `git pull --ff-only && docker compose up -d --build --force-recreate backend`
- `samba-admin-deploy@frontend` -> `git pull --ff-only && docker compose up -d --build --force-recreate --no-deps frontend`
- `samba-admin-deploy@all` -> `git pull --ff-only && docker compose up -d --build --force-recreate`
