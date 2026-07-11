#!/bin/bash
# One-time setup for Oracle Cloud Ampere A1 (Ubuntu 22.04 ARM64)
# Run as: bash setup.sh
set -euo pipefail

REPO_URL="https://github.com/YOUR_USERNAME/music-intelligence-atlas.git"
APP_DIR="/home/ubuntu/music-intelligence-atlas"
PYTHON="python3.11"

echo "=== 1. System packages ==="
sudo apt-get update -qq
sudo apt-get install -y git curl wget software-properties-common build-essential libssl-dev

echo "=== 2. Python 3.11 ==="
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update -qq
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

echo "=== 3. Caddy ==="
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update -qq
sudo apt-get install -y caddy

echo "=== 4. Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama
sleep 5
ollama pull llama3

echo "=== 5. Clone repo ==="
if [ -d "$APP_DIR" ]; then
    echo "  Already exists — pulling latest"
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "=== 6. Python venv + deps ==="
$PYTHON -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "=== 7. .env file ==="
if [ ! -f "$APP_DIR/.env" ]; then
    echo ""
    echo "  IMPORTANT: Copy your .env file to $APP_DIR/.env"
    echo "  From your Mac: scp .env ubuntu@<ORACLE_IP>:~/music-intelligence-atlas/.env"
    echo ""
fi

echo "=== 8. systemd service ==="
sudo cp "$APP_DIR/deploy/music-atlas.service" /etc/systemd/system/music-atlas.service
sudo systemctl daemon-reload
sudo systemctl enable music-atlas

echo "=== 9. Caddy config ==="
sudo cp "$APP_DIR/Caddyfile" /etc/caddy/Caddyfile
sudo systemctl enable caddy

echo "=== 10. Oracle firewall (iptables) ==="
# Oracle blocks ports 80/443 at the OS level by default
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || echo "  (install iptables-persistent if persistence is needed)"

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. scp .env ubuntu@<IP>:~/music-intelligence-atlas/.env"
echo "  2. sudo systemctl start music-atlas"
echo "  3. sudo systemctl start caddy"
echo "  4. Point api.pournamiprakash.dev A record → this server's IP"
echo "  5. Add GitHub deploy key: cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys"
