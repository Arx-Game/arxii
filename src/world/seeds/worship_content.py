"""Worship content seed (#2355): Rites skill, traditions, achievements, beings.

Idempotent. Names and lore are PLACEHOLDER pending Apostate rewrite. Magnitude
tuning is deferred by convention (placeholders-now); the aspect weights below
are the one mechanical knob (Path of the Chosen's ceremony edge).

``skills.skill``, ``traits.trait``, ``checks.checktype``/``checktypetrait``, and
``classes.aspect``/``pathaspect`` are content-repo-owned (#2698) — looked up via
``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT`` is
on. ``checks.checktypeaspect`` stays outside ``CONTENT_MODELS`` and keeps
seeding unconditionally.
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
_CHURCH_LITURGY_TRADITION = "Church Liturgy"

#: (specialization name, tradition name, tradition description) — PLACEHOLDER names.
_TRADITIONS = [
    ("Liturgy", _CHURCH_LITURGY_TRADITION, "PLACEHOLDER — formal rites of the mainline faiths."),
    ("Spiritcalling", "Spiritcalling", "PLACEHOLDER — shamanic totem and spirit worship."),
    ("Druidry", "Druidry", "PLACEHOLDER — nature worship of the old green ways."),
    ("Occultism", "Occultism", "PLACEHOLDER — veiled rites of darker powers."),
]

#: (being name, tradition name, description) — PLACEHOLDER example beings.
_BEINGS = [
    ("The Shepherd", _CHURCH_LITURGY_TRADITION, "PLACEHOLDER — the mainline god of the flock."),
    (
        "The Gray Sister",
        _CHURCH_LITURGY_TRADITION,
        "PLACEHOLDER — keeper of thresholds and the dead.",
    ),
    ("Old Antler", "Spiritcalling", "PLACEHOLDER — a great totem spirit of the wilds."),
    ("The Verdant", "Druidry", "PLACEHOLDER — the living green, worshipped in groves."),
    ("The Hollow Flame", "Occultism", "PLACEHOLDER — a dark power worshipped in secret."),
]


def ensure_rites_skill_and_specializations() -> dict[str, object]:
    """Look up (or sample) the Rites skill (open to all paths) + tradition specializations.

    ``skills.Skill``/``traits.Trait`` are content-repo-owned (#2698); when the
    Skill isn't authored, ``specs`` is empty (its ``parent_skill`` FK is
    required). ``skills.Specialization`` itself is not content-repo-owned and
    stays unconditional.
    """
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill, Specialization  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait = authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.SOCIAL,
            "is_public": True,
        },
        name=RITES_SKILL_NAME,
    )
    skill = (
        authored_or_sample(
            Skill,
            {
                "tooltip": "Conducting ceremonies: funerals, weddings, blessings, sermons.",
                "display_order": 50,
                "is_active": True,
            },
            trait=trait,
        )
        if trait is not None
        else None
    )
    specs: dict[str, object] = {}
    if skill is not None:
        for order, (spec_name, _tradition, _desc) in enumerate(_TRADITIONS):
            spec, _ = Specialization.objects.get_or_create(
                parent_skill=skill,
                name=spec_name,
                defaults={"display_order": order, "is_active": True},
            )
            specs[spec_name] = spec
    return {"skill": skill, "specs": specs}


def ensure_ceremony_check_type(skill) -> object | None:
    """Look up (or sample) the Ceremony Rites CheckType (presence + Rites) + Devotion aspect.

    Aspect wiring gives Path of the Chosen its ceremony edge through the existing
    ``check_aspect_weight * path_aspect_weight * level`` formula — no new mechanism.
    The Path row may be absent on a bare test DB; the PathAspect link is skipped then.

    ``checks.CheckType``/``CheckTypeTrait`` and ``classes.Aspect``/``PathAspect``
    are content-repo-owned (#2698) — looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. ``checks.CheckTypeAspect`` stays outside
    ``CONTENT_MODELS`` and keeps seeding unconditionally. Returns ``None`` when
    the Social category or the CheckType itself isn't authored.
    """
    from world.checks.models import CheckType, CheckTypeAspect, CheckTypeTrait  # noqa: PLC0415
    from world.classes.models import Aspect, Path, PathAspect  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.seeds.social_checks import (  # noqa: PLC0415
        _ensure_social_category,
        _ensure_stat_trait,
    )

    category = _ensure_social_category()
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType, {"is_active": True}, name=CEREMONY_CHECK_TYPE, category=category
    )
    if check_type is None:
        return None

    presence = _ensure_stat_trait("presence")
    if presence is not None:
        authored_or_sample(CheckTypeTrait, {"weight": 1}, check_type=check_type, trait=presence)
    if skill is not None:
        authored_or_sample(CheckTypeTrait, {"weight": 1}, check_type=check_type, trait=skill.trait)
    aspect = authored_or_sample(
        Aspect,
        {"description": "PLACEHOLDER — faith, devotion, and sacred office."},
        name=DEVOTION_ASPECT_NAME,
    )
    if aspect is None:
        return check_type
    CheckTypeAspect.objects.get_or_create(
        check_type=check_type, aspect=aspect, defaults={"weight": 2}
    )
    chosen = Path.objects.filter(name=PATH_OF_THE_CHOSEN).first()
    if chosen is not None:
        authored_or_sample(PathAspect, {"weight": 2}, character_path=chosen, aspect=aspect)
    return check_type


def ensure_favorite_achievements() -> None:
    """Seed the three God's Favorite achievement rows (Decision 6, #2355).

    Content-repo-owned (#2832) — looked up via ``authored_or_sample`` rather
    than invented. Skips silently (with a warning) when the rows are not
    authored and ``SEED_SAMPLE_CONTENT`` is off.
    """
    from world.achievements.models import Achievement  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    for name in (GODS_FAVORITE_PRINCESS, GODS_FAVORITE_PRINCE, GODS_FAVORITE_CHOSEN):
        authored_or_sample(
            Achievement,
            {
                "name": name,
                "description": (
                    "PLACEHOLDER — stand highest in a worshipped being's devotion. "
                    "The text never names the being."
                ),
                "hidden": False,
                "is_active": True,
            },
            slug=slugify(name),
        )


def ensure_traditions_and_beings(specs: dict[str, object]) -> None:
    """Seed the four traditions and PLACEHOLDER example beings.

    ``rites_specialization`` is a required FK — a tradition whose specialization
    is missing (the Rites Skill/Trait isn't authored, #2698) is skipped entirely.
    """
    from world.worship.models import WorshippedBeing, WorshipTradition  # noqa: PLC0415

    traditions: dict[str, object] = {}
    for spec_name, tradition_name, description in _TRADITIONS:
        spec = specs.get(spec_name)
        if spec is None:
            continue
        tradition, _ = WorshipTradition.objects.get_or_create(
            name=tradition_name,
            defaults={"description": description, "rites_specialization": spec},
        )
        traditions[tradition_name] = tradition
    for being_name, tradition_name, description in _BEINGS:
        tradition = traditions.get(tradition_name)
        if tradition is None:
            continue
        WorshippedBeing.objects.get_or_create(
            name=being_name,
            defaults={
                "description": description,
                "tradition": tradition,
                "is_active": True,
            },
        )


_RITE_KINDS = (
    # (name, tier, description): all PLACEHOLDER; many kinds share a tier.
    ("Vigil", 1, "PLACEHOLDER: a night kept awake in the being's name."),
    ("Sermon", 1, "PLACEHOLDER: preaching the being's word to whoever listens."),
    ("Canticle", 1, "PLACEHOLDER: a sung devotion."),
    ("Blessing", 1, "PLACEHOLDER: a small consecration of a person, place or thing."),
    ("Pilgrimage", 2, "PLACEHOLDER: a demanding journey or service owed to the being."),
    ("Ordeal", 3, "PLACEHOLDER: a dangerous rite held as a full ceremony."),
)

# (tier, outcome name) -> (resonance, favor). PLACEHOLDER magnitudes: every
# tier pays every canonical outcome, a botch included, so a rite always reads
# a row (a missing row raises rather than paying 0).
_RITE_TIER_AWARDS = {
    1: {
        "Critical Failure": (0, 0),
        "Failure": (1, 1),
        "Partial Success": (2, 2),
        "Success": (4, 3),
        "Critical Success": (6, 5),
    },
    2: {
        "Critical Failure": (0, 0),
        "Failure": (2, 2),
        "Partial Success": (4, 4),
        "Success": (8, 6),
        "Critical Success": (12, 10),
    },
    3: {
        "Critical Failure": (0, 0),
        "Failure": (3, 3),
        "Partial Success": (6, 6),
        "Success": (12, 9),
        "Critical Success": (18, 15),
    },
}


def ensure_rite_kinds_and_awards() -> None:
    """Seed the shared RiteKind catalog and the (tier, outcome) award table (#3777).

    Idempotent (get_or_create on names and on the (tier, outcome) pair). The
    five canonical CheckOutcome rows come from ``seed_check_resolution_tables``,
    the same guarantee the anima ritual awards rely on. No per-being rite is
    seeded here: rites are authored per being (the Deity Editor, #3780).
    """
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415
    from world.worship.models import RiteKind, WorshipRiteTierAward  # noqa: PLC0415

    for name, tier, description in _RITE_KINDS:
        RiteKind.objects.get_or_create(
            name=name, defaults={"tier": tier, "description": description}
        )
    seed_check_resolution_tables()
    for tier, rows in _RITE_TIER_AWARDS.items():
        for outcome_name, (resonance_amount, favor_amount) in rows.items():
            WorshipRiteTierAward.objects.get_or_create(
                tier=tier,
                outcome_tier=CheckOutcome.objects.get(name=outcome_name),
                defaults={"resonance_amount": resonance_amount, "favor_amount": favor_amount},
            )


def ensure_shrine_kind():
    """Get-or-create the Shrine ``RoomFeatureKind`` (#3778): persona-owned,
    level 1 only, installed in place by ``found_shrine`` (RITUAL mechanism, no
    project). Idempotent; also called by the service so a fresh database works."""
    from world.room_features.constants import (  # noqa: PLC0415
        RoomFeatureInstallMechanism,
        RoomFeatureOwnerType,
        RoomFeatureServiceStrategy,
    )
    from world.room_features.models import (  # noqa: PLC0415
        RoomFeatureKind,
        RoomFeatureKindOwnerType,
    )
    from world.worship.constants import SHRINE_KIND_NAME  # noqa: PLC0415

    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.SHRINE,
        defaults={
            "name": SHRINE_KIND_NAME,
            "description": "PLACEHOLDER: a household shrine to one being, grown by its rites.",
            "max_level": 1,
            "install_mechanism": RoomFeatureInstallMechanism.RITUAL,
        },
    )
    RoomFeatureKindOwnerType.objects.get_or_create(
        feature_kind=kind, owner_type=RoomFeatureOwnerType.PERSONA
    )
    return kind


# (scope, name, min_points, bonus_percent): PLACEHOLDER tiers, a temple's bigger.
_CONSECRATION_TIERS = (
    ("shrine", "Humble", 0, 5),
    ("shrine", "Tended", 25, 10),
    ("shrine", "Hallowed", 100, 20),
    ("temple", "Founded", 0, 10),
    ("temple", "Consecrated", 100, 25),
    ("temple", "Great", 500, 50),
)


def ensure_consecration_tiers() -> None:
    """Seed the shrine and temple consecration tier tables (#3778), idempotently."""
    from world.worship.models import ConsecrationTier  # noqa: PLC0415

    for scope, name, min_points, bonus_percent in _CONSECRATION_TIERS:
        ConsecrationTier.objects.get_or_create(
            scope=scope,
            min_points=min_points,
            defaults={"name": name, "bonus_percent": bonus_percent},
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
    ensure_rite_kinds_and_awards()
    ensure_shrine_kind()
    ensure_consecration_tiers()

    from world.worship.factories import wire_miracle_content  # noqa: PLC0415

    wire_miracle_content()
