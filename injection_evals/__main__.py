"""Command line entry point."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .experiment import environment, run, verify
from .model import LocalModel, download


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("download", "run", "verify"))
    parser.add_argument("--tasks", type=Path, default=Path("data/tasks.json"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/model"))
    parser.add_argument("--split", choices=("dev", "eval"), default="eval")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    result: dict[str, Any]
    try:
        if args.command == "download":
            download(args.cache)
            result = {"downloaded": True}
        elif args.command == "verify":
            if args.report is None:
                raise ValueError("--report is required")
            result = verify(args.report, args.tasks)
        else:
            if args.output is None or args.output.exists():
                raise ValueError("--output must be a new directory")
            metadata = environment(args.cache)
            start = time.perf_counter()
            model = LocalModel(args.cache)
            metadata["model_load_seconds"] = time.perf_counter() - start
            result = run(args.tasks, args.split, args.output, model, metadata)
            if sys.platform != "win32":
                import resource

                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                result["metadata"]["process_peak_rss_bytes"] = peak * (
                    1 if sys.platform == "darwin" else 1024
                )
                (args.output / "report.json").write_text(
                    json.dumps(result, indent=2) + "\n", encoding="utf-8"
                )
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
