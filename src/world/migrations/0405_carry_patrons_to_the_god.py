"""A house's patron becomes the god, not one of the god's nicknames (#5110).

Data only (the columns come from 0404; the old ones are dropped in 0406).

Carries across, in this order:

- ``Organization.patron`` takes ``patron_nickname.being`` for every organization that
  has a patron nickname. The god is kept; which nickname the house used is the
  deliberate discard the issue records (owner ruling 2026-11-12: the plain name).
- ``HouseClaim.patron_being`` takes the being of the option a claim picked on its
  template's patron question, so a claim already submitted keeps its pick.
- The facets on patron questions (``OrganizationFacet``, ``HouseClaimFacet``) and the
  option rows of those questions are deleted: the choices are now the gods themselves,
  and a row left behind would be a stale choice nothing reads. Facets first, since
  they protect their option.

Which worship a patron question draws its gods from (``patron_tradition``) is content
and is not set here; staff set it on the question after the deploy.

Reversing is a no-op: the nickname a house used and the deleted option rows cannot be
rebuilt from what remains, and reversing 0404 drops the new columns.
"""

from django.db import migrations


def carry_patrons(apps, schema_editor):
    Organization = apps.get_model("arxii", "Organization")
    HouseClaim = apps.get_model("arxii", "HouseClaim")
    HouseClaimFacet = apps.get_model("arxii", "HouseClaimFacet")
    OrganizationFacet = apps.get_model("arxii", "OrganizationFacet")
    HouseCharterOption = apps.get_model("arxii", "HouseCharterOption")

    sworn = Organization.objects.filter(patron_nickname__isnull=False).values_list(
        "pk", "patron_nickname__being_id"
    )
    for org_id, being_id in list(sworn):
        Organization.objects.filter(pk=org_id).update(patron_id=being_id)

    picks = HouseClaimFacet.objects.filter(
        definition__sets_patron=True, option__being__isnull=False
    ).values_list("claim_id", "option__being_id")
    for claim_id, being_id in list(picks):
        HouseClaim.objects.filter(pk=claim_id).update(patron_being_id=being_id)

    OrganizationFacet.objects.filter(definition__sets_patron=True).delete()
    HouseClaimFacet.objects.filter(definition__sets_patron=True).delete()
    HouseCharterOption.objects.filter(definition__sets_patron=True).delete()


class Migration(migrations.Migration):
    dependencies = [("arxii", "0404_patron_from_the_gods")]

    operations = [
        migrations.RunPython(carry_patrons, migrations.RunPython.noop),
    ]
