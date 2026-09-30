# Territory (#4060 slice 1): NeighborhoodTurf becomes Turf at every rung, and every
# held rung (a Domain or a Turf) carries a TERRITORY income stream. Schema-only;
# existing turf rows keep their area, grip and controller, and their streams are
# created lazily by the weekly territory phase, so no backfill is needed.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0162_distinctionstartinggrant"),
    ]

    operations = [
        migrations.RenameModel(old_name="NeighborhoodTurf", new_name="Turf"),
        migrations.AlterModelOptions(
            name="turf",
            options={"verbose_name": "Turf", "verbose_name_plural": "Turf"},
        ),
        migrations.AlterField(
            model_name="turf",
            name="area",
            field=models.OneToOneField(
                blank=True,
                help_text=(
                    "The contested area: NEIGHBORHOOD, WARD or CITY level (clean()-enforced)."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="turf",
                to="arxii.area",
            ),
        ),
        migrations.AddField(
            model_name="turf",
            name="room_profile",
            field=models.OneToOneField(
                blank=True,
                help_text=(
                    "The contested corner: one outdoor room, a crew's ground (clean()-enforced)."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="turf",
                to="arxii.roomprofile",
            ),
        ),
        migrations.AlterField(
            model_name="orgincomestream",
            name="kind",
            field=models.CharField(
                choices=[
                    ("domain_tax", "Domain Tax"),
                    ("crime_kickup", "Crime Kick-up"),
                    ("territory", "Territory"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="holdingkind",
            name="stream_kind",
            field=models.CharField(
                choices=[
                    ("domain_tax", "Domain Tax"),
                    ("crime_kickup", "Crime Kick-up"),
                    ("territory", "Territory"),
                ],
                help_text="currency.IncomeStreamKind value the materialized stream uses.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="orgincomestream",
            name="room_profile",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The one outdoor room this stream is anchored to, for a crew's turf "
                    "(#4060); ``area`` anchors every larger rung. A stream anchors to at most "
                    "one of the two."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="income_streams",
                to="arxii.roomprofile",
            ),
        ),
        migrations.AddField(
            model_name="turf",
            name="income_stream",
            field=models.OneToOneField(
                blank=True,
                help_text="The TERRITORY stream that is this ground's base value (#4060).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="turf",
                to="arxii.orgincomestream",
            ),
        ),
        migrations.AddField(
            model_name="domain",
            name="territory_stream",
            field=models.OneToOneField(
                blank=True,
                help_text=(
                    "The TERRITORY stream that is this land's base value (#4060): its gross "
                    "is recomputed each cycle from the domain's land units and prosperity."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="territory_domain",
                to="arxii.orgincomestream",
            ),
        ),
        migrations.AddConstraint(
            model_name="turf",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("area__isnull", False), ("room_profile__isnull", True))
                    | models.Q(("area__isnull", True), ("room_profile__isnull", False))
                ),
                name="societies_turf_exactly_one_site",
            ),
        ),
    ]
