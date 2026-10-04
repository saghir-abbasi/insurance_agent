# Asterisk Environment Local Deployment Guide

## 1. Setup Project Directory
Create and navigate to the deployment directory:
```
mkdir -p /opt/insurance_agent_backend
cd /opt/insurance_agent_backend
```

---

## 2. Clone Required Repositories
Clone the backend repository using Git (replace `<repo-url>` with your repository URL):
```
git clone <repo-url> /opt/insurance_agent_backend
```

Verify repositories:
```
git remote -v
```

---

## 3. Setup Python Virtual Environment
```
python3.12 -m venv venv
source venv/bin/activate
```

---

## 4. Environment Configuration
Create a `.env` file if it does not exist.

Install dependencies:
```
pip install -U pip
pip install .
```

---

## 5. Run Application Server
Start the FastAPI server:
```
uvicorn insurance_agent.main:app --host 0.0.0.0 --port 8002 --reload
or
uvicorn insurance_agent.main:app --host 0.0.0.0 --port 8002 --reload --loop asyncio

```

Update port if required (e.g., 8000 or 8001).

---

## 6. Run Server as a System Service (Permanent Setup)

### Step 1: Create Service File
```
sudo nano /etc/systemd/system/insurance_agent.service
```

### Step 2: Add Configuration
```
[Unit]
Description=Emma Insurance AI Agent FastAPI Service
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/insurance_agent_backend
ExecStart=/opt/insurance_agent_backend/venv/bin/uvicorn insurance_agent.main:app --host 0.0.0.0 --port 8002
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

> Note: Adjust paths (WorkingDirectory and virtual environment path) as per your setup.

---

### Step 3: Enable and Start Service
```
sudo systemctl daemon-reload
sudo systemctl enable insurance_agent.service
sudo systemctl start insurance_agent.service
```

### Step 4: Check Service Status
```
sudo systemctl status insurance_agent.service
```

---

## 7. Updating Code Changes
Navigate to project directory:
```
cd /opt/insurance_agent_backend
```

Reinstall in editable mode:
```
/opt/insurance_agent_backend/venv/bin/pip install -e .
```

Restart service:
```
sudo systemctl restart insurance_agent.service
```
