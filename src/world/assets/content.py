"""Idempotent seed for the demo NPCRole + the three promotion offers (#1872).

Reuses the EXISTING Stealth/Leadership/Persuasion check-content seeders
(world.seeds.stealth_checks/governance_checks/social_checks) rather than
inventing new "Subterfuge"/"Politics"/"Allure" Trait rows — see this app's
module docstring / the PR description for the anti-reinvention rationale.
Exercised from tests only in this pass, matching world.companions.content's
precedent (no build_schema.py wiring yet — this is the only concrete
consumer shipping in this PR). Callers place their own Functionary in a
specific room via the existing
world.npc_services.functionaries.place_functionary.
"""

from __future__ import annotations

from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.models import NPCRole, NPCServiceOffer
from world.seeds.governance_checks import seed_governance_check_content
from world.seeds.social_checks import seed_social_check_content
from world.seeds.stealth_checks import seed_stealth_check_content

CULTIVABLE_ROLE_NAME = "Cultivable Contact"

# (OfferKind, label, check_type name, trait name for the eligibility gate,
#  rapport_requirement, min_trait value).
_PROMOTION_OFFERS: list[tuple[str, str, str, str, int, int]] = [
    (OfferKind.INFORMANT.value, "Cultivate as Informant", "Stealth", "Stealth", 20, 3),
    (OfferKind.CONTACT.value, "Cultivate as Contact", "Household Command", "Leadership", 20, 3),
    (
        OfferKind.PERSONAL_FAVOR.value,
        "Cultivate as Personal Favor",
        "Seduction",
        "Persuasion",
        20,
        3,
    ),
]


def ensure_asset_promotion_content() -> NPCRole:
    """Idempotently seed one demo NPCRole/Functionary + the three promotion offers.

    Returns the seeded NPCRole (callers placing a room-specific demo
    Functionary need it).
    """
    seed_stealth_check_content()
    seed_governance_check_content()
    seed_social_check_content()

    from world.checks.models import CheckType  # noqa: PLC0415

    role, _ = NPCRole.objects.get_or_create(
        name=CULTIVABLE_ROLE_NAME,
        defaults={
            "description": "A minor functionary worth cultivating.",
            "default_rapport_starting_value": 0,
        },
    )
    for (
        kind,
        label,
        check_type_name,
        trait_name,
        rapport_requirement,
        min_value,
    ) in _PROMOTION_OFFERS:
        check_type = CheckType.objects.get(name=check_type_name)
        NPCServiceOffer.objects.get_or_create(
            role=role,
            label=label,
            defaults={
                "kind": kind,
                "draw_mode": DrawMode.MENU,
                "eligibility_rule": {
                    "leaf": "min_trait",
                    "params": {"trait": trait_name, "value": min_value},
                },
                "rapport_requirement": rapport_requirement,
                "is_final": True,
                "check_type": check_type,
                "check_difficulty": 20,
            },
        )
    return role
