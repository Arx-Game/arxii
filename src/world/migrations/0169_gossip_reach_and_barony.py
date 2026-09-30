# Hand-written for #4085 (Django's generator would drop and re-add the renamed column,
# losing every gossip row; a rename keeps them). Schema only: the re-level of rows at
# the retired 46 and 50 is 0170.

from django.db import migrations, models
import django.db.models.deletion

LEVEL_CHOICES = [
    (10, "Building"),
    (20, "Neighborhood"),
    (30, "Ward"),
    (40, "Barony"),
    (53, "County"),
    (56, "Duchy"),
    (60, "Kingdom"),
    (65, "Empire"),
    (70, "Continent"),
    (80, "World"),
    (90, "Plane"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0168_crew_slots"),
    ]

    operations = [
        # SecretGossip.region becomes area: the rumor's reach, not a fixed region.
        migrations.RemoveIndex(
            model_name="secretgossip",
            name="arxii_secre_region__d5f215_idx",
        ),
        migrations.RenameField(
            model_name="secretgossip",
            old_name="region",
            new_name="area",
        ),
        migrations.AlterField(
            model_name="secretgossip",
            name="area",
            field=models.ForeignKey(
                help_text="The rumor's reach: the highest area it has climbed to; heard everywhere below.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="gossip_heat",
                to="arxii.area",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="secretgossip",
            unique_together={("secret", "area")},
        ),
        migrations.AddIndex(
            model_name="secretgossip",
            index=models.Index(fields=["area", "heat"], name="arxii_secre_area_id_9586dc_idx"),
        ),
        # The level ladder loses Region (50) and City (40 becomes Barony); no column changes.
        migrations.AlterField(
            model_name="area",
            name="level",
            field=models.IntegerField(choices=LEVEL_CHOICES, db_index=True),
        ),
        migrations.AlterField(
            model_name="areabuildgrant",
            name="max_level",
            field=models.IntegerField(
                choices=LEVEL_CHOICES,
                default=10,
                help_text="Broadest AreaLevel this grant may create/act on within the subtree.",
            ),
        ),
        migrations.AlterField(
            model_name="turf",
            name="area",
            field=models.OneToOneField(
                blank=True,
                help_text="The contested area: NEIGHBORHOOD, WARD or BARONY level (clean()-enforced).",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="turf",
                to="arxii.area",
            ),
        ),
        migrations.AlterField(
            model_name="areaelevationrequirement",
            name="to_level",
            field=models.IntegerField(
                choices=LEVEL_CHOICES,
                help_text="The AreaLevel a declaration against this row elevates an area into.",
                unique=True,
            ),
        ),
    ]
