"""Emit one deterministic slice of an app's test modules as Django test labels.

CI splits oversized apps (world.magic is a whole shard by itself) below the
app level. A static module list in ci.yml would rot silently: a new test
module added to the app but not to either list would simply never run. This
script makes the split safe by construction — every invocation re-discovers
the app's `test_*.py` modules from disk, partitions them deterministically,
and asserts the parts are a disjoint, complete cover of the discovered set
before printing anything.

Usage (from the repo root):

    uv run python tools/split_test_labels.py world.magic --part 1 --of 2

prints space-separated dotted labels (`world.magic.tests.test_ritual ...`)
for part 1 of a 2-way split, suitable for passing straight to `arx test`.
Both parts run the same code against the same checkout, so they compute the
same partition; part N is stable for a given tree state.

Modules are weighted by their `def test_` count and greedily assigned
(heaviest first) to the currently lightest part, so parts are balanced by
approximate runtime, not module count. A module whose tests are all
inherited from a mixin counts 0 but is still assigned — completeness never
depends on the weight heuristic.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import NoReturn

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

MIN_PARTS = 2

_TEST_DEF_RE = re.compile(r"^\s*def test_", re.MULTILINE)


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def discover_test_modules(app_label: str) -> dict[str, int]:
    """Map each of the app's test modules (dotted label) to its test count."""
    app_dir = SRC_DIR / Path(*app_label.split("."))
    if not app_dir.is_dir():
        _fail(f"app directory not found: {app_dir}")
    modules: dict[str, int] = {}
    for path in sorted(app_dir.rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        label = ".".join(path.relative_to(SRC_DIR).with_suffix("").parts)
        modules[label] = len(_TEST_DEF_RE.findall(path.read_text(encoding="utf-8")))
    if not modules:
        _fail(f"no test_*.py modules found under {app_dir}")
    return modules


def partition(modules: dict[str, int], parts: int) -> list[list[str]]:
    """Greedily balance modules into `parts` bins by descending test count."""
    bins: list[dict] = [{"weight": 0, "labels": []} for _ in range(parts)]
    for label, weight in sorted(modules.items(), key=lambda kv: (-kv[1], kv[0])):
        # min() is stable: ties go to the lowest-index bin, keeping the
        # partition deterministic across both shards' invocations.
        target = min(bins, key=lambda b: b["weight"])
        target["weight"] += weight
        target["labels"].append(label)
    return [sorted(b["labels"]) for b in bins]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", help="App label to split, e.g. world.magic")
    parser.add_argument("--part", type=int, required=True, help="1-indexed part to emit")
    parser.add_argument("--of", type=int, required=True, dest="parts", help="Total parts")
    args = parser.parse_args()

    if args.parts < MIN_PARTS:
        parser.error("--of must be at least 2 (use the plain app label otherwise)")
    if not 1 <= args.part <= args.parts:
        parser.error(f"--part must be in 1..{args.parts}")

    modules = discover_test_modules(args.app)
    if len(modules) < args.parts:
        _fail(f"{args.app} has only {len(modules)} test modules; cannot split {args.parts} ways")
    parts = partition(modules, args.parts)

    # Guard: the parts must be a disjoint, complete cover of what's on disk,
    # with no empty part. If any of this fails, emit nothing and fail the job
    # rather than silently running a subset.
    flat = [label for part in parts for label in part]
    if sorted(flat) != sorted(modules) or any(not part for part in parts):
        _fail("partition is not a disjoint complete cover")

    print(" ".join(parts[args.part - 1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
