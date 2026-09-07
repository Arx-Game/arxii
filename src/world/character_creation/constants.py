"""Character creation constants.

TextChoices and IntegerChoices are placed here to avoid circular imports
and keep models.py focused on model definitions.
"""

from django.db import models

# STAT_DISPLAY_DIVISOR's canonical definition lives in world.traits.constants (#2894);
# re-exported here for the CG modules that convert display allocations to internal scale.
from world.traits.constants import STAT_DISPLAY_DIVISOR, PrimaryStat  # noqa: F401

# Primary stat constants (1-5 DISPLAY scale — draft_data holds display values;
# finalization multiplies by STAT_DISPLAY_DIVISOR when writing CharacterTraitValue)
STAT_MIN_VALUE = 1  # Minimum stat value
STAT_MAX_VALUE = 5  # Maximum stat value during character creation
STAT_DEFAULT_VALUE = 2  # Default starting value

# Age constraints for character creation
AGE_MIN = 18
AGE_MAX = 65
# Eternal-youth species (elves, vampires) lock their apparent age in the
# early 20s — CG caps their age input here (#2756, PLACEHOLDER).
AGE_MAX_ETERNAL_YOUTH = 29

# Bounds for OriginTemplateSlotChoice.reputation_seed (#3660)
REPUTATION_SEED_MIN = -1000
REPUTATION_SEED_MAX = 1000

# Required primary stat names
REQUIRED_STATS = PrimaryStat.get_all_stat_names()

# CG technique pick budget (#2426): ModifierTarget/ModifierCategory names read by
# CharacterDraft.starting_technique_picks via _get_distinction_bonus(). The
# ModifierTarget row itself is seeded in Task 7 — these constants are the shared
# contract between this app and that seed data.
STARTING_TECHNIQUE_PICKS_TARGET = "starting_technique_picks"
CG_MODIFIER_CATEGORY = "character_creation"

# Canonical fallback starting room (#2121). Seeded by
# ``world.seeds.character_creation.ensure_canonical_fallback_room`` and wired onto
# the dev-seeded "Arx City" StartingArea's ``default_starting_room``. Also the
# last-resort read ``CharacterDraft.get_starting_room()`` falls back to when
# neither a Beginnings override nor a StartingArea default is set — so a freshly
# approved character never spawns with ``location=None``. Both the seeder and the
# runtime fallback key off this same (name, typeclass) pair so they always agree
# on the same room, regardless of which seed cluster ran first.
FALLBACK_STARTING_ROOM_KEY = "The Wanderer's Rest"
FALLBACK_STARTING_ROOM_TYPECLASS = "typeclasses.rooms.Room"

# Reserved RoomProfile.fixture_key for the canonical fallback room above (#2448),
# marking it AUTHORED so it is stable-identity and included in the grid export.
FALLBACK_STARTING_ROOM_FIXTURE_KEY = "arx/fallback-starting-room"

# Golden Hare CG entrance obligation (#2428): shared contract between the magic
# finalize hook (services.py's finalize_magic_data) and the Academy org seed
# (world.seeds.character_creation.ensure_shroudwatch_academy). Resolved by
# name at finalize time — the Academy is a deliberate NULL-tradition
# ``Organization`` (#2426 ruling), not a Tradition itself.
SHROUDWATCH_ACADEMY_NAME = "Shroudwatch Academy"

# Tradition identifying the tradition-agnostic default CG pick (#2426). Runtime
# code never matches a tradition by name as of #3675 (read ``BeginningTradition
# .state`` / ``world.character_creation.offers.tradition_is_self_taught`` instead).
# This constant survives only for the two callers that still need to name the
# "Unbound" row itself: ``world.seeds.character_creation`` (seeding the row plus
# its slate line) and migration ``0107_distinction_offers_data`` (the one-time
# backfill that stamps ``state`` on it before any state-based reader exists).
UNBOUND_TRADITION_NAME = "Unbound"

# Path of the Chosen name — mirrors the constant in worship_content.py so the
# CG finalize hook can match without importing the seed module (#2550).
PATH_OF_THE_CHOSEN_NAME = "Path of the Chosen"


class Stage(models.IntegerChoices):
    """Character creation stages."""

    ORIGIN = 1, "Origin"
    HERITAGE = 2, "Heritage"
    LINEAGE = 3, "Lineage"
    PATH = 5, "Path"
    GIFT = 6, "Gift"
    ATTRIBUTES = 7, "Attributes & Skills"
    APPEARANCE = 8, "Appearance"
    IDENTITY = 9, "Identity"
    FINAL_TOUCHES = 10, "Final Touches"
    REVIEW = 11, "Review"


class TraditionState(models.TextChoices):
    """How a tradition on a Beginning's slate reads at the tradition step (#3675).

    Decides which standard line the entry prints and which drawback, if any,
    picking it carries into the draft. Read by the tradition serializer, the
    offers module, the Golden Hare obligation and tradition membership; never
    matched by a tradition's name.
    """

    SELF_TAUGHT = "self_taught", "Self-taught"
    TEACHERS_GONE = "teachers_gone", "Teachers gone"
    LIVING_MASTERS = "living_masters", "Living masters"


class OfferChapter(models.TextChoices):
    """The CG chapter an offer line is shown in (#3675).

    Staff pick it on the Distinction Builder; read by
    ``world.character_creation.offers`` to decide which chapter shows the line.
    """

    TRADITION_STEP = "tradition_step", "Gift, tradition step"
    GLIMPSE = "glimpse", "Gift, the Glimpse"
    LINEAGE = "lineage", "Lineage"
    APPEARANCE = "appearance", "Appearance"
    IDENTITY = "identity", "Identity"


class OfferArrival(models.TextChoices):
    """How an offered distinction arrives in the draft (#3675).

    Staff pick it per offer; read by ``offers.reconcile_offer_picks`` to decide
    whether the pick is priced, free, or imposed.
    """

    CHOICE = "choice", "A choice, priced"
    BUNDLED = "bundled", "Bundled free with its opener"
    CARRIED = "carried", "Carried by its opener"


class StartingAreaAccessLevel(models.TextChoices):
    """Access levels for starting areas in character creation."""

    ALL = "all", "All Players"
    TRUST_REQUIRED = "trust_required", "Trust Required"
    STAFF_ONLY = "staff_only", "Staff Only"


class ApplicationStatus(models.TextChoices):
    """Status choices for draft applications."""

    SUBMITTED = "submitted", "Submitted"
    IN_REVIEW = "in_review", "In Review"
    REVISIONS_REQUESTED = "revisions_requested", "Revisions Requested"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"
    WITHDRAWN = "withdrawn", "Withdrawn"


class CommentType(models.TextChoices):
    """Types of application comments."""

    MESSAGE = "message", "Message"
    STATUS_CHANGE = "status_change", "Status Change"


class OriginStoryState(models.TextChoices):
    """Deferral/progress state of the guided origin story (#2478).

    Cache of truth — maintained by
    ``world.character_creation.services.origin_story``, never written directly.
    Mirrors ``GlimpseState`` (#2427).
    """

    NOT_STARTED = "not_started", "Not Started"
    SLOTS_ONLY = "slots_only", "Slots Only"
    COMPLETE = "complete", "Complete"


class FamilyPath(models.TextChoices):
    """How a character's family record relates to their Upbringing (#3617).

    ``ANY`` is only valid on ``OriginTemplateSlot.applies_to`` (the prompt shows on
    every path). A draft's chosen path is one of the other three.
    """

    ANY = "any", "Any path"
    CLAIMED = "claimed", "Claim a staff-authored family"
    NAMED = "named", "Name your own family"
    NONE = "none", "No family"


class QuestionKind(models.TextChoices):
    """What kind of thing an Upbringing prompt asks for (#3660).

    ``TEXT`` and ``PICK`` are the two shapes prompts already had (a write-in, a
    priced pick-list). ``GROUP`` links the answer to a real ``Organization`` (the
    prompt's anchor) and offers stances toward it; ``PERSON`` lets the player
    name someone of their own, optionally inside an earlier prompt's group.
    """

    TEXT = "text", "Write an answer"
    PICK = "pick", "Pick one answer"
    GROUP = "group", "Pick a group"
    PERSON = "person", "Name a person"


class ConnectionKind(models.TextChoices):
    """What the tie to the anchor was. A tag; nothing branches on it (#3660)."""

    RAISED_BY = "raised_by", "Raised by"
    TAUGHT_BY = "taught_by", "Taught by"
    SERVED = "served", "Served"
    SAILED_WITH = "sailed_with", "Sailed with"
    OWES = "owes", "Owes"
    SWORN_TO = "sworn_to", "Sworn to"
    HUNTED_BY = "hunted_by", "Hunted by"


class LifeStage(models.TextChoices):
    """When the tie was formed. A tag; orders the sheet's Origins panel (#3660)."""

    CHILDHOOD = "childhood", "Childhood"
    YOUTH = "youth", "Youth"
    AT_THE_GLIMPSE = "at_the_glimpse", "At the Glimpse"
    SINCE_THE_GLIMPSE = "since_the_glimpse", "Since the Glimpse"


class AnchorSource(models.TextChoices):
    """Which groups a GROUP prompt lets the player pick from (#3660).

    ``POOL``: every active, non-covert org matching ``anchor_org_type`` and/or
    ``anchor_society``. ``LISTED``: ``anchor_orgs``. ``SAME_AS``: the org answered on
    ``same_anchor_as``. ``SERVED_HOUSE``: ``CharacterDraft.served_house``.
    ``OWN_FAMILY``: the org rooted in ``CharacterDraft.family``.
    """

    POOL = "pool", "Every group of a type in a realm"
    LISTED = "listed", "Groups I name"
    SAME_AS = "same_as", "The same group as an earlier question"
    SERVED_HOUSE = "served_house", "The house the character's family served"
    OWN_FAMILY = "own_family", "The character's own family"
