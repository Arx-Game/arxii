"""Kinship demo seed (#2062) — a walkable ducal house tree. PLACEHOLDER content.

Idempotent get-or-create keyed on names. Seeds one noble house with a
three-generation tree, two explicit appable slots, one fuzzy slot pool, a
public-false/hidden-true parentage pair (the Misbegotten pattern), and a
two-life soul chain — enough for CG slot browsing, tree rendering, and the
truth/record loops to be walked on a dev DB.
"""

from __future__ import annotations

DUCAL_HOUSE_NAME = "House Veyrane PLACEHOLDER"
MARRIAGE_KIND_NAME = "Marriage"


def seed_kinship_demo() -> None:
    """Seed the PLACEHOLDER ducal tree (idempotent)."""
    from world.roster.models import Family, UnionKind  # noqa: PLC0415
    from world.roster.services import kinship  # noqa: PLC0415

    family, created = Family.objects.get_or_create(
        name=DUCAL_HOUSE_NAME,
        defaults={
            "family_type": Family.FamilyType.NOBLE,
            "description": "PLACEHOLDER — a ducal house awaiting its authored prose.",
            "is_playable": True,
        },
    )
    if not created:
        return

    marriage, _ = UnionKind.objects.get_or_create(
        name=MARRIAGE_KIND_NAME, defaults={"confers_wedlock": True}
    )

    duchess = kinship.create_person(name="Duchess Maera Veyrane PLACEHOLDER", family=family)
    consort = kinship.create_person(name="Consort Alden PLACEHOLDER", family=family)
    union = kinship.record_union(kind=marriage, members=[duchess, consort])

    heir = kinship.create_person(name="Heir Casella PLACEHOLDER", family=family)
    kinship.record_parentage(child=heir, parent=duchess, born_within_union=union)
    kinship.record_parentage(child=heir, parent=consort, born_within_union=union)

    # Two explicit appable sibling slots for the heir.
    for label in ("Second daughter PLACEHOLDER", "First son PLACEHOLDER"):
        slot = kinship.create_person(name=label, family=family)
        slot.is_appable = True
        slot.save(update_fields=["is_appable"])
        kinship.record_parentage(child=slot, parent=duchess, born_within_union=union)
        kinship.record_parentage(child=slot, parent=consort, born_within_union=union)

    # A fuzzy pool: cousins available among the duchess's late sister's line.
    late_sister = kinship.create_person(
        name="Lady Ysolde PLACEHOLDER", family=family, is_deceased=True
    )
    grandmother = kinship.create_person(
        name="Dowager Serenna PLACEHOLDER", family=family, is_deceased=True
    )
    kinship.record_parentage(child=duchess, parent=grandmother)
    kinship.record_parentage(child=late_sister, parent=grandmother)
    pool = family.kin_slot_pools.create(
        description="Children of Lady Ysolde's line PLACEHOLDER",
        count_remaining=3,
    )
    pool.parents.set([late_sister])

    # The Misbegotten pattern: the heir's official father is the consort
    # (public record, false); the truth is hidden behind a staff-only fact
    # until content authoring attaches a real Secret + clues.
    hidden_sire = kinship.create_person(name="A stranger PLACEHOLDER")
    heir_official = heir.parentage_up.get(parent=consort)
    heir_official.is_true = False
    heir_official.save(update_fields=["is_true"])
    kinship.record_parentage(child=heir, parent=hidden_sire, is_public_record=False, is_true=True)

    # A two-life soul chain anchored on the dowager.
    ancient = kinship.create_person(name="Serenna the Elder PLACEHOLDER", is_deceased=True)
    inc = kinship.record_incarnation(soul=None, kinsperson=ancient, is_public_record=True)
    kinship.record_incarnation(soul=inc.soul, kinsperson=grandmother, is_public_record=True)
