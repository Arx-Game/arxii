# Hand-written (#4198): the being<->tarot card link becomes a real row with an
# orientation, and a relationship gains a story per side.
#
# The through model adopts the auto M2M table in place: the CreateModel and the
# AlterField of the M2M are state-only (SeparateDatabaseAndState), so the table,
# its rows and its unique index on (worshippedbeing_id, tarotcard_id) survive, and
# the rows entered before the orientation existed carry over as uprights. The
# column adds and the rename are ordinary schema operations. Schema-only; no
# RunPython.
#
# The state-side constraint is named unique_being_tarot_card; in the database the
# same uniqueness is the auto M2M's own constraint,
# arxii_worshippedbeing_ta_worshippedbeing_id_tarot_6feeb122_uniq. Nothing addresses
# it by name today; a later RemoveConstraint/AlterConstraint on the state name would
# have to rename the real one first (RunSQL, database side).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0209_facet_alias"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="BeingTarotCard",
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
                            "being",
                            models.ForeignKey(
                                db_column="worshippedbeing_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="card_links",
                                to="arxii.worshippedbeing",
                            ),
                        ),
                        (
                            "card",
                            models.ForeignKey(
                                db_column="tarotcard_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="being_links",
                                to="arxii.tarotcard",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "arxii_worshippedbeing_tarot_cards",
                        "ordering": ["being", "card__name", "is_reversed"],
                    },
                ),
                migrations.AddConstraint(
                    model_name="beingtarotcard",
                    constraint=models.UniqueConstraint(
                        fields=("being", "card"), name="unique_being_tarot_card"
                    ),
                ),
                migrations.AlterField(
                    model_name="worshippedbeing",
                    name="tarot_cards",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "Cards people believe represent this being, upright or reversed "
                            "(BeingTarotCard.is_reversed, #4198). Pure association, no cap."
                        ),
                        related_name="represented_beings",
                        through="arxii.BeingTarotCard",
                        through_fields=("being", "card"),
                        to="arxii.tarotcard",
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.AddField(
            model_name="beingtarotcard",
            name="is_reversed",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text="The card represents the being reversed.",
            ),
        ),
        migrations.RenameField(
            model_name="beingrelationship",
            old_name="public_story",
            new_name="story_from_a",
        ),
        migrations.AlterField(
            model_name="beingrelationship",
            name="story_from_a",
            field=models.TextField(blank=True, help_text="being_a's own telling of it."),
        ),
        migrations.AddField(
            model_name="beingrelationship",
            name="story_from_b",
            field=models.TextField(blank=True, help_text="being_b's own telling of it."),
        ),
    ]
