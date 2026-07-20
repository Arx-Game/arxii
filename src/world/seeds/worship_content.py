"""Worship content seed (#2355): Rites skill, traditions, achievements, beings.

Idempotent. Names and lore are PLACEHOLDER pending Apostate rewrite. Magnitude
tuning is deferred by convention (placeholders-now); the aspect weights below
are the one mechanical knob (Path of the Chosen's ceremony edge).
"""

from django.utils.text import slugify

from world.worship.constants import (
    GODS_FAVORITE_CHOSEN,
    GODS_FAVORITE_PRINCE,
    GODS_FAVORITE_PRINCESS,
)

RITES_SKILL_NAME = "Rites"
CEREMONY_CHECK_TYPE = "Ceremony Rites"
DEVOTION_ASPECT_NAME = "Devotion"
PATH_OF_THE_CHOSEN = "Path of the Chosen"
SECRET_INVESTIGATION_CATEGORY = "secret-investigation"  # noqa: S105 — consent category slug

#: (specialization name, tradition name, tradition description) — PLACEHOLDER names.
_TRADITIONS = [
    ("Liturgy", "Church Liturgy", "PLACEHOLDER — formal rites of the mainline faiths."),
    ("Spiritcalling", "Spiritcalling", "PLACEHOLDER — shamanic totem and spirit worship."),
    ("Druidry", "Druidry", "PLACEHOLDER — nature worship of the old green ways."),
    ("Occultism", "Occultism", "PLACEHOLDER — veiled rites of darker powers."),
]

#: (being name, tradition name, description) — PLACEHOLDER example beings.
_BEINGS = [
    ("The Shepherd", "Church Liturgy", "PLACEHOLDER — the mainline god of the flock."),
    ("The Gray Sister", "Church Liturgy", "PLACEHOLDER — keeper of thresholds and the dead."),
    ("Old Antler", "Spiritcalling", "PLACEHOLDER — a great totem spirit of the wilds."),
    ("The Verdant", "Druidry", "PLACEHOLDER — the living green, worshipped in groves."),
    ("The Hollow Flame", "Occultism", "PLACEHOLDER — a dark power worshipped in secret."),
]


def ensure_rites_skill_and_specializations() -> dict[str, object]:
    """Seed the Rites skill (open to all paths) + tradition specializations."""
    from world.skills.models import Skill, Specialization  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name=RITES_SKILL_NAME,
        defaults={
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.SOCIAL,
            "is_public": True,
        },
    )
    skill, _ = Skill.objects.get_or_create(
        trait=trait,
        defaults={
            "tooltip": "Conducting ceremonies: funerals, weddings, blessings, sermons.",
            "display_order": 50,
            "is_active": True,
        },
    )
    specs: dict[str, object] = {}
    for order, (spec_name, _tradition, _desc) in enumerate(_TRADITIONS):
        spec, _ = Specialization.objects.get_or_create(
            parent_skill=skill,
            name=spec_name,
            defaults={"display_order": order, "is_active": True},
        )
        specs[spec_name] = spec
    return {"skill": skill, "specs": specs}


def ensure_ceremony_check_type(skill) -> object:
    """Seed the Ceremony Rites CheckType (presence + Rites) with the Devotion aspect.

    Aspect wiring gives Path of the Chosen its ceremony edge through the existing
    ``check_aspect_weight * path_aspect_weight * level`` formula — no new mechanism.
    The Path row may be absent on a bare test DB; the PathAspect link is skipped then.
    """
    from world.checks.models import CheckType, CheckTypeAspect, CheckTypeTrait  # noqa: PLC0415
    from world.classes.models import Aspect, Path, PathAspect  # noqa: PLC0415
    from world.seeds.social_checks import (  # noqa: PLC0415
        _ensure_social_category,
        _ensure_stat_trait,
    )

    check_type, _ = CheckType.objects.get_or_create(
        name=CEREMONY_CHECK_TYPE,
        category=_ensure_social_category(),
        defaults={"is_active": True},
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type, trait=_ensure_stat_trait("presence"), defaults={"weight": 1}
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type, trait=skill.trait, defaults={"weight": 1}
    )
    aspect, _ = Aspect.objects.get_or_create(
        name=DEVOTION_ASPECT_NAME,
        defaults={"description": "PLACEHOLDER — faith, devotion, and sacred office."},
    )
    CheckTypeAspect.objects.get_or_create(
        check_type=check_type, aspect=aspect, defaults={"weight": 2}
    )
    chosen = Path.objects.filter(name=PATH_OF_THE_CHOSEN).first()
    if chosen is not None:
        PathAspect.objects.get_or_create(
            character_path=chosen, aspect=aspect, defaults={"weight": 2}
        )
    return check_type


def ensure_favorite_achievements() -> None:
    """Seed the three God's Favorite achievement rows (Decision 6, #2355)."""
    from world.achievements.models import Achievement  # noqa: PLC0415

    for name in (GODS_FAVORITE_PRINCESS, GODS_FAVORITE_PRINCE, GODS_FAVORITE_CHOSEN):
        Achievement.objects.get_or_create(
            name=name,
            defaults={
                "slug": slugify(name),
                "description": (
                    "PLACEHOLDER — stand highest in a worshipped being's devotion. "
                    "The text never names the being."
                ),
                "hidden": False,
                "is_active": True,
            },
        )


def ensure_traditions_and_beings(specs: dict[str, object]) -> None:
    """Seed the four traditions and PLACEHOLDER example beings."""
    from world.worship.models import WorshippedBeing, WorshipTradition  # noqa: PLC0415

    traditions: dict[str, object] = {}
    for spec_name, tradition_name, description in _TRADITIONS:
        tradition, _ = WorshipTradition.objects.get_or_create(
            name=tradition_name,
            defaults={"description": description, "rites_specialization": specs[spec_name]},
        )
        traditions[tradition_name] = tradition
    for being_name, tradition_name, description in _BEINGS:
        WorshippedBeing.objects.get_or_create(
            name=being_name,
            defaults={
                "description": description,
                "tradition": traditions[tradition_name],
                "is_active": True,
            },
        )


def seed_worship_content() -> None:
    """Cluster entry point — idempotent.

    The ``secret-investigation`` consent category lives in the consent seed
    (``seeds/consent.py``) with the rest of the antagonism tree.
    """
    seeded = ensure_rites_skill_and_specializations()
    ensure_ceremony_check_type(seeded["skill"])
    ensure_favorite_achievements()
    ensure_traditions_and_beings(seeded["specs"])

    from world.worship.factories import wire_miracle_content  # noqa: PLC0415

    wire_miracle_content()
