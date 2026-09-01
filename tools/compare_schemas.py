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
    # An int-vs-bigint PK divergence surfaces here - which is about the sequence's
    # TYPE, so the row is keyed on the column the sequence backs, not on the
    # sequence's own name. Postgres does not rename a sequence when its owning
    # table is renamed: after a RenameModel the migrate-built database keeps
    # arxii_commongembucket_id_seq while build_schema.py creates
    # arxii_materialbucket_id_seq for the identical column. Keying on the owner
    # (table, column) makes that a non-event, exactly as normalize_index_line()
    # does for index names - see the module docstring on why names are excluded.
    # deptype 'i' covers identity columns (Django 4.1+ AutoFields) and 'a' the
    # older serial form; refobjsubid > 0 restricts the join to column
    # dependencies, so each sequence yields exactly one row. A sequence with no
    # owning column (a standalone CREATE SEQUENCE) falls back to its own name
    # with an empty column field, so it is still compared rather than dropped.
    "SEQUENCE": """
        SELECT 'SEQUENCE|' || COALESCE(owner.relname, seq.relname) || '|'
               || COALESCE(a.attname, '') || '|'
               || format_type(s.seqtypid, NULL)
        FROM pg_sequence s
        JOIN pg_class seq ON seq.oid = s.seqrelid
        JOIN pg_namespace n ON n.oid = seq.relnamespace
        LEFT JOIN pg_depend d
               ON d.classid = 'pg_class'::regclass
              AND d.objid = s.seqrelid
              AND d.refclassid = 'pg_class'::regclass
              AND d.refobjsubid > 0
              AND d.deptype IN ('a', 'i')
        LEFT JOIN pg_class owner ON owner.oid = d.refobjid
        LEFT JOIN pg_attribute a
               ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
        WHERE n.nspname = 'public'
        ORDER BY 1
    """,
    # pg_inherits also records partitioned INDEX hierarchies (e.g.
    # arxii_interaction_pkey1 <- arxii_interaction_202601_pkey), not just table
    # ones. An index child's relpartbound is always NULL, which would make the
    # whole concatenated row NULL and crash the sort/startswith logic below -
    # restrict to table-kind children ('r' plain, 'p' partitioned) so only real
    # partition attachments are compared.
    "PARTITION": """
        SELECT 'PARTITION|' || parent.relname || '|' || child.relname || '|'
               || pg_get_expr(child.relpartbound, child.oid)
        FROM pg_inherits i
        JOIN pg_class child ON child.oid = i.inhrelid
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_namespace n ON n.oid = parent.relnamespace
        WHERE n.nspname = 'public' AND child.relkind IN ('r', 'p')
        ORDER BY 1
    """,
}

# Differences that are real but deliberately tolerated. Every entry must say
# WHY, because an entry without a reason is indistinguishable from an oversight.
#
# Blind spot: filter_allowed() drops each allowlisted line independently per
# side, not as a matched pair - it never checks that both variants are actually
# present. If, say, auth_group_permissions.id were dropped entirely from one
# database, that side's row would simply be absent while the allowlist still
# silently drops the other side's row, and the diff would report nothing. This
# is inherent to comparing two flat multisets line-by-line, not a defect in any
# one entry - keep entries narrow and re-verify them if a vendored app's own
# schema changes.
ALLOWED_DIFFERENCES: frozenset[str] = frozenset(
    {
        # Vendored Django/allauth M2M through-tables. Their PK width depends on
        # which path built them: the migration chain replays the vendored
        # app's own historical migrations (int), while build_schema.py's
        # migrate --run-syncdb builds from current model state under
        # DEFAULT_AUTO_FIELD (bigint). Both are internally consistent and
        # neither is reachable from first-party code. CLAUDE.md forbids
        # editing dependency code, so this is not ours to reconcile - only to
        # record. Both the bigint (migrate-built) and integer (build_schema-
        # built) forms are listed so the divergent line is dropped from
        # whichever side's snapshot it appears in.
        "COLUMN|auth_group_permissions|id|bigint|false||d",
        "COLUMN|auth_group_permissions|id|integer|false||d",
        "COLUMN|django_flatpage_sites|id|bigint|false||d",
        "COLUMN|django_flatpage_sites|id|integer|false||d",
        "COLUMN|socialaccount_socialapp_sites|id|bigint|false||d",
        "COLUMN|socialaccount_socialapp_sites|id|integer|false||d",
        # Keyed on the owning (table, column) to match SECTION_QUERIES["SEQUENCE"];
        # these are the sequences behind the three id columns listed above.
        "SEQUENCE|auth_group_permissions|id|bigint",
        "SEQUENCE|auth_group_permissions|id|integer",
        "SEQUENCE|django_flatpage_sites|id|bigint",
        "SEQUENCE|django_flatpage_sites|id|integer",
        "SEQUENCE|socialaccount_socialapp_sites|id|bigint",
        "SEQUENCE|socialaccount_socialapp_sites|id|integer",
    }
)


# django_migrations is Django's own migration-bookkeeping table, not
# application schema, and by construction it exists on only one path:
# tools/build_schema.py disables migrations outright and never creates it
# (ADR-0083's #2977 update), while `arx manage migrate` always does. That is a
# single structural fact about the two paths, not six-ish independent
# divergences (a TABLE row, four COLUMN rows, a PK CONSTRAINT row, an INDEX
# row and a SEQUENCE row) - so it is filtered here by object name rather than
# enumerated in ALLOWED_DIFFERENCES one row at a time.
def _is_django_migrations_object(line: str) -> bool:
    """True if the snapshot line's object name is or starts with django_migrations_.

    The '_' boundary keeps this from wrongly excluding a hypothetical unrelated
    table like django_migrationsfoo. 'Starts with' (not just equals) pairs with
    SECTION_QUERIES["SEQUENCE"]'s ownerless fallback: the sequence row normally
    keys on the owning table ('django_migrations'), which the equality arm
    catches, but if that ownership link is ever absent the row falls back to the
    sequence's own name ('django_migrations_id_seq') and only the prefix arm
    catches it. Cheap insurance against this filter re-reddening the nightly.
    """
    object_name = line.split("|", 2)[1]
    return object_name == "django_migrations" or object_name.startswith("django_migrations_")


_INDEX_NAME_RE = re.compile(r"^(CREATE (?:UNIQUE )?INDEX) [^ ]+ (ON )")

# argv[0] is the script name, argv[1:] are the two DSNs.
_EXPECTED_ARGC = 3


def strip_index_name(indexdef: str) -> str:
    """Drop the index's own name from a pg_indexes.indexdef string."""
    return _INDEX_NAME_RE.sub(r"\1 \2", indexdef)


def normalize_index_line(line: str) -> str:
    """Strip the index's own name from a full 'INDEX|table|indexdef' snapshot line.

    strip_index_name()'s regex expects the CREATE clause at the start of the
    string it is given, but the raw snapshot row is 'INDEX|table|indexdef', not
    the bare indexdef - applying strip_index_name() directly to the whole line
    (as an earlier version of this function did) never matched, so index names
    were never actually stripped. Splitting off the indexdef field first keeps
    strip_index_name()'s contract simple and makes the call site correct.
    """
    kind, table, indexdef = line.split("|", 2)
    return "|".join((kind, table, strip_index_name(indexdef)))


def snapshot(dsn: str) -> list[str]:
    """Return the full, sorted catalog snapshot of one database."""
    lines: list[str] = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cursor:
        for query in SECTION_QUERIES.values():
            cursor.execute(query)
            lines.extend(row[0] for row in cursor.fetchall())
    lines = [normalize_index_line(line) if line.startswith("INDEX|") else line for line in lines]
    return sorted(lines)


def filter_allowed(lines: list[str]) -> list[str]:
    """Drop allowlisted lines and django_migrations's own rows before comparison."""
    return [
        line
        for line in lines
        if line not in ALLOWED_DIFFERENCES and not _is_django_migrations_object(line)
    ]


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
