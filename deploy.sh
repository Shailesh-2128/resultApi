#!/bin/bash
# ==============================================================================
# Automated One-Click AWS EC2 Deployment Script for Results Management System
# Target Domain: matkaresult.kingwins.pro
# Target OS: Ubuntu 22.04 LTS / Ubuntu 24.04 LTS on AWS EC2
# ==============================================================================

set -e

echo "🚀 Starting AWS EC2 Deployment Setup for matkaresult.kingwins.pro..."

# 1. Update package list and install prerequisites
sudo apt-get update -y
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common nginx certbot python3-certbot-nginx git

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "📦 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "✅ Docker installed successfully."
fi

# 3. Install Docker Compose plugin if not present
if ! docker compose version &> /dev/null; then
    echo "📦 Installing Docker Compose plugin..."
    sudo apt-get install -y docker-buildx-plugin docker-compose-plugin
fi

# 4. Check .env file
if [ ! -f .env ]; then
    echo "⚠️ .env file not found! Copying from .env.example..."
    cp .env.example .env
    echo "❗ Please update secrets in .env before proceeding!"
fi

# 5. Build and start Docker services (Web, Celery Worker, Celery Beat, Redis)
echo "🐳 Building and starting Docker containers..."
sudo docker compose down --remove-orphans || true
sudo docker compose up -d --build

# 6. Execute Database Migrations and Collectstatic inside container
echo "🗄️ Running Django Database Migrations on Supabase..."
sudo docker compose exec -T web python manage.py migrate --noinput

echo "🌱 Seeding initial market data and admin superuser..."
sudo docker compose exec -T web python manage.py seed_data || true

echo "📁 Collecting static files..."
sudo docker compose exec -T web python manage.py collectstatic --noinput

# 7. Configure Nginx Reverse Proxy
echo "🌐 Configuring Nginx Reverse Proxy for matkaresult.kingwins.pro..."
sudo tee /etc/nginx/sites-available/results_project > /dev/null <<'EOF'
server {
    listen 80;
    server_name matkaresult.kingwins.pro;

    client_max_body_size 20M;

    location /static/ {
        alias /var/lib/docker/volumes/resultapi_static_volume/_data/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/results_project /etc/nginx/sites-enabled/results_project
sudo rm -f /etc/nginx/sites-enabled/default || true
sudo nginx -t
sudo systemctl restart nginx

# 8. Obtain Free SSL Certificate via Let's Encrypt
echo "🔒 Issue SSL Certificate for matkaresult.kingwins.pro..."
sudo certbot --nginx --non-interactive --agree-tos -m admin@kingwins.pro -d matkaresult.kingwins.pro || true

echo "=============================================================================="
echo "🎉 AWS EC2 DEPLOYMENT COMPLETED SUCCESSFULLY!"
echo "=============================================================================="
echo "🌐 Production Domain: https://matkaresult.kingwins.pro/"
echo "⚙️ Management Dashboard: https://matkaresult.kingwins.pro/dashboard/"
echo "📊 Public REST API: https://matkaresult.kingwins.pro/api/results/all/"
echo "🔑 Default Admin Login: admin / admin123"
echo "=============================================================================="
