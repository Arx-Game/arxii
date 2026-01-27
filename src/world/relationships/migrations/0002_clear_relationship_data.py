# Clear CharacterRelationship data before schema changes

from django.db import migrations


class Migration(migrations.Migration):
    """Clear all CharacterRelationship data before schema changes.

    This must run before schema changes that alter FKs from ObjectDB to CharacterSheet.
    """

    # Run each statement in its own transaction to avoid trigger conflicts
    atomic = False

    dependencies = [
        ("relationships", "0001_initial"),
    ]

    operations = [
        # Clear the M2M table first
        migrations.RunSQL(
            sql="DELETE FROM relationships_characterrelationship_conditions;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM relationships_characterrelationship;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
