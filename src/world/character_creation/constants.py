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
# Magic training points (slice 2 of #4659): the pool a draft spends on Magic skills,
# read by CharacterDraft.magic_training_pool via the same distinction-bonus seam.
MAGIC_TRAINING_POINTS_TARGET = "magic_training_points"

# Canonical fallback starting room (#2121). Seeded by
# ``world.seeds.character_creation.ensure_canonical_fallback_room`` and wired onto
# the dev-seeded "Arx City" StartingArea's ``default_starting_room``. Also the
# last-resort read ``CharacterDraft.get_starting_room()`` falls back to when
# neither a Beginnings override nor a StartingArea default is set, and where
# ``Character.at_pre_puppet`` lands a character with no location and no home —
# so nobody ever plays with ``location=None``. Every reader goes through
# ``character_creation.services.resolve_fallback_starting_room`` (#3818), which
# finds the room by ``FALLBACK_STARTING_ROOM_FIXTURE_KEY`` first: staff rename
# this room (it is "City Center" on production), and this name is only the
# seed-time key and the last-resort match for a room seeded before the fixture
# key existed.
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
# its slate line) and migration ``0110_distinction_offers_data`` (the one-time
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


#: The highest schooling stance rank each tradition state opens (#4457 Decision 1). A
#: living tradition offers ranks 0 to 2; an orphaned one (teachers gone) offers 0 and 1,
#: since its teachers were lost before anyone could finish; a self-taught entry opens
#: none. A game rule the maintainers ruled, not tuning; #4536 replaces this when the
#: training level becomes a fact of its own.
SCHOOLING_MAX_RANK_BY_STATE: dict[TraditionState, int] = {
    TraditionState.LIVING_MASTERS: 2,
    TraditionState.TEACHERS_GONE: 1,
}


def schooling_max_rank(state: str) -> int | None:
    """The highest schooling stance rank ``state`` opens, or None when it opens none.

    Called by the offers module (which Tradition Training offers a draft sees)
    and the tradition serializer (which stances are drawn).
    """
    return SCHOOLING_MAX_RANK_BY_STATE.get(TraditionState(state))


#: What the skills step says when skill points sit in a Magic skill or one of its
#: specializations (#4457 Decision 4); the names follow it.
MAGIC_SKILL_POINTS_REFUSAL = "Magic skills come from your Tradition training, not skill points: "


class OfferChapter(models.TextChoices):
    """The CG chapter an offer line is shown in (#3675).

    Staff pick it on the Distinction Builder; read by
    ``world.character_creation.offers`` to decide which chapter shows the line.
    """

    TRADITION_STEP = "tradition_step", "Gift, tradition step"
    GLIMPSE = "glimpse", "Gift, the Glimpse"
    LINEAGE = "lineage", "Lineage"
    APPEARANCE = "appearance", "Appearance"
    ACTORS_SHEET = "actors_sheet", "The actor's sheet"
    ENEMY = "enemy", "Who wants you to fail"
    #: #4124: the beats of a life. Every answer on a beat is one of these lines,
    #: opened by the beat and priced at the distinction's own cost.
    BACKGROUNDS = "backgrounds", "Backgrounds, a beat"
    #: #4846 (slice 5 of #4813): a line a held card unlocks at Final Touches, opened by
    #: ``DistinctionOffer.unlocked_by``; the chapter shows nothing to a draft that holds
    #: no unlocking card.
    FINAL_TOUCHES = "final_touches", "Final Touches, a card"


class FinalTouchesPrompt(models.TextChoices):
    """The optional question a card asks at Final Touches (#4846, slice 5 of #4813).

    Staff set it per card (``Distinction.final_touches_prompt``) on the Distinction Builder
    for a prompt with no sidecar behind it; a grant sidecar raises its own prompt
    (#4852, slice 6 of #4813: a prestige grant asks ``PRESTIGE_STORY``, an organization
    grant with no fixed organization asks ``ORGANIZATION``, a path aspect grant shows
    ``PATH_ASPECT``). ``offers.final_touches_prompts`` collects both for the cards a draft
    holds, ``offers.final_touches_cards`` names the card behind each, and the leaf asks
    each one. A prompt is answerable or skippable, never required (the chapter rule of
    2026-10-29).
    """

    CRIME = "crime", "Name the crime (Jailbird)"
    #: What people say happened: the story behind a starting prestige, kept as the pick's
    #: notes. Raised by ``societies.DistinctionPrestigeGrant``, never set by staff.
    PRESTIGE_STORY = "prestige_story", "What people say happened (a prestige grant)"
    #: Which of the realm's admitting organizations the card seats the character in.
    #: Raised by ``societies.DistinctionOrganizationGrant`` with no fixed organization.
    ORGANIZATION = "organization", "The organization that takes you in (an organization grant)"
    #: Nothing to answer: the line naming the Path's stronger Aspect the bonus lands on.
    #: Raised by ``classes.DistinctionPathAspectGrant``.
    PATH_ASPECT = "path_aspect", "Your Path's stronger Aspect (a path aspect grant)"
    #: The Officially dead door (#4396): the face the world meets while the true one is
    #: believed dead. Raised by a worn ``scenes.DistinctionPersonaGrant`` (Presumed Dead, #4856);
    #: the door shows to no other draft.
    OFFICIALLY_DEAD = "officially_dead", "The face the world meets (a worn persona grant)"
    #: A second face the character is not wearing. Raised by a hidden persona grant (Shady
    #: Alter Ego, #4856); answered in ``draft_data.alter_ego`` with the door's shape.
    ALTER_EGO = "alter_ego", "A second face (a hidden persona grant)"
    #: A membership at the entry rank or starting renown with one of the realm's admitting
    #: organizations of the card's kind. Raised by ``societies.DistinctionOrganizationTie``.
    TIE = "tie", "A tie with an organization (an organization tie)"


#: The prompts a grant sidecar raises on its own (#4852, #4856); the rest come from
#: ``Distinction.final_touches_prompt``.
GRANT_RAISED_PROMPTS: tuple[str, ...] = (
    FinalTouchesPrompt.PRESTIGE_STORY,
    FinalTouchesPrompt.ORGANIZATION,
    FinalTouchesPrompt.PATH_ASPECT,
    FinalTouchesPrompt.OFFICIALLY_DEAD,
    FinalTouchesPrompt.ALTER_EGO,
    FinalTouchesPrompt.TIE,
)


class TieKind(models.TextChoices):
    """What a card's organization tie takes at finalize (#4856, slice 6 of #4813): a seat on
    the bottom rung through ``join_organization``, or renown at the Favored tier's floor
    through ``bump_organization_reputation``. The player's choice, free. A third shape ("a
    tie" in the plan's copy table) has no row ruled for it yet and is not here."""

    MEMBERSHIP = "membership", "A place at the bottom rung"
    RENOWN = "renown", "A name they already know"


class ActorSheetPrompt(models.TextChoices):
    """The question an actor's-sheet offer hangs off (#3709).

    The opener for ``OfferChapter.ACTORS_SHEET``: staff pick it per offer line on the
    Distinction Builder; ``offers.offers_for`` groups the chapter's lines by it so the
    leaf mounts one block under each question. Values are ``ACTOR_SHEET_QUESTIONS``'
    draft_data keys, so the two never drift.
    """

    NEVER_DO = "never_do", "What would you never do?"
    PROTECT = "protect", "What would you protect at all costs?"
    FEAR = "fear", "What are you deathly afraid of?"


class EnemyReasonFits(models.TextChoices):
    """Which enemy kinds an ``EnemyReason`` is offered for (#3709).

    Staff set it per reason; the leaf filters the shared list by the draft's pick.
    """

    PERSON = "person", "A person"
    GROUP = "group", "A group"
    EITHER = "either", "Either"


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


class Parentage(models.TextChoices):
    """Who raised a character with this Upbringing, and how CG frames it (#4024).

    ``UNKNOWN`` (the Misbegotten raised in the Cradle) offers no family and records
    no parents; the tarot ritual gives the surname. ``ADOPTIVE`` offers a family
    framed as adoptive: parent links are ADOPTIVE and the membership is ADOPTED, so
    the name display wears the family's taken-in particle (#3261).
    """

    KNOWN = "known", "Known parents"
    UNKNOWN = "unknown", "No known parents"
    ADOPTIVE = "adoptive", "Adoptive parents"


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


class KinRowKind(models.TextChoices):
    """A person the player seats in the Lineage step beside the parents (#4395).

    The rows live at ``draft_data["kin_rows"]`` until finalize writes them into the
    kinship graph (``services._bind_kin_rows``): a twin shares the character's parents,
    a spouse is a marriage union, a child a parentage edge from the character.
    """

    TWIN = "twin", "A twin"
    SPOUSE = "spouse", "A spouse"
    CHILD = "child", "A child"
    #: A promise of marriage, not yet one (#4870, slice 8 of #4813): a union of the
    #: betrothal kind (``UnionKind.is_betrothal``).
    BETROTHED = "betrothed", "A betrothed"


class SpouseFate(models.TextChoices):
    """What became of a spouse seated at creation (#4395; separated and the missing
    relabel, #4870)."""

    ALIVE = "alive", "Alive"
    DEAD = "dead", "Dead"
    DIVORCED = "divorced", "Divorced"
    #: Living apart, the union standing in law (``Union.separated_at``).
    SEPARATED = "separated", "Separated"
    #: Gone without a word; the value keeps its first name, the word is "missing".
    FLED = "fled", "Missing"


class ChildFate(models.TextChoices):
    """What became of a child seated at creation (#4395)."""

    RAISED = "raised", "Raised"
    FOSTERED_AWAY = "fostered_away", "Fostered away"
    LOST = "lost", "Lost"


class TwinFate(models.TextChoices):
    """What became of a twin seated at creation (#4870)."""

    ALIVE = "alive", "Alive"
    DEAD = "dead", "Dead"


class BetrothedFate(models.TextChoices):
    """What became of a betrothed seated at creation (#4870): the promise stands, the person
    is dead or missing, or the match was called off (the union ended)."""

    PROMISED = "promised", "Promised"
    DEAD = "dead", "Dead"
    MISSING = "missing", "Missing"
    BROKEN = "broken", "Broken off"


class ParentFate(models.TextChoices):
    """What became of a parent the player names (#4870): where every "a parent died or
    vanished" story lives instead of a card. On the named parents only; a claimed family's
    staff-authored parents are not touched."""

    ALIVE = "alive", "Alive"
    DEAD = "dead", "Dead"
    MISSING = "missing", "Missing"


#: ``draft_data`` keys for the named parents' fates (#4870), beside ``line_parent_name`` and
#: ``other_parent_name``; blank or alive is alive.
LINE_PARENT_FATE_KEY = "line_parent_fate"
OTHER_PARENT_FATE_KEY = "other_parent_fate"


#: ``draft_data`` key for the seated kin rows (#4395), and the most a draft may seat.
KIN_ROWS_KEY = "kin_rows"
KIN_ROWS_MAX = 8
KIN_ROW_NAME_MAX_LENGTH = 100


class LifeStage(models.TextChoices):
    """When the tie was formed, and which stage of a life a beat belongs to (#3660, #4124).

    A tag on an Upbringing prompt; the stage a ``LifeBeat`` is pooled under on the
    Lineage page and grouped by on the sheet. ``ADULTHOOD`` is the years before the
    Glimpse that most of the roster has lived through, which no tie-tag needed.
    """

    CHILDHOOD = "childhood", "Childhood"
    YOUTH = "youth", "Youth"
    ADULTHOOD = "adulthood", "Before the Glimpse"
    AT_THE_GLIMPSE = "at_the_glimpse", "At the Glimpse"
    SINCE_THE_GLIMPSE = "since_the_glimpse", "Since the Glimpse"


#: The one optional line a player may write under a taken beat (#4124).
BEAT_LINE_MAX_LENGTH = 200
#: The optional Recent History a life ends on (#4830, ruled 2026-10-30 and 2026-10-31): free
#: text the player writes for the hooks GMs and other players may pick up, public on the sheet,
#: written at finalize as the lead-in paragraph of ``Profile.background``.
RECENT_HISTORY_MAX_LENGTH = 2000


#: The age rule for a beat whose picks scale with age (#4395, re-ruled #4829): one career
#: point at or under ``AGE_PICKS_FROM_AGE``, one more for every ``AGE_PICKS_YEARS_PER_PICK``
#: full years lived past it, and no more past ``AGE_PICKS_CAP_AGE``. Nineteen is one point,
#: twenty-four two, fifty seven, fifty-nine and older nine. A point buys a Past Career or a
#: rank on one (the beat counts ranks, not cards). The rule is ``offers.age_pick_allowance``;
#: these three numbers are the whole of it.
AGE_PICKS_FROM_AGE = 19
AGE_PICKS_YEARS_PER_PICK = 5
AGE_PICKS_CAP_AGE = 59


class BeatSelection(models.TextChoices):
    """How many of a beat's answers may be taken (#4124).

    Staff set it per beat. ``ONE_OF`` draws the answers across and the distinctions
    sync refuses a second pick on the same beat; ``ANY`` draws them down and any
    number may be taken. "Neither" is implicit in both: a taken beat with no pick.
    """

    ONE_OF = "one_of", "One of"
    ANY = "any", "Any that apply"


class BeatMode(models.TextChoices):
    """How a Beginning offers the beat library (#4124).

    ``POOL``: every library beat not excluded for this Beginning, taken by the player as
    the life had them. ``ONE_KEPT`` (the one unexcluded beat was the whole stage, the
    Sleeper's) was retired in #4830: the Sleeper strikes every stage instead and shows
    its ``struck_stages_text``, so no beginning kept a beat. The field stays for the
    next mode a beginning may need.
    """

    POOL = "pool", "A pool to add from"


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
# can (#3660): authored as ``DistinctionOffer`` lines on ``OfferChapter.ENEMY`` opened by
# ``enemy_degree`` (#3709), never named in code. Only these degrees may open one.
ENEMY_MARKING_DEGREES: tuple[str, ...] = ("ruined", "destroy")
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

# Officially dead (#4396): the world believes the character's true face dead, and the face
# it meets instead is an established persona with its own guise bio. The draft_data entry
# under ``OFFICIALLY_DEAD_KEY`` is null, or an object of ``OFFICIALLY_DEAD_FACE_NAME`` plus the
# guise texts; a blank face name means the option was not taken.
OFFICIALLY_DEAD_KEY = "officially_dead"
OFFICIALLY_DEAD_FACE_NAME = "face_name"
OFFICIALLY_DEAD_TEXT_FIELDS: tuple[str, ...] = (
    "concept",
    "quote",
    "never_do",
    "protect",
    "fear",
    "background",
)
# Jailbird's crime (#4846, slice 5 of #4813): the answer to ``FinalTouchesPrompt.CRIME``. The
# draft_data entry under ``CRIME_KEY`` is null, or ``{"kind_id": <CrimeKind id>, "line": <text>}``;
# finalize writes it as a staff-only ``justice.CharacterCrimeNote`` when the draft still holds a
# card that asks it. No heat row and no deed tag come of it (decision 6 of #4813).
CRIME_KEY = "crime"
CRIME_KIND_ID = "kind_id"
CRIME_LINE = "line"
CRIME_LINE_MAX_LENGTH = 500
# The grants' answers (#4852, slice 6 of #4813), each keyed by the card's id as a string, since
# two cards can ask the same thing (Miraculous Survival and Renowned both carry a prestige
# grant). ``PRESTIGE_STORIES_KEY`` maps to the story's text, written at finalize as the pick's
# ``CharacterDistinction.notes``; ``ORGANIZATIONS_KEY`` maps to the chosen organization's id,
# one of ``offers.organization_choices``, seated at finalize through ``join_organization``.
# Neither is gated on the card being held while the draft lives (the slice 5 rule).
PRESTIGE_STORIES_KEY = "prestige_stories"
PRESTIGE_STORY_MAX_LENGTH = 500
ORGANIZATIONS_KEY = "organizations"
# The second face a hidden persona grant asks for (#4856): the Officially dead door's shape
# (``OFFICIALLY_DEAD_FACE_NAME`` plus ``OFFICIALLY_DEAD_TEXT_FIELDS``) under its own key, since a
# draft may hold both persona cards. ``TIES_KEY`` maps the card's id to ``{"organization_id",
# "kind"}``, the organization one of the card's choices and the kind a ``TieKind``.
ALTER_EGO_KEY = "alter_ego"
TIES_KEY = "ties"
TIE_ORGANIZATION_ID = "organization_id"
TIE_KIND = "kind"

# The Final Touches chapter (#4846, slice 5 of #4813): the card-unlocked section's copy keys.
# Every line below is PLACEHOLDER for the maintainer's voice (the authoring plan's Final
# Touches copy table); the leaf's in-code twins must stay identical to these.
FINAL_TOUCHES_CARDS_HEADING = "What the cards leave to settle"
FINAL_TOUCHES_CARDS_INTRO = (
    "A few of the cards you picked leave something for you to settle. Each one here can be "
    "skipped."
)  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_CRIME_PROMPT = "The crime, if you care to name it."  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_CRIME_LINE_LABEL = "In a sentence"  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_CRIME_HELP = (
    "Nothing follows from this unless a GM picks it up."  # PLACEHOLDER: Apostate rewrite
)
FINAL_TOUCHES_CRIME_BLANK = "Unnamed"  # PLACEHOLDER: Apostate rewrite
# The grants' asks (#4852, slice 6 of #4813): a prestige card's story, the organization a card
# seats the character in, Capable Mentor's line. Twins of the leaf's ``GRANTS`` fallbacks.
FINAL_TOUCHES_PRESTIGE_PROMPT = "What people say happened."  # PLACEHOLDER: Apostate rewrite
# PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_PRESTIGE_HELP = (
    "A sentence or two. This is the story attached to your name, not the truth of it."
)
FINAL_TOUCHES_ORGANIZATION_PROMPT = (
    "The body that marked your coming of age takes you in."  # PLACEHOLDER: Apostate rewrite
)
FINAL_TOUCHES_ORGANIZATION_HELP = (
    "Any organization of your realm that admits player characters, secret societies "
    "included. Skipped, the ritual stays a line in your story and no membership is made."
)  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_ORGANIZATION_NONE = "None"  # PLACEHOLDER: Apostate rewrite
# PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_ASPECT_PROMPT = (
    "Your mentor's lessons settle on {aspect}, the stronger Aspect of your Path."
)
FINAL_TOUCHES_ASPECT_HELP = "Applied for you."  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_ASPECT_UNKNOWN = "your Path's stronger Aspect"  # PLACEHOLDER: Apostate rewrite
# The second face and the tie (#4856, slice 6 of #4813). Twins of the leaf's ``SECOND_FACE`` and
# ``TIE`` fallbacks.
ALTER_EGO_HEADING = "A second face"  # PLACEHOLDER: Apostate rewrite
ALTER_EGO_INTRO = (
    "Your best work goes by another name. Name the face some circles know, with a concept, "
    "a quote and a story of its own; the rest of the world meets you."
)  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_TIE_PROMPT = "The ones who remember you."  # PLACEHOLDER: Apostate rewrite
# PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_TIE_HELP = "A place at the bottom rung, or a name they already know. Or neither."
FINAL_TOUCHES_TIE_NONE = "None"  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_TIE_MEMBERSHIP = "A place at the bottom rung"  # PLACEHOLDER: Apostate rewrite
FINAL_TOUCHES_TIE_RENOWN = "A name they already know"  # PLACEHOLDER: Apostate rewrite

OFFICIALLY_DEAD_HEADING = "Officially dead"
OFFICIALLY_DEAD_INTRO = (
    "The world believes you dead. Name the face it meets instead: an established identity "
    "with a concept, a quote and a story of its own, worn from your first day. Your true name "
    "stays on the rolls of the dead until someone sees through the face."
)  # PLACEHOLDER: Apostate rewrite
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

#: CGExplanation keys the Gift stage's "make it yours" panel reads (#4099). Every
#: sentence on that panel is one of these rows, authored in admin; none is a string
#: in the component. A key missing from the database is filled at read time by
#: `CGExplanationsSerializer.to_dict()` with a visible PLACEHOLDER marker (controller
#: ruling: no seed-data migration - authored content lives in the database, and the
#: repo's `check_migration_seed_data` hook forbids seeding it from a migration).
PERSONALIZATION_COPY_KEYS: tuple[str, ...] = (
    "personalize_heading",
    "personalize_name_title",
    "personalize_name_gloss",
    "personalize_flourish_title",
    "personalize_flourish_gloss",
    "personalize_form_title",
    "personalize_form_gloss",
    "personalize_price_title",
    "personalize_price_gloss",
    "personalize_name_label",
    "personalize_description_label",
    "personalize_free_note",
    "personalize_mechanics_note",
    "personalize_needs_resonance",
    #: The collapsed summary row's label when a section (name/description,
    #: flourish, form, or price) carries no pick yet (#4099 demo-fidelity fix,
    #: Screen 1's funnel-door rows) — one generic key shared by all four rows.
    "personalize_summary_none",
)

#: ``draft_data`` key for creation-time technique personalization picks (#4099).
#: Maps a technique id (string key, JSON has no int keys) to its picks — name,
#: description, flourish/form/price ids. Entries for a technique no longer in
#: ``selected_technique_ids`` are ignored by costs, validation and finalize alike.
TECHNIQUE_PERSONALIZATIONS_KEY = "technique_personalizations"
