"""Schema only (#4361): drive reveals name a property; faction rules have one owner.

The contract step after 0230 (add ``drive_property``, drop the two constraints that read
``drive``) and 0231 (copy it): drop the old ``drive`` column (a ``CreatureDrive`` FK),
rename ``drive_property`` to ``drive`` and put the constraints back. The constraints are
dropped in 0230 so the chain reverses cleanly: undoing this migration leaves ``drive``
empty, 0231's reverse fills it, and only then does undoing 0230 re-add the old check.
A placement can add a drive its template lacks, so a reveal can no longer point at a
``CreatureDrive`` row. Play state only.

Also adds ``faction_rule_one_owner``: a FactionRule belongs to exactly one creature
template, organization or society (the owner columns were added in 0230).
"""

from django.db import migrations, models
import django.db.models.deletion


def _kind_check() -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=models.Q(
            models.Q(
                ("drive__isnull", True),
                ("faction_rule__isnull", True),
                ("kind", "cause"),
            ),
            models.Q(
                ("drive__isnull", False),
                ("faction_rule__isnull", True),
                ("kind", "drive"),
            ),
            models.Q(
                ("drive__isnull", True),
                ("faction_rule__isnull", False),
                ("kind", "faction_rule"),
            ),
            _connector="OR",
        ),
        name="standoff_reveal_fk_matches_kind",
    )


def _unique() -> models.UniqueConstraint:
    return models.UniqueConstraint(
        fields=("group", "kind", "drive", "faction_rule"),
        name="unique_standoff_reveal",
        nulls_distinct=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0231_standoff_profile_snapshot_backfill"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="standoffreveal",
            name="drive",
        ),
        migrations.RenameField(
            model_name="standoffreveal",
            old_name="drive_property",
            new_name="drive",
        ),
        migrations.AlterField(
            model_name="standoffreveal",
            name="drive",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The drive revealed, by its property (DRIVE reveals only). A group's "
                    "drives are stamped on its members at spawn, so a placement may add one "
                    "its template lacks."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="arxii.property",
            ),
        ),
        migrations.AddConstraint(
            model_name="standoffreveal",
            constraint=_kind_check(),
        ),
        migrations.AddConstraint(
            model_name="standoffreveal",
            constraint=_unique(),
        ),
        # The one-owner check over FactionRule's new owner columns, added a migration
        # after the columns themselves (expand, then constrain): old rows carry only
        # creature_template, so they satisfy the first branch.
        migrations.AddConstraint(
            model_name="factionrule",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("creature_template__isnull", False),
                        ("organization__isnull", True),
                        ("society__isnull", True),
                    ),
                    models.Q(
                        ("creature_template__isnull", True),
                        ("organization__isnull", False),
                        ("society__isnull", True),
                    ),
                    models.Q(
                        ("creature_template__isnull", True),
                        ("organization__isnull", True),
                        ("society__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="faction_rule_one_owner",
            ),
        ),
    ]
