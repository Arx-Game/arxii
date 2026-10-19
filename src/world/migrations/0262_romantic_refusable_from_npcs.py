from django.db import migrations


def mark_romantic_refusable(apps, schema_editor):
    """Production's existing romantic row predates the field; seeds don't run there (#4418)."""
    SocialConsentCategory = apps.get_model("arxii", "SocialConsentCategory")
    SocialConsentCategory.objects.filter(key="romantic").update(refusable_from_npcs=True)


class Migration(migrations.Migration):
    dependencies = [("arxii", "0261_actiontemplate_resist_check_type_and_more")]

    operations = [
        migrations.RunPython(mark_romantic_refusable, migrations.RunPython.noop),
    ]
