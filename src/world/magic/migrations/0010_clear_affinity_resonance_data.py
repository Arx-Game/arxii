# Clear Affinity and Resonance data before schema change

from django.db import migrations


class Migration(migrations.Migration):
    """Clear all data that references Affinity and Resonance models.

    This must run before the schema changes that alter FKs to point to ModifierType.
    Affinities and Resonances are now managed via ModifierType entries.
    Seed data is managed via fixtures outside version control.
    """

    # Run each statement in its own transaction to avoid trigger conflicts
    atomic = False

    dependencies = [
        ("conditions", "0002_alter_damagetype_resonance"),
        ("magic", "0009_alter_power_options_alter_thread_initiator_and_more"),
        ("mechanics", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DELETE FROM magic_threadresonance;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM magic_characterresonance;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM magic_power_resonances;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM magic_gift_resonances;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM magic_characterpower;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM magic_power;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM magic_charactergift;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DELETE FROM magic_gift;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="UPDATE magic_threadtype SET grants_resonance_id = NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
