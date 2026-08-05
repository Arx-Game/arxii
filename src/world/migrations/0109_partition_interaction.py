"""Restore the arxii_interaction range partition + composite FKs (#2982).

#2906's single-app collapse regenerated the whole chain with a plain
``makemigrations``, which only ever emits ``CreateModel``. The standalone SQL
that rewrites ``arxii_interaction`` into a range-partitioned table and hangs the
composite FKs off it was therefore silently dropped - the same class of loss that
``0101_create_materialized_views`` was added to repair for the 5 materialized
views, caught for those and missed for this.

The consequence was two supported commands producing two different schemas: a
database built by a fully successful ``arx manage migrate`` got an UNPARTITIONED
``arxii_interaction`` with no composite FKs, while ``tools/build_schema.py``
(CI, the parity tier, the devcontainer) applied the SQL explicitly and got the
right one. Production is built by migration replay, so the wrong path was the
one that shipped.

Ordering notes, because this is a table rewrite rather than additive DDL:

* It runs at the TAIL of the chain. Every table the SQL touches is created
  within 0001-0100, and 0102's ``AlterField`` on
  ``clashcontribution.interaction_timestamp`` runs first - index, then the
  composite FK that targets that column, which is the order that works.
* The forward SQL rebuilds ``arxii_interaction`` WITHOUT ``fury_committed_id``
  and ``writer_account_id`` (see POST_PARTITION_COLUMNS in
  ``tools/check_partition_sql_drift.py``), so they are re-added below at the
  database level only - migration state already carries them from CreateModel.
  ``AddField`` there resolves to ``schema_editor.add_field``, the same call
  ``tools/build_schema.py`` makes, so both paths name their objects identically.
* The rewrite's ``DROP TABLE arxii_interaction_old CASCADE`` is not lossy: all
  23 concrete FKs pointing at ``Interaction`` are declared
  ``db_constraint=False`` (a FK to a partitioned table cannot reference the
  plain PK - see docs/evennia-quirks.md), so there are no Django-created
  constraints on the old table for the CASCADE to take.
* Reversing runs the operations backwards - RemoveField x2, drop the composite
  FKs, then un-partition - which is exactly the precondition
  ``partition_interaction_reverse.sql`` documents.
"""

from pathlib import Path

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

_WORLD_DIR = Path(__file__).resolve().parent.parent


def _read_sql(subpackage: str, filename: str) -> str:
    return (_WORLD_DIR / subpackage / "sql" / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0108_draftmarking_formmarking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("scenes", "partition_interaction_forward.sql"),
            reverse_sql=_read_sql("scenes", "partition_interaction_reverse.sql"),
        ),
        migrations.RunSQL(
            sql=_read_sql("combat", "interaction_fk_composites_forward.sql"),
            reverse_sql=_read_sql("combat", "interaction_fk_composites_reverse.sql"),
        ),
        # Database-only: migration state already has both fields from the
        # CreateModel in 0005_initial_part_5, so state_operations is empty.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AddField(
                    model_name="interaction",
                    name="fury_committed",
                    field=models.ForeignKey(
                        blank=True,
                        help_text=(
                            "Post-resolution audit of the realized Fury tier (clash + non-clash)."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="arxii.furytier",
                    ),
                ),
                migrations.AddField(
                    model_name="interaction",
                    name="writer_account",
                    field=models.ForeignKey(
                        blank=True,
                        help_text=(
                            "The account that wrote this, pinned at creation (#1219). "
                            "Party identity for private-content log visibility - stable "
                            "across persona hand-offs, so an inheriting player is never "
                            "treated as a party to the prior player's whispers."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            state_operations=[],
        ),
    ]
