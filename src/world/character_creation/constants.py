"""Character creation constants.

TextChoices and IntegerChoices are placed here to avoid circular imports
and keep models.py focused on model definitions.
"""

from django.db import models

from world.traits.constants import PrimaryStat

# Primary stat constants (1-5 scale)
STAT_MIN_VALUE = 1  # Minimum stat value
STAT_MAX_VALUE = 5  # Maximum stat value during character creation
STAT_DEFAULT_VALUE = 2  # Default starting value

# Internal divisor for converting distinction effect values (stored as 10/20/etc.) to display scale
STAT_DISPLAY_DIVISOR = 10

# Age constraints for character creation
AGE_MIN = 18
AGE_MAX = 65

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
