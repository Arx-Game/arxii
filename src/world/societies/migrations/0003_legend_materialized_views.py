"""Create materialized views for legend summary lookups."""

import pathlib

from django.db import migrations, models
import django.db.models.deletion

SQL_DIR = pathlib.Path(__file__).resolve().parent.parent / "sql"


class Migration(migrations.Migration):
    dependencies = [
        ("character_sheets", "0003_initial"),
        ("objects", "0001_initial"),
        ("societies", "0002_legendsourcetype_spreadingconfig_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CharacterLegendSummary",
            fields=[
                (
                    "character",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to="objects.objectdb",
                    ),
                ),
                ("personal_legend", models.IntegerField()),
            ],
            options={
                "db_table": "societies_characterlegendsummary",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="GuiseLegendSummary",
            fields=[
                (
                    "guise",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to="character_sheets.guise",
                    ),
                ),
                ("guise_legend", models.IntegerField()),
            ],
            options={
                "db_table": "societies_guiselegendsummary",
                "managed": False,
            },
        ),
        migrations.RunSQL(
            sql=(SQL_DIR / "character_legend_summary.sql").read_text(),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_characterlegendsummary;",
        ),
        migrations.RunSQL(
            sql=(SQL_DIR / "guise_legend_summary.sql").read_text(),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_guiselegendsummary;",
        ),
    ]
