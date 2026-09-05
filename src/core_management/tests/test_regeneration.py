"""Django-dependent helpers of ``arx manage squashmigrations arxii`` (ADR-0272)."""

from __future__ import annotations

from pathlib import Path
import sys

from django.test import SimpleTestCase

from core_management.regeneration import post_partition_addfield_sources

TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"


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
