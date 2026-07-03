"""Build the full Arx II schema from current model state — no migration replay.

Replaces `arx manage migrate` for test/CI database construction (see
ADR: ci-schema-from-models). Mirrors the SQLite fast tier's approach
(server/conf/sqlite_test_settings.py): disable every app's migrations and let
`migrate --run-syncdb` create tables straight from models, then apply the
standalone SQL files (range partition, composite FKs, materialized views) and
the idempotent RunPython seeds that migrations would otherwise carry.

The SQL files + seeds run inside a single `transaction.atomic()` block, so the
`_schema_already_built()` guard's skip/run semantics stay binary: idempotency
is whole-block (skip everything if the partition rewrite already landed, else
run everything), not a per-file resume — a failure partway through rolls the
whole block back rather than leaving some files applied and others not.

Usage (any checkout, any target DB):

    DATABASE_URL=postgres://... uv run python tools/build_schema.py

The target database must exist and should be empty (idempotent on re-run).
"""

import importlib
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

# Ordered: the scenes partition rewrite must precede combat's composite FKs
# (they reference the partitioned table); matviews only need base tables.
#
# society_prestige_ranking.sql is deliberately excluded: societies.0012 drops
# that matview (the SocietyPrestigeRanking model was deleted). The file stays
# in-repo only because historical migrations 0008/0010 still read it at replay.
SQL_FILES = [
    "world/scenes/sql/partition_interaction_forward.sql",
    "world/combat/sql/interaction_fk_composites_forward.sql",
    "world/areas/sql/areaclosure.sql",
    "world/codex/sql/subjectbreadcrumb.sql",
    "world/societies/sql/character_legend_summary.sql",
    "world/societies/sql/covenant_legend_summary.sql",
    "world/societies/sql/guise_legend_summary.sql",
]

# (app_dir, seed function name). Resolved to a dotted migration module path by
# globbing rather than hardcoding a migration number — migration file names can
# be renumbered (e.g. #1801) without this script going stale.
SEED_TARGETS = [
    ("world/progression", "create_social_engagement_category"),
    ("world/magic", "grant_accept_soul_tether_to_all_paths"),
]

# Columns on world.scenes.models.Interaction that real migration replay adds
# *after* the partition rewrite (scenes/0024, scenes/0026) via plain AddField
# — see POST_PARTITION_COLUMNS in tools/check_partition_sql_drift.py. The raw
# SQL in SQL_FILES rebuilds scenes_interaction from a frozen pre-partition
# snapshot that deliberately omits them; with every migration disabled here,
# the AddField migrations that would normally backfill them never run, so
# they must be added explicitly. Keep this list in sync with
# check_partition_sql_drift.py's POST_PARTITION_COLUMNS.
POST_PARTITION_FIELDS = [
    ("scenes", "Interaction", "fury_committed"),
    ("scenes", "Interaction", "writer_account"),
]


class _DisableMigrations:
    """Sentinel: tells Django every app has no migrations."""

    def __contains__(self, item: str) -> bool:
        return True

    def __getitem__(self, item: str) -> None:
        return None


def _seed_modules() -> list[tuple[str, str]]:
    """Resolve each (app_dir, func_name) pair to a dotted module path.

    Globs the app's migrations directory for the file that defines the seed
    function instead of hardcoding a migration number, since migration file
    names can be renumbered independently of this script.
    """
    pairs = []
    for app_dir, func_name in SEED_TARGETS:
        for path in sorted((SRC_DIR / app_dir / "migrations").glob("*.py")):
            if func_name in path.read_text():
                dotted = f"{app_dir.replace('/', '.')}.migrations.{path.stem}"
                pairs.append((dotted, func_name))
                break
        else:
            msg = f"seed function {func_name} not found in {app_dir}/migrations"
            raise SystemExit(msg)
    return pairs


def _schema_already_built(connection: "BaseDatabaseWrapper") -> bool:
    """True once the partitioned ``scenes_interaction`` table exists.

    The raw SQL files (partition rewrite, composite FKs, matviews) are
    one-shot DDL — e.g. the partition rewrite unconditionally does
    ``CREATE SEQUENCE`` and renames the Django-created table out of the way,
    so replaying it against its own output errors. Checking whether
    ``scenes_interaction`` is already partitioned (``relkind='p'``) tells us
    a prior run already applied the SQL files and seeds, so this run should
    skip straight past them — that's what makes the script idempotent.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT relkind FROM pg_class WHERE relname = 'scenes_interaction'")
        row = cursor.fetchone()
    return row is not None and row[0] == "p"


def main() -> None:
    os.chdir(SRC_DIR)
    sys.path.insert(0, str(SRC_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")

    import django  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    settings.MIGRATION_MODULES = _DisableMigrations()
    django.setup()

    from django.apps import apps  # noqa: PLC0415
    from django.core.management import call_command  # noqa: PLC0415
    from django.db import connection, transaction  # noqa: PLC0415

    call_command("migrate", run_syncdb=True, interactive=False, verbosity=1)

    if _schema_already_built(connection):
        print("schema already built (scenes_interaction is partitioned) — skipping SQL + seeds")
        return

    with transaction.atomic():
        with connection.cursor() as cursor:
            for rel_path in SQL_FILES:
                cursor.execute((SRC_DIR / rel_path).read_text())
                print(f"applied {rel_path}")

        with connection.schema_editor() as schema_editor:
            for app_label, model_name, field_name in POST_PARTITION_FIELDS:
                model = apps.get_model(app_label, model_name)
                field = model._meta.get_field(field_name)  # noqa: SLF001
                schema_editor.add_field(model, field)
                print(f"added post-partition column {model_name}.{field_name}")

        for module_path, func_name in _seed_modules():
            module = importlib.import_module(module_path)
            getattr(module, func_name)(apps, None)
            print(f"seeded {module_path}")


if __name__ == "__main__":
    main()
