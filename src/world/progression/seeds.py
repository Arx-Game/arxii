"""Idempotent deploy/test-DB seeds for the progression app.

Invoked by `tools/build_schema.py` (and callable at deploy time) in place of
a former RunPython seed migration — migrations are ephemeral pre-production
and must contain no data seeding (ADR-0013).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.progression.models import ClassLevelUnlock


def seed_social_engagement_kudos_category() -> None:
    """Seed the social_engagement KudosSourceCategory.

    Used by SceneActionRequest accepts. Fresh deploys need this row to exist
    before any scene-action-accept flow runs. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    KudosSourceCategory.objects.update_or_create(
        name="social_engagement",
        defaults={
            "display_name": "Social Engagement",
            "description": "Awarded for accepting another character's scene action request.",
            "default_amount": 1,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_pose_kudos_category() -> None:
    """Seed the pose_kudos KudosSourceCategory (#2026).

    ``world.progression.reaction_kinds._get_pose_kudos_category`` self-heals via
    ``get_or_create`` the first time anyone acclaims a pose, but that means the row
    (and its default_amount) simply doesn't exist until the first acclaim ever
    happens — nothing surfaces it up front (e.g. to admin/game-ops tooling that
    lists categories before any award has fired). Values mirror that helper's
    defaults exactly. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    KudosSourceCategory.objects.update_or_create(
        name="pose_kudos",
        defaults={
            "display_name": "Pose Kudos",
            "description": "A player acclaimed one of your poses.",
            "default_amount": 1,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_spread_assist_kudos_category() -> None:
    """Seed the spread_assist KudosSourceCategory (#2026).

    ``world.societies.reaction_kinds._get_spread_assist_kudos_category`` self-heals
    via ``get_or_create`` at scene-close settlement. Values mirror that helper's
    defaults exactly. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    KudosSourceCategory.objects.update_or_create(
        name="spread_assist",
        defaults={
            "display_name": "Telling Acclaim",
            "description": "You acclaimed a tale someone told, helping it spread.",
            "default_amount": 1,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_relationship_writeup_kudos_category() -> None:
    """Seed the relationship_writeup KudosSourceCategory (#2026).

    ``world.relationships.services.give_writeup_kudos`` does a plain ``.get()`` on
    this category (no self-heal) — when it's missing, the commendation row is still
    recorded but no kudos are awarded (silent no-op, only a warning log). Name and
    amount must match ``RELATIONSHIP_WRITEUP_KUDOS_CATEGORY`` / ``WRITEUP_KUDOS_AMOUNT``
    in ``world.relationships.constants`` exactly. Idempotent via update_or_create.
    """
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415
    from world.relationships.constants import (  # noqa: PLC0415
        RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
        WRITEUP_KUDOS_AMOUNT,
    )

    KudosSourceCategory.objects.update_or_create(
        name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
        defaults={
            "display_name": "Writeup Commended",
            "description": (
                "Another character commended a relationship writeup written about them."
            ),
            "default_amount": WRITEUP_KUDOS_AMOUNT,
            "is_active": True,
            "staff_only": False,
        },
    )


def seed_xp_kudos_claim_category() -> None:
    """Seed the 'xp' KudosClaimCategory — convert kudos to account XP (#2026).

    Without at least one active ``KudosClaimCategory`` row, ``ClaimKudosAction`` /
    ``claim_kudos_for_xp`` have nothing to claim against and the claim UI (web +
    telnet ``kudos``) is dead on a fresh DB. Rate mirrors the shape already
    exercised in ``world.progression.tests.test_kudos``
    (``KudosClaimCategoryFactory(kudos_cost=10, reward_amount=5)``): 10 kudos ->
    5 XP, a meaningful-but-not-trivial conversion given the reaction kinds above
    grant 1 kudos per acclaim. Idempotent via update_or_create.
    """
    from world.progression.models import KudosClaimCategory  # noqa: PLC0415

    KudosClaimCategory.objects.update_or_create(
        name="xp",
        defaults={
            "display_name": "Convert to XP",
            "description": "Convert kudos points to experience points.",
            "kudos_cost": 10,
            "reward_amount": 5,
            "is_active": True,
        },
    )


def seed_kudos_content() -> None:
    """Seed every kudos source/claim category the kudos economy needs (#2026).

    Without this, ``grant_social_engagement_kudos`` (weekly good-sport grant) and
    ``give_writeup_kudos`` (relationship-writeup commend) both silently no-op on a
    fresh DB — their category lookups raise ``DoesNotExist``, caught and logged as
    a warning rather than awarding anything — and the kudos-claim UI has no
    ``KudosClaimCategory`` to offer. Registered as the "kudos" cluster in
    ``world.seeds.clusters``.
    """
    seed_social_engagement_kudos_category()
    seed_pose_kudos_category()
    seed_spread_assist_kudos_category()
    seed_relationship_writeup_kudos_category()
    seed_xp_kudos_claim_category()


# --- Durance officiant bootstrap (#2121) -----------------------------------

#: PLACEHOLDER class stamped on every seeded Durance training officiant.
#: assert_can_officiate never reads CharacterClass — only current_level (any
#: class) and Path lineage — so one shared class suffices for all 5.
_DURANCE_OFFICIANT_CLASS_NAME = "Adventurer"
#: Comfortably above the only within-PROSPECT-stage Durance target (level 2 —
#: PROSPECT covers levels 1-2; level 3 crosses to POTENTIAL via Audere Majora,
#: not the Durance). assert_can_officiate only requires officiant > target.
_DURANCE_OFFICIANT_LEVEL = 5

#: The 5 CG-selectable PROSPECT paths — real lore-repo content, loaded via
#: load_world_content() (formerly seeded in-repo by the now-retired
#: world.seeds.game_content.magic.seed_starter_gift_catalog, #2426/#2474). One
#: officiant per path — see world/progression/CLAUDE.md's PROSPECT/style mapping.
_DURANCE_OFFICIANT_PATH_NAMES: tuple[str, ...] = (
    "Path of Steel",
    "Path of Whispers",
    "Path of Voice",
    "Path of the Chosen",
    "Path of Tomes",
)

_OFFICIANT_TYPECLASS = "typeclasses.characters.Character"


def seed_durance_officiants() -> list:
    """Seed one NPC officiant + DuranceTrainingSite per PROSPECT path (#2121).

    Without this, no character can ever take the first-ever Ritual of the
    Durance: ``assert_can_officiate`` (``services/advancement.py``) requires a
    same-path-lineage officiant strictly above the inductee's target level,
    and none exists on a fresh DB — ``durance convene`` always raises
    ``NoDuranceSiteError``. Each officiant is a non-CG NPC built via
    ``create_character_with_sheet`` (the same non-CG creation path NPCAsset
    promotion uses, ``world/assets/effects.py``) — not a full CG run — placed
    at the canonical fallback starting room (``ensure_canonical_fallback_room``,
    #2121) so a freshly finalized character can always reach one.

    Idempotent and staff-edit-preserving: officiants are looked up by a
    stable ``ObjectDB.db_key`` (mirrors the cascade-room lookup pattern —
    ``db_key`` is not unique in Evennia, so ``.filter().first()``). The
    officiant's class level and path history are written ONLY at first
    creation (never re-clobbered on a later run, unlike a tuning-knob
    singleton) — a staff-adjusted officiant level survives re-seeding. The
    ``CharacterClass``/``DuranceTrainingSite`` rows are ordinary
    ``get_or_create``.

    Skips a path silently if it hasn't been loaded yet — content-repo load
    running before any cluster seeder (#2474 Decision 5) guarantees this can't
    happen via the Big Button; defensive only.

    Returns:
        The list of DuranceTrainingSite rows (created or fetched), one per
        successfully-resolved PROSPECT path.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.areas.services import get_room_profile  # noqa: PLC0415
    from world.character_sheets.services import create_character_with_sheet  # noqa: PLC0415
    from world.classes.models import CharacterClass, Path  # noqa: PLC0415
    from world.classes.services import set_primary_class_level  # noqa: PLC0415
    from world.progression.models import CharacterPathHistory, DuranceTrainingSite  # noqa: PLC0415
    from world.seeds.character_creation import ensure_canonical_fallback_room  # noqa: PLC0415

    room = ensure_canonical_fallback_room()
    room_profile = get_room_profile(room)
    officiant_class, _ = CharacterClass.objects.get_or_create(
        name=_DURANCE_OFFICIANT_CLASS_NAME,
        defaults={
            "description": "PLACEHOLDER class stamped on seeded Durance training officiants.",
        },
    )

    sites: list[DuranceTrainingSite] = []
    for path_name in _DURANCE_OFFICIANT_PATH_NAMES:
        try:
            path = Path.objects.get(name=path_name)
        except Path.DoesNotExist:
            continue

        officiant_key = f"{path_name} Trainer"
        character = ObjectDB.objects.filter(
            db_key=officiant_key, db_typeclass_path=_OFFICIANT_TYPECLASS
        ).first()
        is_new = character is None
        if is_new:
            character, _sheet, _persona = create_character_with_sheet(
                character_key=officiant_key,
                primary_persona_name=officiant_key,
                home=room,
            )
            character.location = room
            character.save()
            set_primary_class_level(character, officiant_class, _DURANCE_OFFICIANT_LEVEL)
            CharacterPathHistory.objects.create(character=character.sheet_data, path=path)

        sheet = character.sheet_data
        site, _ = DuranceTrainingSite.objects.get_or_create(
            room_profile=room_profile,
            officiant=sheet,
            defaults={"training_path": path, "is_active": True},
        )
        sites.append(site)

    return sites


# --- Level-2 major-gift-technique gate (#2440 ruling 4) --------------------

#: N in "knows >= N techniques of your major gift" — matches CG's upper end
#: (1 + Tradition Training rank of starter picks; see MajorGiftTechniqueRequirement's
#: docstring for the full rationale).
_MAJOR_GIFT_TECHNIQUE_LEVEL_REQUIREMENT_COUNT = 3


def seed_major_gift_technique_level_requirement() -> ClassLevelUnlock:
    """Seed the level-2 ClassLevelUnlock + its MajorGiftTechniqueRequirement (#2440 ruling 4).

    Level 2 requires knowing >= 3 techniques of the character's MAJOR gift —
    CG hands out only 1-3 starter picks from the (Path x Gift) pool; the rest
    are meant to be filled out in play via Academy/Archive TRAIN offers before
    crossing to level 2. No ``ClassLevelUnlock`` row exists for any
    (class, level) pair anywhere in the codebase yet (verified against code —
    this content is staff/admin-authored, never seeded) — this is the first.

    Reuses the same PLACEHOLDER ``_DURANCE_OFFICIANT_CLASS_NAME`` ("Adventurer")
    class ``seed_durance_officiants`` stamps on its officiants: per that
    function's own docstring, ``assert_can_officiate`` and the Durance gate
    read ``current_level``/Path lineage, never a specific ``CharacterClass``
    name, so the same one shared class is the correct generic anchor for the
    level-2 gate too. Idempotent via get_or_create; never overwrites a
    staff-adjusted row (an existing ``MajorGiftTechniqueRequirement`` for this
    unlock is left untouched, including a staff-retuned ``minimum_techniques``).

    Returns:
        The level-2 ``ClassLevelUnlock`` (created or fetched).
    """
    from world.classes.models import CharacterClass  # noqa: PLC0415
    from world.progression.models import (  # noqa: PLC0415
        ClassLevelUnlock,
        MajorGiftTechniqueRequirement,
    )

    character_class, _ = CharacterClass.objects.get_or_create(
        name=_DURANCE_OFFICIANT_CLASS_NAME,
        defaults={
            "description": "PLACEHOLDER class stamped on seeded Durance training officiants.",
        },
    )
    unlock, _ = ClassLevelUnlock.objects.get_or_create(
        character_class=character_class, target_level=2
    )
    MajorGiftTechniqueRequirement.objects.get_or_create(
        class_level_unlock=unlock,
        defaults={
            "minimum_techniques": _MAJOR_GIFT_TECHNIQUE_LEVEL_REQUIREMENT_COUNT,
            "description": "Know at least 3 techniques of your major gift.",
            "is_active": True,
        },
    )
    return unlock
