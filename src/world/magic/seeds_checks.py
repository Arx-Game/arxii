"""Idempotent seeds for magical check content (#709).

The Magic CheckCategory, six composed CheckTypes, the Arcana Aspect, and
per-Ritual RitualCheckConfig rows for the SERVICE sanctum rituals.

No skill is named, created or weighted here (#4547, ADR-4450). Each check
type weights its stat only; the skills a magical roll adds are bespoke Magic
skills staff make and map in admin (``MagicActivitySkill``, the Path, Gift
and technique skill fields), added at roll time as ``extra_traits``. A check
type that weighted a Magic skill as well would count it twice.

Per repo discipline (#683): seeds live in code, get_or_create at every
layer, NOT committed fixtures. Re-runs preserve staff edits; the only write-back is the one-time
placeholder/blank description upgrade (#946 — loaddata cannot update
SharedMemoryModel rows, and the Plan 4 placeholder rows must gain real
content exactly once).

All weights and difficulties are TUNING PLACEHOLDERS — staff tunes in admin.

``checks.checkcategory``/``checktype``/``checktypetrait`` and
``classes.aspect`` are content-repo-owned (#2698) — looked up via
``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT`` is
on (``traits.trait`` too, where this module creates one directly).
``checks.checktypeaspect`` stays outside ``CONTENT_MODELS`` and keeps seeding
unconditionally. ``ensure_character_magic_check_type`` is NOT part of this
gating: it is not a seeder — it is called at runtime
(``world.magic.services.anima``) to synthesize a per-character personal magic
CheckType from an already-resolved stat/skill, which can never be "authored"
in advance (it is parametrized by the character's own pk), so it stays
unconditional.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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

MAGIC_CHECK_CATEGORY_NAME = "Magic"
ANIMA_RESTORATION_CHECK_TYPE_NAME = "Anima Restoration"
SANCTUM_CONSECRATION_CHECK_TYPE_NAME = "Sanctum Consecration"
SANCTUM_DISSOLUTION_CHECK_TYPE_NAME = "Sanctum Dissolution"
MAGICAL_ENDURANCE_CHECK_TYPE_NAME = "Magical Endurance"
RESIST_CORRUPTION_CHECK_TYPE_NAME = "Resist Corruption"
ARCANA_ASPECT_NAME = "Arcana"

# Extracted to satisfy S1192.
MAGIC_CHECK_CATEGORY_DESCRIPTION = "Checks of magical practice, lore, and endurance."

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
    (
        RESIST_CORRUPTION_CHECK_TYPE_NAME,
        "Resisting the pull of corruption when it crosses a stage threshold.",
        5,
    ),
]

# (check_type_name, stat_name, weight). Stats only: the skills a magical roll adds
# come from the magic skill settings at roll time (#4547), never from this table.
_MAGIC_TRAIT_WEIGHTS = [
    (ANIMA_RESTORATION_CHECK_TYPE_NAME, "willpower", "1.00"),
    (SANCTUM_CONSECRATION_CHECK_TYPE_NAME, "presence", "1.00"),
    (SANCTUM_DISSOLUTION_CHECK_TYPE_NAME, "willpower", "1.00"),
    (MAGICAL_ENDURANCE_CHECK_TYPE_NAME, "stability", "1.00"),
    (ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME, "willpower", "1.00"),
    (RESIST_CORRUPTION_CHECK_TYPE_NAME, "willpower", "1.00"),
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


def ensure_magic_check_category() -> CheckCategory | None:
    """Look up (or sample) the Magic CheckCategory — content-repo-owned (#2698)."""
    from world.checks.models import CheckCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    category = authored_or_sample(
        CheckCategory,
        {"description": MAGIC_CHECK_CATEGORY_DESCRIPTION},
        name=MAGIC_CHECK_CATEGORY_NAME,
    )
    if category is not None:
        _upgrade_placeholder_description(category, MAGIC_CHECK_CATEGORY_DESCRIPTION)
    return category


def _ensure_arcana_aspect() -> Any:
    """Look up (or sample) the Arcana Aspect — content-repo-owned (#2698)."""
    from world.classes.models import Aspect  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    return authored_or_sample(
        Aspect,
        {"description": "The magical aspect for path-based checks."},
        name=ARCANA_ASPECT_NAME,
    )


def _compose_trait_weights(check_types: dict, arcana: Any) -> None:
    """Attach trait weights and the Arcana aspect to each seeded CheckType.

    Args:
        check_types: Map of seeded CheckType name -> CheckType instance.
        arcana: The Arcana Aspect instance (or ``None`` to skip aspect wiring).

    Walks ``_MAGIC_TRAIT_WEIGHTS``, resolving each stat (authored or sampled),
    and creates the matching ``CheckTypeTrait`` row. Skips a weight whose
    CheckType or stat row is absent. When ``arcana`` is provided, attaches it
    to every CheckType.
    """
    from world.checks.models import CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    for ct_name, trait_name, weight in _MAGIC_TRAIT_WEIGHTS:
        check_type = check_types.get(ct_name)
        if check_type is None:
            continue
        trait = authored_or_sample(
            Trait,
            {
                "trait_type": TraitType.STAT,
                "category": _STAT_CATEGORIES[trait_name],
                "is_public": True,
            },
            name=trait_name,
        )
        if trait is None:
            continue
        authored_or_sample(
            CheckTypeTrait,
            {"weight": Decimal(weight)},
            check_type=check_type,
            trait=trait,
        )

    if arcana is not None:
        from world.checks.models import CheckTypeAspect  # noqa: PLC0415

        for check_type in check_types.values():
            CheckTypeAspect.objects.get_or_create(
                check_type=check_type,
                aspect=arcana,
                defaults={"weight": Decimal("1.00")},
            )


def ensure_magic_check_types() -> dict[str, CheckType]:
    """Look up (or sample) the six Magic CheckTypes with stat + Arcana aspect composition.

    ``checks.CheckCategory``/``CheckType``/``CheckTypeTrait`` and
    ``classes.Aspect`` are content-repo-owned (#2698) — looked up rather than
    invented unless ``SEED_SAMPLE_CONTENT`` is on. A CheckType whose category
    or row isn't authored is omitted from the returned dict; a trait-weight
    row is skipped when its trait isn't authored either. ``checks.
    CheckTypeAspect`` stays outside ``CONTENT_MODELS`` and keeps seeding
    unconditionally.
    """
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    category = ensure_magic_check_category()
    arcana = _ensure_arcana_aspect()

    check_types: dict[str, CheckType] = {}
    if category is not None:
        for name, description, display_order in _MAGIC_CHECK_TYPES:
            check_type = authored_or_sample(
                CheckType,
                {
                    "description": description,
                    "display_order": display_order,
                    "is_active": True,
                },
                name=name,
                category=category,
            )
            if check_type is None:
                continue
            _upgrade_placeholder_description(check_type, description)
            check_types[name] = check_type

    _compose_trait_weights(check_types, arcana)
    return check_types


def ensure_ritual_check_configs(
    check_types: dict[str, CheckType] | None = None,
) -> dict[str, RitualCheckConfig]:
    """Seed RitualCheckConfig rows for the five SERVICE sanctum rituals.

    Requires ensure_sanctum_rituals() to have run first. Each of the five
    Ritual rows is content-repo-owned (#2698) — ``ensure_sanctum_rituals()``
    skips a ritual it can't find (content repo doesn't author it and
    ``SEED_SAMPLE_CONTENT`` is off), so this looks each ritual up rather than
    asserting it exists, and skips the matching RitualCheckConfig when absent.

    When check_types is None, calls ensure_magic_check_types() internally
    to satisfy its own contract. Pass check_types explicitly (from the umbrella
    caller) to avoid a redundant second run.

    ``stat``/``skill``/``check_type`` are required FKs on ``RitualCheckConfig``
    — a config is skipped entirely when its "willpower" Trait, its skill, or the
    ritual's own CheckType (``checks.checktype``, #2698) isn't there, rather
    than raising ``DoesNotExist``.

    The skill is the one staff mapped to ``MagicActivity.RITUAL_WORKING``, the
    skill these rituals' rolls actually add (``perform_ritual_check``); for a
    SERVICE ritual the config's skill is only an authoring hint. This seeder
    names no skill (#4547): with nothing mapped, it writes no config, and the
    Required content dashboard lists the unmapped activity.
    """
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.models import Ritual  # noqa: PLC0415
    from world.magic.models.magic_activity import MagicActivitySkill  # noqa: PLC0415
    from world.magic.models.ritual_check_config import (  # noqa: PLC0415
        RitualCheckConfig,
    )
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    if check_types is None:
        check_types = ensure_magic_check_types()
    willpower = Trait.objects.filter(name="willpower", trait_type=TraitType.STAT).first()
    mapped = (
        MagicActivitySkill.objects.filter(
            activity=MagicActivity.RITUAL_WORKING, skill__is_active=True
        )
        .select_related("skill")
        .first()
    )
    skill = mapped.skill if mapped is not None else None

    configs: dict[str, RitualCheckConfig] = {}
    if willpower is None or skill is None:
        return configs
    for ritual_name, ct_name, difficulty, non_founder in _RITUAL_CHECK_CONFIGS:
        ritual = Ritual.objects.filter(name=ritual_name).first()
        if ritual is None:
            continue
        check_type = check_types.get(ct_name)
        if check_type is None:
            continue
        config, _ = RitualCheckConfig.objects.get_or_create(
            ritual=ritual,
            defaults={
                "stat": willpower,
                "skill": skill,
                "check_type": check_type,
                "target_difficulty": difficulty,
                "non_founder_target_difficulty": non_founder,
            },
        )
        configs[ritual_name] = config
    return configs


def character_magic_check_type_name(character_sheet: Any) -> str:
    """Stable, per-character CheckType name (natural key with the Magic category)."""
    return f"Magic Check — sheet {character_sheet.pk}"


def ensure_character_magic_check_type(character_sheet: Any, *, stat: Any, skill: Any):
    """Synthesize/return a per-character magic CheckType from stat + skill (+ Arcana).

    The character's signature check: rolled by their Anima Ritual AND their
    technique casts. Idempotent; weights are tuning placeholders (staff-tunable).

    Not part of the #2698 gating itself (see module docstring): unlike
    ``ensure_magic_check_category``/``ensure_magic_check_types`` (which author
    curated, named CheckTypes and stay gated), this function's own Magic
    ``CheckCategory`` dependency is resolved via a plain ``get_or_create`` — a
    per-character CheckType can never be pre-authored (it's parametrized by the
    character's own pk), so blocking it behind unauthored content would silently
    break every character's magic casting in a real deploy with no content repo
    yet seeded. ``get_or_create`` still finds an authored "Magic" category if
    the content repo provides one — no duplicate row, no divergent values. The
    Arcana aspect wiring stays optional and is skipped gracefully when missing.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import (  # noqa: PLC0415
        CheckCategory,
        CheckType,
        CheckTypeAspect,
        CheckTypeTrait,
    )

    category, _ = CheckCategory.objects.get_or_create(
        name=MAGIC_CHECK_CATEGORY_NAME,
        defaults={"description": MAGIC_CHECK_CATEGORY_DESCRIPTION},
    )
    arcana = _ensure_arcana_aspect()
    name = character_magic_check_type_name(character_sheet)
    check_type, _ = CheckType.objects.get_or_create(
        name=name,
        category=category,
        defaults={
            "description": "A character's personal magic check (anima ritual + casting).",
            "is_active": True,
            "owner_sheet": character_sheet,
        },
    )
    if check_type.owner_sheet_id != character_sheet.pk:
        check_type.owner_sheet = character_sheet
        check_type.save(update_fields=["owner_sheet"])
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type, trait=stat, defaults={"weight": Decimal("1.00")}
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type, trait=skill.trait, defaults={"weight": Decimal("1.00")}
    )
    if arcana is not None:
        CheckTypeAspect.objects.get_or_create(
            check_type=check_type, aspect=arcana, defaults={"weight": Decimal("1.00")}
        )
    return check_type


def ensure_magic_check_content() -> MagicCheckContentResult:
    """Umbrella: check types + ritual configs. Safe to call repeatedly."""
    check_types = ensure_magic_check_types()
    configs = ensure_ritual_check_configs(check_types=check_types)
    return MagicCheckContentResult(check_types=check_types, configs=configs)
