"""Start vLLM via Docker using the selected TOML experiment configuration."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import CONFIG_PATH, EXPERIMENT_CONFIG, VLLM_CONFIG

VLLM_IMAGE = "vllm/vllm-openai:v0.22.1"


def main() -> None:
    config = VLLM_CONFIG
    port = str(config["port"])

    cmd = [
        "docker", "run",
        "--gpus", "all",
        "--ipc=host",
        "-p", f"{port}:{port}",
        "-v", os.path.expanduser("~/.cache/huggingface") + ":/root/.cache/huggingface",
        VLLM_IMAGE,
        "--model", str(config["model"]),
        "--served-model-name", str(config["served_model_name"]),
        "--host", "0.0.0.0",
        "--port", port,
        "--dtype", str(config["dtype"]),
        "--kv-cache-dtype", str(config["kv_cache_dtype"]),
        "--max-model-len", str(config["max_model_len"]),
        "--gpu-memory-utilization", str(config["gpu_memory_utilization"]),
        "--max-num-seqs", str(config["max_num_seqs"]),
        "--max-num-batched-tokens", str(config["max_num_batched_tokens"]),
        "--seed", str(config["seed"]),
    ]

    quantization = str(config.get("quantization", "")).strip()
    if quantization:
        cmd.extend(["--quantization", quantization])

    if config.get("enable_prefix_caching", False):
        cmd.append("--enable-prefix-caching")

    print(f"Experiment: {EXPERIMENT_CONFIG['name']}")
    print(f"Config:     {CONFIG_PATH}")
    print(f"Command:    {shlex.join(cmd)}")

    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
