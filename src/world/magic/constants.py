from dataclasses import dataclass

from django.db import models


class TechniqueCategory(models.TextChoices):
    """Player-facing technique grouping (#2426).

    Formerly duplicated on the now-removed CG starter-technique-template
    model (#2426 Task 8); this is the sole surviving grouping.
    """

    ATTACK = "attack", "Attack"
    DEFENSE = "defense", "Defense"
    BUFF = "buff", "Buff"
    DEBUFF = "debuff", "Debuff"
    UTILITY = "utility", "Utility"


class TechniqueFunction(models.TextChoices):
    """Fine-grained technique job labels (#2443, Layer 2 of the vow-power model).

    The SHARED vocabulary both per-vow specialties (#2443) and situational
    perks (#2536) target. Code-defined so data can link to labels with stable,
    validated meanings; WHICH labels a technique carries is content (lore repo).
    Extending this list is a deliberate one-line code change.
    """

    DAMAGE_BUFF_SELF = "damage_buff_self", "Self Damage Buff"
    DAMAGE_BUFF_ALLY = "damage_buff_ally", "Ally Damage Buff"
    DEFENSE_BUFF = "defense_buff", "Defense Buff"
    BARRIER = "barrier", "Barrier"
    CLEANSE = "cleanse", "Cleanse"
    MOBILITY = "mobility", "Mobility"
    CHARM = "charm", "Charm"
    DISTRACTION = "distraction", "Distraction"
    FEAR = "fear", "Fear"
    WEAKEN = "weaken", "Weaken"
    PERCEPTION = "perception", "Perception"
    CONCEALMENT = "concealment", "Concealment"


class StandingCapMode(models.TextChoices):
    """Mode for a StandingCapBand: hard clamp vs. soft diminish (#853)."""

    HARD = "HARD", "Hard (clamp to cap)"
    SOFT = "SOFT", "Soft (diminish excess above cap)"


class AlterationKind(models.TextChoices):
    """Discriminator on MagicalAlterationTemplate (MAGE_SCAR vs CORRUPTION_TWIST)."""

    MAGE_SCAR = "MAGE_SCAR", "Mage Scar"
    CORRUPTION_TWIST = "CORRUPTION_TWIST", "Corruption Twist"


class AlterationTier(models.IntegerChoices):
    """Severity tier for magical alterations. Higher = more dramatic."""

    COSMETIC_TOUCH = 1, "Cosmetic Touch"
    MARKED = 2, "Marked"
    TOUCHED = 3, "Touched"
    MARKED_PROFOUNDLY = 4, "Marked Profoundly"
    REMADE = 5, "Remade"


class PendingAlterationStatus(models.TextChoices):
    """Lifecycle status of a PendingAlteration."""

    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"
    STAFF_CLEARED = "staff_cleared", "Staff Cleared"


# Tier cap configuration. Keys are AlterationTier values.
# Each value is a dict with: social_cap, weakness_cap, resonance_cap,
# visibility_required (bool).
ALTERATION_TIER_CAPS: dict[int, dict[str, int | bool]] = {
    AlterationTier.COSMETIC_TOUCH: {
        "social_cap": 1,
        "weakness_cap": 1,
        "resonance_cap": 1,
        "visibility_required": False,
    },
    AlterationTier.MARKED: {
        "social_cap": 2,
        "weakness_cap": 2,
        "resonance_cap": 2,
        "visibility_required": False,
    },
    AlterationTier.TOUCHED: {
        "social_cap": 3,
        "weakness_cap": 3,
        "resonance_cap": 3,
        "visibility_required": False,
    },
    AlterationTier.MARKED_PROFOUNDLY: {
        "social_cap": 5,
        "weakness_cap": 5,
        "resonance_cap": 5,
        "visibility_required": True,
    },
    AlterationTier.REMADE: {
        "social_cap": 8,
        "weakness_cap": 8,
        "resonance_cap": 7,
        "visibility_required": True,
    },
}

# Minimum description length for player-authored alteration descriptions.
MIN_ALTERATION_DESCRIPTION_LENGTH = 40


class SuggestionStatus(models.TextChoices):
    """Lifecycle status of a DramaticMomentSuggestion (#2183)."""

    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    DISMISSED = "dismissed", "Dismissed"


class TargetKind(models.TextChoices):
    TRAIT = "TRAIT", "Trait"
    TECHNIQUE = "TECHNIQUE", "Technique"
    FACET = "FACET", "Facet"
    RELATIONSHIP_TRACK = "RELATIONSHIP_TRACK", "Relationship Track"
    RELATIONSHIP_CAPSTONE = "RELATIONSHIP_CAPSTONE", "Relationship Capstone"
    COVENANT_ROLE = "COVENANT_ROLE", "Covenant Role"
    MANTLE = "MANTLE", "Mantle"
    SANCTUM = "SANCTUM", "Sanctum"
    GIFT = "GIFT", "Gift"
    ORGANIZATION = "ORGANIZATION", "Organization"


class GiftKind(models.TextChoices):
    """Taxonomy axis on Gift (ADR-0050): Major = CG-chosen, Minor = shared/acquirable.

    Species abilities and acquirable powers are delivered as Minor Gifts. A gift
    is major or minor to everyone, not per-character — so `kind` lives on `Gift`,
    not on `CharacterGift`. Provenance (species-granted vs acquired) is a separate
    axis owned by #1580.
    """

    MAJOR = "MAJOR", "Major (CG-chosen)"
    MINOR = "MINOR", "Minor (shared, acquirable)"


class SanctumSlotKind(models.TextChoices):
    """Per-PC weaving slot rules for SANCTUM-target Threads (Plan 4 §F).

    Each persona has at most one ``PERSONAL_OWN`` Thread (active) and at
    most one ``COVENANT`` Thread (active). ``HELPER`` Threads are
    unlimited (only valid on Personal Sanctums; Covenant Sanctums admit
    only members-as-COVENANT).
    """

    PERSONAL_OWN = "PERSONAL_OWN", "Personal — own home"
    COVENANT = "COVENANT", "Covenant — sacred ground"
    HELPER = "HELPER", "Helper — invited ally on another's personal Sanctum"


class EffectKind(models.TextChoices):
    FLAT_BONUS = "FLAT_BONUS", "Flat Bonus"
    INTENSITY_BUMP = "INTENSITY_BUMP", "Intensity Bump"
    VITAL_BONUS = "VITAL_BONUS", "Vital Bonus"
    CAPABILITY_GRANT = "CAPABILITY_GRANT", "Capability Grant"
    NARRATIVE_ONLY = "NARRATIVE_ONLY", "Narrative Only"
    CORRUPTION_RESISTANCE = "CORRUPTION_RESISTANCE", "Corruption Resistance"
    ASSUME_ALTERNATE_SELF = "ASSUME_ALTERNATE_SELF", "Assume Alternate Self"
    RESISTANCE = "RESISTANCE", "Damage-Type Resistance"


class RegardPolarity(models.TextChoices):
    """How a pull effect responds to the reference persona's signed regard for the
    target (#1831). OFFENSIVE empowered by negative regard, PROTECTIVE by positive,
    NEUTRAL by either. Only consulted by Court-role (COVENANT_ROLE) pull modulation."""

    OFFENSIVE = "offensive", "Offensive (empowered vs. disfavored target)"
    PROTECTIVE = "protective", "Protective (empowered vs. favored target)"
    NEUTRAL = "neutral", "Neutral / social (empowered by either sign)"


COURT_REGARD_PULL_K = 1.0
"""PLACEHOLDER tuning constant (#1831): empower scale at |regard|=REGARD_MAX.

Court-role pull modulation bonus = base_scaled * (abs(regard) / REGARD_MAX) * K.
Tunable via playtest.
"""


class VitalBonusTarget(models.TextChoices):
    MAX_HEALTH = "MAX_HEALTH", "Max Health"
    DAMAGE_TAKEN_REDUCTION = "DAMAGE_TAKEN_REDUCTION", "Damage Taken Reduction"
    DEATH_SAVE = "DEATH_SAVE", "Death Save"
    KNOCKOUT_RESIST = "KNOCKOUT_RESIST", "Knockout Resist"
    PERMANENT_WOUND_RESIST = "PERMANENT_WOUND_RESIST", "Permanent Wound Resist"


class RitualExecutionKind(models.TextChoices):
    SERVICE = "SERVICE", "Service"
    FLOW = "FLOW", "Flow"
    SCENE_ACTION = "SCENE_ACTION", "Scene Action"
    CEREMONY = "CEREMONY", "Ceremony"


class ParticipationRule(models.TextChoices):
    SINGLE_ACTOR = "SINGLE_ACTOR", "Single Actor"
    FORMATION = "FORMATION", "Formation (all must accept, ≥2)"
    INDUCTION = "INDUCTION", "Induction (majority of respondents)"
    BILATERAL = "BILATERAL", "Bilateral (exactly 2, both must accept)"


class ParticipantState(models.TextChoices):
    INVITED = "INVITED", "Invited"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"


class ReferenceKind(models.TextChoices):
    COVENANT = "COVENANT", "Covenant"
    COVENANT_ROLE = "COVENANT_ROLE", "Covenant Role"
    ORGANIZATION = "ORGANIZATION", "Organization"


class SoulTetherRole(models.TextChoices):
    SINEATER = "SINEATER", "Sineater"
    SINNER = "SINNER", "Sinner"


class GainSource(models.TextChoices):
    """Discriminator for ResonanceGrant audit rows. Identifies which
    typed source FK is populated on a given grant row."""

    POSE_ENDORSEMENT = "POSE_ENDORSEMENT", "Pose endorsement"
    SCENE_ENTRY = "SCENE_ENTRY", "Scene entry endorsement"
    ROOM_RESIDENCE = "ROOM_RESIDENCE", "Room residence trickle"
    OUTFIT_TRICKLE = "OUTFIT_TRICKLE", "Outfit trickle"
    STAFF_GRANT = "STAFF_GRANT", "Staff grant"
    # Plan 4 — Sanctum income + Project contribution attribution
    SANCTUM_WEAVING = "SANCTUM_WEAVING", "Sanctum weaving payout"
    SANCTUM_OWNER_BONUS = "SANCTUM_OWNER_BONUS", "Sanctum owner/member bonus"
    PROJECT_CONTRIBUTION = "PROJECT_CONTRIBUTION", "Project contribution payout"
    # Plan 4 — recovered resonance from a Ritual of Dissolution (tiered by check outcome)
    SANCTUM_DISSOLUTION_RECOVERY = (
        "SANCTUM_DISSOLUTION_RECOVERY",
        "Sanctum dissolution recovery",
    )
    # #544/#545 — social action flourishing and staff-tagged dramatic moments
    ENTRY_FLOURISH = "ENTRY_FLOURISH", "Entry flourishing"
    DRAMATIC_MOMENT = "DRAMATIC_MOMENT", "Dramatic moment"
    # #1152 — style presentation endorsement gain
    STYLE_PRESENTATION = "STYLE_PRESENTATION", "Style presentation"
    # #1737 — missions deed rewards
    MISSION_REWARD = "MISSION_REWARD", "Mission reward"
    # #1753 — resonance granted by a mission-report style (humble → Bene, embellish →
    # Insidia). No typed source FK (like STAFF_GRANT); the run is recorded on the instance.
    MISSION_REPORT = "MISSION_REPORT", "Mission report style"
    # #1770 PR3 — stakes-contract WIN reward line. No typed source FK (like
    # MISSION_REPORT); provenance lives on the stories side (StakeOutcome +
    # StakeRewardLine rows).
    STAKE_REWARD = "STAKE_REWARD", "Stake reward"
    # #1834 — distinctions grant resonance
    DISTINCTION = "DISTINCTION", "Distinction"
    # #2017 — combo discovery reward
    COMBO_DISCOVERY = "COMBO_DISCOVERY", "Combo discovery"
    # #1583 — Fall/Redemption: compromising acts grant non-native resonance
    COMPROMISE = "COMPROMISE", "Moral compromise"
    PENANCE = "PENANCE", "Atonement resonance conversion"
    FALL_CONVERSION = "FALL_CONVERSION", "Fall/Redemption conversion"


# ADR-0041 total classification of GainSource: which sources are eligible for the
# distinction earn-rate accelerator (perception/presence-driven gains a character
# actively performs to be seen/witnessed) vs. which are not (authored/system grants,
# including the DISTINCTION seed itself — accelerating a distinction's own seed grant
# would be circular). `grant_resonance` (services/resonance.py) reads this split;
# a total-classification test guards that every GainSource member lands in exactly
# one of the two sets.
ACCELERATED_GAIN_SOURCES: frozenset[str] = frozenset(
    {
        GainSource.POSE_ENDORSEMENT,
        GainSource.SCENE_ENTRY,
        GainSource.ENTRY_FLOURISH,
        GainSource.DRAMATIC_MOMENT,
        GainSource.STYLE_PRESENTATION,
        GainSource.OUTFIT_TRICKLE,
        GainSource.ROOM_RESIDENCE,
    }
)

NON_ACCELERATED_GAIN_SOURCES: frozenset[str] = frozenset(
    {
        GainSource.DISTINCTION,
        GainSource.STAFF_GRANT,
        GainSource.MISSION_REWARD,
        GainSource.MISSION_REPORT,
        GainSource.STAKE_REWARD,
        GainSource.PROJECT_CONTRIBUTION,
        GainSource.SANCTUM_WEAVING,
        GainSource.SANCTUM_OWNER_BONUS,
        GainSource.SANCTUM_DISSOLUTION_RECOVERY,
        GainSource.COMBO_DISCOVERY,
        GainSource.COMPROMISE,
        GainSource.PENANCE,
        GainSource.FALL_CONVERSION,
    }
)


# COVENANT_ROLE anchor cap tuning (use-based; issue #517).
# Additive: covenant component + legend-in-role // legend_divisor + days-held // days_divisor.
ANCHOR_CAP_COVENANT_LEVEL_MULTIPLIER: int = 10
ANCHOR_CAP_COVENANT_LEGEND_DIVISOR: int = 50
ANCHOR_CAP_COVENANT_DAYS_DIVISOR: int = 30


# FACET anchor cap tuning (Spec D §6.1)
ANCHOR_CAP_FACET_DIVISOR: int = 50
"""Divisor applied to lifetime_earned(resonance) to derive FACET anchor cap.

500 lifetime resonance → cap level 10. Tunable via playtest.
"""

ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE: int = 20
"""Hard ceiling on FACET anchor cap, scaled by character path stage.

path_stage × 20 = ceiling. At stage 1, hard max = 20 (well above path cap of 10).
At stage 6, hard max = 120 (well above path cap of 60). Prevents runaway at the
extreme tail of lifetime accumulation.
"""

ANCHOR_CAP_GIFT_PER_STAGE: int = 10
"""GIFT thread anchor cap per path stage (#1580).

path_stage × 10 = GIFT anchor cap. At stage 2, cap = 20 (matches path cap of 20).
A species gift thread can grow in lockstep with the character's path progression.
"""


class ResonanceValence(models.TextChoices):
    ALIGNED = "aligned", "Aligned (amplifies)"
    OPPOSED = "opposed", "Opposed"


class ResonanceDirection(models.TextChoices):
    ENVIRONMENT_DOMINANT = "environment", "Environment affects the caster/working"
    CASTER_DOMINANT = "caster", "Caster affects the place (defilement)"
    BALANCED = "balanced", "Mutual backlash"


class AffinityInteractionKind(models.TextChoices):
    AMPLIFY = "amplify", "Amplify"
    REJECT = "reject", "Reject"
    REPEL = "repel", "Repel"
    CORRUPT = "corrupt", "Corrupt"


class AffinityInteractionAggressor(models.TextChoices):
    ENVIRONMENT = "environment", "Environment"
    CASTER = "caster", "Caster"


# CheckType name for the OPPOSED backfire endurance roll.
# Must exactly match the seeded authored name in world/seeds/game_content/magic.py
# (_seed_endure_hallowed_ground_check). Fetched via CheckType.objects.get() — never
# get_or_create — so a missing seed propagates loudly rather than silently creating
# a chartless CheckType that would break the resolution pipeline.
ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME: str = "endure_hallowed_ground"


class PowerStage(models.TextChoices):
    BASE = "base", "Channeled intensity"
    FLAT_MODIFIER = "flat_modifier", "Power modifier"
    MULTIPLIER = "multiplier", "Power multiplier"
    TERM = "term", "Power term"
    ENVIRONMENT = "environment", "Environment"
    REACTIVE = "reactive", "Pre-cast reactive edit"
    COMBAT_PULL = "combat_pull", "Combat pull"
    PENETRATION = "penetration", "Penetration vs resistance"
    CLAMP = "clamp", "Floor / cap"


class LedgerOp(models.TextChoices):
    ADD = "add", "Add"
    MULTIPLY = "multiply", "Multiply (percent)"
    SET = "set", "Set"


class InapplicabilityReason(models.TextChoices):
    """Stable enum of reasons a thread pull cannot apply to an action context.

    Per design spec §5 — used as a chip label on the inapplicable-row UI.
    """

    WRONG_AFFINITY = "wrong_affinity", "Wrong affinity for this action"
    ANCHOR_TARGET_NOT_PRESENT = (
        "anchor_target_not_present",
        "Anchor target not present in scene",
    )
    ANCHORED_ON_OTHER_TECHNIQUE = (
        "anchored_on_other_technique",
        "Anchored on a different technique not used this round",
    )
    PREREQUISITE_UNMET = "prerequisite_unmet", "Prerequisite condition unmet"
    LOCATION_MISMATCH = "location_mismatch", "Location/property mismatch"
    THREAD_RETIRED = "thread_retired", "Thread is retired"
    COURT_LEADER_NO_STAKE = "court_leader_no_stake", "Court pull has no effect on this target"
    RELATIONSHIP_NO_STAKE = (
        "relationship_no_stake",
        "Relationship pull has no effect on this target",
    )
    OTHER = "other", "Other (see details)"


class AuthoringContext(models.TextChoices):
    """Who is authoring a technique, which selects the AuthoringPolicy.

    STAFF = unrestricted (budget advisory). PLAYER = research-unlocked,
    budget enforced. GM = level-scaled, enforced (calibration is a seam).
    CG = reserved for future character-creation from-scratch design.
    """

    STAFF = "staff", "Staff"
    GM = "gm", "Game Master"
    PLAYER = "player", "Player"
    CG = "cg", "Character Creation"


class MagicMilestoneKind(models.TextChoices):
    RESONANCE_DISCOVERY = "resonance_discovery", "Resonance Discovery"
    THREAD_WEAVING = "thread_weaving", "Thread Weaving"
    MOTIF = "motif", "Motif"
    TECHNIQUE_DEVELOPMENT = "technique_development", "Technique Development"
    ANIMA_RITUAL = "anima_ritual", "Anima Ritual"
    SECOND_GIFT = "second_gift", "Second Gift"
    STAGE_CROSSING = "stage_crossing", "Stage Crossing"


class MilestoneDiscoveryTier(models.TextChoices):
    KNOWN = "known", "Known"
    UNCOVERED = "uncovered", "Uncovered"
    UNKNOWN = "unknown", "Unknown"


class MilestoneEligibility(models.TextChoices):
    ALREADY_HAVE = "already_have", "Already Have"
    ELIGIBLE = "eligible", "Eligible"
    LOCKED = "locked", "Locked"


class TechniqueReach(models.TextChoices):
    SAME = "same", "Same position"
    ADJACENT = "adjacent", "Adjacent position"
    ANY = "any", "Anywhere in room"
    REACH_N = "reach_n", "N-hop reach"


class FuryCheckTrait(models.TextChoices):
    COMPOSURE = "composure", "Composure"
    WILLPOWER = "willpower", "Willpower"


# PLACEHOLDER anima band labels (#1446 bundle 2) — Apostate rewrite pending.
# Qualitative anima vocabulary for status surfaces (player-facing anima is narrative,
# not numerical). Mirrors vitals.constants.WOUND_DESCRIPTIONS: (min_ratio, label),
# descending, first match wins.
ANIMA_BANDS: tuple[tuple[float, str], ...] = (
    (0.95, "brimming"),
    (0.75, "vibrant"),
    (0.5, "steady"),
    (0.3, "dimmed"),
    (0.1, "guttering"),
    (0.0, "spent"),
)


def anima_band_for(current: int, maximum: int) -> str:
    """The qualitative band for an anima pool — the word status surfaces show."""
    if maximum <= 0:
        return ANIMA_BANDS[-1][1]
    ratio = current / maximum
    for threshold, label in ANIMA_BANDS:
        if ratio >= threshold:
            return label
    return ANIMA_BANDS[-1][1]


# The Rite of Imbuing's two identities (2026-07 audit). The CANONICAL seeded
# ritual is CEREMONY-kind with an empty service path, identified by NAME — the
# same identity the ImbueAction finisher and PendingRitualEffectPrerequisite
# already match on. IMBUING_SERVICE_PATH additionally marks a staff-authored
# SERVICE-dispatch variant, which RitualPerformView special-cases (thread_id
# resolution). RitualSerializer.is_imbuing exposes the combined predicate so
# web clients can find the ritual without the API leaking service paths (the
# old frontend filtered on a field the serializer never sent, making web
# imbuing unreachable on every server).
IMBUING_RITUAL_NAME = "Rite of Imbuing"
IMBUING_SERVICE_PATH = "world.magic.services.spend_resonance_for_imbuing"


def is_imbuing_ritual(*, name: str, service_function_path: str) -> bool:
    """Single predicate for "is this the Rite of Imbuing" — serializer + view share it."""
    return name.casefold() == IMBUING_RITUAL_NAME.casefold() or (
        service_function_path == IMBUING_SERVICE_PATH
    )


GHOST_TUTOR_SERVICE_PATH = "world.magic.services.ghost_tutor.summon_ghost_tutor"


def is_ghost_tutor_ritual(*, name: str, service_function_path: str) -> bool:  # noqa: ARG001
    """Whether a Ritual is the ghost-tutor summoning ritual (#2460).

    Matches on the service function path, not the name (which is
    content-authorable). Mirrors ``is_imbuing_ritual``. The ``name``
    parameter is kept for signature parity with ``is_imbuing_ritual``.
    """
    return service_function_path == GHOST_TUTOR_SERVICE_PATH


# Unbound magic-learning AP surcharge (#2442). Shared contract between the seed
# (world.seeds.character_creation.wire_magic_learning_ap_cost_target /
# ensure_unbound_drawback_distinction) and the live read at the technique-acquisition
# seam (world.magic.services.gift_acquisition.charge_and_learn). Lives here (not
# world.character_creation.constants) so the magic app — the more general/foundational
# side per ADR-0010's FK-direction rule — doesn't depend on character_creation to
# resolve its own live-play modifier.
MAGIC_LEARNING_AP_COST_TARGET_NAME = "magic_learning_ap_cost"
MAGIC_MODIFIER_CATEGORY_NAME = "magic"


class GlimpseTagAxis(models.TextChoices):
    """Narrative axis of a GlimpseTag (#2427): the four guided glimpse steps."""

    TONE = "TONE", "Tone"
    CONSEQUENCE = "CONSEQUENCE", "Consequence"
    WITNESS = "WITNESS", "Witness & Secrecy"
    SENSORY = "SENSORY", "Sensory & Discovery"


class GlimpseState(models.TextChoices):
    """Deferral/progress state of a character's Glimpse (#2427).

    A cache of prose+tag truth on CharacterAura, maintained exclusively by
    world.magic.services.glimpse — never written directly.
    """

    NOT_STARTED = "NOT_STARTED", "Not started"
    TAGS_ONLY = "TAGS_ONLY", "Tags chosen, story unwritten"
    COMPLETE = "COMPLETE", "Complete"


@dataclass(frozen=True)
class GlimpseAxisRule:
    """Select-arity + rendering rule for one glimpse axis (#2427)."""

    multi: bool
    prose_prompt: bool


#: Axis → arity/rendering config (#2427). TONE is single-select; SENSORY
#: renders as prose prompts in the writing step rather than hard tags
#: (authored SENSORY tags remain possible without a migration).
GLIMPSE_AXIS_CONFIG: dict[GlimpseTagAxis, GlimpseAxisRule] = {
    GlimpseTagAxis.TONE: GlimpseAxisRule(multi=False, prose_prompt=False),
    GlimpseTagAxis.CONSEQUENCE: GlimpseAxisRule(multi=True, prose_prompt=False),
    GlimpseTagAxis.WITNESS: GlimpseAxisRule(multi=True, prose_prompt=False),
    GlimpseTagAxis.SENSORY: GlimpseAxisRule(multi=True, prose_prompt=True),
}
