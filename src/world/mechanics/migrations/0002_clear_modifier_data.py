# Clear CharacterModifier data before schema changes

from django.db import migrations


class Migration(migrations.Migration):
    """Clear all CharacterModifier data before schema changes.

    This must run before schema changes that alter FKs.
    ModifierSource model and CharacterSheet FK are being added.
    """

    # Run each statement in its own transaction to avoid trigger conflicts
    atomic = False

    dependencies = [
        ("mechanics", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DELETE FROM mechanics_charactermodifier;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
