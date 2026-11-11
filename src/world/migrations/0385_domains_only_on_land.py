"""Domains only on land (data only, #5069 slice 1, #5071, ADR-0237).

Forward: every ``Domain`` whose Area sits above COUNTY (a duchy's, a kingdom's, an
empire's) goes away. A duchy is its counties and a kingdom its duchies: organization
with no ground of its own, so its people and income are sums over the land beneath
it and the row carried nothing a reader needs. Before a row goes:

- its ``description`` is carried onto its Area when the Area's is blank (the layout
  tool and the title page write a duchy's prose there now);
- what hangs on it is re-homed to the Domain of the county of its own chain, the
  ground its holder actually sits in: garrison posts, developments, edicts, crises,
  affliction signs, improvement details, food transfers, org tasks aimed at it. Its
  food stockpile goes (the county keeps its own; a one-to-one cannot move onto a row
  that has one);
- its TERRITORY income stream is deleted. Every such pool on the production copy
  checked on 2026-11-11 held 0 coppers; the PR states the figure from a fresh pull.

A Domain with no title standing on it (nothing on the production copy) has no chain
county to take its dependents, which go with it. All of this is play state (ADR-0237
tier 2); the prose is the one carried column.

Reverse: nothing to put back. The rows are not recreated; the columns the schema step
added come off in 0384's reverse.
"""

from django.db import migrations

COUNTY_LEVEL = 53
# A title's own rung sits at this Atlas level (houses.constants.TIER_TO_AREA_LEVEL).
TIER_LEVELS = {
    "empire": 65,
    "kingdom": 60,
    "duchy": 56,
    "march": 53,
    "county": 53,
    "barony": 40,
}


def _chain_of(area):
    """The Area and its ancestors, nearest first."""
    chain = []
    node = area
    while node is not None:
        chain.append(node)
        node = node.parent
    return chain


def _chain_county_domain(apps, domain):
    """The Domain of the county in the chain of the title whose rung is ``domain``'s
    Area: the title of this Area's tier whose seat barony lies beneath it."""
    Title = apps.get_model("arxii", "Title")
    Domain = apps.get_model("arxii", "Domain")
    level = domain.area.level
    tiers = [tier for tier, tier_level in TIER_LEVELS.items() if tier_level == level]
    for title in Title.objects.filter(tier__in=tiers, seat_domain__isnull=False).select_related(
        "seat_domain__area"
    ):
        chain = _chain_of(title.seat_domain.area)
        if all(node.pk != domain.pk for node in chain):
            continue
        county = next((node for node in chain if node.level == COUNTY_LEVEL), None)
        if county is None:
            return None
        return Domain.objects.filter(pk=county.pk).first()
    return None


def _rehome(apps, old, new):
    """Point every dependent of ``old`` at ``new`` (or drop it when ``new`` is None)."""
    moves = (
        ("DomainGarrisonPost", "domain"),
        ("DomainHolding", "domain"),
        ("DomainEdict", "domain"),
        ("DomainCrisis", "domain"),
        ("AfflictionSign", "domain"),
        ("DomainImprovementDetails", "domain"),
        ("FoodTransfer", "source_domain"),
        ("FoodTransfer", "target_domain"),
    )
    for model_name, field in moves:
        rows = apps.get_model("arxii", model_name).objects.filter(**{field: old})
        if new is None:
            rows.delete()
        else:
            rows.update(**{field: new})
    OrgTask = apps.get_model("arxii", "OrgTask")
    OrgTask.objects.filter(target_domain=old).update(target_domain=new)
    apps.get_model("arxii", "FoodStockpile").objects.filter(domain=old).delete()


def forward(apps, schema_editor):
    Domain = apps.get_model("arxii", "Domain")
    OrgIncomeStream = apps.get_model("arxii", "OrgIncomeStream")
    Area = apps.get_model("arxii", "Area")
    Title = apps.get_model("arxii", "Title")
    # A seat is always the barony at the bottom of a chain; a Domain above county that
    # some Title is seated on would be a legacy seed, and PROTECT would abort the
    # converge, so such a row is left alone rather than guessed at.
    seats = set(Title.objects.exclude(seat_domain=None).values_list("seat_domain_id", flat=True))
    above = (
        Domain.objects.filter(area__level__gt=COUNTY_LEVEL)
        .exclude(pk__in=seats)
        .select_related("area")
    )
    for domain in above:
        area = domain.area
        if domain.description and not area.description:
            Area.objects.filter(pk=area.pk).update(description=domain.description)
        _rehome(apps, domain, _chain_county_domain(apps, domain))
        if domain.territory_stream_id is not None:
            OrgIncomeStream.objects.filter(pk=domain.territory_stream_id).delete()
    above.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0384_dominion_demography"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
