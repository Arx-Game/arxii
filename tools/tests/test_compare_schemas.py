"""Unit tests for the schema-comparison harness's pure functions.

No database: snapshot() is exercised end-to-end by the nightly workflow, while
normalization, allowlisting and diffing are tested here over fixture lines.
"""

import compare_schemas
from compare_schemas import (
    ALLOWED_DIFFERENCES,
    diff_snapshots,
    filter_allowed,
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
