"""Explicit download and offline CPU inference adapter."""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

MODEL_ID = "google/flan-t5-small"
REVISION = "0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab"
FILES = (
    "config.json",
    "generation_config.json",
    "model.safetensors",
    "spiece.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
)
CONFIG = {"seed": 1729, "threads": 2, "max_input_tokens": 512, "max_new_tokens": 48}


def download(cache: Path) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_ID, revision=REVISION, local_dir=cache, allow_patterns=list(FILES))


def hashes(cache: Path) -> dict[str, str]:
    result = {}
    for name in FILES:
        digest = hashlib.sha256()
        with (cache / name).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result[name] = digest.hexdigest()
    return result


class LocalModel:
    def __init__(self, cache: Path):
        expected = json.loads(Path("data/model-hashes.json").read_text(encoding="utf-8"))
        if hashes(cache) != expected:
            raise ValueError("Model files differ from the pinned artifact hashes")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        torch.set_num_threads(CONFIG["threads"])
        torch.set_num_interop_threads(1)
        torch.manual_seed(CONFIG["seed"])
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(cache, local_files_only=True)
        self.model = (
            AutoModelForSeq2SeqLM.from_pretrained(
                cache, local_files_only=True, use_safetensors=True
            )
            .to("cpu")
            .eval()
        )

    def generate(self, text: str) -> dict[str, Any]:
        start = time.perf_counter()
        cpu = time.process_time()
        inputs = self.tokenizer(text, return_tensors="pt", truncation=False)
        count = inputs["input_ids"].shape[1]
        if count > CONFIG["max_input_tokens"]:
            raise ValueError("Input exceeds token budget; truncation is forbidden")
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs, max_new_tokens=CONFIG["max_new_tokens"], do_sample=False, num_beams=1
            )
        return {
            "output": self.tokenizer.decode(output[0], skip_special_tokens=True),
            "input_tokens": count,
            "output_tokens": len(output[0]) - 1,
            "wall_seconds": time.perf_counter() - start,
            "cpu_seconds": time.process_time() - cpu,
        }
