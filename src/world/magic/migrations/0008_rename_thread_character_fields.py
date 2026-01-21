# Generated manually for field rename

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0007_thread_threadjournal_threadtype_threadresonance"),
    ]

    operations = [
        # First, remove the old unique_together constraint
        migrations.AlterUniqueTogether(
            name="thread",
            unique_together=set(),
        ),
        # Rename the fields
        migrations.RenameField(
            model_name="thread",
            old_name="character_a",
            new_name="initiator",
        ),
        migrations.RenameField(
            model_name="thread",
            old_name="character_b",
            new_name="receiver",
        ),
        # Re-add the unique_together constraint with new field names
        migrations.AlterUniqueTogether(
            name="thread",
            unique_together={("initiator", "receiver")},
        ),
    ]
