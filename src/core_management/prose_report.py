"""How much player-facing prose is still a placeholder (#2980).

Scans a content root directly - fixture JSON rows plus the prose domains'
markdown frontmatter - and counts, per domain, how many prose-bearing rows have
a writer and how many do not. A row's writer is recorded by
``world.contributors.models.CreditedContent``, which round-trips through export
and load, so the corpus carries the answer without a database.

Django-free on purpose, the same contract ``content_health.py`` keeps: no Django
imports at module scope, so this runs against a bare lore-repo checkout where a
writer has no game database at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

import yaml

from core_management.prose_fields import PROSE_FIELD_NAMES

WRITTEN_BY = "written_by"
REVIEWED_BY = "reviewed_by"
FRONTMATTER_DELIMITER = "---"

#: Every ``DOMAIN_BUILDERS`` key in ``content_fixtures.py`` (#2980 fix 2): each one
#: is a directory of one markdown file per entry, frontmatter + body, whether or
#: not it also round-trips back out through ``content_export`` (only the four
#: ``content/*`` domains here do - the other six are build-only). Not imported
#: from ``content_fixtures`` directly - this module avoids any dependency on it
#: to stay a plain tuple import, so keep this list in sync with
#: ``DOMAIN_BUILDERS`` by hand.
MARKDOWN_SOURCE_DOMAIN_DIRS = (
    "stats",
    "skills",
    "npc_roles",
    "items",
    "building_kinds",
    "decoration_kinds",
    "content/codex_entries",
    "content/beginnings",
    "content/starting_areas",
    "content/traditions",
)


@dataclass
class DomainProse:
    """Prose counts for one authoring domain."""

    domain: str
    prose_rows: int = 0
    written: int = 0
    reviewed: int = 0
    words: int = 0

    @property
    def unwritten(self) -> int:
        return self.prose_rows - self.written


@dataclass
class ProseReport:
    """Corpus-wide prose authoring state."""

    rows_by_domain: dict[str, DomainProse] = field(default_factory=dict)

    @property
    def prose_rows(self) -> int:
        return sum(row.prose_rows for row in self.rows_by_domain.values())

    @property
    def written(self) -> int:
        return sum(row.written for row in self.rows_by_domain.values())

    @property
    def unwritten(self) -> int:
        return self.prose_rows - self.written

    @property
    def words(self) -> int:
        return sum(row.words for row in self.rows_by_domain.values())


def _count(report: ProseReport, domain: str, fields: dict, extra_words: int = 0) -> None:
    """Fold one row's prose and credit state into *report*.

    ``extra_words`` carries a markdown entry's body, which is prose held outside
    any named field: the exporter writes it as the document body and the builder
    maps it back onto the model's own prose column.
    """
    words = extra_words + sum(
        len(value.split())
        for key, value in fields.items()
        if key.lower() in PROSE_FIELD_NAMES and isinstance(value, str) and value.strip()
    )
    if not words:
        return
    row = report.rows_by_domain.setdefault(domain, DomainProse(domain=domain))
    row.prose_rows += 1
    row.words += words
    if fields.get(WRITTEN_BY):
        row.written += 1
    if fields.get(REVIEWED_BY):
        row.reviewed += 1


def _fixture_records(path: Path) -> list:
    """One fixture file's record list; [] when unreadable or not a list."""
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return records if isinstance(records, list) else []


def _scan_fixture_json(content_root: Path, report: ProseReport) -> None:
    """Count prose rows in ``fixtures/<domain>/<model>.json``."""
    fixtures_dir = content_root / "fixtures"
    if not fixtures_dir.is_dir():
        return
    grid_dir = fixtures_dir / "grid"
    for path in sorted(fixtures_dir.rglob("*.json")):
        if path.is_relative_to(grid_dir):
            continue
        domain = path.relative_to(fixtures_dir).parts[0]
        for record in _fixture_records(path):
            fields = record.get("fields") if isinstance(record, dict) else None
            if isinstance(fields, dict):
                _count(report, domain, fields)


def _parse_markdown_entry(path: Path) -> tuple[dict, int] | None:
    """One entry's frontmatter dict + body word count; None when malformed."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None
    end = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == FRONTMATTER_DELIMITER),
        None,
    )
    if end is None:
        return None
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    body = "\n".join(lines[end + 1 :]).strip()
    return meta, len(body.split())


def _scan_markdown(content_root: Path, report: ProseReport) -> None:
    """Count prose entries in the markdown domains, credits from frontmatter."""
    for domain in MARKDOWN_SOURCE_DOMAIN_DIRS:
        domain_dir = content_root / domain
        if not domain_dir.is_dir():
            continue
        for path in sorted(domain_dir.rglob("*.md")):
            parsed = _parse_markdown_entry(path)
            if parsed is None:
                continue
            meta, body_words = parsed
            _count(report, domain, meta, extra_words=body_words)


def scan_corpus(content_root: Path) -> ProseReport:
    """Walk *content_root* and report prose authoring state per domain."""
    report = ProseReport()
    _scan_fixture_json(content_root, report)
    _scan_markdown(content_root, report)
    return report


def render_report(report: ProseReport) -> list[str]:
    """Render human-readable report lines, worst-off domain first."""
    lines = [
        f"{report.unwritten} of {report.prose_rows} prose rows still have no writer "
        f"({report.words} prose words in the corpus)."
    ]
    lines.extend(
        f"  {row.domain:<24} {row.unwritten:>4} unwritten / {row.prose_rows:>4} rows"
        f"   {row.words:>6} words   {row.reviewed:>4} reviewed"
        for row in sorted(report.rows_by_domain.values(), key=lambda r: -r.unwritten)
    )
    return lines
