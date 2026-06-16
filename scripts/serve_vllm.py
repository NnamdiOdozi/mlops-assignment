"""Start vLLM using the selected TOML experiment configuration."""
from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import CONFIG_PATH, EXPERIMENT_CONFIG, VLLM_CONFIG


def main() -> None:
    config = VLLM_CONFIG

    command = [
        "vllm", "serve", str(config["model"]),
        "--served-model-name", str(config["served_model_name"]),
        "--host", str(config["host"]),
        "--port", str(config["port"]),
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
        command.extend(["--quantization", quantization])

    if config.get("enable_prefix_caching", False):
        command.append("--enable-prefix-caching")

    print(f"Experiment: {EXPERIMENT_CONFIG['name']}")
    print(f"Config:     {CONFIG_PATH}")
    print(f"Command:    {shlex.join(command)}")

    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
