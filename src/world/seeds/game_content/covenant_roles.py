"""Role catalog seed for vows as combat roles (#2022, updated #2529).

Seeds the granted gifts, granted capabilities, and per-role action scaling
rows for the three canonical covenant roles (Vanguard/SWORD, Bulwark/SHIELD,
Harmonizer/CROWN). The role rows themselves are created by
``seed_gear_archetype_compatibility`` in the items seed; this module
attaches the combat-power layer.

Re-keyed by #2529 on ``slug`` rather than the retired single-archetype enum
(roles now carry a SWORD/SHIELD/CROWN blend, not one archetype). The
Vanguard's old ``cast_technique`` scaling row is NOT recreated — that
scaling moved to the blend power term (``covenant_role_blend_power_term``);
only Bulwark (interpose) and Luminary (rally) get a
``CovenantRoleActionScaling`` row.

All writes are idempotent (get_or_create throughout). Safe to call repeatedly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.covenants.models import CovenantRole


def seed_role_catalog_content() -> None:
    """Attach granted gifts, capabilities, and action scaling to the 3 roles.

    Called after ``seed_gear_archetype_compatibility()`` has created the role
    rows. For each role:
    - 1 granted Gift (MINOR) with 2 starter Techniques
    - 2 granted CapabilityTypes
    - a ``CovenantRoleActionScaling`` row for the role's signature action
      (Bulwark/Luminary only — Vanguard's cast-technique scaling lives in
      the blend power term instead, #2529)

    All idempotent via get_or_create.
    """

    from world.covenants.models import CovenantRole  # noqa: PLC0415

    slugs = ["sword-vanguard", "shield-bulwark", "crown-luminary"]
    roles_by_slug: dict[str, CovenantRole] = {
        role.slug: role for role in CovenantRole.objects.filter(slug__in=slugs)
    }

    for slug, role in roles_by_slug.items():
        _ensure_role_gift_and_techniques(role)
        _ensure_role_capabilities(role, slug)
        _ensure_role_action_scaling(role, slug)


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


def _ensure_role_capabilities(role: CovenantRole, slug: str) -> None:
    """Attach 2 granted capability types to the role."""
    from world.conditions.models import CapabilityType  # noqa: PLC0415

    capability_names = {
        "sword-vanguard": ["melee_attack", "ranged_attack"],
        "shield-bulwark": ["melee_attack", "defense"],
        "crown-luminary": ["support", "leadership"],
    }
    for cap_name in capability_names.get(slug, []):
        cap, _ = CapabilityType.objects.get_or_create(
            name=cap_name,
            defaults={"description": f"Capability granted by the {role.name} vow."},
        )
        role.granted_capabilities.add(cap)


def _ensure_role_action_scaling(role: CovenantRole, slug: str) -> None:
    """Create the CovenantRoleActionScaling row for this role's signature action.

    Re-keyed on ``covenant_role`` (was ``role_archetype``) by #2529. The old
    Vanguard (``sword-vanguard``) ``cast_technique`` row is NOT recreated — cast
    scaling moved to the blend power term (``covenant_role_blend_power_term``);
    only Bulwark (interpose) and Luminary (rally) get a row here.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.covenants.models import CovenantRoleActionScaling  # noqa: PLC0415

    # Signature action per role (sword-vanguard intentionally absent):
    action_keys = {
        "shield-bulwark": "combat_interpose",
        "crown-luminary": "combat_rally",
    }
    action_key = action_keys.get(slug)
    if action_key is None:
        return

    CovenantRoleActionScaling.objects.get_or_create(
        covenant_role=role,
        action_key=action_key,
        defaults={"thread_level_multiplier": Decimal("0.10")},
    )
