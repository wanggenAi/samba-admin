
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

---

## 🖥 Environment Requirements

- Ubuntu 24.04 LTS
- Python 3.10+
- Node.js 18+
- Git

---

# 1️⃣ Install Samba (Ubuntu)

sudo apt update
sudo apt install samba -y

sudo systemctl enable smbd
sudo systemctl start smbd

Check status:

systemctl status smbd

Config file:

/etc/samba/smb.conf

Test config:

testparm

---

# 2️⃣ Backend Setup (Ubuntu)

cd backend

sudo apt install python3-venv -y

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

---

# 3️⃣ Frontend Build (Mac or Dev Machine)

cd frontend
npm install
npm run build

This generates:

frontend/dist/

Copy dist to server:

scp -r dist user@SERVER_IP:~/samba-admin/backend/

---

# 4️⃣ Serve Frontend via FastAPI

In backend/app.py add:

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

DIST_DIR = APP_DIR / "dist"

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/")
    async def serve_spa():
        return FileResponse(str(DIST_DIR / "index.html"))

---

# 5️⃣ Run Backend Manually

sudo -E python -m uvicorn app:app --host 0.0.0.0 --port 8000

Access:

http://SERVER_IP:8000

---

# 6️⃣ Deploy Backend as System Service (Recommended)

Create systemd service file:

sudo nano /etc/systemd/system/samba-admin.service

Paste:

[Unit]
Description=Samba Admin FastAPI Service
After=network.target

[Service]
User=root
WorkingDirectory=/home/YOUR_USER/samba-admin/backend
ExecStart=/home/YOUR_USER/samba-admin/backend/.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target

Reload systemd:

sudo systemctl daemon-reload

Enable service:

sudo systemctl enable samba-admin

Start service:

sudo systemctl start samba-admin

Check status:

sudo systemctl status samba-admin

Now backend will automatically start on boot.

---

# 🔐 Permissions Note

Backend requires permission to:

- Modify /etc/samba/smb.conf
- Execute systemctl reload smbd
- Run testparm

Service must run as root.

---

# 📁 Version Backups

Stored in:

backend/data/versions/

Each apply creates a backup.

---

# 🚀 Features

- Service status monitoring
- Safe config validation
- Automatic reload
- Config backup
- Lightweight UI

---

# 👨‍💻 Author

Samba Admin Console – Internship Project
