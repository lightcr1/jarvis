#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


TEMPLATES: tuple[tuple[str, str], ...] = (
    ("deploy_validation.md", "deploy_validation.template.md"),
    ("benchmark_notes.md", "benchmark_notes.template.md"),
    ("recovery_drill_notes.md", "recovery_drill.template.md"),
    ("manual_acceptance_notes.md", "manual_acceptance_checklist.template.md"),
)


def scaffold(output_dir: Path, stamp: str) -> list[Path]:
    template_dir = Path("docs/v1/evidence/templates")
    created: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for target_name, template_name in TEMPLATES:
        source = template_dir / template_name
        target = output_dir / f"{stamp}_{target_name}"
        if target.exists():
            continue
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Create dated V1 evidence note templates.")
    parser.add_argument("--output-dir", default="docs/v1/evidence", help="Target evidence directory.")
    parser.add_argument("--date", default=str(date.today()), help="Date prefix for generated files (YYYY-MM-DD).")
    args = parser.parse_args()

    created = scaffold(Path(args.output_dir), args.date)
    if created:
        for path in created:
            print(path)
    else:
        print("No files created; targets already exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
