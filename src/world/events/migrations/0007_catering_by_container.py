"""Reshape EventCatering from consumed-snapshot to item tag (#2869).

Delete-and-recreate rather than alter: the shipped shape (item_template +
quality_tier snapshot of a destroyed item) and the new one (a permanent tag
on a still-real item_instance, with a role) share no meaningful columns, and
the model carries no production data. Anyone who applied 0006 drops a table
holding nothing.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0006_eventcatering"),
        ("items", "0054_alter_marketsale_buyer_persona"),
        ("scenes", "0058_sceneactionrequest_cast_openly"),
    ]

    operations = [
        migrations.DeleteModel(name="EventCatering"),
        migrations.CreateModel(
            name="EventCatering",
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
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("container", "Catering Vessel"),
                            ("provision", "Provision"),
                        ],
                        help_text=(
                            "CONTAINER (a flagged vessel) or PROVISION (a consumable "
                            "set out in one)."
                        ),
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contributed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Who flagged the vessel or set the dish out (provenance).",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="catering_contributions",
                        to="scenes.persona",
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="catering",
                        to="events.event",
                    ),
                ),
                (
                    "item_instance",
                    models.ForeignKey(
                        help_text=(
                            "The vessel or provision itself — still a real item in the world."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="catering_uses",
                        to="items.iteminstance",
                    ),
                ),
            ],
            options={
                "verbose_name": "Event Catering",
                "verbose_name_plural": "Event Catering",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="eventcatering",
            constraint=models.UniqueConstraint(
                fields=("event", "item_instance"),
                name="events_catering_unique_item_per_event",
            ),
        ),
    ]
