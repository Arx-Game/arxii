"""0102_g2_partition_columns: database-only re-add of the columns the frozen partition SQL omits
(POST_PARTITION_COLUMNS in tools/check_partition_sql_drift.py). Migration state
already carries them from CreateModel; the partition rewrite rebuilt the table
without them. Rendered from the live Interaction model by arx manage
squashmigrations (ADR-0272 tail); do not edit."""

from pathlib import Path

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

from world.migrations._generations import replaced_slice

_WORLD_DIR = Path(__file__).resolve().parent.parent


def _read_sql(subpackage: str, filename: str) -> str:
    return (_WORLD_DIR / subpackage / "sql" / filename).read_text()


class Migration(migrations.Migration):
    replaces = replaced_slice(102, 103)
    dependencies = [
        ("arxii", "0101_g2_partition_sql"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AddField(
                    model_name="interaction",
                    name="attributed_companion",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="Cosmetic pose attribution (#3294): when set, the feed renders this bonded companion as the visible actor with an owner tell, e.g. a wolfhound's growl attributed to the wolfhound. Authorship — block/mute/consent/moderation — stays entirely on `persona`, which is always the companion's OWNER; this field is never a substitute writer and never affects visibility filtering.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="arxii.companion",
                    ),
                ),
                migrations.AddField(
                    model_name="interaction",
                    name="fury_committed",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="Post-resolution audit of the realized Fury tier (clash + non-clash).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="arxii.furytier",
                    ),
                ),
                migrations.AddField(
                    model_name="interaction",
                    name="language",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="Spoken language; null = universal/untagged (poses, emits, pre-#2993 rows).",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="arxii.language",
                    ),
                ),
                migrations.AddField(
                    model_name="interaction",
                    name="writer_account",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="The account that wrote this, pinned at creation (#1219). Party identity for private-content log visibility — stable across persona hand-offs, so an inheriting player is never treated as a party to the prior player's whispers.",
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
