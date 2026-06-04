#!/usr/bin/env python3
"""Lightweight performance benchmark for JARVIS — produces P50/P95 evidence for V1."""
from __future__ import annotations

import argparse
import json
import platform
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
        return (time.perf_counter() - started) * 1000.0, response.getcode()


def summarize(samples: list[float], name: str) -> dict:
    if not samples:
        return {"name": name, "count": 0, "error": "no samples"}
    ordered = sorted(samples)
    return {
        "name": name,
        "count": len(ordered),
        "min_ms": round(min(ordered), 2),
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(percentile(ordered, 0.95), 2),
        "max_ms": round(max(ordered), 2),
    }


def get_bearer_token(base: str, passphrase: str) -> str | None:
    try:
        payload = json.dumps({"passphrase": passphrase}).encode()
        req = urlrequest.Request(f"{base}/unlock", data=payload, headers={"Content-Type": "application/json"})
        with urlrequest.urlopen(req, timeout=10) as r:
            return json.loads(r.read())["token"]
    except Exception as exc:
        print(f"  [warn] Could not obtain token: {exc}")
        return None


def run_benchmark(base: str, n: int, token: str | None, chat_text: str) -> dict:
    auth_headers: dict[str, str] = {"Authorization": f"Bearer {token}"} if token else {}

    results: dict[str, list[float]] = {"health": [], "chat": [], "metrics": []}
    failures: list[str] = []

    for i in range(n):
        # health (no auth)
        try:
            ms, code = timed_request(f"{base}/health")
            if code == 200:
                results["health"].append(ms)
            else:
                failures.append(f"health[{i}]: HTTP {code}")
        except Exception as exc:
            failures.append(f"health[{i}]: {exc}")

        # chat (requires bearer token)
        try:
            payload = json.dumps({"text": chat_text}).encode()
            headers = {"Content-Type": "application/json", **auth_headers}
            ms, code = timed_request(f"{base}/chat", data=payload, headers=headers)
            if code == 200:
                results["chat"].append(ms)
            else:
                failures.append(f"chat[{i}]: HTTP {code}")
        except Exception as exc:
            failures.append(f"chat[{i}]: {exc}")

        # /sys/metrics (requires session or bearer)
        try:
            ms, code = timed_request(f"{base}/sys/metrics", headers=auth_headers)
            if code == 200:
                results["metrics"].append(ms)
            else:
                failures.append(f"metrics[{i}]: HTTP {code}")
        except Exception as exc:
            failures.append(f"metrics[{i}]: {exc}")

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base,
        "iterations": n,
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "python": platform.python_version(),
        },
        "results": {
            k: summarize(v, k) for k, v in results.items()
        },
        "failures": failures,
        "status": "ok" if not failures else "degraded",
    }


def print_report(report: dict) -> None:
    print(f"\n{'='*52}")
    print(f"  JARVIS Benchmark — {report['timestamp']}")
    print(f"  Target: {report['base_url']}")
    print(f"  Platform: {report['hardware']['platform'][:50]}")
    print(f"{'='*52}")
    for name, s in report["results"].items():
        if s.get("count", 0) == 0:
            print(f"  {name:12s}  NO SAMPLES")
            continue
        p50 = s["p50_ms"]
        p95 = s["p95_ms"]
        status = "✓" if p95 < 2000 else "!"
        print(f"  {status} {name:12s}  p50={p50:7.1f}ms  p95={p95:7.1f}ms  n={s['count']}")
    if report["failures"]:
        print(f"\n  Failures ({len(report['failures'])}):")
        for f in report["failures"][:5]:
            print(f"    • {f}")
        if len(report["failures"]) > 5:
            print(f"    … and {len(report['failures']) - 5} more")
    print(f"\n  Overall: {report['status'].upper()}")
    print(f"{'='*52}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS V1 performance benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--chat-text", default="status jarvis")
    parser.add_argument("--passphrase", default="", help="Auto-fetch a bearer token via /unlock")
    parser.add_argument("--token", default="", help="Existing bearer token")
    parser.add_argument("--output", default="benchmark_local_report.json")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token or None
    if not token and args.passphrase:
        print("  Fetching bearer token…")
        token = get_bearer_token(base, args.passphrase)

    if not token:
        print("  [warn] No token — chat and metrics endpoints will likely return 401.")

    report = run_benchmark(base, args.iterations, token, args.chat_text)
    print_report(report)

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  Report saved → {output_path}")

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
