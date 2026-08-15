#!/bin/bash
# One-time setup for an Ubuntu VM (Azure B1ms / any Ubuntu 22.04+ host).
# Serves the FastAPI backend behind Caddy (auto-HTTPS). LLM = Groq (no Ollama).
#
# Before running:
#   1. Push this repo to GitHub, then set REPO_URL (env or edit below).
#   2. Point $DOMAIN's A record → this VM's public IP.
#   3. Open ports 22, 80, 443 in the Azure Network Security Group.
#   4. Have your .env ready (R2_* + GROQ_API_KEY + FRONTEND_URL).
#
# Run:  bash deploy/setup.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Pournami-Prakash/Music-Intelligence.git}"
DOMAIN="${DOMAIN:-api.pournamiprakash.dev}"
APP_USER="$(whoami)"
APP_DIR="$HOME/music-intelligence-atlas"
PYTHON="python3.11"

echo "=== 1. Swap (safety on a 2 GB VM — working set is ~1.8 GB) ==="
if ! sudo swapon --show | grep -q '/swapfile'; then
  sudo fallocate -l 3G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "=== 2. System packages ==="
sudo apt-get update -qq
sudo apt-get install -y git curl wget build-essential libgomp1 software-properties-common

echo "=== 3. Python 3.11 ==="
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update -qq
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

echo "=== 4. Caddy ==="
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y caddy

echo "=== 5. Clone repo ==="
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR" && git pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "=== 6. Python venv + SLIM serving deps (requirements-api.txt, NOT the heavy compute stack) ==="
$PYTHON -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-api.txt

echo "=== 7. .env check ==="
if [ ! -f "$APP_DIR/.env" ]; then
  echo "  ⚠️  Copy your .env to $APP_DIR/.env before starting."
  echo "     From your Mac:  scp .env $APP_USER@<VM_IP>:~/music-intelligence-atlas/.env"
  echo "     Must include R2_* + GROQ_API_KEY + FRONTEND_URL=https://pournamiprakash.dev"
fi

echo "=== 8. systemd service (generated for user '$APP_USER') ==="
sudo tee /etc/systemd/system/music-atlas.service >/dev/null <<UNIT
[Unit]
Description=Music Intelligence Atlas API
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=SKIP_STARTUP_WARMUP=1
ExecStart=$APP_DIR/.venv/bin/python3 -m uvicorn src.app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=music-atlas

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable music-atlas

echo "=== 9. Caddy config (auto-HTTPS + reverse proxy for $DOMAIN) ==="
sudo cp "$APP_DIR/Caddyfile" /etc/caddy/Caddyfile
sudo systemctl enable caddy

echo ""
echo "=== Setup complete ==="
echo "Ports 80/443 are opened via the Azure Network Security Group (portal), not iptables."
echo "Start it:"
echo "  sudo systemctl start music-atlas && sudo systemctl restart caddy"
echo "Verify:"
echo "  systemctl status music-atlas --no-pager"
echo "  curl https://$DOMAIN/api/stats"
