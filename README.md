# Django Results Management & Display System

A production-ready **results management and display web application** using **Django 5** for backend & frontend templates, **Supabase PostgreSQL** as the database, **Celery + Redis** for background scheduled result polling, and **Django REST Framework** for clean JSON APIs.

---

## 🌟 Key Features

* **Market Management**: Configure active markets, external API aliases, and daily declaration times (`first_result_time`, `second_result_time`). Adding a market via Django Admin requires zero Python code changes.
* **Scheduled Background Polling**: Celery Beat schedules polling tasks when result times arrive. Celery workers poll the external API based on configured intervals (`RESULT_POLL_INTERVAL`), max poll window (`RESULT_MAX_POLL_MINUTES`), and max retries.
* **Idempotent Storage**: Unique database-level constraints on `(market, result_date, result_type)` prevent duplicate daily result entries.
* **Audit Trail**: Every fetch operation records status in `FetchAttempt` (`WAITING`, `FETCHING`, `SUCCESS`, `NOT_AVAILABLE`, `FAILED`, `TIMEOUT`), with error details and HTTP response codes visible in Django Admin.
* **Responsive Dark UI**: Modern dark theme built with Bootstrap 5, glassmorphism cards, status badges ("170-8", "Waiting for result", "Updating...", "Temporarily unavailable").
* **Client-Side Live Refresh**: Vanilla JavaScript polls internal Django REST API (`/api/results/today/`) every 30 seconds to update result cards dynamically without page reload.
* **REST API**: Normalized JSON endpoints (`/api/results/today/`, `/api/results/?date=YYYY-MM-DD`, `/api/markets/`, `/api/markets/<slug>/results/`).
* **Supabase PostgreSQL Integration**: Fully supported via `dj-database-url` and `psycopg2`.

---

## 🏗️ Architecture Overview

```text
External Result API
        │
        ▼
   Celery Worker (markets.tasks)
        │ (ResultFetcherService & ResultAPIClient)
        ▼
   Supabase PostgreSQL <─────── Django Admin / ORM
        │
        ▼
   Django REST API (/api/results/today/)
        │
        ▼
   Vanilla JS Frontend (30s Background Auto-Refresh)
```

---

## 🚀 Quick Setup Guide

### 1. Prerequisites
- **Python 3.12+** installed.
- **Redis** server running locally (or via Docker).
- **Supabase PostgreSQL database** (or SQLite fallback for offline development).

---

### 2. Local Environment Setup

#### Clone repository & navigate to directory:
```bash
cd f:\resultApi
```

#### Create and activate virtual environment:
**Windows (PowerShell/CMD):**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### Install dependencies:
```bash
pip install -r requirements.txt
```

---

### 3. Environment Configuration (`.env`)

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Configure settings inside `.env`:
```env
SECRET_KEY=your-production-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,*
TIME_ZONE=Asia/Kolkata

# Database URL (Supabase PostgreSQL)
DATABASE_URL=postgresql://postgres.xxx:your-password@aws-0-region.pooler.supabase.com:6543/postgres

# External Result API Credentials
RESULT_API_URL=https://api.example.com/v1/results
RESULT_API_KEY=your_secret_api_key
RESULT_API_DOMAIN=api.example.com

# Polling Rules
RESULT_POLL_INTERVAL=15
RESULT_MAX_POLL_MINUTES=30
RESULT_MAX_RETRIES=100

# Redis & Celery
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
```

*Note: If `DATABASE_URL` is commented out or left blank, the application gracefully defaults to SQLite for local development.*

---

### 4. Supabase Setup Guide

1. Log in to [Supabase](https://supabase.com) and create a project.
2. Go to **Project Settings** -> **Database**.
3. Under **Connection string**, copy the URI under **Transaction Pooler** or **Direct Connection**.
4. Paste it as `DATABASE_URL` in `.env`.
5. Run Django migrations:
   ```bash
   python manage.py migrate
   ```
6. Verify in Supabase Dashboard -> **Table Editor** that tables (`markets_market`, `markets_result`, `markets_fetchattempt`) appear automatically.

---

### 5. Database Migration & Seed Data

Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

Seed default superuser (`admin` / `admin123`) and sample active markets:
```bash
python manage.py seed_data
```

To manually create a custom admin superuser:
```bash
python manage.py createsuperuser
```

---

### 6. Running Local Servers

#### A. Run Django Web Server:
```bash
python manage.py runserver
```
Access the application at `http://127.0.0.1:8000/` and Admin Portal at `http://127.0.0.1:8000/admin/`.

#### B. Run Redis:
Using Docker:
```bash
docker run -p 6379:6379 -d redis:7-alpine
```

#### C. Run Celery Worker:
**Windows (Requires Execution Pool flag):**
```bash
celery -A config worker -l info -P solo
```

**Linux/macOS:**
```bash
celery -A config worker -l info
```

#### D. Run Celery Beat Scheduler:
```bash
celery -A config beat -l info
```

---

## 🧪 Running Automated Tests

Run the full Django test suite (models, DRF API, tasks, idempotency):
```bash
python manage.py test
```

---

## ☁️ AWS EC2 Single-Instance Deployment

The project includes an automated one-click deployment script [`deploy.sh`](file:///f:/resultApi/deploy.sh) and a comprehensive step-by-step guide [`AWS_EC2_DEPLOYMENT.md`](file:///f:/resultApi/AWS_EC2_DEPLOYMENT.md).

### Quick 1-Command EC2 Deploy:
On your Ubuntu 22.04 LTS AWS EC2 instance:
```bash
git clone https://github.com/your-username/resultApi.git
cd resultApi
chmod +x deploy.sh
./deploy.sh
```

---

## 🐳 Local Docker Deployment

Start the complete application stack (Web, Celery Worker, Celery Beat, Redis) using Docker Compose:

```bash
docker compose up -d --build
```

View logs:
```bash
docker compose logs -f
```

Stop stack:
```bash
docker compose down
```

---

## 🌐 Production Deployment (Gunicorn + Nginx + Systemd)

### 1. Gunicorn Command
```bash
gunicorn --config gunicorn.conf.py config.wsgi:application
```

### 2. Nginx Reverse Proxy Setup
Copy `nginx.conf` to `/etc/nginx/sites-available/results_project` and enable it:
```bash
sudo ln -s /etc/nginx/sites-available/results_project /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Systemd Services Setup
Copy service files from `deployment/systemd/` to `/etc/systemd/system/`:
```bash
sudo cp deployment/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn celery_worker celery_beat
```

---

## 🛠️ Troubleshooting

1. **Supabase Connection Error (`OperationalError` / Connection Refused)**:
   - Ensure `psycopg2-binary` is installed.
   - Verify network firewall / ISP allows outbound connection to port 5432 or 6543 (Pooler).
   - Test fallback to SQLite by temporarily commenting out `DATABASE_URL` in `.env`.

2. **Celery Worker Error on Windows (`ValueError: not enough values to unpack`)**:
   - Celery on Windows requires the `-P solo` or `-P gevent` flag when running worker commands locally.
   - Example: `celery -A config worker -l info -P solo`.

3. **Redis Connection Refused**:
   - Ensure Redis server is active on `127.0.0.1:6379` or update `REDIS_URL` in `.env`.

4. **Timezone Discrepancies**:
   - Verify `TIME_ZONE=Asia/Kolkata` (or your local timezone) in `.env`.
   - Django settings use `USE_TZ = True` for proper timezone conversion.

---

## 📝 Deliverables Summary

- [x] Django 5 Web Application Structure
- [x] Supabase PostgreSQL Database Integration & Migrations
- [x] Custom Django Admin with Status Badges and Editable Schedules
- [x] External API Service Abstraction (`ResultAPIClient` & `ResultFetcherService`)
- [x] Celery & Celery Beat Scheduled Background Polling Tasks
- [x] Idempotency & Database Unique Constraints
- [x] Responsive Bootstrap 5 Public Frontend & Date History Selector
- [x] REST API Endpoints with DRF
- [x] Vanilla JS Client-Side Auto-Refresh (30s interval)
- [x] Automated Unit Test Suite
- [x] Dockerfile & Docker Compose Stack
- [x] Production Deployment Configs (Gunicorn, Nginx, Systemd)
