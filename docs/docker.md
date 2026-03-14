# Docker Deployment

This document explains how to run `samba-admin` using Docker.

## 1. Docker Files

```text
samba-admin/
├─ docker/
│  ├─ backend.Dockerfile
│  ├─ frontend.Dockerfile
│  ├─ backend.env.example
│  └─ nginx.conf
├─ docker-compose.yml
└─ data/                      # Host-side persistent runtime data (auto-created)
```

## 2. Quick Start

1. Create your backend environment file:

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

## 3. Default Endpoints

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## 4. Logs

Follow backend logs from Docker:

```bash
docker compose logs -f backend
```

Or read the persisted log file on the host:

```bash
tail -f data/logs/backend.log
```

## 5. Data Persistence

Backend runtime data is stored in the container at:
- `/app/backend/app/data`

It is mapped to the host directory:
- `./data`

Current volume mapping:

```yaml
volumes:
  - ./data:/app/backend/app/data
```

Keep these files/directories when backing up or migrating:
- `rbac.json`
- `logs/`

## 6. How To Change Ports

Edit `docker-compose.yml` and update the host-side port values in `ports`.

Current mappings:
- `8000:8000` means `host:8000 -> backend container:8000`
- `5173:80` means `host:5173 -> frontend container (nginx):80`

Example: change backend to `18000` and frontend to `15173` on host:

```yaml
services:
  backend:
    ports:
      - "18000:8000" # host 18000 -> container 8000

  frontend:
    ports:
      - "15173:80"   # host 15173 -> container 80
```

After changing ports, start again:

```bash
docker compose up -d --build
```

Then access:
- Frontend: `http://localhost:15173`
- Backend: `http://localhost:18000`

## 7. How To Change Paths

You can customize host paths for persistent data and env files.

### 7.1 Change persistent data path

Example: store data in `/srv/samba-admin/data` instead of `./data`:

```yaml
services:
  backend:
    volumes:
      - /srv/samba-admin/data:/app/backend/app/data # host path -> container path
```

Or use a project-relative path:

```yaml
services:
  backend:
    volumes:
      - ./runtime-data:/app/backend/app/data # runtime-data/ will contain logs and rbac.json
```

### 7.2 Change env file path

Example: store env file at `/etc/samba-admin/backend.env`:

```yaml
services:
  backend:
    env_file:
      - /etc/samba-admin/backend.env # host-side env file path
```

## 8. Useful Commands

Start:

```bash
docker compose up -d
```

Stop:

```bash
docker compose down
```

Rebuild:

```bash
docker compose up -d --build
```

List containers:

```bash
docker compose ps
```

## 9. Troubleshooting

Port already in use:
- Change host ports in `docker-compose.yml` (`ports`) and restart.

LDAP connection failed:
- Verify `LDAP_HOST`, `LDAP_PORT`, `LDAP_BIND_USER`, `LDAP_BIND_PASSWORD`, `LDAP_BASE_DN` in `docker/backend.env`.
- Confirm network/firewall/TLS settings between container and LDAP server.

Environment file missing or incomplete:
- Ensure `docker/backend.env` exists and required values are set.
- Recreate from template if needed:
  - `cp docker/backend.env.example docker/backend.env`

Container startup failed:
- Check logs:
  - `docker compose logs backend`
  - `docker compose logs frontend`
- Confirm Docker is running and disk space is sufficient.
