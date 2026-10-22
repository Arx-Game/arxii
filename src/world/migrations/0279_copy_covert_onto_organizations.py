"""Copy the covert flag from each organization type onto its organizations (#4570).

Data only. Covertness moves from ``OrganizationType.is_covert`` to ``Organization.is_covert``
(0278 adds the column, 0280 drops the type's): a type such as "tradition" holds an open academy
and a secret lodge alike, so the fact belongs to the organization. Every organization of a
covert type is marked covert here so nothing that was hidden becomes visible. The reverse
marks a type covert when every one of its organizations is, which is the only shape the old
column could express.
"""

from django.db import migrations
from django.db.models import Count, F, Q


def copy_onto_organizations(apps, schema_editor):
    Organization = apps.get_model("arxii", "Organization")
    Organization.objects.filter(org_type__is_covert=True).update(is_covert=True)


def copy_onto_types(apps, schema_editor):
    OrganizationType = apps.get_model("arxii", "OrganizationType")
    all_covert = (
        OrganizationType.objects.annotate(
            total=Count("organizations"),
            covert=Count("organizations", filter=Q(organizations__is_covert=True)),
        )
        .filter(total__gt=0, total=F("covert"))
        .values_list("pk", flat=True)
    )
    OrganizationType.objects.filter(pk__in=list(all_covert)).update(is_covert=True)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0278_organization_is_covert"),
    ]

    operations = [
        migrations.RunPython(copy_onto_organizations, copy_onto_types),
    ]
