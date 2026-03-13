# Samba Admin Frontend

Vue 3 + Vite frontend for the Samba Admin Console (LDAP-first mode).

## Requirements

- Node.js `20.19+` (or `22.12+`)
- npm `10+` recommended

## Setup

```bash
cd frontend
npm install
cp .env.example .env.development
```

`VITE_API_TARGET` controls where `/api/*` calls are proxied in local development.

## Development

```bash
npm run dev
```

Default URL: `http://127.0.0.1:5173`  
Default API target: `http://127.0.0.1:8000` (from `vite.config.js` fallback)

## Build and Preview

```bash
npm run build
npm run preview
```

Note:
- Vite dev proxy is configured under `server.proxy` in `vite.config.js`.
- `vite preview` serves static build output. For `/api` in deployment, use a reverse proxy (Nginx/Caddy) or same-origin backend routing.

## Main Routes

- `/dashboard`: LDAP health and environment status
- `/users`: user list, group filter, TXT import, CSV export
- `/users/new`: create user
- `/users/edit/:username`: edit user
- `/ous`: OU tree operations
- `/config`, `/versions`: placeholder pages in current LDAP-only mode
