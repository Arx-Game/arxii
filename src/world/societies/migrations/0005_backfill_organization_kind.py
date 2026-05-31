"""Data migration: backfill Organization.kind from org_type.name.

Maps legacy OrganizationType.name values (noble_family etc.) to the new
OrganizationKind enum values (noble etc.). Any unmapped rows get OTHER as
a safe default.

Per CLAUDE.md, data migrations pre-production are usually avoided, but this
is infrastructure-cleanup that handles whatever dev rows exist. Production
is assumed empty.
"""

from django.db import migrations

LEGACY_NAME_TO_KIND_VALUE = {
    "noble_family": "noble",
    "business": "business",
    "guild": "guild",
    "gang": "gang",
    "secret_society": "secret_society",
    "commoner_family": "commoner_family",
}


def backfill_kind_from_org_type(apps, schema_editor):
    Organization = apps.get_model("societies", "Organization")
    for org in Organization.objects.all():
        if org.org_type_id is None:
            org.kind = "other"
        else:
            legacy_name = org.org_type.name
            org.kind = LEGACY_NAME_TO_KIND_VALUE.get(legacy_name, "other")
        org.save(update_fields=["kind"])


def reverse(apps, schema_editor):
    Organization = apps.get_model("societies", "Organization")
    Organization.objects.update(kind=None)


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0004_organization_kind"),
    ]

    operations = [
        migrations.RunPython(backfill_kind_from_org_type, reverse_code=reverse),
    ]
