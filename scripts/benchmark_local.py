#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


def percentile(sorted_values: list[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * ratio)))
    return sorted_values[idx]


def timed_request(url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[float, int]:
    req = urlrequest.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    started = time.perf_counter()
    with urlrequest.urlopen(req, timeout=30) as response:
        response.read()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return elapsed_ms, response.getcode()


def summarize(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "min_ms": round(min(ordered), 2) if ordered else 0.0,
        "p50_ms": round(statistics.median(ordered), 2) if ordered else 0.0,
        "p95_ms": round(percentile(ordered, 0.95), 2) if ordered else 0.0,
        "max_ms": round(max(ordered), 2) if ordered else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight local benchmark for Jarvis health/chat endpoints.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Jarvis base URL")
    parser.add_argument("--iterations", type=int, default=15, help="Number of requests per endpoint")
    parser.add_argument("--chat-text", default="status jarvis", help="Chat payload for benchmark")
    parser.add_argument("--output", default="benchmark_local_report.json", help="Output JSON report path")
    args = parser.parse_args()

    health_samples: list[float] = []
    chat_samples: list[float] = []
    failures: list[str] = []

    for idx in range(args.iterations):
        try:
            elapsed, status = timed_request(f"{args.base_url.rstrip('/')}/health")
            health_samples.append(elapsed)
            if status != 200:
                failures.append(f"health iteration {idx + 1}: HTTP {status}")
        except (urlerror.URLError, TimeoutError) as exc:
            failures.append(f"health iteration {idx + 1}: {type(exc).__name__}: {exc}")

        try:
            payload = json.dumps({"text": args.chat_text}).encode("utf-8")
            elapsed, status = timed_request(
                f"{args.base_url.rstrip('/')}/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            chat_samples.append(elapsed)
            if status != 200:
                failures.append(f"chat iteration {idx + 1}: HTTP {status}")
        except (urlerror.URLError, TimeoutError) as exc:
            failures.append(f"chat iteration {idx + 1}: {type(exc).__name__}: {exc}")

    report = {
        "base_url": args.base_url,
        "iterations": args.iterations,
        "health": summarize(health_samples),
        "chat": summarize(chat_samples),
        "failures": failures,
        "status": "ok" if not failures else "degraded",
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output_path)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
