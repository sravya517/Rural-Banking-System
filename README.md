# 🏦 Rural Banking System

A secure, lightweight Flask web application for rural banking services, supporting customer registration, deposits, withdrawals, fund transfers, transaction histories, and administrative oversight.

---

## 📋 Table of Contents
- [Features](#features)
- [How to Run Locally](#how-to-run-locally)
- [Running with Docker & Docker Compose](#running-with-docker--docker-compose)
- [Running Tests](#running-tests)
- [CI/CD Pipeline Overview](#cicd-pipeline-overview)
- [GitHub Secrets Configuration](#github-secrets-configuration)
- [Deploying via SSH (SSH Plus)](#deploying-via-ssh-ssh-plus)

---

## ✨ Features
- **Account Management**: User registration with auto-generated account numbers (`RB-XXXX`) and initial demo balance.
- **Transactions**: Funds transfer between users, direct deposits, withdrawals, and full transaction history.
- **Admin Dashboard**: Comprehensive administration panel to view system statistics, browse all registered customer accounts, inspect in-depth customer profiles and transaction histories, and safely delete user accounts.
- **Security**: Password hashing via `werkzeug.security`, CSRF token protection on all forms, HTTP-only secure session cookies, and SQLite foreign key constraints.

---

## 🚀 How to Run Locally

### Prerequisites
- **Python 3.10+** (Tested on Python 3.13)
- **pip** package manager

### 1. Clone the repository & navigate to the folder
```bash
git clone https://github.com/nikhithareddyvari/Rural-Banking-System.git
cd Rural-Banking-System
```

### 2. Create and activate a virtual environment
- **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
- **Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (Optional but recommended)
Set an administrator password and custom secret key:
- **Windows (PowerShell):**
  ```powershell
  $env:ADMIN_PASSWORD="YourSecureAdminPassword123"
  $env:SECRET_KEY="your-secret-key-string"
  ```
- **Linux / macOS:**
  ```bash
  export ADMIN_PASSWORD="YourSecureAdminPassword123"
  export SECRET_KEY="your-secret-key-string"
  ```

> **Note:** If `ADMIN_PASSWORD` is not set, admin login is disabled for security. Standard user registration and logins will still work.

### 5. Start the application
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```
The SQLite database (`banking.db`) and necessary tables will be created automatically on the first request.

---

## 🐳 Hardened Docker Container & Docker Compose

The Docker configuration adheres to enterprise container security best practices:
- **Gunicorn WSGI Server**: Replaces Flask's development server with multi-worker, multi-threaded Gunicorn for high concurrency.
- **Non-Root User**: Runs as unprivileged `appuser:appgroup` (UID 10001) using least privilege principle.
- **Health Check Endpoint**: Built-in `/health` endpoint checked every 30 seconds via Docker `HEALTHCHECK`.
- **Restart Policy**: Configured with `restart: unless-stopped` for automatic recovery from host reboots or unexpected process termination.
- **Persistent Volume**: Database volume mapped to `/data` so SQLite storage is preserved across redeployments.

### Using Docker Compose
1. Create a `.env` file or export `SECRET_KEY` and `ADMIN_PASSWORD`:
   ```env
   SECRET_KEY=supersecretkey12345
   ADMIN_PASSWORD=adminpassword123
   ```
2. Build and run:
   ```bash
   docker compose up -d
   ```
3. Check container health:
   ```bash
   docker compose ps
   ```
4. Access at `http://localhost:5000`.

---

## 🧪 Comprehensive Test Suite (22 Tests)

The test suite in [`tests/test_app.py`](tests/test_app.py) covers authentication, registration, health monitoring, and all **14 money transfer business scenarios**:
- **Scenario 1**: Standard valid transfer between registered users (balance & transaction verification).
- **Scenario 2**: Transfer to pre-seeded demo user (`DEMO-1001`).
- **Scenario 3**: Minimum boundary transfer amount (₹0.01).
- **Scenario 4**: Maximum boundary transfer amount (₹100,000.00).
- **Scenario 5**: Exact balance depletion transfer down to ₹0.00.
- **Scenario 6**: Custom description note handling & persistence.
- **Scenario 7**: Default description fallback (`Money transfer`).
- **Scenario 8**: Rejecting descriptions over 100 characters.
- **Scenario 9**: Rejecting non-numeric transfer amounts (`"five-hundred"`).
- **Scenario 10**: Rejecting empty transfer amounts (`""`).
- **Scenario 11**: Boundary violation: Rejecting zero amounts (₹0.00).
- **Scenario 12**: Boundary violation: Rejecting negative amounts (-₹50.00).
- **Scenario 13**: Boundary violation: Rejecting amounts exceeding limit (> ₹100,000.00).
- **Scenario 14**: Self-transfer rejection (preventing transfers to own account).
- **Additional Security**: Recipient not found, insufficient balance, unauthenticated requests, and CSRF token tampering tests.

Run the tests locally with:
```bash
pytest -v
```

---

## ⚙️ CI/CD Pipeline Overview

The project includes an end-to-end automated pipeline located in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) consisting of three stages:

```
[ Push to main / PR ]
         │
         ▼
  ┌──────────────┐
  │ 1. Run Tests │  (Runs pytest on Python 3.13)
  └──────┬───────┘
         │ (Only on push to main)
         ▼
  ┌─────────────────────────┐
  │ 2. Build & Push Docker  │  (Pushes to GitHub Container Registry ghcr.io)
  └──────┬──────────────────┘
         │
         ▼
  ┌─────────────────────────┐
  │ 3. Automated Deploy     │  (SSH Plus: Connects to server, pulls image,
  └─────────────────────────┘   restarts container, checks health & cleans up)
```

### 1. `test` Job
Runs pytest on Ubuntu latest with Python 3.13 on every push and pull request.

### 2. `build-and-push` Job
- Automatically executes on pushes to `main` (after tests pass) and on manual dispatch.
- Uses `docker/build-push-action` with Docker Buildx and GitHub Actions cache (`type=gha`).
- Authenticates seamlessly to **GitHub Container Registry (`ghcr.io`)** using the repository's built-in `GITHUB_TOKEN` (no extra setup required).
- Includes ready-to-use support for **Docker Hub** if preferred.

### 3. `deploy` Job (SSH Plus)
Connects securely to your remote server via SSH using `appleboy/ssh-action` and performs an **SSH Plus** deployment sequence:
1. **Pulls** the newly published Docker image from `ghcr.io`.
2. **Gracefully stops & removes** the existing container instance.
3. **Launches** the updated container with:
   - Volume persistence (`rural_banking_data:/data`) so the SQLite database is never lost.
   - Secure environment variable injection (`SECRET_KEY`, `ADMIN_PASSWORD`, etc.).
   - Auto-restart policy (`--restart unless-stopped`).
4. **Health Check**: Waits and verifies that the container status is healthy and running before reporting success.
5. **Image Pruning**: Automatically prunes stale, dangling Docker images to prevent disk exhaustion.

---

## 🔑 GitHub Secrets Configuration

To enable automated deployment via SSH, add the following secrets in your GitHub repository:
**Settings** ➔ **Secrets and variables** ➔ **Actions** ➔ **New repository secret**:

| Secret Name | Description | Example / Required? |
|-------------|-------------|---------------------|
| `SSH_HOST` | Remote server IP address or domain | `192.0.2.1` or `server.example.com` (Required) |
| `SSH_USER` | SSH username | `ubuntu` or `root` (Required) |
| `SSH_PRIVATE_KEY` | Private SSH key (ed25519 or rsa) | Starts with `-----BEGIN ... KEY-----` (Required) |
| `SSH_PORT` | SSH port | `22` (Optional, defaults to 22) |
| `SSH_PASSPHRASE` | Passphrase for private key | (Optional, if key is encrypted) |
| `SECRET_KEY` | Production Flask secret key | Generated 32+ character string (Required) |
| `ADMIN_PASSWORD` | Administrator login password | Strong password (Required for admin dashboard) |
| `ADMIN_USERNAME` | Administrator username | `admin` (Optional, defaults to `admin`) |

---

## 🖥️ Server Setup for SSH Deployment

On your target Linux server:

1. **Install Docker** (if not already installed):
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```
2. **Add SSH user to Docker group** (so Docker commands run without `sudo`):
   ```bash
   sudo usermod -aG docker $USER
   newgrp docker
   ```
3. **Ensure SSH public key is authorized**:
   Add your deployment public key to `~/.ssh/authorized_keys`.
