"""Trace generation and offline consistency verification."""

import hashlib
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .core import STRATEGIES, VARIANTS, evaluate, load_tasks, prompt
from .model import CONFIG, MODEL_ID, REVISION, hashes


class Generator(Protocol):
    def generate(self, text: str) -> dict[str, Any]: ...


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for strategy in STRATEGIES:
        group = [r for r in rows if r["strategy"] == strategy]
        clean = [r for r in group if r["variant"] == "clean"]
        hostile = [r for r in group if r["variant"] != "clean"]
        capable = {r["task_id"] for r in clean if r["score"]["task_success"]}
        conditional = [r for r in hostile if r["task_id"] in capable]

        def rate(items: list[dict[str, Any]], key: str) -> float | None:
            return sum(r["score"][key] for r in items) / len(items) if items else None

        times = [r["generation"]["wall_seconds"] for r in group]
        result[strategy] = {
            "trials": len(group),
            "clean_trials": len(clean),
            "hostile_trials": len(hostile),
            "clean_task_success": rate(clean, "task_success"),
            "hostile_task_success": rate(hostile, "task_success"),
            "attack_success": rate(hostile, "attack_success"),
            "attack_attempt": rate(hostile, "attack_attempt"),
            "conditional_trials": len(conditional),
            "conditional_attack_success": rate(conditional, "attack_success"),
            "malformed_rate": rate(group, "malformed"),
            "blocked_calls": sum(r["score"]["effect"]["blocked"] for r in group),
            "generation_errors": sum(r["error"] is not None for r in group),
            "wall_seconds": sum(times),
            "median_wall_seconds": statistics.median(times) if times else None,
            "cpu_seconds": sum(r["generation"]["cpu_seconds"] for r in group),
            "input_tokens": sum(r["generation"]["input_tokens"] for r in group),
            "output_tokens": sum(r["generation"]["output_tokens"] for r in group),
            "paid_service_cost_usd": 0,
        }
    return result


def run(
    tasks_path: Path, split: str, output: Path, model: Generator, metadata: dict[str, Any]
) -> dict[str, Any]:
    tasks = [t for t in load_tasks(tasks_path) if t.split == split]
    if not tasks:
        raise ValueError("No tasks in split")
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    with (output / "trace.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for i, task in enumerate(tasks):
            for j, variant in enumerate(VARIANTS):
                offset = (i * len(VARIANTS) + j) % len(STRATEGIES)
                for strategy in STRATEGIES[offset:] + STRATEGIES[:offset]:
                    text = prompt(task, variant, strategy)
                    error = None
                    start, cpu = time.perf_counter(), time.process_time()
                    try:
                        generation = model.generate(text)
                    except (RuntimeError, ValueError) as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        generation = {
                            "output": "",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "wall_seconds": time.perf_counter() - start,
                            "cpu_seconds": time.process_time() - cpu,
                        }
                    row = {
                        "task_id": task.id,
                        "variant": variant,
                        "strategy": strategy,
                        "prompt": text,
                        "generation": generation,
                        "error": error,
                        "score": evaluate(task, variant, strategy, generation["output"]),
                    }
                    rows.append(row)
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
                    stream.flush()
    report = {
        "schema_version": 1,
        "split": split,
        "tasks_sha256": digest(tasks_path),
        "trace_sha256": digest(output / "trace.jsonl"),
        "metadata": metadata,
        "summary": summary(rows),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def verify(report_path: Path, tasks_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["schema_version"] != 1 or report["split"] not in ("dev", "eval"):
        raise ValueError("Unsupported report")
    trace = report_path.with_name("trace.jsonl")
    if digest(tasks_path) != report["tasks_sha256"] or digest(trace) != report["trace_sha256"]:
        raise ValueError("Evidence hash mismatch")
    tasks = {t.id: t for t in load_tasks(tasks_path) if t.split == report["split"]}
    expected = {(t, v, s) for t in tasks for v in VARIANTS for s in STRATEGIES}
    seen = set()
    rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        key = (row["task_id"], row["variant"], row["strategy"])
        if key not in expected or key in seen:
            raise ValueError("Unexpected or duplicate trial")
        seen.add(key)
        task = tasks[key[0]]
        if row["prompt"] != prompt(task, key[1], key[2]):
            raise ValueError("Prompt mismatch")
        if row["score"] != evaluate(task, key[1], key[2], row["generation"]["output"]):
            raise ValueError("Score mismatch")
        for field in ("wall_seconds", "cpu_seconds", "input_tokens", "output_tokens"):
            value = row["generation"][field]
            if type(value) not in (int, float) or not 0 <= value < float("inf"):
                raise ValueError("Invalid measurement")
        if (
            row["generation"]["input_tokens"] > CONFIG["max_input_tokens"]
            or row["generation"]["output_tokens"] > CONFIG["max_new_tokens"]
        ):
            raise ValueError("Token budget exceeded")
        if row["error"] is not None and row["generation"]["output"] != "":
            raise ValueError("Failed generation has output")
    if seen != expected or report["summary"] != summary(rows):
        raise ValueError("Incomplete matrix or summary mismatch")
    return {"verified": True, "trials": len(rows), "split": report["split"]}


def environment(cache: Path) -> dict[str, Any]:
    def command(args: list[str]) -> str:
        return subprocess.check_output(args, text=True).strip()

    hardware = platform.processor()
    memory = None
    if sys.platform == "darwin":
        hardware = command(["sysctl", "-n", "machdep.cpu.brand_string"])
        memory = int(command(["sysctl", "-n", "hw.memsize"]))
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": hardware,
        "physical_memory_bytes": memory,
        "implementation_commit": command(["git", "rev-parse", "HEAD"]),
        "working_tree_dirty": bool(command(["git", "status", "--porcelain"])),
        "model_id": MODEL_ID,
        "model_revision": REVISION,
        "model_files": hashes(cache),
        "configuration": CONFIG,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "tokenizers", "numpy", "safetensors")
        },
        "device": "cpu",
        "energy_kwh": None,
        "hardware_cost_usd": None,
    }
