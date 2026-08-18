"""Choices for the houses system (#1884)."""

from django.db import models

# --- Domain economics (#2238) — PLACEHOLDER magnitudes ---
# Prosperity at which a domain's holdings yield their base gross (a neutral 1.0x).
# Above it holdings over-yield; below they under-yield; at 0 prosperity, no income.
DOMAIN_PROSPERITY_BASELINE = 50

# Unrest above this threshold can boil over into a DomainCrisis on the weekly tick;
# each point above it adds UNREST_CRISIS_PCT_PER_POINT% to the weekly chance.
UNREST_CRISIS_THRESHOLD = 60
UNREST_CRISIS_PCT_PER_POINT = 2

# --- Delegation (#2239) ---
# Slug of the OrganizationOffice whose holder may run a house's domain in play
# (add holdings, commission improvements) alongside the org's leadership rank.
DOMAIN_STEWARD_OFFICE = "domain-steward"

# --- Crisis lifecycle (#2238) — PLACEHOLDER magnitudes ---
# While a crisis is open, holding income is further scaled by severity: the
# domain sits in a damaged-but-stable neutral state (never compounds on its own).
CRISIS_INCOME_FACTORS: dict[str, float] = {
    "trouble": 0.9,
    "crisis": 0.75,
    "catastrophe": 0.5,
}

# --- Generated threat/opportunity loop (#2837) — PLACEHOLDER magnitudes ---
# Generated (non-staff) crises stay covert this long before surfacing on the
# public feed; spy sweeps buy the reaction time.
COVERT_WINDOW_DAYS = 7
# An unseized opportunity closes this long after it opened.
OPPORTUNITY_LIFETIME_DAYS = 21
# Weekly ambient spawn chances (percent), rolled by crisis_generation_tick.
AMBIENT_DOMAIN_THREAT_PCT = 10
AMBIENT_DOMAIN_OPPORTUNITY_PCT = 8
AMBIENT_ORG_THREAT_PCT = 8
AMBIENT_ORG_OPPORTUNITY_PCT = 6
# Seizing/exploiting an event pays the acting org by magnitude (severity
# doubles as an opportunity's size). Domain-owner seizure pays prosperity.
OPPORTUNITY_BOON_COPPERS: dict[str, int] = {
    "trouble": 5_000,
    "crisis": 15_000,
    "catastrophe": 40_000,
}
OPPORTUNITY_PROSPERITY_BOON: dict[str, int] = {
    "trouble": 2,
    "crisis": 4,
    "catastrophe": 8,
}


class CrisisOrigin(models.TextChoices):
    """How a DomainCrisis came to exist — drives the auto-mint rule (#2238)."""

    IMPROVEMENT = "improvement", "Failed Improvement"
    UNREST = "unrest", "Unrest Boil-over"
    STAFF = "staff", "Staff/GM Crafted"
    AMBIENT = "ambient", "Ambient Generation"
    PREDATOR = "predator", "Predator Raid"
    AFFLICTION = "affliction", "Affliction Outbreak"


class CrisisResolutionKind(models.TextChoices):
    """The kinds of resolution option a crisis type may offer (#2238)."""

    PAY = "pay", "Pay It Off"
    MISSION = "mission", "Confront It (mission)"
    WAIT = "wait", "Ride It Out"


class CrisisResolution(models.TextChoices):
    """How a resolved crisis ended (#2238; task/exploit/expiry #2837)."""

    PAID = "paid", "Paid Off"
    MISSION_COMPLETED = "mission_completed", "Mission Completed"
    SELF_RESOLVED = "self_resolved", "Blew Over"
    TASK_COMPLETED = "task_completed", "Handled by an Agent"
    EXPLOITED = "exploited", "Turned by Another Hand"
    EXPIRED = "expired", "The Window Closed"


class TitleTier(models.TextChoices):
    """Rank of a landed/dynastic title. Realm-specific display labels are
    authorable on the Title row itself; this is the mechanical ladder (#3091:
    six consistent-noun steps — Apostate's ruling).

    EMPIRE is a genuinely separate title, not a styling of KINGDOM: Umbros's
    Emperor holds a kingdom-level title in addition to the imperial one, and
    an empress could be selected while holding no lower title. MARCH marks
    militarily vital counties or multi-county holdings short of ducal (held
    by a marquis/marquessa).
    """

    EMPIRE = "empire", "Empire"
    KINGDOM = "kingdom", "Kingdom"
    DUCHY = "duchy", "Duchy"
    MARCH = "march", "March"
    COUNTY = "county", "County"
    BARONY = "barony", "Barony"


# Mechanical ordering of TitleTier for band resolution (#3261): a particle row
# with ``tier_floor`` applies to houses whose highest held title ranks at or
# above the floor; the blank-floor row is the realm's default band.
TITLE_TIER_RANK: dict[str, int] = {
    TitleTier.EMPIRE: 6,
    TitleTier.KINGDOM: 5,
    TitleTier.DUCHY: 4,
    TitleTier.MARCH: 3,
    TitleTier.COUNTY: 2,
    TitleTier.BARONY: 1,
}

# Continental née grammar (#3261, canon 2026-08-17): ``ne <BirthFamilyName>``,
# bare — it REPLACES the birth family's particle, and renders only at the
# full-formal degree, before the current-house segment.
NEE_MARKER = "ne"

# Evennia alias category for derived name forms (#3261): sync_name_aliases
# clears/re-adds only this category, so player-set aliases survive.
DERIVED_NAME_ALIAS_CATEGORY = "derived_name"

# PLACEHOLDER personal styles by tier, (male, female, neutral) — used when the
# Title row's authorable holder-style fields are blank.
DEFAULT_TIER_STYLES: dict[str, tuple[str, str, str]] = {
    TitleTier.EMPIRE: ("Emperor", "Empress", "Sovereign"),
    TitleTier.KINGDOM: ("King", "Queen", "Monarch"),
    TitleTier.DUCHY: ("Duke", "Duchess", "Grace"),
    TitleTier.MARCH: ("Margrave", "Margravine", "Warden"),
    TitleTier.COUNTY: ("Count", "Countess", "Excellency"),
    TitleTier.BARONY: ("Baron", "Baroness", "Lordship"),
}


class NameDegree(models.TextChoices):
    """How much of a name renders (#3261): the degree a character leads with.

    The née segment appears only at FULL_FORMAL; formal contexts (ceremony,
    proclamation, sheet header) render FULL_FORMAL regardless of preference.
    """

    FAMILIAR = "familiar", "Familiar"
    COMMON = "common", "Common"
    STYLED = "styled", "Styled"
    FULL_FORMAL = "full_formal", "Full Formal"


class TitleSuffixMode(models.TextChoices):
    """Orthogonal title-suffix axis (#3261): what trails the composed name."""

    NONE = "none", "No Titles"
    PRIMARY = "primary", "Primary Title"
    ALL = "all", "All Titles"


class RecognitionRuleKind(models.TextChoices):
    """Per-realm house-recognition rules (#1884, Apostate lore rulings).

    Umbral matrilineality: a noblewoman's in-wedlock children are recognized
    automatically; out of wedlock it is the mother's option; a nobleman's
    children by a commoner woman belong to HER family (commoner, not
    bastard). Inferna ennobles the female titleholder's children by male
    consorts.
    """

    MATRILINEAL_AUTO_WEDLOCK = "matrilineal_auto_wedlock", "Matrilineal (auto in wedlock)"
    MOTHER_OPTION_OUT_OF_WEDLOCK = "mother_option", "Mother's option (out of wedlock)"
    CONSORT_CHILDREN_ENNOBLED = "consort_ennobled", "Titleholder's consort children ennobled"
    PATRILINEAL_AUTO_WEDLOCK = "patrilineal_auto_wedlock", "Patrilineal (auto in wedlock)"


class SuccessionDerivation(models.TextChoices):
    """How the candidate set derives from the kinship graph (#1884)."""

    PRIMOGENITURE_WEDLOCK = "primogeniture_wedlock", "Eldest legitimate child"
    MATRILINEAL_RECOGNITION = "matrilineal_recognition", "Recognized matrilineal issue"
    FEMALE_LINE_CONSORTS_ENNOBLED = "female_line", "Female-line issue (consorts ennobled)"
    CHOSEN_HEIR = "chosen_heir", "Chosen heir"
    TANISTRY_ELECTION = "tanistry_election", "Tanistry election"


class SuccessionOrdering(models.TextChoices):
    """How candidates are ranked (#1884). MOST_POWERFUL_GIFTED resolves via a
    pluggable registry with a PLACEHOLDER proxy — never hardcoded."""

    ELDEST = "eldest", "Eldest first"
    MOST_POWERFUL_GIFTED = "most_powerful_gifted", "Most powerful Gifted first"


class PactCommitmentKind(models.TextChoices):
    """Coded marriage-pact commitments that fire mechanically (#1884).

    DOWRY: one-time treasury transfer at signing. SUBSIDY: recurring
    OrgObligation from senior to junior house. CRISIS_RESPONSE: the
    committed person is auto-invited into the ally's crisis content.
    RESIDENCY: the junior spouse joins the senior house (org membership +
    family channel + estate). CUSTOM: recorded prose, socially binding only.
    """

    DOWRY = "dowry", "Dowry"
    SUBSIDY = "subsidy", "Recurring Subsidy"
    CRISIS_RESPONSE = "crisis_response", "Crisis Response"
    RESIDENCY = "residency", "Residency"
    CUSTOM = "custom", "Custom (prose)"


class PactDissolutionReason(models.TextChoices):
    DEATH = "death", "A spouse died"
    ANNULMENT = "annulment", "Annulled"
    BREACH = "breach", "Broken by breach"
    DIVORCE = "divorce", "Divorced"


class DomainCrisisSeverity(models.TextChoices):
    TROUBLE = "trouble", "Trouble"
    CRISIS = "crisis", "Crisis"
    CATASTROPHE = "catastrophe", "Catastrophe"


class CrisisValence(models.TextChoices):
    """Whether a generated event hurts or helps its target (#2837).

    Opportunities reuse the whole spawn/option/feed pipeline; severity scales
    the payoff instead of the income malus, and they expire if not seized.
    """

    THREAT = "threat", "Threat"
    OPPORTUNITY = "opportunity", "Opportunity"


class CrisisAudience(models.TextChoices):
    """What kind of target a crisis type can spawn against (#2837).

    CRIMINAL_ORG = an org running a crime kick-up stream or of a covert org
    type — criminal flavor lives in content, not new mechanics.
    """

    DOMAIN = "domain", "Domain"
    ORG = "org", "Any Organization"
    CRIMINAL_ORG = "criminal_org", "Criminal Organization"


class CrisisIntelSource(models.TextChoices):
    """How an org learned of a still-covert crisis (#2837)."""

    SPY_SWEEP = "spy_sweep", "Spy Sweep"
    STAFF = "staff", "Staff Grant"


class HouseClaimStatus(models.TextChoices):
    """Lifecycle of a CG house-founding claim (#1884 Phase D)."""

    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


# --- House Stature (#3091) — PLACEHOLDER magnitudes, inventoried for the ---
# --- tuning pass. All relative/rank-based reads happen at consume time.  ---

# Component weights: renown-heavy by ruling — the Gifted who stand with a
# house matter as much as (possibly more than) its armies.
STATURE_RENOWN_WEIGHT = 1.5
STATURE_MILITARY_WEIGHT = 1.0
STATURE_ECONOMIC_WEIGHT = 0.5

# A standing pact contributes the counterpart's NET own-strength at this
# factor. One hop only, both directions (strength and crisis drag alike).
STATURE_ALLY_FACTOR = 0.5

# Weekly perceived→true convergence share (word travels slowly).
STATURE_CONVERGENCE_RATE = 0.25

# Share of a dead contributor's weight that hits perceived stature instantly
# (a public death is news; the rest arrives via weekly convergence).
STATURE_DEATH_SHOCK_SHARE = 0.6

# Whisper campaigns can displace perceived at most this fraction below true.
STATURE_WHISPER_MAX_DISPLACEMENT = 0.25

# Persona renown score terms (prestige counts at 1.0 implicitly).
STATURE_FAME_WEIGHT = 1.0
STATURE_LEGEND_WEIGHT = 2.0

# Renown value per authored Kinsperson.gifted_rating point (sheetless kin).
GIFTED_RATING_RENOWN = 2_000

# Succession's MOST_POWERFUL_GIFTED rater compares sheeted kin (max class
# level, 1-30) against sheetless kin (gifted_rating 0-5) on one scale:
# rating x this equivalent (rating 5 ~ level 20).
GIFTED_RATING_LEVEL_EQUIV = 4

# MilitaryUnit strength scales by quality when summed into stature.
UNIT_QUALITY_STATURE_MULTIPLIERS: dict[str, float] = {
    "militia": 0.5,
    "levy": 0.75,
    "trained": 1.0,
    "veteran": 1.5,
    "elite": 2.0,
}

# An open threat deducts this fraction of the org's own gross strength
# (blood in the water) until resolved.
CRISIS_STATURE_PENALTIES: dict[str, float] = {
    "trouble": 0.05,
    "crisis": 0.12,
    "catastrophe": 0.25,
}

# Economic component: coppers of treasury per stature point, and the weight
# on summed weekly stream gross.
TREASURY_STATURE_DIVISOR = 10_000
INCOME_GROSS_STATURE_WEIGHT = 0.1

# Prestige→prosperity drift (ruled: benefit routes through bounded prosperity;
# ~3x base income cap emerges from prosperity 100 vs baseline 50 plus band
# bonuses — never a raw accrual factor). Bonus applies only with zero open
# threats; capped per week.
PRESTIGE_PROSPERITY_DRIFT_MAX = 5

# Band cohort continent key until a continent model exists (#3091 ruling:
# continental bands + realm rank; only Catenys is defined today).
CONTINENT_CATENYS = "catenys"

# Flat permanent prestige (fires at marriage formation in phase 3; callable
# from seeds now). Award per tier-gap step for marrying up; scandal penalty
# for pact breach.
MARRIAGE_TIER_PRESTIGE_AWARD_STEP = 5_000
SCANDAL_PRESTIGE_PENALTY = 10_000


class StatureShiftCause(models.TextChoices):
    """Why a house's stature moved (#3091) — the 'why it moved' ledger."""

    DEATH = "death", "A Death"
    PACT_SIGNED = "pact_signed", "Pact Signed"
    PACT_DISSOLVED = "pact_dissolved", "Pact Dissolved"
    CRISIS_OPENED = "crisis_opened", "Crisis Opened"
    CRISIS_SURFACED = "crisis_surfaced", "Crisis Surfaced"
    CRISIS_RESOLVED = "crisis_resolved", "Crisis Resolved"
    WHISPERS = "whispers", "Whisper Campaign"
    CONVERGENCE = "convergence", "Word Spreads"
    RECOMPUTE = "recompute", "Weekly Recompute"
    BAND_CHANGE = "band_change", "Standing Repriced"
    GRAND_DISPLAY = "grand_display", "Grand Display"


# --- Grand displays (#3093) — the upward half of the bluffing game ---
# An event whose catering PROVISION score clears the bar pushes the host
# org's perceived stature up, capped this fraction above true. PLACEHOLDER.
GRAND_DISPLAY_MIN_QUALITY = 6
GRAND_DISPLAY_ELEVATION_PER_POINT = 150
STATURE_BLUFF_MAX_ELEVATION = 0.15


# --- Org pacts & betrothal (#2999) — PLACEHOLDER magnitudes ---
# A betrothal previews the eventual alliance at a fraction of full weight:
# the world already treats the match as likely, but the wedding is the payoff.
BETROTHAL_STATURE_SHARE_PCT = 25
# Breaking a betrothal is a scandal: flat permanent prestige penalty on the
# breaking side's house (same channel as pact breach).
BETROTHAL_BREAK_PRESTIGE_PENALTY = 5_000

# Divorce (#2358 overnight ruling): either spouse may end a living union
# unilaterally; BOTH take a personal deed-prestige hit (award_deed_prestige,
# the same channel award_marriage_tier_prestige uses — a PERSONAL penalty,
# distinct from apply_pact_shift's house-level alliance reprice, which already
# fires on dissolution regardless of reason). The initiator's hit is steeper.
# PLACEHOLDER magnitudes pending Apostate's tuning pass.
DIVORCE_INITIATOR_PRESTIGE_PENALTY = 5_000
DIVORCE_OTHER_SPOUSE_PRESTIGE_PENALTY = 3_000


class OrgPactDissolutionReason(models.TextChoices):
    """How an OrgPact ended (#2999). BETRAYAL is a world event, not prose."""

    DISSOLVED = "dissolved", "Dissolved by Agreement"
    BETRAYAL = "betrayal", "Betrayed"
    FULFILLED = "fulfilled", "Fulfilled"
