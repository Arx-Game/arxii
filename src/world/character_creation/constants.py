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

# Tradition identifying the tradition-agnostic default CG pick (#2426). There is
# no boolean "is Unbound" field on ``Tradition`` — every existing caller (the
# magic seed, ``seed_beginning_traditions`` above) matches by name, so the
# finalize hook does the same rather than inventing a new marker.
UNBOUND_TRADITION_NAME = "Unbound"

# Path of the Chosen name — mirrors the constant in worship_content.py so the
# CG finalize hook can match without importing the seed module (#2550).
PATH_OF_THE_CHOSEN_NAME = "Path of the Chosen"

# Slug of the "Unbound" drawback Distinction (#2442) — seeded by
# ``world.seeds.character_creation.ensure_unbound_drawback_distinction`` and
# wired onto Unbound's own ``BeginningTradition.required_distinction`` (same
# seeder, ``seed_beginning_traditions``). Read by ``select_tradition``
# (views.py) to special-case Unbound's auto-add UX: unlike Orphaned Tradition
# (a deliberate opt-in pick, #2428 Task 5), Unbound is CG's tradition-agnostic
# default — a player must not be forced to already know about this specific
# drawback before CG can complete (see
# ``world.seeds.tests.test_playable_slice.TestSeededCharacterCreation
# .test_tradition_step_completable_for_every_seeded_beginning``, the existing
# "CG must remain completable via the Unbound path with zero manual steps"
# regression proof #2426 shipped).
UNBOUND_DRAWBACK_DISTINCTION_SLUG = "unbound"


class Stage(models.IntegerChoices):
    """Character creation stages."""

    ORIGIN = 1, "Origin"
    HERITAGE = 2, "Heritage"
    LINEAGE = 3, "Lineage"
    DISTINCTIONS = 4, "Distinctions"
    PATH = 5, "Path"
    GIFT = 6, "Gift"
    ATTRIBUTES = 7, "Attributes & Skills"
    APPEARANCE = 8, "Appearance"
    IDENTITY = 9, "Identity"
    FINAL_TOUCHES = 10, "Final Touches"
    REVIEW = 11, "Review"


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


# ---------------------------------------------------------------------------
# The Actor's Sheet and the priced enemy (#3621)
# ---------------------------------------------------------------------------

# The realm whose starts are offered the First Journal at character generation; anyone
# else writes one at the Great Archive in play (a later verb).
ARX_REALM_NAME = "Arx"

# CG points awarded for carrying an enemy, by scale x degree. PLACEHOLDER numbers: 1 at
# the bottom corner (a Quiescent person who wants you annoyed), 150 at the top (a realm
# that will relentlessly try to destroy you), tuned by hand from the demo. Keyed by the
# societies.EnemyReach / character_sheets.EnemyPowerTier / EnemyDegree values.
ENEMY_PRICE_GROUP: dict[str, dict[str, int]] = {
    "household": {"annoyed": 3, "thwarted": 6, "ruined": 12, "destroy": 18},
    "house": {"annoyed": 8, "thwarted": 16, "ruined": 32, "destroy": 48},
    "society": {"annoyed": 15, "thwarted": 30, "ruined": 60, "destroy": 90},
    "realm": {"annoyed": 25, "thwarted": 50, "ruined": 100, "destroy": 150},
}
ENEMY_PRICE_PERSON: dict[str, dict[str, int]] = {
    "quiescent": {"annoyed": 1, "thwarted": 2, "ruined": 4, "destroy": 6},
    "prospect": {"annoyed": 2, "thwarted": 4, "ruined": 8, "destroy": 12},
    "potential": {"annoyed": 4, "thwarted": 8, "ruined": 16, "destroy": 24},
    "puissant": {"annoyed": 8, "thwarted": 16, "ruined": 32, "destroy": 48},
    "true": {"annoyed": 15, "thwarted": 30, "ruined": 60, "destroy": 90},
    "grand": {"annoyed": 15, "thwarted": 30, "ruined": 60, "destroy": 90},
}
# A free-written enemy nobody has placed yet is worth this until staff link it.
ENEMY_PRICE_PENDING = 1

# The worst two degrees mark the character with a Distinction, the way a Lineage answer
# can (#3660). Resolved by name at finalize; PLACEHOLDER names, authored rows. A missing
# row is logged and skipped, never invented.
ENEMY_DEGREE_DISTINCTION_NAMES: dict[str, str] = {
    "ruined": "Marked",
    "destroy": "Hunted",
}
# What the group thinks of the character at finalize, by degree (OrganizationReputation
# delta through bump_organization_reputation, the same seam as a Lineage answer's seed).
ENEMY_REPUTATION_SEED: dict[str, int] = {
    "annoyed": -100,
    "thwarted": -250,
    "ruined": -500,
    "destroy": -1000,
}
# Pursuit heat seeded where the character starts, when the enemy is a society or a realm
# whose enforcing society covers that start, from ruined upward. PLACEHOLDER magnitudes.
ENEMY_HEAT_SEED: dict[str, int] = {"ruined": 20, "destroy": 60}
ENEMY_HEAT_PIN_DAYS = 30  # at destroy the heat is pinned (decay-exempt) this long

# Each Whispers line is a Level-1 secret with this much gossip heat in the start region,
# so it is overhearable at a hub from day one (GOSSIP_DECAY_FLOOR is 1; public at 40).
WHISPERS_SEED_HEAT = 5

# The three questions of the Actor's Sheet, in order: (draft_data key, copy key stem).
# The wording lives in CG copy (CG_EXPLANATION_COPY / CGExplanation rows); the set is fixed.
ACTOR_SHEET_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("never_do", "finaltouches_never_do"),
    ("protect", "finaltouches_protect"),
    ("fear", "finaltouches_fear"),
)

# The Introductions (#3621): three white journals in the character's own voice. Frames and
# questions are world-level copy; the defaults here seed CG_EXPLANATION_COPY and are the
# finalize fallback when a copy row is missing. Wording is the reviewer's own.
INTRODUCTION_FIRST_JOURNAL = "first_journal"
INTRODUCTION_APPLICATION = "application"
INTRODUCTION_WHISPERS = "whispers"
INTRODUCTIONS_INTRO = (
    "These are optional IC introductions that can be answered IC as another way to help "
    "flesh out a character in their past. The First Journal is a white journal in the "
    "Great Archive, and would be a reference point to any other character that reads "
    "someone's profile inside the Archive. Each of these count as journals mechanically, "
    "and award xp for writing them."
)
FIRST_JOURNAL_INSTITUTION = "The Great Archive of Vellichor"
FIRST_JOURNAL_FRAME = (
    "The Great Archive strives to collect the stories of everyone that ever lived, and to "
    "record the journey of those on their Durance. In the First Journal, one responds to "
    "three questions in any manner they desire."
)
FIRST_JOURNAL_QUESTIONS: tuple[str, ...] = (
    "What should the world know of you first?",
    "What is a day that made you who you are?",
    "What do you think of the City of Arx?",
)
APPLICATION_TITLE = "An Application to Shroudwatch Academy"
APPLICATION_FRAME = (
    "All throughout the continent of Catenys, all who have their Glimpse and many who just "
    "hope for it perform a ritual to write an application to Shroudwatch Academy, burn it, "
    "and hope one day to receive word. Alarmingly, some people receive answers to "
    "applications they never recall writing at all, even if it seems exactly what they "
    "might have written."
)
APPLICATION_QUESTIONS: tuple[str, ...] = (
    "What dost thou hope to become?",
    "What are thy talents?",
    "What drives thee to distraction?",
)
WHISPERS_TITLE = "The Whispers - Rumors of Deeds and Misdeeds"
WHISPERS_FRAME = (
    "Rumors of note about the character, and what they consider vile slander and what "
    "might be pleasant hyperbole."
)
