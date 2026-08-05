"""Prove two databases have the same schema, whichever path built them.

Arx II supports two schema-construction paths (ADR-0083): replaying the
migration chain (``arx manage migrate``, production's path) and building from
model state (``tools/build_schema.py``, CI's and the devcontainer's path). They
are only useful if they agree, and when they silently stop agreeing the symptom
is not an error - it is a missing object nobody looks for. #2982 is what that
costs: the chain lost the ``arxii_interaction`` partition rewrite in #2906's
squash and nothing noticed for two months, because the per-PR drift gate
compares models to MIGRATIONS and never inspects the resulting SCHEMA.

This dumps an exhaustive, order-stable snapshot of each database's public
schema and diffs them. Every section emits one line per catalog row and is
sorted, so the comparison is a MULTISET - two identically-defined constraints on
one table do not collapse into one.

Constraint and index NAMES are deliberately excluded. Postgres object names are
not semantic, nothing in this repo depends on ours, and the two paths disagree
on roughly fifty of them purely because Django's ``schema_editor`` hashes a
different construction order. Comparing ``(table, definition)`` removes that
noise structurally, so the allowlist below carries only genuine differences and
a non-empty diff is always signal.

Usage:

    uv run python tools/compare_schemas.py <dsn-a> <dsn-b>

Exits 0 when the two are equivalent, 1 with a unified diff when they are not.
"""

from __future__ import annotations

import difflib
import re
import sys

import psycopg

# Catalog facts, one section per query. Each SELECT must return exactly one
# text column and order by it, so the snapshot is stable across runs.
SECTION_QUERIES: dict[str, str] = {
    # relkind is included so a lost partition reads as a kind change ('p' ->
    # 'r') rather than silently matching on name alone.
    "TABLE": """
        SELECT 'TABLE|' || c.relname || '|' || c.relkind::text
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'm', 'v', 'f')
        ORDER BY 1
    """,
    "COLUMN": """
        SELECT 'COLUMN|' || c.relname || '|' || a.attname || '|'
               || format_type(a.atttypid, a.atttypmod) || '|'
               || (NOT a.attnotnull)::text || '|'
               || COALESCE(pg_get_expr(d.adbin, d.adrelid), '') || '|'
               || a.attidentity::text
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped
          AND c.relkind IN ('r', 'p', 'm', 'v', 'f')
        ORDER BY 1
    """,
    # No conname: see the module docstring on why names are excluded.
    "CONSTRAINT": """
        SELECT 'CONSTRAINT|' || c.relname || '|' || pg_get_constraintdef(k.oid)
        FROM pg_constraint k
        JOIN pg_class c ON c.oid = k.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
        ORDER BY 1
    """,
    "INDEX": """
        SELECT 'INDEX|' || tablename || '|' || indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY 1
    """,
    # An int-vs-bigint PK divergence surfaces here.
    "SEQUENCE": """
        SELECT 'SEQUENCE|' || c.relname || '|' || format_type(s.seqtypid, NULL)
        FROM pg_sequence s
        JOIN pg_class c ON c.oid = s.seqrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
        ORDER BY 1
    """,
    "PARTITION": """
        SELECT 'PARTITION|' || parent.relname || '|' || child.relname || '|'
               || pg_get_expr(child.relpartbound, child.oid)
        FROM pg_inherits i
        JOIN pg_class child ON child.oid = i.inhrelid
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_namespace n ON n.oid = parent.relnamespace
        WHERE n.nspname = 'public'
        ORDER BY 1
    """,
}

# Differences that are real but deliberately tolerated. Every entry must say
# WHY, because an entry without a reason is indistinguishable from an oversight.
#
# Populated in Task 4 from the actual verification run.
ALLOWED_DIFFERENCES: frozenset[str] = frozenset()

_INDEX_NAME_RE = re.compile(r"^(CREATE (?:UNIQUE )?INDEX) [^ ]+ (ON )")

# argv[0] is the script name, argv[1:] are the two DSNs.
_EXPECTED_ARGC = 3


def strip_index_name(indexdef: str) -> str:
    """Drop the index's own name from a pg_indexes.indexdef string."""
    return _INDEX_NAME_RE.sub(r"\1 \2", indexdef)


def snapshot(dsn: str) -> list[str]:
    """Return the full, sorted catalog snapshot of one database."""
    lines: list[str] = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cursor:
        for query in SECTION_QUERIES.values():
            cursor.execute(query)
            lines.extend(row[0] for row in cursor.fetchall())
    lines = [strip_index_name(line) if line.startswith("INDEX|") else line for line in lines]
    return sorted(lines)


def filter_allowed(lines: list[str]) -> list[str]:
    """Drop allowlisted lines before comparison."""
    return [line for line in lines if line not in ALLOWED_DIFFERENCES]


def diff_snapshots(left: list[str], right: list[str], left_label: str, right_label: str) -> str:
    """Return a unified diff of two snapshots. Empty string means equivalent."""
    return "".join(
        difflib.unified_diff(
            [f"{line}\n" for line in filter_allowed(left)],
            [f"{line}\n" for line in filter_allowed(right)],
            fromfile=left_label,
            tofile=right_label,
            n=0,
        )
    )


def main(argv: list[str]) -> int:
    if len(argv) != _EXPECTED_ARGC:
        sys.stderr.write("usage: compare_schemas.py <dsn-a> <dsn-b>\n")
        return 2
    left_dsn, right_dsn = argv[1], argv[2]
    left, right = snapshot(left_dsn), snapshot(right_dsn)
    result = diff_snapshots(left, right, "migrate-built", "build_schema-built")
    if result:
        sys.stderr.write(
            "The two schema-construction paths disagree.\n\n"
            "Left is the database built by replaying the migration chain; right "
            "is the one built by tools/build_schema.py. A '-' line is present "
            "only on the left, a '+' line only on the right.\n\n"
        )
        sys.stderr.write(result)
        sys.stderr.write(
            "\nIf this is a standalone SQL step wired into only one path, see "
            "docs/evennia-quirks.md and tools/check_standalone_sql_wiring.py.\n"
        )
        return 1
    print(f"schemas are equivalent ({len(left)} catalog rows compared)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
