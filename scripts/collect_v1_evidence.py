#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


RECOMMENDED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("deploy_validation", "*deploy*validation*"),
    ("manual_acceptance", "*manual_acceptance*"),
    ("benchmark_report", "*benchmark*report*"),
    ("recovery_drill_report", "*recovery*drill*report*"),
    ("token_lifecycle_report", "*token_lifecycle*drill*report*"),
    ("admin_backup_restore_report", "*admin_backup_restore*drill*report*"),
)


@dataclass(frozen=True)
class EvidenceItem:
    key: str
    pattern: str
    matches: tuple[str, ...]

    @property
    def present(self) -> bool:
        return bool(self.matches)


def collect_evidence(evidence_dir: Path) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for key, pattern in RECOMMENDED_PATTERNS:
        matches = tuple(sorted(path.name for path in evidence_dir.glob(pattern) if path.is_file()))
        items.append(EvidenceItem(key=key, pattern=pattern, matches=matches))
    return items


def render_report(*, evidence_dir: Path, items: list[EvidenceItem]) -> str:
    lines = [
        "# V1 Evidence Status",
        "",
        f"- Evidence directory: `{evidence_dir}`",
        f"- Required artifact groups: `{len(items)}`",
        f"- Present groups: `{sum(1 for item in items if item.present)}`",
        "",
        "## Artifact Groups",
        "",
    ]
    for item in items:
        status = "PASS" if item.present else "MISSING"
        lines.append(f"- {status} `{item.key}`")
        lines.append(f"  - Pattern: `{item.pattern}`")
        if item.matches:
            lines.append(f"  - Files: {', '.join(f'`{name}`' for name in item.matches)}")
        else:
            lines.append("  - Files: none")
    lines.extend(
        [
            "",
            "## Remaining Environment-Bound Work",
            "",
            "- Run deploy/update/rollback evidence on a real target host.",
            "- Capture benchmark and recovery drill reports on target hardware.",
            "- Complete and sign the manual acceptance pack.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize current V1 evidence artifacts.")
    parser.add_argument(
        "--evidence-dir",
        default="docs/v1/evidence",
        help="Directory containing V1 evidence artifacts.",
    )
    parser.add_argument(
        "--output",
        help="Optional markdown output path. Defaults to stdout.",
    )
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.exists():
        raise SystemExit(f"Evidence directory not found: {evidence_dir}")

    items = collect_evidence(evidence_dir)
    report = render_report(evidence_dir=evidence_dir, items=items)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(output_path)
    else:
        print(report, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
