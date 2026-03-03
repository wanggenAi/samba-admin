
# Samba Admin Console

A lightweight web-based management system for Samba configuration.

This project provides a simple web UI to:

- Check Samba service status
- Validate smb.conf configuration
- Apply configuration safely
- Automatically reload smbd
- Maintain configuration backups

---

## 🏗 Architecture

Browser (Vue + Vite)
        ↓
FastAPI Backend
        ↓
systemctl / testparm
        ↓
Samba (smbd)

### Development Mode
- Frontend runs on Vite dev server (5173)
- Backend runs on Ubuntu (8000)
- Vite proxy forwards `/api` requests

### Production Mode
- Frontend is built to static files
- FastAPI serves frontend + API on port 8000

---

## 🖥 Environment Requirements

Recommended:

- Ubuntu 24.04 LTS
- Python 3.10+
- Node.js 18+
- Git

---

# 1️⃣ Install Samba (Ubuntu)

sudo apt update
sudo apt install samba -y

Start and enable Samba:

sudo systemctl enable smbd
sudo systemctl start smbd

Check status:

systemctl status smbd

Default configuration file:

/etc/samba/smb.conf

Test configuration:

testparm

---

# 2️⃣ Clone Project

git clone https://github.com/YOUR_GITHUB_USERNAME/samba-admin.git
cd samba-admin

---

# 3️⃣ Backend Setup (Ubuntu)

cd backend

sudo apt install python3-venv -y

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

Start backend (important: use sudo for systemctl access):

sudo -E python -m uvicorn app:app --host 0.0.0.0 --port 8000

Backend API documentation:

http://SERVER_IP:8000/docs

---

# 4️⃣ Frontend Development (Local Machine)

cd frontend
npm install

Create environment file:

frontend/.env.development

VITE_API_TARGET=http://SERVER_IP:8000

Start development server:

npm run dev

Open in browser:

http://localhost:5173

---

# 5️⃣ Production Deployment (Single-Port Mode – No Nginx Required)

## Step 1: Build frontend

cd frontend
npm run build

This generates:

frontend/dist/

## Step 2: Copy dist to backend

scp -r dist user@SERVER_IP:~/samba-admin/backend/

## Step 3: Serve frontend with FastAPI

Add in backend/app.py:

from fastapi.staticfiles import StaticFiles

DIST_DIR = APP_DIR / "dist"
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="spa")

Restart backend:

sudo -E python -m uvicorn app:app --host 0.0.0.0 --port 8000

Access:

http://SERVER_IP:8000

---

# 🔐 Permissions Note

The backend needs permission to:

- Modify /etc/samba/smb.conf
- Execute systemctl reload smbd
- Run testparm

Therefore backend must be started with sudo.

---

# 📁 Data & Versioning

Configuration backups are stored in:

backend/data/versions/

Each apply operation creates a backup for rollback.

---

# 🚀 Features

- Service status monitoring
- Safe config validation
- Automatic reload
- Configuration backup
- Clean and lightweight UI

---

# 👨‍💻 Author

Samba Admin Console – Internship Project
