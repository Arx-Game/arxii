"""A CHECK constraint that pairs a new nullable column with an old one fails on rows.

0149_partitioned_metadata_integrity added ``posesubmission.timestamp`` (nullable)
and, in the same migration, a CHECK requiring it whenever ``interaction`` is set.
Every existing row with an interaction had a NULL timestamp, so ``ADD CONSTRAINT``
raised ``IntegrityError: check constraint ... is violated by some row``. CI never
sees it (empty database); the 2026-09-24 production deploy did.
"""

from pathlib import Path

from lint_migration_constraint_on_new_column import (
    GRANDFATHERED,
    check_migration,
    check_source,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def migration(*operations: str) -> str:
    body = "\n".join(f"        migrations.{op}," for op in operations)
    return (
        "from django.db import migrations, models\nfrom django.db.models import Q\n\n"
        "class Migration(migrations.Migration):\n    operations = [\n" + body + "\n    ]\n"
    )


PAIRED_CHECK = (
    'AddConstraint(model_name="posesubmission", constraint=models.CheckConstraint('
    "check=(Q(interaction__isnull=True, timestamp__isnull=True) "
    "| Q(interaction__isnull=False, timestamp__isnull=False)), "
    'name="pose_submission_interaction_timestamp_pair"))'
)


def test_new_nullable_column_paired_with_an_old_one_is_flagged():
    source = migration(
        'AddField(model_name="posesubmission", name="timestamp", '
        "field=models.DateTimeField(blank=True, null=True))",
        PAIRED_CHECK,
    )
    assert check_source(source) == [("posesubmission", "timestamp", "interaction")]


def test_a_check_that_only_references_the_new_column_is_clean():
    """NULL satisfies a CHECK, so a constraint on the new column alone cannot fail."""
    source = migration(
        'AddField(model_name="thing", name="score", field=models.IntegerField(null=True))',
        'AddConstraint(model_name="thing", constraint=models.CheckConstraint('
        'check=Q(score__gte=0), name="score_non_negative"))',
    )
    assert check_source(source) == []


def test_a_column_added_with_a_default_is_clean():
    """A non-null column with a default is populated on every existing row."""
    source = migration(
        'AddField(model_name="posesubmission", name="timestamp", '
        "field=models.DateTimeField(default=django.utils.timezone.now), "
        "preserve_default=False)",
        PAIRED_CHECK,
    )
    assert check_source(source) == []


def test_a_check_on_columns_that_already_existed_is_clean():
    source = migration(
        'AddField(model_name="thing", name="other", field=models.IntegerField(null=True))',
        PAIRED_CHECK,
    )
    assert check_source(source) == []


def test_a_new_column_on_a_different_model_is_clean():
    source = migration(
        'AddField(model_name="scene", name="timestamp", field=models.DateTimeField(null=True))',
        PAIRED_CHECK,
    )
    assert check_source(source) == []


def test_the_message_names_the_columns_and_the_fix(tmp_path):
    path = tmp_path / "0149_partitioned_metadata_integrity.py"
    path.write_text(
        migration(
            'AddField(model_name="posesubmission", name="timestamp", '
            "field=models.DateTimeField(null=True))",
            PAIRED_CHECK,
        )
    )
    message = check_migration(path)
    assert message is not None
    assert "posesubmission.timestamp" in message
    assert "interaction" in message
    assert "expand/migrate/contract" in message


def test_the_migration_that_broke_the_deploy_is_caught():
    """0149 as merged, read from the repo: the founding grandfathered entry."""
    path = PROJECT_ROOT / "src/world/migrations/0149_partitioned_metadata_integrity.py"
    assert check_source(path.read_text(encoding="utf-8")) == [
        ("posesubmission", "timestamp", "interaction")
    ]
    assert check_migration(path) is None, "applied to production 2026-09-24; grandfathered"


def test_grandfathered_migrations_are_all_real_files():
    """The list is closed, so every entry must still name a migration that exists."""
    for relative in GRANDFATHERED:
        assert (PROJECT_ROOT / "src" / relative).is_file(), relative
