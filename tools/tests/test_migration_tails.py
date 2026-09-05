"""The three infrastructure tails a regenerated chain needs (ADR-0272, spec #3656 Design 4).

Rendered from ``tools/build_schema.py``'s ``SQL_FILES`` so the two schema paths cannot
diverge, and shaped so ``tools/check_standalone_sql_wiring.py`` counts every
``_read_sql`` call: literal, one per ``RunSQL``, inside ``operations``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from migration_tails import (
    matview_name,
    read_sql_files,
    render_matviews_tail,
    render_partition_columns_tail,
    render_partition_sql_tail,
    tail_names,
)

REPO = Path(__file__).resolve().parents[2]


def _ops_calls(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    ops = next(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "operations" for t in n.targets)
    )
    assert isinstance(ops, ast.List)
    return [e for e in ops.elts if isinstance(e, ast.Call)]


def _op_names(source: str) -> list[str]:
    names = []
    for call in _ops_calls(source):
        assert isinstance(call.func, ast.Attribute)
        names.append(call.func.attr)
    return names


def test_read_sql_files_matches_build_schema():
    files = read_sql_files(REPO / "tools" / "build_schema.py")
    assert files[0] == "world/scenes/sql/partition_interaction_forward.sql"
    assert "world/areas/sql/areaclosure.sql" in files


def test_matview_name_is_parsed_from_create_statement():
    assert (
        matview_name("-- header\nCREATE MATERIALIZED VIEW areas_areaclosure AS SELECT 1;")
        == "areas_areaclosure"
    )
    assert (
        matview_name("CREATE MATERIALIZED VIEW IF NOT EXISTS codex_subjectbreadcrumb AS ...")
        == "codex_subjectbreadcrumb"
    )


def test_tail_names_follow_the_last_chunk_in_build_schema_order():
    assert tail_names(2, 101) == (
        "0101_g2_partition_sql",
        "0102_g2_partition_columns",
        "0103_g2_matviews",
    )


def test_matviews_tail_has_one_runsql_per_file_with_literal_read_sql_calls():
    src = render_matviews_tail(
        "0103_g2_matviews",
        "0102_g2_partition_columns",
        [
            ("areas", "areaclosure.sql", "areas_areaclosure"),
            ("codex", "subjectbreadcrumb.sql", "codex_subjectbreadcrumb"),
        ],
    )
    assert _op_names(src) == ["RunSQL", "RunSQL"]
    assert '_read_sql("areas", "areaclosure.sql")' in src
    assert 'reverse_sql="DROP MATERIALIZED VIEW IF EXISTS areas_areaclosure;"' in src
    assert "replaces = REPLACED" in src
    assert '("arxii", "0102_g2_partition_columns")' in src
    assert "def _read_sql" in src


def test_partition_sql_tail_pairs_forward_with_reverse():
    src = render_partition_sql_tail(
        "0101_g2_partition_sql",
        "0100_g2_part_100",
        [
            ("scenes", "partition_interaction_forward.sql"),
            ("combat", "interaction_fk_composites_forward.sql"),
        ],
    )
    assert _op_names(src) == ["RunSQL", "RunSQL"]
    assert '_read_sql("scenes", "partition_interaction_forward.sql")' in src
    assert '_read_sql("scenes", "partition_interaction_reverse.sql")' in src
    assert '_read_sql("combat", "interaction_fk_composites_reverse.sql")' in src


def test_partition_columns_tail_wraps_addfields_in_separate_database_and_state():
    src = render_partition_columns_tail(
        "0102_g2_partition_columns",
        "0101_g2_partition_sql",
        [
            'migrations.AddField(model_name="interaction", name="language", '
            'field=models.ForeignKey(to="arxii.language", '
            "on_delete=django.db.models.deletion.SET_NULL, null=True))"
        ],
        {"import django.db.models.deletion", "from django.db import migrations, models"},
    )
    assert _op_names(src) == ["SeparateDatabaseAndState"]
    assert "state_operations=[]" in src.replace(" ", "").replace("\n", "")
    assert "migrations.swappable_dependency(settings.AUTH_USER_MODEL)" in src
    assert "import django.db.models.deletion" in src
    assert src.count("from django.db import migrations, models") == 1


def test_every_tail_is_valid_python():
    for src in (
        render_matviews_tail("0103_g2_matviews", "0102_g2_partition_columns", []),
        render_partition_sql_tail("0101_g2_partition_sql", "0100_g2_part_100", []),
        render_partition_columns_tail(
            "0102_g2_partition_columns", "0101_g2_partition_sql", [], set()
        ),
    ):
        ast.parse(src)
