#!/usr/bin/env bash
#
# Start vLLM using the TOML experiment config.
# Override config: CONFIG_PATH=configs/fp8_weights.toml bash scripts/start_vllm.sh

set -euo pipefail

exec uv run --extra serving python scripts/serve_vllm.py
