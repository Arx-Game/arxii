"""Idempotent CG-world content seeder (#1333).

Promotes the character-creation "world" content currently living ad-hoc in
``FinalizationTestMixin._setup_finalization_base`` into shared, production-callable
seed rows — the content a fresh DB needs to actually run ``finalize_character``.
Create-if-missing; never overwrites; never deletes (the #651 invariant).

Child of #651 / epic #1220 (Phase A). Registered in ``CLUSTER_SEEDERS`` after
``magic`` because ``finalize_character`` picks the magic-seeded catalog
``Gift``/``Technique`` + ``Resonance``/``TechniqueStyle`` at finalize time (#2426),
and ``seed_beginning_traditions`` (below) links every seeded ``Beginnings`` to the
magic-seeded Unbound ``Tradition`` — NOT because ``Beginnings`` FKs into magic (it
FKs ``starting_area`` -> ``Realm`` and an M2M ``allowed_species`` -> ``Species``).
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import TYPE_CHECKING

from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    FALLBACK_STARTING_ROOM_FIXTURE_KEY,
    FALLBACK_STARTING_ROOM_KEY,
    FALLBACK_STARTING_ROOM_TYPECLASS,
    STARTING_TECHNIQUE_PICKS_TARGET,
)
from world.character_creation.models import Beginnings, StartingArea
from world.character_sheets.models import Gender, Heritage, Pronouns
from world.classes.models import Path, PathStage
from world.forms.models import (
    Build,
    FormTrait,
    FormTraitOption,
    HeightBand,
    SpeciesFormTrait,
    TraitType as FormTraitType,
)
from world.realms.models import Realm
from world.roster.models import Roster
from world.roster.models.families import Family
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.models import Trait, TraitType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

logger = logging.getLogger(__name__)

# Reserved slug for the AUTHORED Area that houses the canonical fallback
# starting room (#2448) — a room with no area is silently unexportable
# (export_grid_bundles only visits rooms via AUTHORED areas), so the fallback
# room must live somewhere AUTHORED too. Never assigned a realm here — this
# helper must stay callable independent of cluster order.
RESERVED_FALLBACK_AREA_SLUG = "arx"

# The canonical 12 stat names. Mirrors the set FinalizationTestMixin uses; kept
# here as the single seed-time source (factories-as-seed-data). The test mixin's
# DEFAULT_STATS dict carries per-stat starting *values* for a different purpose
# and is left where it is.
DEFAULT_STAT_NAMES: tuple[str, ...] = (
    "strength",
    "agility",
    "stamina",
    "charm",
    "presence",
    "composure",
    "intellect",
    "wits",
    "stability",
    "luck",
    "perception",
    "willpower",
)

# Explanatory copy for every character-creation stage's heading/intro (#2162), keyed
# to match the frontend's `copy?.<key>` lookups in
# frontend/src/character-creation/components/*Stage.tsx. Staff can edit any row
# in the admin afterward without a migration; this dict only supplies the
# fresh-deploy default so a new DB never ships blank stages.
CG_EXPLANATION_COPY: dict[str, str] = {
    "origin_heading": "Choose Your Origin",
    "origin_intro": (
        "Where does your story begin? Your starting realm shapes who your character "
        "already knows, what they take for granted, and which conflicts will find "
        "them first."
    ),
    "heritage_heading": "Your Heritage",
    "heritage_intro": (
        "Beginnings, species, and gender decide what your character is — and what "
        "the world assumes about them before they say a word."
    ),
    "heritage_beginnings_heading": "Your Beginnings",
    "heritage_beginnings_desc": (
        "Your beginnings set the household and circumstances your character was "
        "raised in, and which species and families are open to you."
    ),
    "heritage_species_heading": "Choose Your Species",
    "heritage_species_desc": (
        "Species carries its own stat leanings and how other characters read your "
        "character on sight — pick the one whose instincts suit your concept."
    ),
    "heritage_gender_heading": "Gender & Pronouns",
    "lineage_heading": "Family & Lineage",
    "lineage_intro": (
        "Claim a family within your starting area, go an orphan, or step forward as "
        "someone whose origins are still unknown — family ties bring kin, "
        "obligations, and a name people already have opinions about."
    ),
    "distinctions_heading": "Your Distinctions",
    "distinctions_intro": (
        "Distinctions are the advantages and disadvantages that make your character "
        "specific — a sharp mind, a bad leg, a secret debt. Spend your points "
        "deliberately; disadvantages give points back but shape play."
    ),
    "attributes_heading": "Attribute Scores",
    "attributes_intro": (
        "Allocate your twelve core statistics across the physical, social, mental, "
        "and meta categories. These numbers back every roll your character makes, "
        "so weight them toward how you want to play."
    ),
    "path_heading": "Choose Your Path",
    "path_intro": (
        "Your path is the road your character walks toward greatness — a "
        "narrative class shaping the skills, techniques, and story beats "
        "available as they grow."
    ),
    "path_skills_heading": "Starting Skills",
    "path_skills_desc": (
        "Spend your skill points across the specializations your path opens up; "
        "these are the trained competencies your character can already call on."
    ),
    "magic_heading": "Magic & Gifts",
    "identity_heading": "Name & Identity",
    "identity_intro": (
        "Give your character a name, a guiding concept, and the words and history "
        "that make them feel real before anyone else meets them."
    ),
    "appearance_heading": "Appearance & Build",
    "appearance_intro": (
        "Set your character's age, build, and physical traits, then write the "
        "description other players will see when they look at your character."
    ),
    "finaltouches_heading": "Goals & Motivations",
    "finaltouches_intro": (
        "Choose the goals and motivations that drive your character forward — "
        "checks that align with a goal earn a bonus, so pick what your character "
        "actually wants."
    ),
    "review_heading": "Review & Submit",
    "review_intro": (
        "Look over the whole character before you submit. Once it's in for "
        "review, staff will read it and either welcome your character to Arx or "
        "ask for revisions."
    ),
}


def ensure_canonical_fallback_room() -> ObjectDB:
    """Get-or-create the canonical fallback starting Room (#2121).

    Lazy-created via ``evennia_create.create_object`` the same way the magic
    cluster's cascade rooms are (``world/seeds/game_content/magic.py``) —
    ``ObjectDB.db_key`` is not unique in Evennia, so lookup uses
    ``filter().first()`` for idempotency. Callable independently of cluster
    order: any seeder needing "the" canonical starting room (character_creation,
    missions, progression) calls this and gets the same row back.

    Also marks the room's ``RoomProfile`` identity idempotently (#2448): AUTHORED
    origin + the reserved ``FALLBACK_STARTING_ROOM_FIXTURE_KEY``, so this row is
    stable-identity and included in the grid export. Never clobbers a staff-edited
    ``fixture_key`` on re-run.

    Also houses the room in a reserved AUTHORED Area (``RESERVED_FALLBACK_AREA_SLUG``,
    #2448): an AUTHORED room whose area is NULL or non-AUTHORED is silently
    unexportable (``export_grid_bundles`` only visits rooms via AUTHORED areas), so
    a room marked AUTHORED with no home area would export a StartingArea fixture
    referencing a room no bundle ever contains. Never overwrites an already-set
    ``area`` (staff edit wins), and never reassigns the reserved area if it already
    exists with a non-AUTHORED origin (staff edit wins there too — just warns).
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    existing = ObjectDB.objects.filter(
        db_key=FALLBACK_STARTING_ROOM_KEY,
        db_typeclass_path=FALLBACK_STARTING_ROOM_TYPECLASS,
    ).first()
    if existing is not None:
        room = existing
    else:
        room = evennia_create.create_object(
            typeclass=FALLBACK_STARTING_ROOM_TYPECLASS,
            key=FALLBACK_STARTING_ROOM_KEY,
            nohome=True,
        )

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.constants import AreaLevel, GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    reserved_area, area_created = Area.objects.get_or_create(
        slug=RESERVED_FALLBACK_AREA_SLUG,
        defaults={"name": "Arx", "level": AreaLevel.CITY, "origin": GridOrigin.AUTHORED},
    )
    if not area_created and reserved_area.origin != GridOrigin.AUTHORED:
        logger.warning(
            "Reserved fallback area (slug=%r) exists with origin=%r, not AUTHORED — "
            "leaving it alone. The canonical fallback room will not be assigned to it, "
            "which means it stays unexportable until a staff member fixes the area's "
            "origin.",
            RESERVED_FALLBACK_AREA_SLUG,
            reserved_area.origin,
        )
        reserved_area = None

    profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
    update_fields = []
    if profile.fixture_key is None:
        profile.fixture_key = FALLBACK_STARTING_ROOM_FIXTURE_KEY
        profile.origin = GridOrigin.AUTHORED
        update_fields.extend(["fixture_key", "origin"])
    if profile.area_id is None and reserved_area is not None:
        profile.area = reserved_area
        update_fields.append("area")
    if update_fields:
        profile.save(update_fields=update_fields)
    return room


def wire_starting_technique_picks_target():
    """Seed the 'starting_technique_picks' ModifierTarget (#2426).

    A character-creation-scoped flat bonus: distinctions granting extra CG
    magic-stage technique picks (e.g. Tradition Training) target this row.
    ``CharacterDraft.starting_technique_picks`` sums it via
    ``_get_distinction_bonus(STARTING_TECHNIQUE_PICKS_TARGET, CG_MODIFIER_CATEGORY)``.
    Idempotent via get_or_create on (category, name) — mirrors
    ``wire_elevation_advantage_modifier_target`` (world/combat/factories.py).
    """
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415

    category, _ = ModifierCategory.objects.get_or_create(name=CG_MODIFIER_CATEGORY)
    target, _ = ModifierTarget.objects.get_or_create(
        name=STARTING_TECHNIQUE_PICKS_TARGET,
        category=category,
        defaults={
            "description": "Extra CG magic-stage technique picks, beyond the base of 1.",
        },
    )
    return target


def ensure_tradition_training_distinction() -> None:
    """Seed the 'Tradition Training' distinction (#2426).

    Grants +1 CG magic-stage technique pick per rank (max_rank=2) via a
    DistinctionEffect targeting ``starting_technique_picks``. ``cost_per_rank=1``
    mirrors the existing seeded-distinction convention (the "Attractive"
    distinction, ``world/seeds/social_relationships.py``); "Arcane" is the
    magic-flavored category named in ``DistinctionCategory``'s own docstring
    ("the initial set: Physical, Mental, Personality, Social, Background, Arcane").
    """
    from world.distinctions.models import (  # noqa: PLC0415
        Distinction,
        DistinctionCategory,
        DistinctionEffect,
    )

    target = wire_starting_technique_picks_target()

    category, _ = DistinctionCategory.objects.get_or_create(
        slug="arcane",
        defaults={
            "name": "Arcane",
            "description": (
                "Distinctions tied to a character's magical tradition, practice, or gifts."
            ),
        },
    )
    distinction, _ = Distinction.objects.get_or_create(
        slug="tradition-training",
        defaults={
            "name": "Tradition Training",
            "category": category,
            "description": (
                "PLACEHOLDER: Years spent under a tradition's tutelage broaden which "
                "techniques you can call your own at the outset."
            ),
            "cost_per_rank": 1,
            "max_rank": 2,
        },
    )
    DistinctionEffect.objects.update_or_create(
        distinction=distinction,
        target=target,
        defaults={
            "value_per_rank": 1,
            "description": "+1 CG magic-stage technique pick per rank.",
        },
    )


#: Must match ``_UNBOUND_TRADITION_NAME`` in
#: ``world.seeds.game_content.magic.seed_starter_gift_catalog`` — that's the
#: "magic" cluster seeder that creates the row; this module only looks it up by
#: name (get_or_create ownership stays on the magic seeder).
_UNBOUND_TRADITION_NAME = "Unbound"


# The three Arx traditions, authored in the lore repo (beginnings/arx.md;
# fixtures/magic/tradition.json). Tradition rows are content-fixture data, not
# seeded here — the links below attach whichever of them exist.
_ARX_TRADITION_NAMES: tuple[str, ...] = (
    "The Vigil",
    "Metallic Order",
    "Fractals of the Abyss",
)

_ARX_BEGINNING_NAMES: tuple[str, ...] = ("Caretaker", "Sleeper", "Misbegotten")

# Player-facing Beginnings descriptions. Canonical text lives in the lore
# repo's beginnings/arx.md ("Player-facing description" blocks) — edit there
# first, then mirror here.
_CARETAKER_DESC = (
    "Arx is a city built for three million that holds fifty thousand, and your "
    "family has tended it for a thousand years. You grew up under the Shroud's "
    "grey twilight: sweeping steps no one would climb, lighting lamps in streets "
    "where nothing living walked, learning the names of every house on your row — "
    "including the empty ones. Especially the empty ones. Your people were offered "
    "the Great Callings and stayed; someone had to keep the city. When you came of "
    "age you were deeded a dark house of your own from among the countless empty, "
    "and you read its registry aloud the day you took the keys, so the house would "
    "know it was remembered. Then the Vanishing took the teachers, the Shroud "
    "fell, and the world outside — older now by ages you cannot count — began "
    "speaking your city's name like a prayer. The duty your family deferred for "
    "forty generations has come due. It is time, at last, to complete the Durance."
)

_SLEEPER_DESC = (
    "You woke in the dark beneath Arx, in a tomb that was never quite a grave. The "
    "stone lid moved because you pushed it; the cold preserving light faded as you "
    "sat up; and cut into the slab where your head had lain was a single line of "
    "text: your name. It is the only thing you have. Not your family, not your "
    "first language, not the reason you were set aside like a letter addressed to "
    "someone not yet born. The Caretakers found you wandering the necropolis and "
    "took you in gently — they have found others like you, more and more since the "
    "Shroud fell, and no one says aloud what everyone thinks about the timing. "
    "Sometimes your hands know things. A ward-sign drawn without thinking. A "
    "phrase of the craft pronounced a way that makes your teachers go quiet, "
    "because it is how their tradition sounded before their tradition began. "
    "Whoever preserved you meant you for something. The Vanishing took everyone "
    "who might have remembered what."
)

_MISBEGOTTEN_DESC = (
    "No one carried you into the world. The Tree of Souls simply had you, the way "
    "a tree has fruit: you were found at its roots, an infant with no mother, no "
    "lineage, and no explanation, and the Vigil carried you to the Cradle to be "
    "raised with the others like you. Arx lives easily with its ghosts, but it has "
    "never decided what you are — blessing or omen — so it treats you carefully, "
    "like a dropped thing that might be sacred: doors close politely as you pass, "
    "and prayers are said just after. Inside the Cradle you had what the rest of "
    "the ghost city forgot it missed. Noise. Siblings. A family assembled from "
    "foundlings, fiercer for being chosen. You speak the common tongue of Arx and "
    "nothing older; whatever people the Tree shaped you from, it did not pass "
    "along their words. And the question follows you up every empty street: the "
    "Tree keeps making people, in the emptiest city in the world, in the hour of "
    "its greatest need. What are you for?"
)


def seed_beginning_traditions() -> None:
    """Seed a BeginningTradition (Unbound, no gate) for every seeded Beginnings row.

    Without this, the CG Tradition step is empty for every Beginning on a fresh
    Big-Button-only DB: ``TraditionViewSet.get_queryset()`` returns nothing when
    ``beginning.cached_beginning_traditions`` is empty, and ``select_tradition``
    independently 400s without a matching ``BeginningTradition`` row — CG is
    uncompletable, even the tradition-agnostic Unbound path (#2426 whole-branch
    review finding).

    The Unbound ``Tradition`` row itself is seeded by
    ``world.seeds.game_content.magic.seed_starter_gift_catalog`` (the "magic"
    cluster), which runs BEFORE "character_creation" in cluster order
    (``world.seeds.clusters``) precisely so both sides of this join exist by the
    time this function runs. ``required_distinction=None`` — Unbound is the
    tradition-agnostic default, open to every beginning with no gate.
    Idempotent via get_or_create; never overwrites a staff-adjusted row.

    Skips silently (logged) if the Unbound tradition hasn't been seeded yet —
    cluster ordering guarantees this can't happen via the Big Button; defensive
    only, mirrors the per-row skip in ``seed_durance_officiants``
    (``world.progression.seeds``).
    """
    from world.character_creation.models import BeginningTradition  # noqa: PLC0415
    from world.magic.models import Tradition  # noqa: PLC0415

    unbound = Tradition.objects.filter(name=_UNBOUND_TRADITION_NAME).first()
    if unbound is None:
        logger.warning(
            "Skipping BeginningTradition seeding: %r tradition is not seeded.",
            _UNBOUND_TRADITION_NAME,
        )
        return

    for beginning in Beginnings.objects.all():
        BeginningTradition.objects.get_or_create(
            beginning=beginning,
            tradition=unbound,
            defaults={"required_distinction": None, "sort_order": 0},
        )

    # Arx beginnings additionally offer the city's three orphaned traditions
    # (lore repo: beginnings/arx.md). Those Tradition rows are authored content
    # loaded from the lore-repo fixture, not seeded — link whichever exist, so
    # a fixture-less dev DB still seeds cleanly with just Unbound.
    arx_traditions = list(Tradition.objects.filter(name__in=_ARX_TRADITION_NAMES, is_active=True))
    arx_beginnings = Beginnings.objects.filter(
        starting_area__name="Arx City", name__in=_ARX_BEGINNING_NAMES
    )
    for beginning in arx_beginnings:
        for sort_order, tradition in enumerate(arx_traditions, start=1):
            BeginningTradition.objects.get_or_create(
                beginning=beginning,
                tradition=tradition,
                defaults={"required_distinction": None, "sort_order": sort_order},
            )


def _seed_beginnings(area: StartingArea, area_luxen: StartingArea) -> tuple[Species, Species]:
    """Seed the Arx and Luxen Beginnings rows, species gates, and heritages.

    Canonical player-facing text and per-beginning mechanical gates live in
    the lore repo (beginnings/arx.md) — edit there first, mirror here.

    Returns the (Human, Khati) rows the caller wires into form traits.
    """
    human, _ = Species.objects.get_or_create(
        name="Human",
        defaults={"description": "The default species.", "sort_order": 0},
    )
    khati, _ = Species.objects.get_or_create(
        name="Khati",
        defaults={
            "description": "A feline species known for agility and perception.",
            "sort_order": 1,
        },
    )
    daeva, _ = Species.objects.get_or_create(
        name="Daeva",
        defaults={
            "description": "Angelic beings with divine heritage, always bearing feathered wings.",
            "sort_order": 30,
        },
    )
    # Elves begin only in Arx (world-lore-reference; lore repo). The parent row
    # exists so allowed_species can grant "all elves" via parent expansion.
    elf, _ = Species.objects.get_or_create(
        name="Elf",
        defaults={
            "description": "The elder peoples of the deep ages. Elves begin only in Arx.",
            "sort_order": 40,
        },
    )
    nox, _ = Species.objects.get_or_create(
        name="Nox'alfar",
        defaults={
            "description": (
                "Dark elves of the deep past, night-bound and easy among the dead. "
                "Sunlight is lethal to them; the grey twilight of Arx never was."
            ),
            "parent": elf,
            "sort_order": 41,
        },
    )
    sylv, _ = Species.objects.get_or_create(
        name="Sylv'alfar",
        defaults={
            "description": (
                "Wood elves, children of the old forests who once settled Arvum "
                "before the world outside forgot them."
            ),
            "parent": elf,
            "sort_order": 42,
        },
    )
    Species.objects.get_or_create(
        name="Rex'alfar",
        defaults={
            "description": (
                "High elves of lost Caer'alfar, rarest and proudest of the elder peoples."
            ),
            "parent": elf,
            "sort_order": 43,
        },
    )
    # Heritage rows must exist before the Arx beginnings that FK them.
    _seed_heritages()
    heritage_sleeper = Heritage.objects.get(name="Sleeper")
    heritage_misbegotten = Heritage.objects.get(name="Misbegotten")
    beginnings_caretaker, _ = Beginnings.objects.get_or_create(
        starting_area=area,
        name="Caretaker",
        defaults={
            "description": _CARETAKER_DESC,
            "trust_required": 0,
            "is_active": True,
            "sort_order": 0,
            "family_known": True,
        },
    )
    beginnings_sleeper, _ = Beginnings.objects.get_or_create(
        starting_area=area,
        name="Sleeper",
        defaults={
            "description": _SLEEPER_DESC,
            "trust_required": 0,
            "is_active": True,
            "sort_order": 1,
            "family_known": False,
            "heritage": heritage_sleeper,
        },
    )
    beginnings_misbegotten, _ = Beginnings.objects.get_or_create(
        starting_area=area,
        name="Misbegotten",
        defaults={
            "description": _MISBEGOTTEN_DESC,
            "trust_required": 0,
            "is_active": True,
            "sort_order": 2,
            "family_known": False,
            "heritage": heritage_misbegotten,
            "grants_species_languages": False,
        },
    )
    beginnings_luxen, _ = Beginnings.objects.get_or_create(
        starting_area=area_luxen,
        name="Luxen Commoner",
        defaults={
            "description": "A common beginning in the sunlit port of Luxen.",
            "trust_required": 0,
            "is_active": True,
            "sort_order": 3,
            "family_known": False,
        },
    )
    # Retire the pre-content Arx placeholders. Exact-description guard: a row
    # staff have edited no longer matches and is never touched.
    stale_placeholders = Beginnings.objects.filter(
        starting_area=area,
        name__in=("Commoner", "Noble"),
        description__in=(
            "A common beginning.",
            "A noble upbringing with known family and standing.",
        ),
        is_active=True,
    )
    for stale in stale_placeholders:
        stale.is_active = False
        stale.save(update_fields=["is_active"])
    # Species gates (beginnings/arx.md): Caretaker is Human; Sleeper adds the
    # night and wood elves; Misbegotten spans Human, Daeva, and all elves (via
    # the Elf parent). Luxen: Human + Khati.
    beginnings_caretaker.allowed_species.add(human)
    beginnings_sleeper.allowed_species.add(human, nox, sylv)
    beginnings_misbegotten.allowed_species.add(human, daeva, elf)
    beginnings_luxen.allowed_species.add(human)
    beginnings_luxen.allowed_species.add(khati)
    return human, khati


def seed_character_creation_dev() -> None:
    """Seed the CG-world content a fresh DB needs to run character creation.

    Idempotent: every write is ``get_or_create`` (or idempotent M2M ``add``);
    safe to re-run; never overwrites an edited row.
    """
    realm, _ = Realm.objects.get_or_create(
        name="Arx",
        defaults={"description": "The default realm.", "crest_asset": "", "theme": ""},
    )
    realm_luxen, _ = Realm.objects.get_or_create(
        name="Luxen",
        defaults={
            "description": "A sunlit coastal realm of trade and intrigue.",
            "crest_asset": "",
            "theme": "",
        },
    )
    area, _ = StartingArea.objects.get_or_create(
        name="Arx City",
        defaults={
            "description": "The default starting area.",
            "realm": realm,
            "is_active": True,
            "sort_order": 0,
            "access_level": StartingArea.AccessLevel.ALL,
            "minimum_trust": 0,
        },
    )
    area_luxen, _ = StartingArea.objects.get_or_create(
        name="Luxen Port",
        defaults={
            "description": "A bustling port city in the Luxen realm.",
            "realm": realm_luxen,
            "is_active": True,
            "sort_order": 1,
            "access_level": StartingArea.AccessLevel.ALL,
            "minimum_trust": 0,
        },
    )
    # #2121 — every seeded StartingArea must resolve to a real room (never a
    # silent None spawn). Never overwrite an already-wired room (staff edit).
    if area.default_starting_room_id is None:
        area.default_starting_room = ensure_canonical_fallback_room().room_profile
        area.save(update_fields=["default_starting_room"])
    if area_luxen.default_starting_room_id is None:
        area_luxen.default_starting_room = ensure_canonical_fallback_room().room_profile
        area_luxen.save(update_fields=["default_starting_room"])
    species, species_khati = _seed_beginnings(area, area_luxen)
    Gender.objects.get_or_create(
        key="male",
        defaults={"display_name": "Male", "is_default": False},
    )
    Gender.objects.get_or_create(
        key="female",
        defaults={"display_name": "Female", "is_default": False},
    )
    Gender.objects.get_or_create(
        key="non_binary",
        defaults={"display_name": "Non-Binary", "is_default": False},
    )
    Gender.objects.get_or_create(
        key="unspecified",
        defaults={"display_name": "Unspecified", "is_default": True},
    )
    TarotCard.objects.get_or_create(
        name="The Fool",
        defaults={
            "arcana_type": ArcanaType.MAJOR,
            "rank": 0,
            "latin_name": "Fatui",
        },
    )
    HeightBand.objects.get_or_create(
        name="average_band",
        defaults={
            "display_name": "Average",
            "min_inches": 60,
            "max_inches": 74,
            "weight_min": 120,
            "weight_max": 220,
            "is_cg_selectable": True,
        },
    )
    Build.objects.get_or_create(
        name="average_build",
        defaults={
            "display_name": "Average",
            "weight_factor": Decimal("1.0"),
            "is_cg_selectable": True,
        },
    )
    _seed_form_traits(species)
    _seed_form_traits(species_khati)
    _seed_pronouns()
    _seed_commoner_families(realm)
    for stat_name in DEFAULT_STAT_NAMES:
        Trait.objects.get_or_create(
            name=stat_name,
            defaults={"trait_type": TraitType.STAT, "description": stat_name},
        )
    Roster.objects.get_or_create(name="Available Characters")
    Roster.objects.get_or_create(name="Active Characters")
    Path.objects.get_or_create(
        name="The Wanderer",
        defaults={
            "description": "A default path.",
            "stage": PathStage.PROSPECT,
            "minimum_level": 1,
            "is_active": True,
        },
    )
    _seed_cg_explanations()
    ensure_tradition_training_distinction()
    seed_beginning_traditions()


def _seed_cg_explanations() -> None:
    """Upsert every ``CGExplanation`` row from ``CG_EXPLANATION_COPY`` (#2162).

    Unlike the rest of this seeder's create-if-missing rows, explanation copy is
    re-synced on every run via ``update_or_create`` so prose fixes made here in
    the repo keep reaching already-seeded deploys instead of being stuck behind
    whatever text happened to land first.
    """
    from world.character_creation.models import CGExplanation  # noqa: PLC0415

    for key, text in CG_EXPLANATION_COPY.items():
        CGExplanation.objects.update_or_create(key=key, defaults={"text": text})


# ---------------------------------------------------------------------------
# Appearance traits (FormTrait / FormTraitOption / SpeciesFormTrait)
# ---------------------------------------------------------------------------

# Each entry is (trait_name, display_name, trait_type, is_cosmetic, [options]).
# Options are (name, display_name) tuples. These are the minimum viable
# appearance choices a player needs to complete the Appearance stage of CG.
_APPEARANCE_TRAITS: tuple[tuple[str, str, str, bool, tuple[tuple[str, str], ...]], ...] = (
    (
        "hair_color",
        "Hair Color",
        FormTraitType.COLOR,
        True,
        (
            ("black", "Black"),
            ("brown", "Brown"),
            ("blonde", "Blonde"),
            ("red", "Red"),
            ("auburn", "Auburn"),
            ("white", "White"),
            ("gray", "Gray"),
        ),
    ),
    (
        "eye_color",
        "Eye Color",
        FormTraitType.COLOR,
        False,
        (
            ("brown", "Brown"),
            ("blue", "Blue"),
            ("green", "Green"),
            ("gray", "Gray"),
            ("hazel", "Hazel"),
        ),
    ),
    (
        "skin_tone",
        "Skin Tone",
        FormTraitType.COLOR,
        False,
        (
            ("fair", "Fair"),
            ("light", "Light"),
            ("medium", "Medium"),
            ("tan", "Tan"),
            ("dark", "Dark"),
        ),
    ),
)


def _seed_form_traits(species: Species) -> None:
    """Seed FormTrait, FormTraitOption, and SpeciesFormTrait for the given species.

    Creates the minimum viable appearance options for character creation.
    Each trait is linked to the species via SpeciesFormTrait with
    ``is_available_in_cg=True`` and no ``allowed_options`` restriction
    (all options are available).
    """
    for sort_idx, (name, display_name, trait_type, is_cosmetic, options) in enumerate(
        _APPEARANCE_TRAITS
    ):
        trait, _ = FormTrait.objects.get_or_create(
            name=name,
            defaults={
                "display_name": display_name,
                "trait_type": trait_type,
                "is_cosmetic": is_cosmetic,
                "sort_order": sort_idx,
            },
        )
        for opt_sort_idx, (opt_name, opt_display) in enumerate(options):
            FormTraitOption.objects.get_or_create(
                trait=trait,
                name=opt_name,
                defaults={
                    "display_name": opt_display,
                    "sort_order": opt_sort_idx,
                },
            )
        SpeciesFormTrait.objects.get_or_create(
            species=species,
            trait=trait,
            defaults={"is_available_in_cg": True},
        )


# ---------------------------------------------------------------------------
# Heritage
# ---------------------------------------------------------------------------

_HERITAGES: tuple[tuple[str, str, bool, bool, str], ...] = (
    # (name, description, is_special, family_known, family_display)
    (
        "Normal",
        "A standard upbringing with known family and origins.",
        False,
        True,
        "",
    ),
    (
        "Sleeper",
        "Awakened from magical slumber with unknown origins.",
        True,
        False,
        "Unknown",
    ),
    (
        "Misbegotten",
        "Born from the Tree of Souls with no parents.",
        True,
        False,
        "Discoverable in play",
    ),
)


def _seed_heritages() -> None:
    """Seed canonical Heritage rows for the Lineage stage of CG."""
    for name, description, is_special, family_known, family_display in _HERITAGES:
        Heritage.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "is_special": is_special,
                "family_known": family_known,
                "family_display": family_display,
            },
        )


# ---------------------------------------------------------------------------
# Pronouns
# ---------------------------------------------------------------------------

_PRONOUNS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    # (key, display_name, subject, object, possessive, is_default)
    ("he_him", "He/Him", "he", "him", "his", False),
    ("she_her", "She/Her", "she", "her", "hers", False),
    ("they_them", "They/Them", "they", "them", "theirs", False),
)


def _seed_pronouns() -> None:
    """Seed canonical Pronouns rows for the Identity stage of CG."""
    for key, display_name, subject, obj, possessive, is_default in _PRONOUNS:
        Pronouns.objects.get_or_create(
            key=key,
            defaults={
                "display_name": display_name,
                "subject": subject,
                "object": obj,
                "possessive": possessive,
                "is_default": is_default,
            },
        )


# ---------------------------------------------------------------------------
# Commoner families
# ---------------------------------------------------------------------------

_COMMONER_FAMILIES: tuple[str, ...] = (
    "The Vintners",
    "The Ironwrights",
    "The Millers",
)


def _seed_commoner_families(realm: Realm) -> None:
    """Seed at least one commoner family per realm for the Lineage stage.

    Players with the "Normal" heritage need a family to claim during CG.
    These are placeholder commoner families — staff can rename or add
    noble houses via the admin.
    """
    for name in _COMMONER_FAMILIES:
        Family.objects.get_or_create(
            name=name,
            defaults={
                "family_type": Family.FamilyType.COMMONER,
                "description": f"A commoner family of {realm.name}.",
                "is_playable": True,
                "origin_realm": realm,
            },
        )
