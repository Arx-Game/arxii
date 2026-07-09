"""Seed combo palette content for team finishers (#2017).

Creates 4-6 ``ComboDefinition`` rows with ``ComboSlot`` children across
the seeded EffectTypes and Resonances. At least 2 are
``discoverable_via_combat`` with linked ``discovery_achievement`` rows
and ceremony copy.

Idempotent — all rows are created via ``get_or_create`` on slug/name.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.combat.models import ComboDefinition
    from world.magic.models import EffectType, Resonance

logger = logging.getLogger(__name__)


def seed_combo_palette() -> None:
    """Create 4-6 authored combos as factory data.

    Called from the magic dev seed. Each combo has 2-3 slots with
    distinct EffectTypes. At least 2 are discoverable_via_combat with
    linked discovery achievements + ceremony copy.
    """
    from world.achievements.factories import AchievementFactory  # noqa: PLC0415
    from world.combat.models import ComboDefinition  # noqa: PLC0415
    from world.magic.models import Gift, TechniqueStyle  # noqa: PLC0415

    # Reuse or create the EffectTypes we need.
    effect_types = _ensure_effect_types()
    resonances = _ensure_resonances()

    # Create a shared gift for combo techniques.
    Gift.objects.get_or_create(name="Combo Arts")
    TechniqueStyle.objects.get_or_create(
        name="Combo",
        defaults={"description": "Magic expressed through coordinated team techniques."},
    )

    # --- Combo 1: Twin Strike (2-slot, Attack + Attack) ---
    combo_1, _ = ComboDefinition.objects.get_or_create(
        slug="twin-strike",
        defaults={
            "name": "Twin Strike",
            "description": "Two attackers strike in perfect unison, overwhelming defenses.",
            "hidden": False,
            "discoverable_via_combat": True,
            "bonus_damage": 25,
            "bypass_soak": True,
            "discovery_first_body": (
                "For the first time, a pair of combatants has executed Twin Strike in battle."
            ),
            "discovery_personal_body": "You have discovered Twin Strike.",
        },
    )
    _ensure_slots(combo_1, [effect_types["ranged_attack"]])

    # --- Combo 2: Shield and Spear (2-slot, Defense + Attack) ---
    combo_2, _ = ComboDefinition.objects.get_or_create(
        slug="shield-and-spear",
        defaults={
            "name": "Shield and Spear",
            "description": "One defends while the other strikes, an ancient pairing.",
            "hidden": False,
            "discoverable_via_combat": True,
            "bonus_damage": 20,
            "bypass_soak": False,
            "discovery_first_body": (
                "For the first time, a pair has executed Shield and Spear in battle."
            ),
            "discovery_personal_body": "You have discovered Shield and Spear.",
        },
    )
    _ensure_slots(combo_2, [effect_types["defense"], effect_types["ranged_attack"]])

    # --- Combo 3: Weakening Volley (2-slot, Debuff + Attack, resonance-gated) ---
    combo_3, _ = ComboDefinition.objects.get_or_create(
        slug="weakening-volley",
        defaults={
            "name": "Weakening Volley",
            "description": "A debuff opens the target before the strike lands.",
            "hidden": True,
            "discoverable_via_combat": True,
            "bonus_damage": 15,
            "bypass_soak": True,
            "discovery_first_body": (
                "For the first time, a pair has executed Weakening Volley in battle."
            ),
            "discovery_personal_body": "You have discovered Weakening Volley.",
        },
    )
    _ensure_slots(
        combo_3,
        [effect_types["debuff"], effect_types["ranged_attack"]],
        resonance=resonances.get("light"),
    )

    # --- Combo 4: Triumphant Surge (3-slot, Buff + Attack + Attack) ---
    combo_4, _ = ComboDefinition.objects.get_or_create(
        slug="triumphant-surge",
        defaults={
            "name": "Triumphant Surge",
            "description": "A buff amplifies two simultaneous strikes into a devastating finisher.",
            "hidden": True,
            "discoverable_via_combat": True,
            "bonus_damage": 40,
            "bypass_soak": True,
            "discovery_first_body": (
                "For the first time, a trio has executed Triumphant Surge in battle."
            ),
            "discovery_personal_body": "You have discovered Triumphant Surge.",
        },
    )
    _ensure_slots(
        combo_4,
        [effect_types["buff"], effect_types["ranged_attack"], effect_types["ranged_attack"]],
    )

    # Link discovery achievements for the discoverable combos.
    for combo in [combo_1, combo_2, combo_3, combo_4]:
        if combo.discovery_achievement_id is None:
            achievement = AchievementFactory(
                name=f"Discovered: {combo.name}",
                description=f"First discovered the {combo.name} combo in combat.",
                hidden=True,
            )
            combo.discovery_achievement = achievement
            combo.save(update_fields=["discovery_achievement"])

    logger.info("Seeded combo palette: %s combos", 4)


def _ensure_effect_types() -> dict[str, EffectType]:
    """Get or create the EffectTypes needed for the combo palette."""
    from world.magic.models import EffectType  # noqa: PLC0415

    result: dict[str, EffectType] = {}
    for name, desc, base_power, anima in [
        ("Ranged Attack", "Projects destructive energy at a distant target.", 10, 3),
        ("Defense", "Interposes magical protection between the caster and harm.", 8, 3),
        ("Buff", "Enhances the caster or an ally with a temporary magical boon.", None, 2),
        ("Debuff", "Weakens or hampers a target with a magical affliction.", None, 2),
    ]:
        et, _ = EffectType.objects.get_or_create(
            name=name,
            defaults={
                "description": desc,
                "base_power": base_power,
                "base_anima_cost": anima,
                "has_power_scaling": base_power is not None,
            },
        )
        result[name.lower().replace(" ", "_")] = et
    return result


def _ensure_resonances() -> dict[str, Resonance]:
    """Get or create the Resonances needed for resonance-gated combos."""
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415

    celestial, _ = Affinity.objects.get_or_create(name="Celestial")
    light, _ = Resonance.objects.get_or_create(name="Light", defaults={"affinity": celestial})
    return {"light": light}


def _ensure_slots(
    combo: ComboDefinition,
    effect_types: list[EffectType],
    *,
    resonance: Resonance | None = None,
) -> None:
    """Ensure ComboSlot rows exist for a combo, one per effect_type."""
    from world.combat.models import ComboSlot  # noqa: PLC0415

    for i, et in enumerate(effect_types, start=1):
        ComboSlot.objects.get_or_create(
            combo=combo,
            slot_number=i,
            defaults={
                "required_action_type": et,
                "resonance_requirement": resonance,
            },
        )
