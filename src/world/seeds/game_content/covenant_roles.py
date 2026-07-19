"""Role catalog seed for vows as combat roles (#2022, updated #2529).

Seeds the granted gifts, granted capabilities, and per-role action scaling
rows for the three canonical covenant roles (Vanguard/SWORD, Bulwark/SHIELD,
Harmonizer/CROWN). The role rows themselves are created by
``seed_gear_archetype_compatibility`` in the items seed; this module
attaches the combat-power layer.

All writes are idempotent (get_or_create throughout). Safe to call repeatedly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.covenants.models import CovenantRole


def seed_role_catalog_content() -> None:
    """Attach granted gifts, capabilities, and archetype scaling to the 3 roles.

    Called after ``seed_gear_archetype_compatibility()`` has created the role
    rows. For each role:
    - 1 granted Gift (MINOR) with 2 starter Techniques
    - 2 granted CapabilityTypes
    - 1 CovenantRoleActionScaling row for the role's signature action

    All idempotent via get_or_create.
    """

    from world.covenants.constants import RoleArchetype  # noqa: PLC0415
    from world.covenants.models import (  # noqa: PLC0415
        CovenantRole,
    )

    roles_by_slug = {
        "sword-vanguard": RoleArchetype.SWORD,
        "shield-bulwark": RoleArchetype.SHIELD,
        "crown-luminary": RoleArchetype.CROWN,
    }

    for slug, archetype in roles_by_slug.items():
        try:
            role = CovenantRole.objects.get(slug=slug)
        except CovenantRole.DoesNotExist:
            continue

        _ensure_role_gift_and_techniques(role)
        _ensure_role_capabilities(role, archetype)
        _ensure_role_action_scaling(role, archetype)


def _ensure_role_gift_and_techniques(role: CovenantRole) -> None:
    """Create or update the role's granted gift + starter techniques."""
    from world.magic.constants import GiftKind  # noqa: PLC0415
    from world.magic.models import EffectType, Gift, Technique  # noqa: PLC0415
    from world.magic.models.techniques import TechniqueStyle  # noqa: PLC0415

    gift_name = f"{role.name} Vow"
    gift, _ = Gift.objects.get_or_create(
        name=gift_name,
        defaults={
            "description": f"Combat techniques granted by the {role.name} covenant vow.",
            "kind": GiftKind.MINOR,
        },
    )

    # Link via CovenantRoleGiftGrant (unlock_thread_level=0 = always while engaged)
    from world.covenants.models import CovenantRoleGiftGrant  # noqa: PLC0415

    CovenantRoleGiftGrant.objects.get_or_create(
        covenant_role=role,
        gift=gift,
        defaults={"unlock_thread_level": 0},
    )

    # 2 starter techniques per role gift. These are real Technique rows.
    # "Manifestation" (the most universal style) is get_or_create'd here rather
    # than merely looked up (#2474): it was formerly guaranteed present as a
    # side effect of the magic cluster's now-retired starter-catalog seed
    # (which ran before this "covenant_roles" cluster) — that guarantee is
    # gone now that the starter catalog is lore-repo content, loaded (or not)
    # independently of this seed's own cluster ordering.
    style, _ = TechniqueStyle.objects.get_or_create(
        name="Manifestation",
        defaults={
            "description": "Magic made tangible — raw elemental force given shape and weight.",
        },
    )

    # Get or create a basic Attack effect type for the techniques
    effect_type, _ = EffectType.objects.get_or_create(
        name="Attack",
        defaults={"description": "Offensive magical effect."},
    )

    technique_specs = [
        (f"{role.name} Strike", f"A {role.name} vow technique."),
        (f"{role.name} Guard", f"A defensive {role.name} vow technique."),
    ]
    for tech_name, tech_desc in technique_specs:
        Technique.objects.get_or_create(
            name=tech_name,
            gift=gift,
            defaults={
                "description": tech_desc,
                "style": style,
                "effect_type": effect_type,
                "level": 1,
                "intensity": 3,
                "control": 5,
                "anima_cost": 2,
            },
        )


def _ensure_role_capabilities(role: CovenantRole, archetype: str) -> None:
    """Attach 2 granted capability types to the role."""
    from world.conditions.models import CapabilityType  # noqa: PLC0415

    capability_names = {
        "sword": ["melee_attack", "ranged_attack"],
        "shield": ["melee_attack", "defense"],
        "crown": ["support", "leadership"],
    }
    for cap_name in capability_names.get(archetype, []):
        cap, _ = CapabilityType.objects.get_or_create(
            name=cap_name,
            defaults={"description": f"Capability granted by the {role.name} vow."},
        )
        role.granted_capabilities.add(cap)


def _ensure_role_action_scaling(role: CovenantRole, archetype: str) -> None:
    """Create the CovenantRoleActionScaling row for this role's signature action.

    Re-keyed on ``covenant_role`` (was ``role_archetype``) by #2529 — the ``archetype``
    param still selects which signature action this role gets.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.covenants.models import CovenantRoleActionScaling  # noqa: PLC0415

    # Each archetype's signature action:
    action_keys = {
        "sword": "cast_technique",
        "shield": "combat_interpose",
        "crown": "combat_rally",
    }
    action_key = action_keys.get(archetype)
    if action_key is None:
        return

    CovenantRoleActionScaling.objects.get_or_create(
        covenant_role=role,
        action_key=action_key,
        defaults={"thread_level_multiplier": Decimal("0.10")},
    )
