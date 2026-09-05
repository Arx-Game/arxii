"""Data step for #3648: derive org_type from the liege, mint templates for set kinds."""

from django.db import migrations


def forwards(apps, schema_editor):
    HouseTemplate = apps.get_model("arxii", "HouseTemplate")
    OriginTemplate = apps.get_model("arxii", "OriginTemplate")
    OrganizationType = apps.get_model("arxii", "OrganizationType")
    for template in HouseTemplate.objects.filter(
        org_type__isnull=True, liege__isnull=False
    ):
        template.org_type_id = template.liege.org_type_id
        template.save(update_fields=["org_type"])
    for upbringing in OriginTemplate.objects.filter(named_family_kind__isnull=False):
        if upbringing.family_templates.exists():
            continue
        area = upbringing.beginning.starting_area
        society = upbringing.beginning.societies.first()
        if society is None:
            message = (
                f"OriginTemplate {upbringing.pk} names a family kind but its beginning has "
                "no society to hang a Family Template on; author one before migrating."
            )
            raise RuntimeError(message)
        org_type, _ = OrganizationType.objects.get_or_create(
            name="commoner_family",
            defaults={
                "rank_1_title": "Head of the Family",
                "rank_2_title": "Elder",
                "rank_3_title": "Family",
                "rank_4_title": "Household",
                "rank_5_title": "Hands",
            },
        )
        template, _ = HouseTemplate.objects.get_or_create(
            name=f"{upbringing.beginning.name} {upbringing.named_family_kind.name} family",
            defaults={
                "realm": area.realm,
                "kind": upbringing.named_family_kind,
                "society": society,
                "org_type": org_type,
            },
        )
        upbringing.family_templates.add(template)


class Migration(migrations.Migration):
    dependencies = [("arxii", "0225_family_templates_and_vacancies_expand")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
