"""Replace CGExplanations singleton (41 columns) with CGExplanation key-value table."""

from django.db import migrations, models

# Map of old column names to their help_text for the new rows.
FIELD_HELP_TEXT = {
    "origin_heading": "Origin stage - page heading",
    "origin_intro": "Origin stage - intro paragraph",
    "heritage_heading": "Heritage stage - page heading",
    "heritage_intro": "Heritage stage - intro paragraph",
    "heritage_beginnings_heading": "Heritage stage - Beginnings section heading",
    "heritage_beginnings_desc": "Heritage stage - Beginnings description",
    "heritage_species_heading": "Heritage stage - Species section heading",
    "heritage_species_desc": "Heritage stage - Species description",
    "heritage_gender_heading": "Heritage stage - Gender section heading",
    "heritage_cg_points_explanation": "Heritage stage - CG points sidebar explanation",
    "lineage_heading": "Lineage stage - page heading",
    "lineage_intro": "Lineage stage - intro paragraph",
    "distinctions_heading": "Distinctions stage - page heading",
    "distinctions_intro": "Distinctions stage - intro paragraph",
    "distinctions_budget_explanation": "Distinctions stage - budget explanation",
    "path_heading": "Path stage - page heading",
    "path_intro": "Path stage - intro paragraph",
    "path_skills_heading": "Path stage - Skills section heading",
    "path_skills_desc": "Path stage - Skills description",
    "attributes_heading": "Attributes stage - page heading",
    "attributes_intro": "Attributes stage - intro paragraph",
    "attributes_bonus_explanation": "Attributes stage - bonus explanation",
    "magic_heading": "Magic stage - page heading",
    "magic_intro": "Magic stage - intro paragraph",
    "magic_gift_heading": "Magic stage - Gift section heading",
    "magic_gift_desc": "Magic stage - Gift description",
    "magic_anima_heading": "Magic stage - Anima Ritual section heading",
    "magic_anima_desc": "Magic stage - Anima Ritual description",
    "magic_motif_heading": "Magic stage - Motif section heading",
    "magic_motif_desc": "Magic stage - Motif description",
    "magic_glimpse_heading": "Magic stage - Glimpse section heading",
    "magic_glimpse_desc": "Magic stage - Glimpse description",
    "appearance_heading": "Appearance stage - page heading",
    "appearance_intro": "Appearance stage - intro paragraph",
    "identity_heading": "Identity stage - page heading",
    "identity_intro": "Identity stage - intro paragraph",
    "finaltouches_heading": "Final Touches stage - page heading",
    "finaltouches_intro": "Final Touches stage - intro paragraph",
    "review_heading": "Review stage - page heading",
    "review_intro": "Review stage - intro paragraph",
    "review_xp_explanation": "Review stage - XP conversion explanation",
}


def forward(apps, schema_editor):
    """Convert singleton columns into key-value rows."""
    OldModel = apps.get_model("character_creation", "CGExplanations")
    NewModel = apps.get_model("character_creation", "CGExplanation")

    try:
        old = OldModel.objects.get(pk=1)
    except OldModel.DoesNotExist:
        # No singleton exists — just create empty rows with help_text
        NewModel.objects.bulk_create(
            [NewModel(key=key, text="", help_text=ht) for key, ht in FIELD_HELP_TEXT.items()]
        )
        return

    NewModel.objects.bulk_create(
        [
            NewModel(key=key, text=getattr(old, key, ""), help_text=ht)
            for key, ht in FIELD_HELP_TEXT.items()
        ]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("character_creation", "0003_cgexplanations"),
    ]

    operations = [
        # 1. Create new key-value table
        migrations.CreateModel(
            name="CGExplanation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=100, unique=True)),
                ("text", models.TextField(blank=True)),
                (
                    "help_text",
                    models.TextField(
                        blank=True,
                        help_text="Reminder of which CG stage uses this key",
                    ),
                ),
            ],
            options={
                "verbose_name": "CG Explanation",
                "verbose_name_plural": "CG Explanations",
            },
        ),
        # 2. Migrate data from old singleton to new rows
        migrations.RunPython(forward, migrations.RunPython.noop),
        # 3. Drop old singleton table
        migrations.DeleteModel(name="CGExplanations"),
    ]
