"""Idempotent CG-world content seeder (#1333).

Promotes the character-creation "world" content currently living ad-hoc in
``FinalizationTestMixin._setup_finalization_base`` into shared, production-callable
seed rows — the content a fresh DB needs to actually run ``finalize_character``.
Create-if-missing; never overwrites; never deletes (the #651 invariant).

Child of #651 / epic #1220 (Phase A). Registered in ``CLUSTER_SEEDERS`` after
``magic`` because ``finalize_character`` picks the magic-seeded selectable
``Cantrip`` + ``Resonance``/``TechniqueStyle`` at finalize time — NOT because
``Beginnings`` FKs into magic (it FKs ``starting_area`` -> ``Realm`` and an M2M
``allowed_species`` -> ``Species``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from world.character_creation.constants import (
    FALLBACK_STARTING_ROOM_KEY,
    FALLBACK_STARTING_ROOM_TYPECLASS,
)
from world.character_creation.models import Beginnings, StartingArea
from world.character_sheets.models import Gender
from world.classes.models import Path, PathStage
from world.forms.models import Build, HeightBand
from world.realms.models import Realm
from world.roster.models import Roster
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.models import Trait, TraitType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

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


def ensure_canonical_fallback_room() -> ObjectDB:
    """Get-or-create the canonical fallback starting Room (#2121).

    Lazy-created via ``evennia_create.create_object`` the same way the magic
    cluster's cascade rooms are (``world/seeds/game_content/magic.py``) —
    ``ObjectDB.db_key`` is not unique in Evennia, so lookup uses
    ``filter().first()`` for idempotency. Callable independently of cluster
    order: any seeder needing "the" canonical starting room (character_creation,
    missions, progression) calls this and gets the same row back.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    existing = ObjectDB.objects.filter(
        db_key=FALLBACK_STARTING_ROOM_KEY,
        db_typeclass_path=FALLBACK_STARTING_ROOM_TYPECLASS,
    ).first()
    if existing is not None:
        return existing
    return evennia_create.create_object(
        typeclass=FALLBACK_STARTING_ROOM_TYPECLASS,
        key=FALLBACK_STARTING_ROOM_KEY,
        nohome=True,
    )


def seed_character_creation_dev() -> None:
    """Seed the CG-world content a fresh DB needs to run character creation.

    Idempotent: every write is ``get_or_create`` (or idempotent M2M ``add``);
    safe to re-run; never overwrites an edited row.
    """
    realm, _ = Realm.objects.get_or_create(
        name="Arx",
        defaults={"description": "The default realm.", "crest_asset": "", "theme": ""},
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
    # #2121 — every seeded StartingArea must resolve to a real room (never a
    # silent None spawn). Never overwrite an already-wired room (staff edit).
    if area.default_starting_room_id is None:
        area.default_starting_room = ensure_canonical_fallback_room()
        area.save(update_fields=["default_starting_room"])
    species, _ = Species.objects.get_or_create(
        name="Human",
        defaults={"description": "The default species.", "sort_order": 0},
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
    beginnings.allowed_species.add(species)  # M2M add is idempotent
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
