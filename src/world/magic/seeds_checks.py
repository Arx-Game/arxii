"""Idempotent seeds for magical check content (#709).

Skills (ritualism / occult / theology), the Magic CheckCategory, five
composed CheckTypes, the Arcana Aspect, and per-Ritual RitualCheckConfig
rows for the SERVICE sanctum rituals. Per repo discipline (#683): seeds
live in code, get_or_create at every layer, NOT committed fixtures.
Re-runs preserve staff edits; the only write-back is the one-time
placeholder/blank description upgrade (#946 — loaddata cannot update
SharedMemoryModel rows, and the Plan 4 placeholder rows must gain real
content exactly once).

All weights and difficulties are TUNING PLACEHOLDERS — staff tunes in admin.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.constants import ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME
from world.magic.seeds_sanctum import (
    DISSOLUTION_RITUAL_NAME,
    HOMECOMING_RITUAL_NAME,
    PURGING_RITUAL_NAME,
    SANCTIFICATION_COVENANT_RITUAL_NAME,
    SANCTIFICATION_PERSONAL_RITUAL_NAME,
)

if TYPE_CHECKING:
    from world.checks.models import CheckCategory, CheckType
    from world.magic.models.ritual_check_config import RitualCheckConfig
    from world.skills.models import Skill

MAGIC_CHECK_CATEGORY_NAME = "Magic"
ANIMA_RESTORATION_CHECK_TYPE_NAME = "Anima Restoration"
SANCTUM_CONSECRATION_CHECK_TYPE_NAME = "Sanctum Consecration"
SANCTUM_DISSOLUTION_CHECK_TYPE_NAME = "Sanctum Dissolution"
MAGICAL_ENDURANCE_CHECK_TYPE_NAME = "Magical Endurance"
ARCANA_ASPECT_NAME = "Arcana"

# (name, description, display_order)
_MAGIC_SKILLS = [
    ("ritualism", "Performing and leading rites — the practice of magic.", 0),
    ("occult", "Hidden lore and the mechanics of magic — the theory.", 1),
    ("theology", "Faith-framed magical practice — the divine frame.", 2),
]

# (name, description, display_order)
_MAGIC_CHECK_TYPES = [
    (
        ANIMA_RESTORATION_CHECK_TYPE_NAME,
        "Restoring anima through one's personal ritual practice.",
        0,
    ),
    (
        SANCTUM_CONSECRATION_CHECK_TYPE_NAME,
        "Consecrating, re-consecrating, or imbuing a Sanctum.",
        1,
    ),
    (
        SANCTUM_DISSOLUTION_CHECK_TYPE_NAME,
        "Tearing down a Sanctum and reclaiming its imbued resonance.",
        2,
    ),
    (
        MAGICAL_ENDURANCE_CHECK_TYPE_NAME,
        "Enduring magical strain — soulfray resilience, soul-tether rescue.",
        3,
    ),
    (
        ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME,
        "Endurance check against the spiritual pressure of hallowed ground.",
        4,
    ),
]

# (check_type_name, trait_name, weight)
# stat-ness is derived from trait_name in _STAT_CATEGORIES
_MAGIC_TRAIT_WEIGHTS = [
    (ANIMA_RESTORATION_CHECK_TYPE_NAME, "willpower", "1.00"),
    (ANIMA_RESTORATION_CHECK_TYPE_NAME, "ritualism", "1.00"),
    (ANIMA_RESTORATION_CHECK_TYPE_NAME, "theology", "0.50"),
    (SANCTUM_CONSECRATION_CHECK_TYPE_NAME, "presence", "1.00"),
    (SANCTUM_CONSECRATION_CHECK_TYPE_NAME, "theology", "1.00"),
    (SANCTUM_CONSECRATION_CHECK_TYPE_NAME, "ritualism", "0.50"),
    (SANCTUM_DISSOLUTION_CHECK_TYPE_NAME, "willpower", "1.00"),
    (SANCTUM_DISSOLUTION_CHECK_TYPE_NAME, "occult", "1.00"),
    (SANCTUM_DISSOLUTION_CHECK_TYPE_NAME, "ritualism", "0.50"),
    (MAGICAL_ENDURANCE_CHECK_TYPE_NAME, "stability", "1.00"),
    (MAGICAL_ENDURANCE_CHECK_TYPE_NAME, "occult", "0.50"),
    (ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME, "willpower", "1.00"),
    (ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME, "theology", "0.50"),
]

# Stat trait defaults used only when the stat row doesn't exist yet.
# Values are TraitCategory DB strings (TextChoices: META="meta", etc.).
_STAT_CATEGORIES: dict[str, str] = {
    "willpower": "meta",
    "presence": "social",
    "stability": "mental",
}

# (ritual_name, check_type_name, target_difficulty, non_founder_target_difficulty)
_RITUAL_CHECK_CONFIGS = [
    (HOMECOMING_RITUAL_NAME, SANCTUM_CONSECRATION_CHECK_TYPE_NAME, 10, None),
    (PURGING_RITUAL_NAME, SANCTUM_CONSECRATION_CHECK_TYPE_NAME, 15, None),
    (SANCTIFICATION_PERSONAL_RITUAL_NAME, SANCTUM_CONSECRATION_CHECK_TYPE_NAME, 12, None),
    (
        SANCTIFICATION_COVENANT_RITUAL_NAME,
        SANCTUM_CONSECRATION_CHECK_TYPE_NAME,
        12,
        None,
    ),
    (DISSOLUTION_RITUAL_NAME, SANCTUM_DISSOLUTION_CHECK_TYPE_NAME, 20, 40),
]


@dataclass(frozen=True)
class MagicCheckContentResult:
    """Returned by ensure_magic_check_content()."""

    skills: dict[str, Skill]
    check_types: dict[str, CheckType]
    configs: dict[str, RitualCheckConfig]


def _upgrade_placeholder_description(obj: CheckCategory | CheckType, description: str) -> None:
    """One-time content upgrade: only rewrite blank or PLACEHOLDER descriptions.

    A BLANK description is treated as unseeded and will be re-filled on every run.
    Only a non-blank, non-PLACEHOLDER-prefixed description is treated as a staff
    edit and preserved. Staff edits survive re-runs; the Plan 4 placeholder rows
    gain real content exactly once (#946 — loaddata can't update idmapper rows).
    """
    if not obj.description or obj.description.startswith("PLACEHOLDER"):
        obj.description = description
        obj.save(update_fields=["description"])


def ensure_magic_check_category() -> CheckCategory:
    """Single home for the Magic CheckCategory row."""
    from world.checks.models import CheckCategory  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(
        name=MAGIC_CHECK_CATEGORY_NAME,
        defaults={"description": "Checks of magical practice, lore, and endurance."},
    )
    _upgrade_placeholder_description(category, "Checks of magical practice, lore, and endurance.")
    return category


def ensure_magic_skills() -> dict[str, Skill]:
    """Seed the three magical Skill rows + backing SKILL Traits."""
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    skills: dict[str, Skill] = {}
    for name, description, display_order in _MAGIC_SKILLS:
        trait, _ = Trait.objects.get_or_create(
            name=name,
            defaults={
                "trait_type": TraitType.SKILL,
                "category": TraitCategory.MAGIC,
                "description": description,
                "is_public": True,
            },
        )
        skill, _ = Skill.objects.get_or_create(
            trait=trait,
            defaults={"display_order": display_order, "is_active": True},
        )
        skills[name] = skill
    return skills


def _ensure_arcana_aspect():
    from world.classes.models import Aspect  # noqa: PLC0415

    aspect, _ = Aspect.objects.get_or_create(
        name=ARCANA_ASPECT_NAME,
        defaults={"description": "The magical aspect for path-based checks."},
    )
    return aspect


def ensure_magic_check_types() -> dict[str, CheckType]:
    """Seed the five Magic CheckTypes with trait + Arcana aspect composition."""
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeAspect,
        CheckTypeTrait,
    )
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    category = ensure_magic_check_category()
    ensure_magic_skills()
    arcana = _ensure_arcana_aspect()

    check_types: dict[str, CheckType] = {}
    for name, description, display_order in _MAGIC_CHECK_TYPES:
        check_type, _ = CheckType.objects.get_or_create(
            name=name,
            category=category,
            defaults={
                "description": description,
                "display_order": display_order,
                "is_active": True,
            },
        )
        _upgrade_placeholder_description(check_type, description)
        check_types[name] = check_type

    for ct_name, trait_name, weight in _MAGIC_TRAIT_WEIGHTS:
        if trait_name in _STAT_CATEGORIES:
            trait, _ = Trait.objects.get_or_create(
                name=trait_name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": _STAT_CATEGORIES[trait_name],
                    "is_public": True,
                },
            )
        else:
            trait = Trait.objects.get(name=trait_name, trait_type=TraitType.SKILL)
        CheckTypeTrait.objects.get_or_create(
            check_type=check_types[ct_name],
            trait=trait,
            defaults={"weight": Decimal(weight)},
        )

    for check_type in check_types.values():
        CheckTypeAspect.objects.get_or_create(
            check_type=check_type,
            aspect=arcana,
            defaults={"weight": Decimal("1.00")},
        )

    return check_types


def ensure_ritual_check_configs(
    check_types: dict[str, CheckType] | None = None,
) -> dict[str, RitualCheckConfig]:
    """Seed RitualCheckConfig rows for the five SERVICE sanctum rituals.

    Requires ensure_sanctum_rituals() to have run (the Ritual rows must
    exist) — raises Ritual.DoesNotExist otherwise.

    When check_types is None, calls ensure_magic_check_types() internally
    to satisfy its own contract. Pass check_types explicitly (from the umbrella
    caller) to avoid a redundant second run.
    """
    from world.magic.models import Ritual  # noqa: PLC0415
    from world.magic.models.ritual_check_config import (  # noqa: PLC0415
        RitualCheckConfig,
    )
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    if check_types is None:
        check_types = ensure_magic_check_types()
    willpower = Trait.objects.get(name="willpower", trait_type=TraitType.STAT)
    ritualism = Skill.objects.get(trait__name="ritualism")

    configs: dict[str, RitualCheckConfig] = {}
    for ritual_name, ct_name, difficulty, non_founder in _RITUAL_CHECK_CONFIGS:
        ritual = Ritual.objects.get(name=ritual_name)
        config, _ = RitualCheckConfig.objects.get_or_create(
            ritual=ritual,
            defaults={
                "stat": willpower,
                "skill": ritualism,
                "check_type": check_types[ct_name],
                "target_difficulty": difficulty,
                "non_founder_target_difficulty": non_founder,
            },
        )
        configs[ritual_name] = config
    return configs


def ensure_magic_check_content() -> MagicCheckContentResult:
    """Umbrella: skills + check types + ritual configs. Safe to call repeatedly."""
    skills = ensure_magic_skills()
    check_types = ensure_magic_check_types()
    configs = ensure_ritual_check_configs(check_types=check_types)
    return MagicCheckContentResult(skills=skills, check_types=check_types, configs=configs)
