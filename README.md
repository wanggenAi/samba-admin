# Samba Admin Console

LDAP-first web console for AD/Samba environments.

## Current project status

This repository currently runs in **LDAP-only mode** for user and OU management.

- Fully available:
  - LDAP health check
  - User list/search/filter/delete
  - User create and edit
  - OU tree browse/create/rename/delete
  - Group listing and group-based user filtering
- Disabled placeholders (by design in current code):
  - Samba config validate/apply APIs (`/api/config/*` -> `501`)
  - Version rollback APIs (`/api/versions/{id}/rollback` -> `501`, list returns `[]`)

## Architecture

```
Browser (Vue 3 + Vite)
  -> FastAPI backend
  -> LDAP (ldap3)
  -> Active Directory / Samba AD DC
```

## Tech stack

- Backend: FastAPI, ldap3, Pydantic v2
- Frontend: Vue 3, Vue Router, Vite
- Runtime: Python 3.10+, Node.js 18+

## Features implemented

### Dashboard
- LDAP connectivity check (`/api/ldap/health`)
- Shows host, port, base DN, SSL/StartTLS state

### Users page
- OU tree panel with expand/collapse and search (OU/user/DN)
- User list with pagination
- Username column stays visible while horizontal scrolling (sticky column)
- Group column shows memberships per user
- Group filter is **multi-select OR logic**
- Text search includes username/display name/UPN/DN/OU path/groups
- Batch delete selected users
- Protected account guard: `krbtgt` cannot be deleted
- Legacy TXT import (batch create users)
- CSV export (all users with OU path and groups)

### User create/edit
- Create and update use the same API: `POST /api/users`
- Create requires password
- Edit can leave password blank to keep current password
- Paid flag validation: only `"$"` or empty
- OU path single-select input with path parsing rules (see below)
- Groups multi-select (adds memberships)
- Success toast/mask display duration aligned to current UI behavior

### OU manager (`/ous`)
- Separate workspace route for OU operations
- Create OU under selected parent (or base DN)
- Rename selected OU
- Delete OU:
  - tries non-recursive delete first
  - if OU not empty, prompts for recursive delete
- Tree includes OU and user nodes for context

## OU path input rules

Used in user create/edit and documented in OU Manager:

1. Preferred separator is `>` for levels  
   Example: `Students > ms > 63/24`
2. Script-style shorthand is supported  
   Example: `ms-63/24` -> `Students > ms > 63/24`
3. Single value is treated as one OU level
4. Do **not** use `/` or `;` as level separators
5. `/` can be part of OU name (for example `63/24`)

## Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` (example):

```env
# Samba (kept for compatibility; Samba APIs are disabled in current mode)
SAMBA_SERVICE=samba-ad-dc
SAMBA_CONF=/etc/samba/smb.conf
SAMBA_TESTPARM=testparm
ALLOW_APPLY=false

# LDAP connection
LDAP_HOST=127.0.0.1
LDAP_PORT=389
LDAP_USE_SSL=false
LDAP_START_TLS=false
LDAP_TLS_SKIP_VERIFY=true
LDAP_BIND_USER=Administrator@EXAMPLE.COM
LDAP_BIND_PASSWORD=change_me
LDAP_BASE_DN=DC=example,DC=com

# Optional
# LDAP_USER_CONTAINER_DN=CN=Users,DC=example,DC=com
# LDAP_USER_UPN_SUFFIX=example.com
```

Important:
- `LDAP_BIND_PASSWORD` must be set, otherwise LDAP APIs return `400`.
- `LDAP_USE_SSL=true` and `LDAP_START_TLS=true` are mutually exclusive; SSL wins.

Run backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/ldap/health
```

OpenAPI docs:
- `http://127.0.0.1:8000/docs`

## Frontend setup

```bash
cd frontend
npm install
```

Development API target (optional, default already points to localhost:8000):

```bash
echo "VITE_API_TARGET=http://localhost:8000" > .env.development
```

Run frontend dev server:

```bash
npm run dev
```

Build frontend:

```bash
npm run build
npm run preview
```

## API quick reference

### Health and LDAP
- `GET /health`
- `GET /api/ldap/health`
- `GET /api/ldap/users`
- `GET /api/ldap/groups`
- `GET /api/ldap/tree`
- `GET /api/ldap/ou-tree`

### OU operations
- `POST /api/ldap/ou`
  - body: `{ "name": "63/24", "parent_dn": "OU=ms,OU=Students,DC=example,DC=com" }`
- `PATCH /api/ldap/ou`
  - body: `{ "dn": "OU=old,OU=Students,DC=example,DC=com", "new_name": "new" }`
- `DELETE /api/ldap/ou?dn=...&recursive=false|true`

### User operations
- `POST /api/users`
  - create new user if username not found
  - overwrite/update existing user if found
  - if `username` is omitted on create, backend auto-generates it
- `DELETE /api/users/{username}`
- `POST /api/users/import` (multipart form)
  - fields:
    - `files`: one or more `.txt` files
    - `default_group_cn`: default `Students`
    - `password_length`: default `12`
  - response includes per-row status and generated passwords for newly created users
- `GET /api/users/export`
  - downloads CSV with columns:
    `username, first_name, last_name, display_name, student_id, paid_flag, upn, ou_path, groups, dn`

### Legacy TXT import format (reverse-engineered)

Each TXT file is treated as one study group batch.

1. File must contain a line with `группа CODE-NUMBER` (case-insensitive), for example:
   - `Группа МС-63/24`
2. `CODE` mapping:
   - `МС -> ms`
   - `ПЭ -> pe`
   - `Э -> e`
   - `КС -> ks`
   - `ИИ -> ii`
3. Target OU path is generated as:
   - `Students > <mapped code> > <group number>`
4. User rows are lines that contain only Russian letters/spaces.
   - first word is `Last Name`
   - remaining words are `First Name` (supports multi-word)
   - lines containing other symbols (for example `|`, `$`, digits) are ignored, matching old grep-style script behavior
5. Username is generated by old-script style rule:
   - transliterate to ASCII
   - `last_name[:4] + each(first_name_part[:2])`
   - if conflict exists, append numeric suffix
6. If generated base username already exists and existing `givenName/sn` matches imported name, row is skipped.

Minimal example:

```txt
Группа МС-63/24
Иванов Иван
Петров Петр Сергеевич
Сидорова Анна
```

Create user example:

```json
{
  "password": "Test@123456",
  "student_id": "2026001",
  "first_name": "Ivan",
  "last_name": "Ivanov",
  "display_name": "Ivan Ivanov",
  "paid_flag": "$",
  "groups": ["Domain Admins"],
  "ou_path": ["Students", "ms", "63/24"]
}
```

Edit user example (keep password unchanged):

```json
{
  "username": "u10001",
  "password": null,
  "student_id": "2026001",
  "first_name": "Ivan",
  "last_name": "Ivanov",
  "display_name": "Ivan Ivanov",
  "paid_flag": null,
  "groups": ["Domain Users"],
  "ou_path": ["Students", "ms", "63/24"]
}
```

### Samba/config placeholders (current behavior)
- `GET /api/system/status` -> returns `ldap-only` mode status
- `POST /api/config/validate` -> `501`
- `POST /api/config/apply` -> `501`
- `GET /api/versions/` -> `[]`
- `POST /api/versions/{id}/rollback` -> `501`

## Known behavior and limitations

- Group updates are additive (`add member`) in current backend flow.
- Group removal is not automatically applied when a group is unselected in edit UI.
- CORS is currently permissive (`allow_origins=["*"]`) for development convenience.

## Security notes

- Do not expose this API directly to the public Internet.
- Use TLS and authentication at reverse proxy level.
- Keep LDAP bind credentials in environment variables only.
- In production, set strict CORS origins.
