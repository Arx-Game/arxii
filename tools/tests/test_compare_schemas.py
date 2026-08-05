"""Unit tests for the schema-comparison harness's pure functions.

No database: snapshot() is exercised end-to-end by the nightly workflow, while
normalization, allowlisting and diffing are tested here over fixture lines.
"""

import compare_schemas
from compare_schemas import (
    ALLOWED_DIFFERENCES,
    SECTION_QUERIES,
    diff_snapshots,
    filter_allowed,
    normalize_index_line,
    strip_index_name,
)


def test_index_name_is_stripped_so_naming_drift_does_not_register():
    indexdef = (
        "CREATE INDEX arxii_inte_persona_ts_idx ON public.arxii_interaction "
        'USING btree (persona_id, "timestamp")'
    )
    assert strip_index_name(indexdef) == (
        'CREATE INDEX ON public.arxii_interaction USING btree (persona_id, "timestamp")'
    )


def test_unique_index_name_is_stripped_too():
    indexdef = "CREATE UNIQUE INDEX foo_key ON public.bar USING btree (baz)"
    assert strip_index_name(indexdef) == "CREATE UNIQUE INDEX ON public.bar USING btree (baz)"


def test_full_index_snapshot_line_has_its_name_stripped():
    # snapshot() applies name-stripping to the WHOLE raw row - 'INDEX|table|
    # indexdef' - not to a bare indexdef. An earlier version called
    # strip_index_name() directly on that whole line; its regex requires the
    # CREATE clause at position 0, which a pipe-prefixed line never satisfies,
    # so nothing was ever stripped and every index-naming difference between
    # the two schema-construction paths (Django's schema_editor hashes a
    # different name per build, per the module docstring) showed up as a false
    # positive. normalize_index_line() splits the line first so the transform
    # reaches the right substring.
    line = (
        "INDEX|comms_msg|CREATE INDEX comms_msg_db_date_sent_6971d29a "
        "ON public.comms_msg USING btree (db_date_created)"
    )
    assert normalize_index_line(line) == (
        "INDEX|comms_msg|CREATE INDEX ON public.comms_msg USING btree (db_date_created)"
    )


def test_partition_query_only_considers_table_kind_children():
    # pg_inherits also records partitioned INDEX hierarchies (e.g. a global
    # index's per-partition children), not just table ones. An index child's
    # relpartbound is always NULL, which makes the whole concatenated
    # 'PARTITION|...' expression NULL - and snapshot() then crashes on
    # `None.startswith(...)`. snapshot() itself needs a live database with a
    # real partitioned table to exercise end to end (see the nightly workflow),
    # so this pins the fix at the query-text level: the PARTITION query must
    # constrain child.relkind to table kinds ('r', 'p') so index-hierarchy rows
    # with a NULL relpartbound are never selected in the first place.
    partition_query = SECTION_QUERIES["PARTITION"]
    assert "relkind IN ('r', 'p')" in partition_query


def test_identical_snapshots_produce_no_diff():
    lines = ["TABLE|arxii_interaction|p", "COLUMN|arxii_interaction|id|bigint|false||"]
    assert diff_snapshots(lines, list(lines), "a", "b") == ""


def test_a_missing_partition_shows_up_as_a_relkind_change():
    left = ["TABLE|arxii_interaction|r"]
    right = ["TABLE|arxii_interaction|p"]
    result = diff_snapshots(left, right, "migrate", "models")
    assert "TABLE|arxii_interaction|r" in result
    assert "TABLE|arxii_interaction|p" in result


def test_duplicate_definitions_are_compared_as_a_multiset():
    # Two identically-defined constraints on one table must not collapse to one.
    left = ["CONSTRAINT|t|CHECK ((x > 0))", "CONSTRAINT|t|CHECK ((x > 0))"]
    right = ["CONSTRAINT|t|CHECK ((x > 0))"]
    assert diff_snapshots(left, right, "a", "b") != ""


def test_filter_allowed_drops_allowlisted_lines(monkeypatch):
    monkeypatch.setattr(
        compare_schemas, "ALLOWED_DIFFERENCES", frozenset({"SEQUENCE|vendored_id_seq|integer"})
    )
    assert filter_allowed(["SEQUENCE|vendored_id_seq|integer", "TABLE|keepme|r"]) == [
        "TABLE|keepme|r"
    ]


def test_filter_allowed_drops_django_migrations_rows_by_object_name():
    # django_migrations exists only on the migrate-built path (build_schema.py
    # disables migrations outright), which would otherwise be six-ish separate
    # allowlist rows (TABLE, four COLUMN, CONSTRAINT, INDEX, SEQUENCE) for one
    # structural fact - filtered by object name instead of enumerated. 'Starts
    # with' (not just equals) is required for django_migrations_id_seq, whose
    # object name is not the bare table name.
    lines = [
        "TABLE|django_migrations|r",
        "COLUMN|django_migrations|id|bigint|false||d",
        "SEQUENCE|django_migrations_id_seq|bigint",
        "TABLE|django_migration|r",  # singular - not the real table; must survive
        "TABLE|keepme|r",
    ]
    result = filter_allowed(lines)
    assert result == [
        "TABLE|django_migration|r",
        "TABLE|keepme|r",
    ]


def test_allowlist_entries_are_whole_snapshot_lines():
    # Guards against someone allowlisting a fragment or a regex - filter_allowed
    # compares whole lines, so a partial entry would silently never match.
    for entry in ALLOWED_DIFFERENCES:
        assert "\n" not in entry
        assert entry.split("|", 1)[0] in {
            "TABLE",
            "COLUMN",
            "CONSTRAINT",
            "INDEX",
            "SEQUENCE",
            "PARTITION",
        }
