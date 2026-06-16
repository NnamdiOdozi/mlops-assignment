#!/usr/bin/env bash
#
# Start vLLM with the official Docker image and a checked-in config file.
# The image carries the heavy serving stack (CUDA runtime, PyTorch,
# Transformers and vLLM), keeping those packages out of the app uv env.
#
# Optional overrides:
#   VLLM_IMAGE=vllm/vllm-openai:v0.22.1
#   HF_CACHE_DIR=$HOME/.cache/huggingface

set -euo pipefail

VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:v0.22.1}"
HF_CACHE_DIR="${HF_CACHE_DIR:-$HOME/.cache/huggingface}"
mkdir -p "$HF_CACHE_DIR"

exec docker run --rm \
    --gpus all \
    --ipc=host \
    -p 8000:8000 \
    -v "$PWD/infra:/infra:ro" \
    -v "$HF_CACHE_DIR:/root/.cache/huggingface" \
    -e "HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN:-}" \
    "$VLLM_IMAGE" \
    --config /infra/vllm_config.yaml
