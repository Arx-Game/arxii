#!/usr/bin/env python3
"""Generate and validate the exact-revision #3951 A01-A22 evidence ledger.

This harness never upgrades a missing live prerequisite to PASS.  Reviewers may
replace a row only with captured evidence from the same reviewed revision.
"""

# The subprocess calls intentionally invoke trusted local tools discovered on PATH.
# ruff: noqa: EM101, EM102, S603, S607, TRY003

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import shutil
import subprocess

STATUSES = {"PASS", "BLOCKED", "OUT_OF_SCOPE"}
MIN_REVISION_LENGTH = 7


class LedgerError(ValueError):
    """Raised when a ledger is incomplete or inconsistent."""


@dataclass(frozen=True)
class Gate:
    gate_id: str
    requirement: str
    default_status: str = "BLOCKED"
    default_decision: str = (
        "Live evidence was not captured; rerun this gate in the required environment."
    )


GATES = tuple(
    Gate(f"A{number:02d}", requirement)
    for number, requirement in enumerate(
        (
            "Real account login and game entry through the live backend.",
            "Complete room/exploration state without a scene.",
            "Independent feed and history scrolling on a live app.",
            "Bounded pagination across long histories and equal timestamps.",
            "Reply/thread history navigation.",
            "Collapsed thread reply expansion.",
            "Folded thread read/unread behavior.",
            "History scroll-anchor restoration.",
            "Date-bounded search over retained authorized rows.",
            "Private conversation draft and whisper context.",
            "Deleted or blocked parent reference handling.",
            "Character handoff and private-history isolation.",
            "Language, mute/block, hidden identity, and VERY_PRIVATE boundaries.",
            "Live pose submission and delivery echo.",
            "Retry and stale-response handling across context changes.",
            "Ephemeral-scene high-volume and reconnect behavior.",
            "Encounter reachability while ordinary conversation remains usable.",
            "Mobile, zoom, keyboard, and responsive layout behavior.",
            "Corrupt-storage recovery and cross-account draft isolation.",
            "#3299 OOC dependency: unavailable channel rows are omitted.",
            "Live accessibility/error-state checks.",
            "PostgreSQL migration replay and partition/composite-FK checks.",
        ),
        start=1,
    )
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _database_available() -> bool:
    pg_isready = shutil.which("pg_isready")
    if pg_isready is None:
        return False
    return (
        subprocess.run(
            [pg_isready],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def _browser_available() -> bool:
    return (
        Path(__file__).parents[1] / "frontend" / "node_modules" / ".bin" / "playwright"
    ).exists()


def collect_rows() -> list[dict[str, str]]:
    postgres = _database_available()
    browser = _browser_available()
    rows = []
    for gate in GATES:
        status = gate.default_status
        decision = gate.default_decision
        if gate.gate_id == "A20":
            decision = (
                "#3299 is not delivered. OOC/channel rows are intentionally omitted; "
                "no legacy channel is presented as persistent OOC."
            )
        elif gate.gate_id == "A22":
            decision = (
                "PostgreSQL is unavailable in this environment; migration replay and partition DDL "
                "remain blocked. SQLite results do not prove composite partition integrity."
                if not postgres
                else (
                    "Run migration replay and partition constraint assertions before "
                    "changing this row to PASS."
                )
            )
        elif gate.gate_id in {f"A{n:02d}" for n in range(1, 21)} or gate.gate_id == "A21":
            missing = []
            if not postgres:
                missing.append("live PostgreSQL/backend")
            if not browser:
                missing.append("installed Playwright browser harness")
            decision = (
                "Required live acceptance evidence is blocked: "
                f"{', '.join(missing) or 'test fixture'} is unavailable."
            )
        rows.append({"id": gate.gate_id, "status": status, "evidence": "n/a", "decision": decision})
    return rows


def render(*, revision: str, reviewer: str, verdict: str, rows: list[dict[str, str]]) -> str:
    environment = os.environ.get("EVIDENCE_ENVIRONMENT") or "local devcontainer"
    build = os.environ.get("EVIDENCE_BUILD") or "not captured"
    lines = [
        "# Issue #3951 exact-revision A01-A22 evidence ledger",
        "",
        f"- Reviewed revision: `{revision}`",
        f"- Generated at (UTC): `{datetime.now(UTC).isoformat()}`",
        f"- Reviewer: {reviewer}",
        f"- Reviewer verdict: **{verdict}**",
        f"- Application/build identity: {build}",
        f"- Environment: {environment}",
        "- #3299 decision: OOC/channel rows are unavailable and omitted; "
        "no legacy channel is represented as persistent OOC.",
        "- Evidence rule: a PASS requires evidence captured against the reviewed revision. "
        "BLOCKED and OUT_OF_SCOPE rows require the visible decision below.",
        "",
        "| ID | Status | Evidence | Decision / blocker |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(f"| {r['id']} | {r['status']} | {r['evidence']} | {r['decision']} |" for r in rows)
    return "\n".join(lines) + "\n"


def validate(*, revision: str, verdict: str, rows: list[dict[str, str]]) -> None:
    if not revision or len(revision) < MIN_REVISION_LENGTH:
        raise LedgerError("exact reviewed revision is required")
    if verdict not in STATUSES:
        raise LedgerError(f"reviewer verdict must be one of {sorted(STATUSES)}")
    ids = [row["id"] for row in rows]
    expected = [gate.gate_id for gate in GATES]
    if ids != expected:
        raise LedgerError("ledger must contain exactly A01-A22 in order")
    for row in rows:
        if row["status"] not in STATUSES:
            raise LedgerError(f"invalid status for {row['id']}: {row['status']}")
        if row["status"] != "PASS" and not row["decision"].strip():
            raise LedgerError(f"{row['id']} requires an explicit decision")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--reviewer", default="Pending human reviewer")
    parser.add_argument("--verdict", default="BLOCKED", choices=sorted(STATUSES))
    args = parser.parse_args()
    revision = args.revision or _git("rev-parse", "HEAD")
    rows = collect_rows()
    validate(revision=revision, verdict=args.verdict, rows=rows)
    document = render(revision=revision, reviewer=args.reviewer, verdict=args.verdict, rows=rows)
    if args.output:
        args.output.write_text(document)
    else:
        print(document, end="")


if __name__ == "__main__":
    main()
