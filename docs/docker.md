# Docker Deployment

This document is the single source of truth for Docker deployment of `samba-admin`.

## 1. What This Guide Covers

- Docker installation on Ubuntu
- First-time startup
- Daily operations
- Unified configuration policy (`docker/backend.env` + `docker/compose.env`)
- systemd runtime and deploy workflows
- Troubleshooting for real production issues

## 2. Deployment Files

```text
samba-admin/
├─ docker/
│  ├─ backend.Dockerfile
│  ├─ frontend.Dockerfile
│  ├─ backend.env.example
│  ├─ backend.env                # local, ignored by Git
│  ├─ compose.env.example
│  ├─ compose.env                # local, ignored by Git
│  ├─ nginx.conf
│  └─ systemd/
│     ├─ samba-admin@.service
│     ├─ samba-admin-deploy@.service
│     └─ install-systemd.sh
├─ docker-compose.yml            # tracked baseline
└─ data/                         # backend runtime data on host
```

## 3. Install Docker (Ubuntu)

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

Optional Docker group (no `sudo` for docker CLI):

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Remove Docker group access later:

```bash
sudo gpasswd -d $USER docker
```

## 4. First-Time Startup

1. Create local env files:

```bash
cp docker/backend.env.example docker/backend.env
cp docker/compose.env.example docker/compose.env
```

2. Edit `docker/backend.env` and set required values at least:
- `APP_JWT_SECRET`
- `LDAP_HOST`
- `LDAP_BIND_USER`
- `LDAP_BIND_PASSWORD`
- `LDAP_BASE_DN`

3. (Optional) Edit `docker/compose.env` for ports, data path, and limits.

4. Build and start:

```bash
docker compose --env-file docker/compose.env up -d --build
```

Default URLs:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## 5. Configuration Policy (Important)

Current policy is intentionally simple:
- Do not use `docker-compose.override.yml`
- Do not edit tracked `docker-compose.yml` directly on servers
- Put server-specific values only in:
  - `docker/backend.env`
  - `docker/compose.env`

Why:
- deterministic behavior
- less `git pull --ff-only` conflict risk
- easier operations and debugging

If advanced compose layering is needed later, add it as a separate documented change.

## 6. `docker/compose.env` Variables

`docker-compose.yml` reads runtime/deploy parameters from these variables:

- `BACKEND_ENV_FILE` (default `docker/backend.env`)
- `BACKEND_PORT` (default `8000`)
- `FRONTEND_PORT` (default `5173`)
- `BACKEND_DATA_PATH` (default `./data`)
- `BACKEND_CPUS` (default `1.00`)
- `BACKEND_MEM_LIMIT` (default `1g`)
- `BACKEND_MEM_RESERVATION` (default `512m`)
- `FRONTEND_CPUS` (default `0.50`)
- `FRONTEND_MEM_LIMIT` (default `512m`)
- `FRONTEND_MEM_RESERVATION` (default `256m`)

Example:

```bash
BACKEND_ENV_FILE=docker/backend.env
BACKEND_PORT=8000
FRONTEND_PORT=5174
BACKEND_DATA_PATH=./data
BACKEND_CPUS=1.00
BACKEND_MEM_LIMIT=1g
BACKEND_MEM_RESERVATION=512m
FRONTEND_CPUS=0.50
FRONTEND_MEM_LIMIT=512m
FRONTEND_MEM_RESERVATION=256m
```

Apply changes:

```bash
docker compose --env-file docker/compose.env up -d --force-recreate
```

## 7. Daily Operations

Start:

```bash
docker compose --env-file docker/compose.env up -d
```

Stop:

```bash
docker compose --env-file docker/compose.env down
```

Rebuild and recreate:

```bash
docker compose --env-file docker/compose.env up -d --build --force-recreate
```

Status:

```bash
docker compose --env-file docker/compose.env ps
```

Logs:

```bash
docker compose --env-file docker/compose.env logs -f backend
docker compose --env-file docker/compose.env logs -f frontend
```

Host log file:

```bash
tail -f data/logs/backend.log
```

Resource usage:

```bash
docker stats
docker stats samba-admin-backend samba-admin-frontend
docker system df
docker system df -v
```

## 8. systemd Workflows

Install/update systemd units (safe to run multiple times):

```bash
./docker/systemd/install-systemd.sh
sudo systemctl daemon-reload
```

The installer replaces placeholders with your current absolute repo path.

### 8.1 Runtime Unit (`samba-admin@...`)

Purpose: fast operations without build.

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

Boot auto-start:

```bash
sudo systemctl enable samba-admin@all
sudo systemctl disable samba-admin@all
```

### 8.2 Deploy Unit (`samba-admin-deploy@...`)

Purpose: pull + rebuild + recreate.

What deploy does:
1. `git pull --ff-only`
2. `docker compose ... up -d --build --force-recreate`

Commands:

```bash
sudo systemctl start samba-admin-deploy@backend
sudo systemctl start samba-admin-deploy@frontend
sudo systemctl start samba-admin-deploy@all
sudo systemctl status samba-admin-deploy@all
```

Notes:
- Deploy unit is `oneshot`; use `start`, not `restart`
- Runtime restart remains `samba-admin@all`

## 9. Validation Commands

Check resolved compose config:

```bash
docker compose --env-file docker/compose.env config | sed -n '/frontend:/,/restart/p'
```

Check actual published ports:

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep samba-admin-frontend
```

Check applied resource limits:

```bash
docker inspect samba-admin-backend --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}'
docker inspect samba-admin-frontend --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}'
```

## 10. Troubleshooting

### 10.1 `fatal: detected dubious ownership`

Symptom:

```text
fatal: detected dubious ownership in repository at '/home/<user>/samba-admin'
```

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

### 10.2 `git pull --ff-only` fails in deploy

Common reasons:
- uncommitted tracked changes
- non-fast-forward branch state
- network/DNS/Git auth issue

Check manually:

```bash
cd /absolute/path/to/samba-admin
git status --porcelain
git pull --ff-only
```

### 10.3 Network/DNS cannot reach GitHub

Symptom example:

```text
Could not resolve host: github.com
```

Quick checks:

```bash
getent hosts github.com || nslookup github.com
ping -c 2 1.1.1.1
curl -I https://github.com --max-time 10
```

### 10.4 systemd result differs from manual compose

If manual `docker compose --env-file docker/compose.env ...` works but systemd behavior differs:

```bash
cd /home/parallels/samba-admin
git pull --ff-only origin main
./docker/systemd/install-systemd.sh
sudo systemctl daemon-reload
sudo systemctl restart samba-admin@all
```

Then verify:

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep samba-admin-frontend
```

### 10.5 Repo moved to a new path

Reinstall units from the new repo location:

```bash
cd /new/absolute/path/to/samba-admin
./docker/systemd/install-systemd.sh
sudo systemctl daemon-reload
```

### 10.6 Full recovery sequence

```bash
cd /home/parallels/samba-admin
git pull --ff-only origin main
./docker/systemd/install-systemd.sh
sudo git config --global --add safe.directory /home/parallels/samba-admin
sudo git config --system --add safe.directory /home/parallels/samba-admin
sudo systemctl daemon-reload
sudo systemctl reset-failed samba-admin-deploy@all
sudo systemctl start samba-admin-deploy@all
sudo systemctl status samba-admin-deploy@all --no-pager -l
```
