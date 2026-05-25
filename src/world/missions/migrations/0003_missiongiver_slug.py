"""Add MissionGiver.slug — stable string identifier for predicate authoring.

Hand-written because the field is `unique=True, null=False` and Django's
auto-detected migration can't supply a unique non-null default for
existing rows. Dev DB has no MissionGiver rows (table only just landed in
the rebuild), and there is no other deployed environment yet, so we land
the column directly non-null without a backfill stage.

Future need: if MissionGiver ever has live data when this migration is
re-applied (it can't — this is part of the 0001/0002 initial set's first
extension), this approach would need a 3-step sequence (add nullable +
backfill data migration + AlterField non-null). Not needed today.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("missions", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="missiongiver",
            name="slug",
            field=models.SlugField(
                max_length=200,
                unique=True,
                help_text=(
                    "Stable string identifier (URL-safe). Used by predicate "
                    "authoring (e.g. min_giver_standing references a giver by "
                    "slug) and by future authoring-tool URLs. Required so that "
                    "templates and predicates have a refactor-safe pointer to a "
                    "specific giver."
                ),
                # Placeholder default for migration application — overridden
                # by every concrete write path (admin form, factory, mission
                # tool). No production data exists yet, so the default never
                # actually surfaces; the unique=True constraint would reject
                # multiple rows hitting this default.
                default="missiongiver-needs-slug",
            ),
            preserve_default=False,
        ),
    ]
