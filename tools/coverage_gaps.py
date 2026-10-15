"""What no journey reaches (#3657): the bridges to nowhere, from a coverage JSON.

Run via: uv run python tools/coverage_gaps.py .coverage-journeys.json [--min-percent 0]

Reads the JSON ``coverage json`` writes after a run of the journey layer
(``just coverage-journeys``) and lists every source file under ``src/`` that
the journeys executed at or below the threshold, grouped by package, with the
line counts. The list is design input, never a gate: a service function or a
branch no journey touches is either a missing story (write the journey) or a
stub nobody reaches (retire it). Tests, migrations, factories and settings are
left out; they are not behaviour a player reaches.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

_LEFT_OUT = ("/tests/", "/migrations/", "/factories", "/conf/", "/test_settings", "conftest")


@dataclass(frozen=True)
class Gap:
    """One source file the journeys reached at or below the threshold."""

    path: str
    statements: int
    executed: int

    @property
    def percent(self) -> float:
        return 100.0 * self.executed / self.statements if self.statements else 100.0

    @property
    def package(self) -> str:
        parts = self.path.split("/")
        if parts[0] == "world" and len(parts) > 1:
            return f"world.{parts[1]}"
        return parts[0]


def is_left_out(path: str) -> bool:
    return any(marker in f"/{path}" for marker in _LEFT_OUT) or path.endswith("__init__.py")


def gaps_from(report: dict, min_percent: float = 0.0) -> list[Gap]:
    """Files at or below ``min_percent`` executed, by package then by name."""
    out: list[Gap] = []
    for raw_path, data in report.get("files", {}).items():
        path = raw_path.replace("\\", "/")
        path = path.removeprefix("src/")
        if is_left_out(path):
            continue
        summary = data.get("summary", {})
        statements = int(summary.get("num_statements", 0))
        if statements == 0:
            continue
        gap = Gap(path, statements, int(summary.get("covered_lines", 0)))
        if gap.percent <= min_percent:
            out.append(gap)
    return sorted(out, key=lambda g: (g.package, g.path))


def render(gaps: list[Gap], min_percent: float) -> str:
    if not gaps:
        return f"No source file under src/ sits at or below {min_percent:g}% under the journeys.\n"
    by_package: dict[str, list[Gap]] = {}
    for gap in gaps:
        by_package.setdefault(gap.package, []).append(gap)
    lines = [
        f"# What no journey reaches (at or below {min_percent:g}% executed)",
        "",
        f"{len(gaps)} files in {len(by_package)} packages. Each is a missing journey or a stub;",
        "the ledger decides which. Never a gate.",
        "",
        "| Package | Files | Statements unreached |",
        "|---|---|---|",
    ]
    lines += [
        f"| `{package}` | {len(rows)} | {sum(g.statements - g.executed for g in rows)} |"
        for package, rows in sorted(by_package.items(), key=lambda kv: -len(kv[1]))
    ]
    lines += ["", "| File | Statements | Executed |", "|---|---|---|"]
    lines += [f"| `{g.path}` | {g.statements} | {g.executed} ({g.percent:.0f}%) |" for g in gaps]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("report", type=Path, help="the file `coverage json -o` wrote")
    parser.add_argument("--min-percent", type=float, default=0.0)
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    sys.stdout.write(render(gaps_from(report, args.min_percent), args.min_percent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
