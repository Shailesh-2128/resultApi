# Complete AWS EC2 Production Deployment Guide

This guide details how to deploy the **Django Results Management & Display System** on a single AWS EC2 instance for domain **`matkaresult.kingwins.pro`**, connected to your **Supabase PostgreSQL** database and **Matka API** (`matkaapi.com`).

---

## 📋 System Requirements & Architecture

- **Target Domain**: `matkaresult.kingwins.pro`
- **AWS EC2 Instance**: `t3.small` (2 vCPU, 2 GB RAM) or `t3.micro`
- **Operating System**: Ubuntu 22.04 LTS / 24.04 LTS
- **Database**: Supabase PostgreSQL (Remote)
- **Application Stack**: Docker Compose (`web` + `worker` + `beat` + `redis`)
- **Reverse Proxy**: Nginx + Let's Encrypt SSL (HTTPS)

---

## ⚡ Quick 5-Step Deployment

### Step 1: Launch AWS EC2 Instance

1. Log in to your [AWS EC2 Management Console](https://console.aws.amazon.com/ec2/).
2. Click **Launch Instance**.
3. **Name**: `Results-Management-App`
4. **AMI**: Ubuntu Server 22.04 LTS (64-bit x86).
5. **Instance Type**: Select `t3.small` (recommended) or `t3.micro`.
6. **Key Pair**: Select your existing SSH key pair (`.pem`).
7. **Network Settings / Security Group**:
   - Create Security Group named `results-app-sg`
   - Add Inbound Rules:
     - **SSH**: Port `22` | Source: `0.0.0.0/0`
     - **HTTP**: Port `80` | Source: `0.0.0.0/0`
     - **HTTPS**: Port `443` | Source: `0.0.0.0/0`
8. Click **Launch Instance**.

---

### Step 2: Point Domain DNS (`matkaresult.kingwins.pro`)

In your Domain DNS Provider (Cloudflare, Namecheap, Route 53, GoDaddy) for `kingwins.pro`:
- **Type**: `A Record`
- **Host / Name**: `matkaresult`
- **Value**: `YOUR_EC2_PUBLIC_IP`
- **TTL**: `Auto` or `300`

---

### Step 3: Connect to EC2 & Clone Repository

Connect via SSH:
```bash
ssh -i /path/to/your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

Clone repository onto EC2:
```bash
git clone https://github.com/your-username/resultApi.git
cd resultApi
```

---

### Step 4: Verify `.env` Environment Secrets

Check `.env` configuration:
```bash
nano .env
```

Ensure domain and credentials are set:
```env
SECRET_KEY=generate-a-strong-random-50-character-secret-key
DEBUG=False
ALLOWED_HOSTS=matkaresult.kingwins.pro,YOUR_EC2_PUBLIC_IP,localhost,127.0.0.1
TIME_ZONE=Asia/Kolkata

# Supabase PostgreSQL Connection
DATABASE_URL=postgresql://postgres.kvpfmrtzlluepteqbufb:Shaileshapi@aws-0-ap-south-1.pooler.supabase.com:5432/postgres

# Matka API Provider Credentials
RESULT_API_URL=https://www.matkaapi.com/mapi/market_api.php
RESULT_API_KEY=6dc0d710909e4710a1df481c6e095be8
RESULT_API_DOMAIN=matkaresult.kingwins.pro

# Polling Settings
RESULT_POLL_INTERVAL=15
RESULT_MAX_POLL_MINUTES=30
RESULT_MAX_RETRIES=100

# Redis Connection
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

---

### Step 5: Run Automated One-Click Deployment Script

Make `deploy.sh` executable and run it:
```bash
chmod +x deploy.sh
./deploy.sh
```

The script automatically:
- Installs Docker, Docker Compose, Nginx, and Certbot.
- Starts Docker containers (`web`, `worker`, `beat`, `redis`).
- Applies Supabase PostgreSQL migrations (`python manage.py migrate`).
- Seeds default superuser (`admin` / `admin123`) and initial market schedules.
- Configures Nginx reverse proxy to port `8000`.
- Obtains free SSL certificate via Let's Encrypt for `matkaresult.kingwins.pro`.

---

## 🌐 Post-Deployment Verification

1. **Public Website**: Visit `https://matkaresult.kingwins.pro/`
2. **Management Dashboard**: Visit `https://matkaresult.kingwins.pro/dashboard/`
3. **Public Matka REST API**: `GET https://matkaresult.kingwins.pro/api/results/all/`
4. **Django Admin**: `https://matkaresult.kingwins.pro/admin/` (Login: `admin` / `admin123`)

---

## 🛠️ Useful Management Commands

### Live Logs:
```bash
sudo docker compose logs -f
```

### Manual SSL Renewal Test:
```bash
sudo certbot renew --dry-run
```
