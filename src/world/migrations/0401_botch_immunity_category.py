"""The "botch_immunity" ModifierCategory (#4386).

Data only (the ModifierTarget check-scope columns come from 0394).

Get-or-create the category the check seam reads by name, so production has it without a
seeder run. It is a prose-light mechanical catalog row (owner ruling 2026-10-22: such rows
may ship by data migration); staff author its targets, one per check category or check
type. An existing row keeps its description.

The name is copied here, never imported from app code. Reversing is a no-op: reversing
0394 drops the scope columns, and an empty category does nothing.
"""

from django.db import migrations

# seed-data-ok: #4386 one prose-light mechanical ModifierCategory the code reads by name,
# the owner's 2026-10-22 ruling (as 0334); an existing row is left as it is.

BOTCH_IMMUNITY_CATEGORY_NAME = "botch_immunity"
CATEGORY_DESCRIPTION = (
    "Targets that stop a character botching. Scope each target to one check category or one "
    "check type; a character with a positive total for it cannot botch at those checks."
)


def create_botch_immunity_category(apps, schema_editor):
    ModifierCategory = apps.get_model("arxii", "ModifierCategory")
    ModifierCategory.objects.get_or_create(
        name=BOTCH_IMMUNITY_CATEGORY_NAME,
        defaults={"description": CATEGORY_DESCRIPTION},
    )


class Migration(migrations.Migration):
    dependencies = [("arxii", "0400_botch_immunity_check_scope")]

    operations = [
        migrations.RunPython(create_botch_immunity_category, migrations.RunPython.noop),
    ]
