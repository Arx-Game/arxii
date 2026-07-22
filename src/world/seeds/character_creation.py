"""Idempotent CG-world content seeder (#1333).

Promotes the character-creation "world" content currently living ad-hoc in
``FinalizationTestMixin._setup_finalization_base`` into shared, production-callable
seed rows — the content a fresh DB needs to actually run ``finalize_character``.
Create-if-missing; never overwrites; never deletes (the #651 invariant).

Child of #651 / epic #1220 (Phase A). Registered in ``CLUSTER_SEEDERS`` after
``magic`` because ``finalize_character`` picks catalog ``Gift``/``Technique`` +
``Resonance``/``TechniqueStyle`` rows at finalize time (#2426), and
``seed_beginning_traditions`` (below) links every seeded ``Beginnings`` to the
Unbound ``Tradition`` — NOT because ``Beginnings`` FKs into magic (it FKs
``starting_area`` -> ``Realm`` and an M2M ``allowed_species`` -> ``Species``).
Since #2474 those catalog rows are lore-repo content loaded by
``load_world_content`` before any cluster seeder runs (ADR-0142), not
magic-cluster-seeded.
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
    UNBOUND_DRAWBACK_DISTINCTION_SLUG,
    UNBOUND_TRADITION_NAME,
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

    from world.societies.models import Organization

logger = logging.getLogger(__name__)

# Reserved slug for the AUTHORED Area that houses the canonical fallback
# starting room (#2448) — a room with no area is silently unexportable
# (export_grid_bundles only visits rooms via AUTHORED areas), so the fallback
# room must live somewhere AUTHORED too. Never assigned a realm here — this
# helper must stay callable independent of cluster order.
RESERVED_FALLBACK_AREA_SLUG = "arx"

# Shared description for magic-tied distinction seeds.
_MAGIC_DISTINCTION_DESCRIPTION = (
    "Distinctions tied to a character's magical tradition, practice, or gifts."
)

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
    "anima_check_heading": "Anima Check",
    "anima_check_intro": (
        "Every cast rolls a check built from a stat and a skill you choose now. "
        "This is purely mechanical — how your magic looks and feels in a scene is "
        "always yours to describe."
    ),
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
    "review_heading": "Your Testament",
    "review_intro": (
        "You are preparing the testament your character will carry into the "
        "Ritual of the Durance — the moment they stand before the assembly and "
        "speak who they are. The words you choose here are what they will "
        "present. The actual rite happens later, in play; for now, this is your "
        "chance to see your character whole before submitting them for review."
    ),
    "review_epigraph": ("One stands before us in Durance, speak thy name and testament."),
    "review_testament_heading": "The Testament",
    "review_glimpse_label": "What your character would speak of themselves",
    "review_record_heading": "The Record",
    "review_banner_submitted": "Your testament has been submitted for review.",
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
            "description": (_MAGIC_DISTINCTION_DESCRIPTION),
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


#: Canonical name: ``world.character_creation.constants.UNBOUND_TRADITION_NAME``
#: (#2428 Task 3). The row itself is real lore-repo content, loaded via
#: ``core_management.content_fixtures.load_world_content()`` ahead of every
#: cluster seeder (formerly created here-adjacent by the now-retired
#: ``world.seeds.game_content.magic.seed_starter_gift_catalog``, #2474) —
#: this module only looks it up by name.
_UNBOUND_TRADITION_NAME = UNBOUND_TRADITION_NAME

#: Slug for the "Orphaned Tradition" drawback distinction (#2428 Task 5). Local
#: to this module — unlike ``UNBOUND_TRADITION_NAME``/``SHROUDWATCH_ACADEMY_NAME``
#: (``character_creation/constants.py``), nothing outside seed content and its
#: tests resolves this by name; the CG-finalize hook never reads it.
_ORPHANED_TRADITION_DISTINCTION_SLUG = "orphaned-tradition"

#: Canonical name: ``world.character_creation.constants.UNBOUND_DRAWBACK_DISTINCTION_SLUG``
#: (#2442). Also referenced by name (this exact string) in
#: ``world.magic.services.tradition_membership`` (the
#: ``_SHED_ON_JOIN_SLUGS``/``_REAPPLY_ON_LEAVE_SLUG`` constants, #2441 Task 8/9) —
#: keep in sync if this ever changes.
_UNBOUND_DRAWBACK_DISTINCTION_SLUG = UNBOUND_DRAWBACK_DISTINCTION_SLUG

#: Name for the one example orphaned Arx tradition seeded alongside the
#: drawback (#2428 Task 5). Richer lore ("ancient Traditions for the Metallic
#: Order and the Fractals of the Abyss" per the #2428 vision) is a lore-repo
#: authoring pass; this row is a PLACEHOLDER, content-overridable.
_METALLIC_ORDER_TRADITION_NAME = "Metallic Order"


def wire_magic_learning_ap_cost_target():
    """Seed the 'magic_learning_ap_cost' ModifierTarget (#2442).

    A live-play percent AP surcharge on magic-learning activities: the "Unbound"
    drawback distinction (``ensure_unbound_drawback_distinction`` below) authors a
    +50 ``DistinctionEffect`` targeting this row. Read at the technique-acquisition
    seam (``world.magic.services.gift_acquisition.charge_and_learn``) via
    ``world.mechanics.services.get_modifier_total`` — the live post-CG
    ``CharacterModifier`` resolution path every other distinction-authored modifier
    uses, NOT the CG-draft ``CharacterDraft._get_distinction_bonus`` helper (that
    reads a draft's in-progress ``draft_data``, never a committed
    ``CharacterDistinction``). Idempotent via get_or_create on (category, name) —
    mirrors ``wire_starting_technique_picks_target`` above.
    """
    from world.magic.constants import (  # noqa: PLC0415
        MAGIC_LEARNING_AP_COST_TARGET_NAME,
        MAGIC_MODIFIER_CATEGORY_NAME,
    )
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415

    category, _ = ModifierCategory.objects.get_or_create(name=MAGIC_MODIFIER_CATEGORY_NAME)
    target, _ = ModifierTarget.objects.get_or_create(
        name=MAGIC_LEARNING_AP_COST_TARGET_NAME,
        category=category,
        defaults={
            "description": (
                "Percent AP surcharge on magic-learning activities (technique "
                "acquisition — teaching-offer accepts and #2440 TRAIN offers)."
            ),
        },
    )
    return target


def ensure_unbound_drawback_distinction():
    """Seed the 'Unbound' drawback distinction (#2442).

    Marks a character as self-taught/traditionless-in-play: a +50%-AP-cost
    surcharge on magic-learning activities (the "uphill battle" the Unbound codex
    lore describes — TIME, not power; resonance earning/spending is untouched, per
    the 2026-07-17 spec correction). Wired onto the Unbound ``BeginningTradition``
    row via ``required_distinction`` (``seed_beginning_traditions`` below) — the
    same #2426 gate ``ensure_tradition_training_distinction``/
    ``ensure_orphaned_tradition_distinction`` use, so selecting Unbound at CG
    requires the drawback already be in the draft (no auto-attach — mirrors
    Orphaned Tradition's shape exactly; ``world.character_creation.views
    .TraditionViewSet.select_tradition``'s gate is generic and was not changed by
    this task).

    ``cost_per_rank=-2`` mirrors ``ensure_orphaned_tradition_distinction``'s
    convention (a modest CG point refund; the drawback's teeth are the AP
    surcharge, not the refund). Shed automatically on joining a living tradition
    and re-applied on leaving one (``world.magic.services.tradition_membership``,
    #2441 Task 8/9) — this seed only authors the row; the shed/reapply lifecycle
    lives there.

    "Arcane" reuses the magic-flavored ``DistinctionCategory`` first seeded by
    ``ensure_tradition_training_distinction`` (get_or_create is a no-op on a
    second creation regardless of call order). Idempotent via get_or_create /
    update_or_create; never overwrites a staff-adjusted ``Distinction`` row (the
    ``DistinctionEffect`` value is re-synced on every run, same as
    ``ensure_tradition_training_distinction``'s).
    """
    from world.distinctions.models import (  # noqa: PLC0415
        Distinction,
        DistinctionCategory,
        DistinctionEffect,
    )

    target = wire_magic_learning_ap_cost_target()

    category, _ = DistinctionCategory.objects.get_or_create(
        slug="arcane",
        defaults={
            "name": "Arcane",
            "description": (_MAGIC_DISTINCTION_DESCRIPTION),
        },
    )
    distinction, _ = Distinction.objects.get_or_create(
        slug=_UNBOUND_DRAWBACK_DISTINCTION_SLUG,
        defaults={
            "name": "Unbound",
            "category": category,
            "description": (
                "PLACEHOLDER: self-taught, with no living tradition to formally guide "
                "your practice — your magic develops just as strong as anyone "
                "else's, only slower. Shed automatically the moment you join a "
                "tradition. Content-overridable — real lore lives in the private "
                "lore repo."
            ),
            "cost_per_rank": -2,
            "max_rank": 1,
        },
    )
    DistinctionEffect.objects.update_or_create(
        distinction=distinction,
        target=target,
        defaults={
            "value_per_rank": 50,
            "description": "+50% AP cost on magic-learning activities.",
        },
    )
    return distinction


def seed_beginning_traditions() -> None:
    """Seed a BeginningTradition (Unbound, gated on the "Unbound" drawback) for
    every seeded Beginnings row.

    Without this, the CG Tradition step is empty for every Beginning on a fresh
    Big-Button-only DB: ``TraditionViewSet.get_queryset()`` returns nothing when
    ``beginning.cached_beginning_traditions`` is empty, and ``select_tradition``
    independently 400s without a matching ``BeginningTradition`` row — CG is
    uncompletable, even the tradition-agnostic Unbound path (#2426 whole-branch
    review finding).

    The Unbound ``Tradition`` row itself is real lore-repo content, loaded via
    ``core_management.content_fixtures.load_world_content()`` — which
    ``world.seeds.database.seed_dev_database()`` runs BEFORE any cluster
    seeder (formerly seeded here-adjacent by the now-retired "magic" cluster
    helper ``seed_starter_gift_catalog``, #2474), precisely so both sides of
    this join exist by the time this function runs.
    ``required_distinction=<Unbound drawback>`` (#2442,
    was ``None`` pre-#2442) — selecting Unbound now requires the draft already
    hold the "Unbound" drawback distinction, exactly the same gate shape
    ``seed_metallic_order_tradition`` uses for its orphaned-tradition example
    (no auto-attach anywhere in the stack; see ``ensure_unbound_drawback_
    distinction``'s docstring). Idempotent via get_or_create; never overwrites a
    staff-adjusted row — an already-seeded pre-#2442 row keeps
    ``required_distinction=None`` until staff (or a fresh DB) re-seeds it.

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

    unbound_drawback = ensure_unbound_drawback_distinction()

    for beginning in Beginnings.objects.all():
        BeginningTradition.objects.get_or_create(
            beginning=beginning,
            tradition=unbound,
            defaults={"required_distinction": unbound_drawback, "sort_order": 0},
        )


def ensure_shroudwatch_academy() -> Organization:
    """Seed the Shroudwatch Academy org — every Prospect's CG entrance point (#2428).

    ``tradition=None`` is deliberate (ruling on #2426): the Academy is a
    multi-tradition teaching structure that trains through its trainer NPCs
    rather than being a single Tradition's own dedicated org. Resolved by
    name (``SHROUDWATCH_ACADEMY_NAME``) at CG-finalize time
    (``world.character_creation.services._finalize_academy_entrance_obligation``)
    to create the Unbound entrance obligation / sponsor-settled row.

    ``description``/rank titles are PLACEHOLDER and content-overridable — the
    real Academy prose (rooms, trainer Functionaries, The Vanishing lore) is a
    lore-repo authoring pass (#2428's spec, "Content" section), not this seed.
    Idempotent via get_or_create; never overwrites a staff-adjusted row.
    """
    from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME  # noqa: PLC0415
    from world.societies.models import Organization, OrganizationType  # noqa: PLC0415

    org_type, _ = OrganizationType.objects.get_or_create(
        name="guild",
        defaults={
            "rank_1_title": "Headmaster",
            "rank_2_title": "Senior Trainer",
            "rank_3_title": "Trainer",
            "rank_4_title": "Journeyman",
            "rank_5_title": "Prospect",
        },
    )
    academy, _ = Organization.objects.get_or_create(
        name=SHROUDWATCH_ACADEMY_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: the academy every Prospect passes through on the way "
                "to becoming a Potential. Content-overridable — real lore (rooms, "
                "trainer Functionaries, The Vanishing) is a lore-repo authoring pass."
            ),
            "org_type": org_type,
            "tradition": None,  # deliberate NULL — #2426 ruling
        },
    )
    return academy


def ensure_orphaned_tradition_distinction():
    """Seed the 'Orphaned Tradition' drawback distinction (#2428 Task 5).

    Marks a tradition as currently teacherless (post-Vanishing Arx traditions
    especially — see #2428's addendum). Wired onto a ``BeginningTradition`` row
    via ``required_distinction`` (the same #2426 gate ``ensure_tradition_training_
    distinction`` uses), so selecting an orphaned tradition at CG auto-attaches
    this drawback. ``cost_per_rank`` is negative — the house drawback convention
    (``Distinction.cost_per_rank`` docstring: "Positive costs points, negative
    reimburses"; e.g. the ``-2``/``-5``/``-10`` fixtures across
    ``world/distinctions/tests``) — refunding CG points the way any other
    disadvantage does. ``-2`` is a modest refund: per the #2428 spec, this
    drawback's teeth are trainerlessness (#2440's members-only/no-trainer rules),
    not a stat penalty, so deliberately NO ``DistinctionEffect`` is attached here
    (contrast ``ensure_tradition_training_distinction``, which does attach one).

    "Arcane" reuses the magic-flavored ``DistinctionCategory`` first seeded by
    ``ensure_tradition_training_distinction`` (get_or_create is a no-op on a
    second creation regardless of call order). Idempotent via get_or_create;
    never overwrites a staff-adjusted row.
    """
    from world.distinctions.models import Distinction, DistinctionCategory  # noqa: PLC0415

    category, _ = DistinctionCategory.objects.get_or_create(
        slug="arcane",
        defaults={
            "name": "Arcane",
            "description": (_MAGIC_DISTINCTION_DESCRIPTION),
        },
    )
    distinction, _ = Distinction.objects.get_or_create(
        slug=_ORPHANED_TRADITION_DISTINCTION_SLUG,
        defaults={
            "name": "Orphaned Tradition",
            "category": category,
            "description": (
                "PLACEHOLDER: your tradition's teachers are gone — lost to The "
                "Vanishing, scattered, or simply dead — and no one at Shroudwatch "
                "Academy can train you in its ways until they're found or replaced. "
                "Content-overridable — real lore lives in the private lore repo."
            ),
            "cost_per_rank": -2,
            "max_rank": 1,
        },
    )
    return distinction


def seed_metallic_order_tradition():
    """Seed the 'Metallic Order' example orphaned Arx tradition (#2428 Task 5).

    Demonstrates the orphaned-tradition shape end to end:

    - The "Orphaned Tradition" drawback (``ensure_orphaned_tradition_distinction``).
    - A ``Tradition`` row (get_or_create by name; PLACEHOLDER description,
      content-overridable — real Metallic Order lore is a lore-repo authoring
      pass per the #2428 vision).
    - ``TraditionGiftGrant`` rows granting it the same starter Gifts Unbound
      grants — reads Unbound's own ``TraditionGiftGrant`` rows (real lore-repo
      content, loaded via ``load_world_content()``) rather than hardcoding gift
      names, so this stays in sync with the starter catalog automatically.
    - ``BeginningTradition`` rows for every Arx-realm ``Beginnings`` (``starting_
      area__realm__name="Arx"`` — the #2428 vision names Arx as the realm with
      "many orphans" and ancient traditions like this one), each carrying
      ``required_distinction=<Orphaned Tradition>``. Per the #2428 spec ruling,
      this is authored data staff can mutate as story unfolds (a recovery quest
      restoring teachers => staff clears ``required_distinction`` on these rows),
      and CG reflects the change automatically — no code change needed.

    Skips (logged) if the Unbound tradition or its starter gift grants aren't
    seeded yet — mirrors ``seed_beginning_traditions``'s defensive skip;
    content-repo load running before any cluster seeder (#2474 Decision 5)
    guarantees this can't happen via the Big Button. Idempotent throughout via
    get_or_create; never overwrites a staff-adjusted row.
    """
    from world.character_creation.models import BeginningTradition  # noqa: PLC0415
    from world.magic.models import Tradition  # noqa: PLC0415
    from world.magic.models.grants import TraditionGiftGrant  # noqa: PLC0415

    unbound = Tradition.objects.filter(name=_UNBOUND_TRADITION_NAME).first()
    if unbound is None:
        logger.warning(
            "Skipping %r tradition seeding: %r tradition is not seeded.",
            _METALLIC_ORDER_TRADITION_NAME,
            _UNBOUND_TRADITION_NAME,
        )
        return None

    starter_grants = list(TraditionGiftGrant.objects.filter(tradition=unbound))
    if not starter_grants:
        logger.warning(
            "Skipping %r tradition seeding: no starter TraditionGiftGrant rows found for %r.",
            _METALLIC_ORDER_TRADITION_NAME,
            _UNBOUND_TRADITION_NAME,
        )
        return None

    distinction = ensure_orphaned_tradition_distinction()

    tradition, _ = Tradition.objects.get_or_create(
        name=_METALLIC_ORDER_TRADITION_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: an ancient Arx tradition whose teachers vanished long "
                "before living memory — its rites are still practiced by those who "
                "carry its name, but no living trainer walks Shroudwatch Academy's "
                "halls. Content-overridable — real lore lives in the private lore repo."
            ),
            "is_active": True,
            "sort_order": 1,
        },
    )

    for grant in starter_grants:
        TraditionGiftGrant.objects.get_or_create(tradition=tradition, gift=grant.gift)

    for beginning in Beginnings.objects.filter(starting_area__realm__name="Arx"):
        BeginningTradition.objects.get_or_create(
            beginning=beginning,
            tradition=tradition,
            defaults={"required_distinction": distinction, "sort_order": 1},
        )

    return tradition


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
    species, _ = Species.objects.get_or_create(
        name="Human",
        defaults={"description": "The default species.", "sort_order": 0},
    )
    species_khati, _ = Species.objects.get_or_create(
        name="Khati",
        defaults={
            "description": "A feline species known for agility and perception.",
            "sort_order": 1,
        },
    )
    beginnings, _ = Beginnings.objects.get_or_create(
        name="Commoner",
        defaults={
            "description": "A common beginning.",
            "starting_area": area,
            "trust_required": 0,
            "is_active": True,
            "sort_order": 0,
            "family_known": False,
        },
    )
    beginnings_noble, _ = Beginnings.objects.get_or_create(
        name="Noble",
        defaults={
            "description": "A noble upbringing with known family and standing.",
            "starting_area": area,
            "trust_required": 0,
            "is_active": True,
            "sort_order": 1,
            "family_known": True,
        },
    )
    beginnings_luxen, _ = Beginnings.objects.get_or_create(
        name="Luxen Commoner",
        defaults={
            "description": "A common beginning in the sunlit port of Luxen.",
            "starting_area": area_luxen,
            "trust_required": 0,
            "is_active": True,
            "sort_order": 2,
            "family_known": False,
        },
    )
    # Arx beginnings: Human only. Luxen beginnings: Human + Khati.
    # This tests the species-filtering UI — Khati only appears when Luxen
    # is selected as the starting area.
    beginnings.allowed_species.add(species)
    beginnings_noble.allowed_species.add(species)
    beginnings_luxen.allowed_species.add(species)
    beginnings_luxen.allowed_species.add(species_khati)
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
    _seed_heritages()
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
    ensure_shroudwatch_academy()
    seed_metallic_order_tradition()
    ensure_somehow_always_broke_distinction()


def ensure_somehow_always_broke_distinction():
    """Seed the 'Somehow Always Broke' economic distinction + its drain (#2613).

    A large negative (``cost_per_rank=-50``) that a player takes so their
    perpetually-broke concept cannot be undone by another player's generosity —
    a consent mechanic (like the antagonism register #2170), not a balance knob.
    ``max_rank=1``. Personality category per Apostate's ruling (the flaw reads as
    a trait — compulsion, recklessness, the addictions the description names).

    The mechanic lives in the ``DistinctionPurseDrain`` sidecar
    (``100% / floor 0``): the two weekly cron tasks empty every holder's purse
    down to just that week's income. Both rows are idempotent ``get_or_create``;
    the drain row's ``distinction`` O2O keys off the seeded distinction. Never
    overwrites a staff-adjusted row.
    """
    from world.currency.models import DistinctionPurseDrain  # noqa: PLC0415
    from world.distinctions.models import Distinction, DistinctionCategory  # noqa: PLC0415

    category, _ = DistinctionCategory.objects.get_or_create(
        slug="personality",
        defaults={
            "name": "Personality",
            "description": (
                "Distinctions rooted in a character's temperament, habits, and compulsions."
            ),
        },
    )
    distinction, _ = Distinction.objects.get_or_create(
        slug="somehow-always-broke",
        defaults={
            "name": "Somehow Always Broke",
            "category": category,
            "description": (
                "To the exasperation of all that know them, they somehow find a way to "
                "spend, waste or lose all money that finds a way into their possession, "
                "without fail. It could be for any number of reasons, from unfettered "
                "addictions to preposterous luck, but they will go broke again."
            ),
            "cost_per_rank": -50,
            "max_rank": 1,
        },
    )
    DistinctionPurseDrain.objects.get_or_create(
        distinction=distinction,
        defaults={"drain_percent": 100, "floor_coppers": 0},
    )
    return distinction


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
            # #2632 — basic chromatic dye colors (a magical world dyes freely;
            # each has a matching "<Color> Dye" bottle in world.seeds.styling).
            ("blue", "Blue"),
            ("green", "Green"),
            ("yellow", "Yellow"),
            ("violet", "Violet"),
            ("orange", "Orange"),
            # #2632 umbrella value: honest one-word form for multi-colored hair
            # (streaks, ornate dye work) — the descriptor carries the specifics;
            # under descriptor concealment a viewer still sees the true,
            # memorable fact ("multihued") without the detail.
            ("multihued", "Multihued"),
            # #2632 — magical shimmer, distinct from mundane multihued combos;
            # set by Prism's Dye ("blended with magical light").
            ("prismatic", "Prismatic"),
        ),
    ),
    (
        "hair_style",
        "Hair Style",
        FormTraitType.STYLE,
        True,
        (
            # PLACEHOLDER style list (#2632) — staff/content can extend freely.
            ("loose", "Loose"),
            ("braided", "Braided"),
            ("cropped", "Cropped"),
            ("swept_up", "Swept Up"),
            ("shaved", "Shaved"),
        ),
    ),
    (
        "eye_color",
        "Eye Color",
        FormTraitType.COLOR,
        # Cosmetic as of #2632 (ApostateCD ruling via the approved spec): eye
        # color has no mundane restyle path — the enchanted-lens ItemTemplate
        # is the gate, because the item IS the gate.
        True,
        (
            ("brown", "Brown"),
            ("blue", "Blue"),
            ("green", "Green"),
            ("gray", "Gray"),
            ("hazel", "Hazel"),
            # #2632 umbrella value: heterochromia — the descriptor names the
            # pair ("one blue, one amber"); the one-word form stays honest.
            ("mismatched", "Mismatched"),
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
