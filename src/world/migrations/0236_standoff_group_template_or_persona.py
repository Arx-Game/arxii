# The check over StandoffGroup.persona sits apart from 0235, which adds the column
# (tools/lint_migration_constraint_on_new_column.py: never constrain a column in the
# migration that adds it). Every existing group has a template, so it validates at once.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0235_named_npc_groups_and_language"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="standoffgroup",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("creature_template__isnull", False),
                    ("persona__isnull", False),
                    _connector="OR",
                ),
                name="standoff_group_template_or_persona",
            ),
        ),
    ]
