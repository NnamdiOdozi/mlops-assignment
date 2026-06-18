#!/bin/bash
# GPU node setup — run once after SSH-ing into a fresh GPU instance.
# Usage: bash scripts/setup_gpu.sh

set -e

REPO_URL="https://github.com/NnamdiOdozi/mlops-assignment.git"
PROJECT_DIR="$HOME/mlops-assignment"

echo "=== Git config ==="
git config --global user.name "NnamdiOdozi"
git config --global user.email "NnamdiOdozi@users.noreply.github.com"
git config --global pull.rebase true

echo "=== Clone or pull repo ==="
if [ -d "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
    git pull
else
    git clone "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

echo "=== Install python3-dev headers ==="
sudo apt-get update -y && sudo apt-get install -y python3-dev

echo "=== Install Node.js (for Claude Code) ==="
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

echo "=== Install Claude Code ==="
sudo npm install -g @anthropic-ai/claude-code

echo "=== Install uv ==="
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "=== Install Python 3.12 via uv ==="
uv python install 3.12

echo "=== Install project dependencies ==="
uv sync

echo "=== Install Docker + NVIDIA Container Toolkit ==="
sudo apt-get install -y nvidia-container-toolkit && \
    sudo nvidia-ctk runtime configure --runtime=docker && \
    sudo apt install -y docker-compose && \
    sudo adduser "$(id -un)" docker && \
    sudo systemctl restart docker

echo "=== Pull vLLM Docker image ==="
sg docker -c "docker pull vllm/vllm-openai:v0.22.1"

echo "=== Download BIRD data ==="
uv run python scripts/load_data.py

echo "=== Start observability stack ==="
sg docker -c "docker compose up -d"

echo "=== Create logs directory ==="
mkdir -p logs

echo ""
echo "=== Done ==="
echo ""
echo "Next steps (copy-paste each block):"
echo ""
echo "  1. Copy your .env file into $PROJECT_DIR/"
echo ""
echo "  2. Activate docker group (REQUIRED before any docker command):"
echo "     newgrp docker"
echo ""
echo "  3. Reload shell to pick up uv path:"
echo "     source \$HOME/.local/bin/env"
echo ""
echo "  4. Start vLLM (in background):"
echo "     export CONFIG_PATH=configs/fp8_weights.toml"
echo "     CONFIG_PATH=\$CONFIG_PATH nohup uv run python scripts/serve_vllm.py > logs/vllm.log 2>&1 & echo \$! > logs/vllm.pid"
echo ""
echo "  5. Start agent server (4 workers, in background):"
echo "     CONFIG_PATH=\$CONFIG_PATH PYTHONUNBUFFERED=1 nohup uv run uvicorn agent.server:app --host 127.0.0.1 --port 8001 --workers 4 > logs/agent.log 2>&1 & echo \$! > logs/agent.pid"
echo ""
echo "  6. Run eval:"
echo "     CONFIG_PATH=\$CONFIG_PATH uv run python scripts/test_five.py --agent-url http://localhost:8001/answer"
echo ""
echo "  7. SSH port forwarding (run from your LOCAL machine):"
echo "     ssh -L 8000:localhost:8000 -L 8001:localhost:8001 -L 3000:localhost:3000 -L 9090:localhost:9090 <gpu-host>"
echo "     Then open: Grafana http://localhost:3000 (admin/admin)"
echo "                Prometheus http://localhost:9090"
