"""Framework-proving seed content for touchstones + generic reagents (#707).

Small, idempotent seed set: enough to prove the mechanism end-to-end on
Ritual of Sanctification. A full per-resonance/per-tier catalog is separate
content-authoring work, not framework work.
"""

from __future__ import annotations

from world.items.models import ItemTemplate
from world.magic.models import ResonanceTier, Ritual

PRAEDARI_PAW_TEMPLATE_NAME = "Paw of a Predatory Animal"
CANDLE_TEMPLATE_NAME = "Tallow Candle"
SALT_TEMPLATE_NAME = "Handful of Salt"
INCENSE_TEMPLATE_NAME = "Bundle of Incense"

_TIER_DEFAULTS = (
    ("Faint", 1, "A whisper of resonance, barely enough to matter."),
    ("Resonant", 2, "A clear, steady thrum of resonance."),
    ("Profound", 3, "Resonance dense enough to reshape a room."),
)


def ensure_resonance_tiers() -> list[ResonanceTier]:
    """Get-or-create the three framework-proving ResonanceTier rows."""
    tiers = []
    for name, level, description in _TIER_DEFAULTS:
        tier, _ = ResonanceTier.objects.get_or_create(
            tier_level=level, defaults={"name": name, "description": description}
        )
        tiers.append(tier)
    return tiers


def ensure_touchstone_content() -> tuple[ItemTemplate, list[ItemTemplate]]:
    """Get-or-create one example touchstone template + generic reagent templates.

    Self-contained: no canonical Resonance/Affinity catalog exists yet in
    production seed code (Resonances today are authored ad hoc, e.g. by
    story-specific dev-content seeds via ``ResonanceFactory``) — so this
    get-or-creates its own "Praedari" Resonance (+ "Primal" Affinity) by
    name rather than assuming some other seed ran first. This module is
    called unconditionally from ``seeds_sanctum.ensure_sanctum_rituals()``,
    which itself is called broadly (dev seed + many unrelated tests), so it
    must never hard-fail on a missing prerequisite.
    """
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415

    tiers = {t.tier_level: t for t in ensure_resonance_tiers()}
    primal_affinity, _ = Affinity.objects.get_or_create(
        name="Primal",
        defaults={"description": "The affinity of nature, beasts, and raw survival."},
    )
    praedari, _ = Resonance.objects.get_or_create(
        name="Praedari",
        defaults={
            "description": "The resonance of the predator, the hunt, and the kill.",
            "affinity": primal_affinity,
        },
    )

    touchstone, _ = ItemTemplate.objects.get_or_create(
        name=PRAEDARI_PAW_TEMPLATE_NAME,
        defaults={
            "description": "A dried predatory animal's paw, warm to the touch.",
            "weight": 0.2,
            "size": 1,
            "value": 0,
            "tied_resonance": praedari,
            "resonance_tier": tiers[1],
        },
    )

    reagent_names = (
        (CANDLE_TEMPLATE_NAME, "A plain tallow candle."),
        (SALT_TEMPLATE_NAME, "Coarse salt, enough for a warding line."),
        (INCENSE_TEMPLATE_NAME, "A bundle of dried, fragrant herbs."),
    )
    reagents = []
    for name, description in reagent_names:
        template, _ = ItemTemplate.objects.get_or_create(
            name=name, defaults={"description": description, "weight": 0.1, "size": 1, "value": 0}
        )
        reagents.append(template)

    return touchstone, reagents


def ensure_sanctification_requirements(ritual: Ritual) -> None:
    """Attach 1x touchstone-mode + reagent requirements to a Sanctification Ritual."""
    from world.magic.models import RitualComponentRequirement  # noqa: PLC0415

    tiers = {t.tier_level: t for t in ensure_resonance_tiers()}
    _, reagents = ensure_touchstone_content()

    RitualComponentRequirement.objects.get_or_create(
        ritual=ritual, min_touchstone_tier=tiers[1], defaults={"item_template": None, "quantity": 1}
    )
    for reagent in reagents:
        RitualComponentRequirement.objects.get_or_create(
            ritual=ritual,
            item_template=reagent,
            defaults={"min_touchstone_tier": None, "quantity": 1},
        )


def ensure_generic_reagents() -> list[ItemTemplate]:
    """Public alias used by tests/other seed callers that only need the reagent templates."""
    _, reagents = ensure_touchstone_content()
    return reagents
