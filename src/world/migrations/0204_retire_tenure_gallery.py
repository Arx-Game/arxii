"""#4151, contract: one owner per picture, and retire named galleries.

Adds the CHECK that a picture belongs to exactly one of a tenure or a roster entry. Every
existing row has a tenure and (roster_entry being new in 0203) no entry, so it holds.

Schema only. Disposition (ADR-0237): these rows are player uploads, which is play state,
not authored content, and per the product owner no players or designed characters exist
yet, so there is no private gallery to carry (the production dump holds 0 galleries and
0 tenure media, 2026-10-05). Any rows are test data and are discarded
with the table; the pictures themselves (TenureMedia, Media) are untouched.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0203_gallery_looks_and_character_art"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="tenuremedia",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("roster_entry__isnull", True), ("tenure__isnull", False)),
                    models.Q(("roster_entry__isnull", False), ("tenure__isnull", True)),
                    _connector="OR",
                ),
                name="tenuremedia_one_owner",
            ),
        ),
        migrations.RemoveField(
            model_name="tenuregallery",
            name="allowed_viewers",
        ),
        migrations.RemoveField(
            model_name="tenuregallery",
            name="tenure",
        ),
        migrations.RemoveField(
            model_name="tenuremedia",
            name="gallery",
        ),
        migrations.DeleteModel(
            name="TenureGallery",
        ),
    ]
