"""Unit tests for the schema-comparison harness's pure functions.

No database: snapshot() is exercised end-to-end by the nightly workflow, while
normalization, allowlisting and diffing are tested here over fixture lines.
"""

import re

import compare_schemas
from compare_schemas import (
    ALLOWED_DIFFERENCES,
    diff_snapshots,
    filter_allowed,
    normalize_index_line,
    strip_index_name,
)


class _FakeCursor:
    """Stands in for a psycopg cursor, answering execute()/fetchall() from `rows_for`."""

    def __init__(self, rows_for):
        self._rows_for = rows_for
        self._pending: list[tuple[object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query):
        self._pending = [(value,) for value in self._rows_for(query)]

    def fetchall(self):
        return self._pending


class _FakeConnection:
    """Stands in for a psycopg connection; snapshot() only needs `.cursor()`."""

    def __init__(self, rows_for):
        self._rows_for = rows_for

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def cursor(self):
        return _FakeCursor(self._rows_for)


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


def test_snapshot_strips_index_names_at_the_real_call_site(monkeypatch):
    # Regression seam for the wiring bug, not just the pure function:
    # normalize_index_line() alone (see the test above) does not prove
    # snapshot() actually calls it. Fake out psycopg.connect so snapshot() runs
    # for real and reach the assertion through its own output - reverting the
    # call site back to strip_index_name(line) makes this fail, because that
    # regex never matches a 'INDEX|table|...'-prefixed line (see
    # normalize_index_line()'s docstring).
    def rows_for(query: str) -> list[str]:
        if "'INDEX|'" in query:
            return [
                "INDEX|comms_msg|CREATE INDEX comms_msg_db_date_sent_6971d29a "
                "ON public.comms_msg USING btree (db_date_created)"
            ]
        return []

    monkeypatch.setattr(
        compare_schemas.psycopg, "connect", lambda *_a, **_kw: _FakeConnection(rows_for)
    )
    lines = compare_schemas.snapshot("fake-dsn")
    assert lines == [
        "INDEX|comms_msg|CREATE INDEX ON public.comms_msg USING btree (db_date_created)"
    ]


def test_snapshot_partition_query_excludes_null_bound_index_children(monkeypatch):
    # Behavioral pin for the PARTITION crash fix, run through snapshot() itself
    # rather than asserting on the query's source text. The fake cursor
    # simulates what pg_inherits/pg_class actually contain: a real partitioned
    # table child (relkind 'p', a real relpartbound) and a partitioned INDEX's
    # own per-partition child (relkind 'i', relpartbound always NULL - see the
    # comment above SECTION_QUERIES["PARTITION"]). It derives which rows the
    # real query would admit by reading the *actual* relkind allowlist out of
    # SECTION_QUERIES["PARTITION"]'s live text, so if that clause is ever
    # loosened or removed, the NULL-bound row is re-admitted here too and
    # snapshot() reproduces the original `None.startswith(...)` crash - this
    # test does not need to be told what the clause says.
    catalog = [("p", "FOR VALUES FROM (MINVALUE) TO (MAXVALUE)"), ("i", None)]

    def rows_for(query: str) -> list[str | None]:
        if "'PARTITION|'" not in query:
            return []
        match = re.search(r"relkind IN \(([^)]+)\)", query)
        allowed = (
            {token.strip().strip("'") for token in match.group(1).split(",")} if match else None
        )
        rows: list[str | None] = []
        for relkind, bound in catalog:
            if allowed is not None and relkind not in allowed:
                continue
            rows.append(None if bound is None else f"PARTITION|parent|child|{bound}")
        return rows

    monkeypatch.setattr(
        compare_schemas.psycopg, "connect", lambda *_a, **_kw: _FakeConnection(rows_for)
    )
    lines = compare_schemas.snapshot("fake-dsn")
    assert lines == ["PARTITION|parent|child|FOR VALUES FROM (MINVALUE) TO (MAXVALUE)"]


def test_sequence_query_keys_on_the_owning_column_not_the_sequence_name():
    # Regression pin for #3544, which reddened the nightly migration replay for
    # six consecutive nights. Postgres does not rename a sequence when its owning
    # table is renamed, so after migration 0174's and 0203's RenameModel steps the
    # migrate-built database held arxii_commongembucket_id_seq where
    # build_schema.py had created arxii_materialbucket_id_seq - identical columns,
    # four diff lines, and a gate that is red for a reason nobody needs to act on.
    #
    # Asserted against the query's source text because snapshot() is faked here
    # (no database), the same approach the PARTITION test above takes. Reverting
    # the projection to the sequence's own relname fails this.
    query = compare_schemas.SECTION_QUERIES["SEQUENCE"]
    assert "pg_depend" in query, "sequence rows must resolve their owner via pg_depend"
    assert "owner.relname" in query, "sequence rows must key on the OWNING table's name"
    # Both dependency kinds must be admitted: 'i' for identity columns (Django
    # 4.1+ AutoFields) and 'a' for the older serial form.
    assert "'a', 'i'" in query or "'i', 'a'" in query
    # Column dependencies only - without this the namespace/table-level pg_depend
    # rows would multiply each sequence into several snapshot lines.
    assert "refobjsubid > 0" in query


def test_a_renamed_table_produces_no_sequence_diff():
    # The end-to-end shape of #3544 over the snapshot format itself: the same
    # column reached by two paths (renamed vs created fresh) must produce one
    # identical line, regardless of what the underlying sequence is named.
    migrate_built = ["SEQUENCE|arxii_materialbucket|id|bigint"]
    schema_built = ["SEQUENCE|arxii_materialbucket|id|bigint"]
    assert diff_snapshots(migrate_built, schema_built, "migrate", "models") == ""


def test_an_int_vs_bigint_sequence_still_diffs_under_the_owner_anchored_key():
    # The divergence the SEQUENCE section exists to catch must survive the
    # re-keying - owner-anchoring removes the NAME noise, not the TYPE signal.
    left = ["SEQUENCE|arxii_personatitle|id|bigint"]
    right = ["SEQUENCE|arxii_personatitle|id|integer"]
    assert diff_snapshots(left, right, "migrate", "models") != ""


def test_allowlisted_sequence_entries_are_owner_anchored():
    # A name-keyed entry ('SEQUENCE|auth_group_permissions_id_seq|bigint') would
    # silently never match after the re-keying, so the vendored through-table
    # divergence it exists to tolerate would resurface as a red nightly. Owner-
    # anchored rows carry four fields; name-keyed ones carried three.
    sequence_entries = [e for e in ALLOWED_DIFFERENCES if e.startswith("SEQUENCE|")]
    assert sequence_entries, "the vendored PK-width entries must still be present"
    for entry in sequence_entries:
        assert len(entry.split("|")) == 4, f"{entry} is not owner-anchored"
        assert not entry.split("|")[1].endswith("_seq"), f"{entry} keys on a sequence name"


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
    # object name is not the bare table name. The '_' boundary keeps a
    # hypothetical unrelated django_migrationsfoo table from being wrongly
    # excluded, and a singular django_migration table (also unrelated) must
    # survive too.
    lines = [
        "TABLE|django_migrations|r",
        "COLUMN|django_migrations|id|bigint|false||d",
        # Owner-anchored form: the sequence row keys on its owning table, so the
        # equality arm catches it.
        "SEQUENCE|django_migrations|id|bigint",
        # Ownerless-fallback form: if the ownership link were ever absent the row
        # keys on the sequence's own name, and only the prefix arm catches it.
        "SEQUENCE|django_migrations_id_seq||bigint",
        "TABLE|django_migration|r",  # singular - not the real table; must survive
        "TABLE|django_migrationsfoo|r",  # no '_' boundary; must survive
        "TABLE|keepme|r",
    ]
    result = filter_allowed(lines)
    assert result == [
        "TABLE|django_migration|r",
        "TABLE|django_migrationsfoo|r",
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
