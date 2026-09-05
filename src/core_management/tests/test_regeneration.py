"""Django-dependent helpers of ``arx manage squashmigrations arxii`` (ADR-0272)."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

from django.test import SimpleTestCase

from core_management.regeneration import (
    deferred_verdict,
    drop_report,
    post_partition_addfield_sources,
    prune_lint_lists,
)

TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"

RUNPYTHON_RESTRUCTURE = (
    '"""Backfill (#1)."""\n'
    "from django.db import migrations\n\n"
    "def forwards(apps, schema_editor):\n"
    '    Model = apps.get_model("arxii", "Thing")\n'
    "    Model.objects.update(x=1)\n\n"
    "class Migration(migrations.Migration):\n"
    "    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]\n"
)
RUNPYTHON_DISCARD = (
    '"""Discard (#2)."""\n'
    "from django.db import migrations\n\n"
    "def forwards(apps, schema_editor):\n"
    '    apps.get_model("arxii", "Thing").objects.filter(x=None).delete()\n\n'
    "class Migration(migrations.Migration):\n"
    "    operations = [migrations.RunPython(forwards)]\n"
)
RUNSQL = (
    "from django.db import migrations\n\n"
    "class Migration(migrations.Migration):\n"
    '    operations = [migrations.RunSQL(sql=_read_sql("areas", "areaclosure.sql"))]\n'
)


class DropReportTests(SimpleTestCase):
    def test_classifies_restructure_discard_and_carried_sql(self) -> None:
        report = drop_report(
            {
                "0186_backfill": RUNPYTHON_RESTRUCTURE,
                "0207_discard": RUNPYTHON_DISCARD,
                "0101_views": RUNSQL,
            },
            sql_files=["world/areas/sql/areaclosure.sql"],
        )
        assert "0186_backfill" in report
        assert "restructure" in report
        assert "0207_discard" in report
        assert "discard" in report
        assert "0101_views" in report
        assert "carried forward" in report
        assert "Backfill (#1)." in report

    def test_runsql_not_in_sql_files_is_flagged(self) -> None:
        report = drop_report({"0999_odd": RUNSQL.replace("areaclosure", "mystery")}, sql_files=[])
        assert "NOT in SQL_FILES" in report


class DeferredVerdictTests(SimpleTestCase):
    def test_at_or_below_baseline_proceeds(self) -> None:
        assert deferred_verdict(34, 12, None) is None
        assert deferred_verdict(34, 34, None) is None

    def test_no_baseline_proceeds(self) -> None:
        assert deferred_verdict(None, 82, None) is None

    def test_rise_refuses_and_names_the_flag(self) -> None:
        problem = deferred_verdict(34, 82, None)
        assert problem is not None
        assert "34 to 82" in problem
        assert "--accept-deferred 82" in problem

    def test_accepting_the_measured_count_proceeds(self) -> None:
        assert deferred_verdict(34, 82, 82) is None

    def test_accepting_a_different_count_refuses(self) -> None:
        problem = deferred_verdict(34, 82, 80)
        assert problem is not None
        assert "does not match" in problem


class PruneLintListsTests(SimpleTestCase):
    def test_removes_entries_whose_file_is_gone(self) -> None:
        lint = self._tmp(
            "X = frozenset({\n"
            '    "world/migrations/0113_partition.py",\n'
            '    "world/migrations/0999_keep.py",\n'
            "})\n"
        )
        removed = prune_lint_lists([lint], existing_names={"0999_keep"})
        assert removed == {str(lint): ["world/migrations/0113_partition.py"]}
        text = lint.read_text()
        assert '"world/migrations/0113_partition.py"' not in text
        assert '"world/migrations/0999_keep.py"' in text

    def test_nothing_to_prune_leaves_the_file_alone(self) -> None:
        lint = self._tmp('X = {\n    "world/migrations/0999_keep.py",\n}\n')
        before = lint.read_text()
        assert prune_lint_lists([lint], existing_names={"0999_keep"}) == {}
        assert lint.read_text() == before

    def _tmp(self, content: str) -> Path:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
            handle.write(content)
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)


class PostPartitionAddFieldTests(SimpleTestCase):
    """The frozen partition SQL omits some Interaction columns; the tail re-adds them
    from the live model, never from a hand copy (#2982 is what a hand copy costs)."""

    def test_every_post_partition_column_renders_once(self) -> None:
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))
        from check_partition_sql_drift import POST_PARTITION_COLUMNS

        sources, imports = post_partition_addfield_sources()

        assert len(sources) == len(POST_PARTITION_COLUMNS)
        for column in POST_PARTITION_COLUMNS:
            field_name = column.removesuffix("_id")
            # Django's writer emits single quotes; ruff reformats the file later.
            assert sum(f"name='{field_name}'" in source for source in sources) == 1
        assert all(source.startswith("migrations.AddField(") for source in sources)
        assert "model_name='interaction'" in sources[0]
        assert any("django.db.models.deletion" in line for line in imports)
