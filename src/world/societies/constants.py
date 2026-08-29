"""Constants for the societies system.

Currently houses the Renown system constants (#676 Phase A). Other shared
society / org / reputation primitives live in models.py alongside their
field definitions for historical reasons.
"""

from django.db import models

# Office slug for the parent-org oversight seat over covert children (#2820).
# Mirrors DOMAIN_STEWARD_OFFICE (houses) / MAGISTRATE_OFFICE (justice): the
# holder gets READ access to associated covert child orgs' boards; command
# always stays with the child org's own leadership.
SPYMASTER_OFFICE = "spymaster"

# Covert-membership secret level by rank tier (#2820): the spymaster's identity
# is a DANGEROUS secret; a street courier is merely uncommon knowledge.
COVERT_SECRET_LEVEL_BY_TIER = {1: 4, 2: 3, 3: 2}
COVERT_SECRET_DEFAULT_LEVEL = 1

# ---------------------------------------------------------------------------
# Fame tier ladder (Renown system, #676)
#
# Fame is a per-persona accumulating buffer with cron decay (5 + 5%/IC day).
# The five tiers are derived display labels — the persona's fame_tier field
# stores the tier name as a CharField, recomputed on every fame_points write.
# Tier multipliers are NOT stored on the persona; they're applied at display
# time by viewer-facing code.
# ---------------------------------------------------------------------------


class FameTier(models.TextChoices):
    """Derived fame tier labels for the Renown system.

    The persona's ``fame_tier`` field stores one of these values. The numeric
    threshold and multiplier are looked up from ``FAME_TIER_THRESHOLDS`` and
    ``FAME_TIER_MULTIPLIERS`` at tier-derivation and display time respectively.
    """

    NORMAL = "normal", "Normal"
    TALKED_ABOUT = "talked_about", "Talked About"
    CELEBRITY = "celebrity", "Celebrity"
    HOUSEHOLD_NAME = "household_name", "Household Name"
    WORLD_FAMOUS = "world_famous", "World Famous"


# Minimum fame_points required to enter each tier. Floors at NORMAL = 0.
# Admin-tunable via a future settings model; hard-coded for now.
FAME_TIER_THRESHOLDS: dict[str, int] = {
    FameTier.NORMAL.value: 0,
    FameTier.TALKED_ABOUT.value: 100,
    FameTier.CELEBRITY.value: 1_000,
    FameTier.HOUSEHOLD_NAME.value: 10_000,
    FameTier.WORLD_FAMOUS.value: 100_000,
}

# Multiplier applied to total_prestige to compute displayed prestige when this
# tier is active. Admin-tunable via a future settings model.
FAME_TIER_MULTIPLIERS: dict[str, float] = {
    FameTier.NORMAL.value: 1.0,
    FameTier.TALKED_ABOUT.value: 1.25,
    FameTier.CELEBRITY.value: 2.5,
    FameTier.HOUSEHOLD_NAME.value: 5.0,
    FameTier.WORLD_FAMOUS.value: 10.0,
}

# Ordered tier list from lowest to highest. Used by the tier-derivation
# service to walk thresholds in order.
FAME_TIER_ORDER: tuple[str, ...] = (
    FameTier.NORMAL.value,
    FameTier.TALKED_ABOUT.value,
    FameTier.CELEBRITY.value,
    FameTier.HOUSEHOLD_NAME.value,
    FameTier.WORLD_FAMOUS.value,
)


# ---------------------------------------------------------------------------
# Decay rates (Renown system, #676)
#
# Fame decay is per IC day. With the canonical 3:1 IC:OOC time ratio
# (game_clock.GameClock.time_ratio default), 1 IC day == 8 real hours.
# The renown decay cron fires every 8 real hours.
#
# Formula: fame_new = max(0, fame_old - FAME_DECAY_FLAT - FAME_DECAY_PCT * fame_old)
#
# Half-life at high fame is dominated by the percentage term (~14 IC days
# = ~4.6 real days). At low fame the flat term drains the residue in
# ~3 weeks of real time.
# ---------------------------------------------------------------------------

FAME_DECAY_FLAT: int = 5
FAME_DECAY_PCT: float = 0.05

# Organization accumulated_prestige and accumulated_fame decay rates,
# matching the persona fame cadence and curve. accumulated_legend on
# covenants is permanent and never appears here.
ORG_PRESTIGE_DECAY_FLAT: int = 5
ORG_PRESTIGE_DECAY_PCT: float = 0.05
ORG_FAME_DECAY_FLAT: int = 5
ORG_FAME_DECAY_PCT: float = 0.05


# ---------------------------------------------------------------------------
# Renown event bundle scales (Phase B, #676)
#
# Each Renown event carries up to three independent scales:
#
#   * Magnitude — drives fame buffer + permanent prestige-from-deeds.
#   * Risk      — drives legend.
#   * Archetypes — drive reputation via principle dot product.
#
# Magnitude and Risk are admin-tunable TextChoices with numeric mappings
# below. Archetypes are model rows (PhilosophicalArchetype) defined in
# the societies models.
# ---------------------------------------------------------------------------


class RenownMagnitude(models.TextChoices):
    """How fame-worthy / prestige-worthy this event is.

    Drives both the fame buffer bump (visibility multiplier) and the
    permanent prestige-from-deeds increment.
    """

    SMALL = "small", "Small"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    VERY_HIGH = "very_high", "Very High"


class RenownRisk(models.TextChoices):
    """How life-threatening / consequential this event was.

    Drives only legend. NONE means no legend awarded — a famous-but-safe
    event like a royal wedding has high Magnitude and None Risk.
    """

    NONE = "none", "None"
    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    EXTREME = "extreme", "Extreme"


class RenownReach(models.TextChoices):
    """How widely news of this event propagates.

    Binary awareness gate per Realm: a Realm either becomes aware of the
    event (full reputation delta applied) or doesn't (nothing happens for
    that Realm's societies). Defaults from Magnitude per
    ``MAGNITUDE_TO_DEFAULT_REACH`` below; authors can override per event.
    """

    LOCAL = "local", "Local"
    REGIONAL = "regional", "Regional"
    CONTINENTAL = "continental", "Continental"
    WORLD = "world", "World"


# Magnitude → numeric awards.
#
# NOT admin-tunable, despite what this comment claimed until #3463: these are
# Python constants and changing them needs a deploy. Legend's equivalent moved
# to RiskCalibration.legend_award, which is a real per-risk-tier DB row staff
# can edit; the table below stays the fallback for a tier with no calibration
# row. Fame and prestige have no such row yet — if they need tuning, they want
# the same treatment rather than a second constants edit.
# Fame outscales prestige — a Very High event puts you instantly at
# Household Name fame (10k threshold), but permanent prestige climbs slowly.
MAGNITUDE_FAME_AWARDS: dict[str, int] = {
    RenownMagnitude.SMALL.value: 30,
    RenownMagnitude.MODERATE.value: 150,
    RenownMagnitude.HIGH.value: 1_200,
    RenownMagnitude.VERY_HIGH.value: 12_000,
}

MAGNITUDE_PRESTIGE_AWARDS: dict[str, int] = {
    RenownMagnitude.SMALL.value: 3,
    RenownMagnitude.MODERATE.value: 15,
    RenownMagnitude.HIGH.value: 75,
    RenownMagnitude.VERY_HIGH.value: 300,
}

# #3463 — the minimum EFFECTIVE risk at which any source may mint Legend.
# Below this, a settled unit mints nothing at all: not a reduced award, zero.
#
# Generalized from world.missions.constants.LEGEND_RISK_FLOOR_TIER (#2051),
# which enforced the same bar for one system only and keyed on a mission's
# *declared* risk_tier. This one keys on EFFECTIVE risk — the value
# compute_effective_risk (ADR-0077) prices against the beat's target_level —
# which is what makes "challenging" mean challenging *to you*: a level-10
# party's raid on level-4 content decays below the floor and pays nothing.
#
# Designer-tunable by code change only, deliberately: the bar for what is
# worth a song is an invariant, not content.
LEGEND_RISK_FLOOR: str = str(RenownRisk.HIGH.value)


def risk_meets_legend_floor(risk: str) -> bool:
    """Is this (EFFECTIVE, not declared) risk at or above the Legend floor?

    Ordering comes from ``RenownRisk``'s own declaration order, weakest to
    strongest, which is authoritative. ``world.stories.constants.RISK_LADDER``
    is a hand-maintained copy of the same sequence used for effective-risk
    ladder shifts; both agree, and this deliberately reads the enum rather
    than the copy. An unknown value is treated as below the floor — the safe
    direction, since the failure mode is minting Legend that was not earned.
    """
    ladder = list(RenownRisk.values)
    try:
        return ladder.index(risk) >= ladder.index(LEGEND_RISK_FLOOR)
    except ValueError:
        return False


# Risk → legend base_value FALLBACK. The authored value is
# RiskCalibration.legend_award (#3463); this table is what a tier with no
# calibration row falls back to.
RISK_LEGEND_AWARDS: dict[str, int] = {
    RenownRisk.NONE.value: 0,
    RenownRisk.LOW.value: 10,
    RenownRisk.MODERATE.value: 50,
    RenownRisk.HIGH.value: 250,
    RenownRisk.EXTREME.value: 1_500,
}

# Magnitude → default Reach (event author can override per event).
# Small events stay local; Very High events ripple worldwide.
MAGNITUDE_TO_DEFAULT_REACH: dict[str, str] = {
    RenownMagnitude.SMALL.value: RenownReach.LOCAL.value,
    RenownMagnitude.MODERATE.value: RenownReach.REGIONAL.value,
    RenownMagnitude.HIGH.value: RenownReach.CONTINENTAL.value,
    RenownMagnitude.VERY_HIGH.value: RenownReach.WORLD.value,
}


class DeedKnowledgeSource(models.TextChoices):
    """How a persona came to know a deed (#902 — provenance, not permission).

    The DOER needs no row (it's their deed); common knowledge (total legend
    ≥ COMMON_KNOWLEDGE_MULTIPLIER × base) is computed, not stored.
    """

    WITNESSED = "witnessed", "Witnessed"
    HEARD_TOLD = "heard_told", "Heard the tale told"


# A deed whose total legend (base + spreads) reaches this multiple of its
# base value has entered common knowledge: any persona may see and spread
# it. Halfway through the 10× spread ceiling — the back half of a tale's
# growth is the communal phase. (#902)
COMMON_KNOWLEDGE_MULTIPLIER = 5


# Names of the six society principle fields. Used by the archetype dot
# product to walk fields uniformly via getattr.
PRINCIPLE_FIELD_NAMES: tuple[str, ...] = (
    "mercy",
    "method",
    "status",
    "change",
    "allegiance",
    "power",
)


# ---------------------------------------------------------------------------
# Scandal reach & containment minting (#1464). Magnitudes PLACEHOLDER and
# never player-documented; the judgment is the archetype·principles dot.
# ---------------------------------------------------------------------------

# An act is scandalous TO a society when its archetype dot-product against
# that society's principles is at or below this (negative) threshold.
SCANDAL_THRESHOLD = -10

# Containment difficulty grows with the crowd: base + step per witness.
CONTAINMENT_BASE_DIFFICULTY = 0
CONTAINMENT_DIFFICULTY_PER_WITNESS = 2

# Act-time concealment (#1824): a declared-sneaky deed rolls Stealth against
# the crowd before witnesses are minted. success_level at/past FULL removes
# every witness but the actor; at/past PARTIAL drops half. PLACEHOLDER tuning.
CONCEALMENT_FULL_LEVEL = 3
CONCEALMENT_PARTIAL_LEVEL = 1

# Contained-scandal Secret level scales with how badly the act reads
# (|worst dot| at or past each floor, descending). (level, |dot| floor).
SCANDAL_SECRET_LEVEL_FLOORS: tuple[tuple[int, int], ...] = (
    (4, 60),  # DANGEROUS
    (3, 30),  # CAREFULLY_KEPT
    (2, 0),  # WHISPERS — the floor for any minted scandal
)

# Spread scales with who was involved: fame tier → spread_multiplier factor
# (applied to SpreadingConfig.default_spread_multiplier at deed birth).
FAME_SPREAD_FACTORS: dict[str, int] = {
    "normal": 1,
    "talked_about": 2,
    "celebrity": 3,
    "household_name": 4,
    "world_famous": 5,
}


# ---------------------------------------------------------------------------
# Org accumulation flow (Phase C, #676)
#
# Inflow: every member's renown deed contributes a flat fraction to each of
# their org memberships' accumulated values. Flat (not rank-weighted) per
# the spec — "any member's deeds reflect on the org because they're a member."
#
# Outflow: persona.prestige_from_orgs reads back the org's accumulated
# values weighted by the member's rank — heads of org extract full standing,
# peripheral members barely benefit. The asymmetric inflow/outflow creates
# the patronage feel.
#
# Loop-safety: outflow is a pure *readout* of org state. It never feeds back
# into the org's accumulated values. Deeds → org accumulated is the only
# direction of write; prestige_from_orgs is recomputed on the persona side
# whenever an affecting org changes.
# ---------------------------------------------------------------------------

# Fraction of a persona's renown-deed prestige/fame/legend that flows into
# each of their org memberships. Flat across all ranks.
ORG_INFLOW_FRACTION: float = 0.10

# Rank-weighted outflow multipliers (1 = highest rank, 5 = lowest). Heads of
# org get full org standing; aspirants get a token share. Admin-tunable in
# a future settings model.
RANK_OUTFLOW_MULTIPLIERS: dict[int, float] = {
    1: 1.0,
    2: 0.5,
    3: 0.25,
    4: 0.10,
    5: 0.05,
}


# ---------------------------------------------------------------------------
# OrganizationObligation (#2428) — Golden Hare entrance debt
#
# Unbound Prospects owe Shroudwatch Academy a Golden Hare on CG finalize
# (no Tradition sponsor covered their entrance); sponsored Prospects start
# with a SETTLED_BY_SPONSOR row recording the literal Hare their sponsor
# spent on their behalf. Rows are never deleted — settled history persists.
# ---------------------------------------------------------------------------


class ObligationOrigin(models.TextChoices):
    """What created an :class:`~world.societies.models.OrganizationObligation`."""

    ACADEMY_ENTRANCE = "academy_entrance", "Academy Entrance"
    OTHER = "other", "Other"


class ObligationState(models.TextChoices):
    """Lifecycle of an :class:`~world.societies.models.OrganizationObligation`.

    ``OWED`` is the only settleable state; ``SETTLED`` and
    ``SETTLED_BY_SPONSOR`` are both terminal, distinguished only by whether
    the debtor or a sponsor surrendered the Hare.
    """

    OWED = "owed", "Owed"
    SETTLED = "settled", "Settled"
    SETTLED_BY_SPONSOR = "settled_by_sponsor", "Settled by Sponsor"


# ---------------------------------------------------------------------------
# StandingDeclaration (#3290) — leader-declared favor/disfavor
#
# An org leader (OrganizationRank.can_declare_standing) deliberately moves a
# persona's OrganizationReputation via the existing bump_organization_reputation
# writer (renown.py) and mints an audit row. PLACEHOLDER magnitudes; tuning
# is a follow-up once play tests how fast declared standing should move the
# hidden -1000..+1000 value relative to deed-driven bumps.
# ---------------------------------------------------------------------------


class StandingDirection(models.TextChoices):
    """Which way a :class:`~world.societies.models.StandingDeclaration` pushes standing."""

    FAVOR = "favor", "Favor"
    DISFAVOR = "disfavor", "Disfavor"


# PLACEHOLDER magnitude: a single declaration nudges standing by this much.
# Small relative to the -1000..+1000 range so a leader can't singlehandedly
# swing a tier in one act; repeated declarations (rate-limited to one per
# (org, target) per IC week) accumulate over time.
STANDING_DECLARATION_FAVOR_DELTA = 50
STANDING_DECLARATION_DISFAVOR_DELTA = -50

# Antagonism consent category key gating DISFAVOR declarations (#2170 seam).
# Reuses the same "hostile" category the frame-job denounce/accusation gate
# consults (world.secrets.services.accusation_permitted) rather than minting
# a new category — a leader publicly marking a PC disfavored is the same
# antagonism-consent question ("has this player opted into being targeted by
# hostile play?"), not a distinct flavor of antagonism deserving its own
# category and its own row in every player's consent settings.
STANDING_DISFAVOR_CONSENT_CATEGORY_KEY = "hostile"
# OrgAppeal (#3293) — appeals to organizations
# ---------------------------------------------------------------------------


class OrgAppealState(models.TextChoices):
    """Lifecycle of an :class:`~world.societies.models.OrgAppeal`.

    ``OPEN`` is the only state a member may sign onto or leadership may
    resolve; ``GRANTED``/``DECLINED``/``WITHDRAWN`` are all terminal.
    """

    OPEN = "open", "Open"
    GRANTED = "granted", "Granted"
    DECLINED = "declined", "Declined"
    WITHDRAWN = "withdrawn", "Withdrawn"
