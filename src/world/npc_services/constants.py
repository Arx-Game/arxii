"""Constants for the NPC services framework."""

from django.db import models


class OfferKind(models.TextChoices):
    """Discriminator for the per-kind details model + effect handler."""

    PERMIT = "permit", "Permit"
    MISSION = "mission", "Mission"
    LOAN = "loan", "Loan"
    # #930 — the domain-running loop: dispatch a collection / invest in the domain.
    COLLECTION = "collection", "Collection"
    IMPROVEMENT = "improvement", "Improvement"
    COURT_GRANT = "court_grant", "Court Grant"
    # #1872 — promote a class-1 Functionary into a privately-owned NPCAsset.
    INFORMANT = "informant", "Informant"
    CONTACT = "contact", "Contact"
    PERSONAL_FAVOR = "personal_favor", "Personal Favor"
    # #1907 — guard/fan/minor-ally asset role_context variants.
    GUARD = "guard", "Guard"
    FAN = "fan", "Fan"
    MINOR_ALLY = "minor_ally", "Minor Ally"
    # #1905 — asset tasking: PC directs an owned asset to gather intel.
    ASSET_TASK_INTEL = "asset_task_intel", "Asset Task: Intel"
    # #2294 — PC collects accumulated income from an owned asset.
    ASSET_TASK_COLLECT = "asset_task_collect", "Asset Task: Collect"
    # #2440 — Academy/Great Archive trainer teaches a technique for AP + coin
    # + a Golden Hare (see world.npc_services.effects.run_train_offer).
    TRAIN = "train", "Train"
    # #2428 whole-branch fix — the Academy Registrar clears a learner's OWED
    # entrance obligation by redeeming a Golden Hare (see
    # world.npc_services.effects.run_settle_obligation_offer).
    SETTLE_OBLIGATION = "settle_obligation", "Settle Obligation"
    # #2632 — NPC stylist restyles one cosmetic trait for coin (menu-driven:
    # one offer per (trait, option); see run_styling_offer).
    STYLING = "styling", "Styling"
    # #2632 — Great Archive scholar records the character's profile: pays for
    # a sitting; the write-up completes via RecordedProfile (the diegetic
    # desc-update + permanent archive; see run_profile_recording_offer).
    PROFILE_RECORDING = "profile_recording", "Profile Recording"
    # Future kinds: marriage/attunement.


class DrawMode(models.TextChoices):
    """How offers on a role are surfaced to the player."""

    MENU = "menu", "Menu"  # Deterministic — every eligible offer is shown.
    POOL = "pool", "Pool"  # NPC draws a subset per visit (mission-style; #686).


# #726 — how many POOL offers an NPC surfaces, by the PC's durable standing
# (``NPCStanding.affection``). Ordered ascending by affection floor;
# ``offer_policy.mission_pool_count`` walks the bands and keeps the count of the
# highest band whose floor the standing meets. A stranger (no standing row /
# class-1 functionary) or a neutral/disliked PC lands on the first band — one
# trial job; a trusted contact reaches the ceiling. These are mechanical tuning
# values, not player-visible flavor — adjust freely.
MISSION_POOL_COUNT_FLOOR = 1
MISSION_POOL_COUNT_BANDS: tuple[tuple[int, int], ...] = (
    (0, 1),  # neutral / stranger — one trial job
    (10, 2),  # acquaintance
    (25, 3),  # trusted
    (50, 4),  # confidant
    (100, 5),  # inner circle — full slate
)

# #1020 — org-reputation lift to the POOL count for NPCs that front an org
# (``NPCRole.faction_affiliation``). Keyed on the persona's ReputationTier
# *rank* — the declaration order of ``societies.types.ReputationTier``
# (reviled=0 … unknown=4 … revered=8). Walked like MISSION_POOL_COUNT_BANDS
# (highest met floor wins). The final POOL count is
# ``max(npc-standing count, org count)``, so org favor lifts the floor without
# capping a personally-cultivated contact. Tuning values — adjust freely.
MISSION_POOL_ORG_COUNT_BANDS: tuple[tuple[int, int], ...] = (
    (0, 1),  # reviled..unknown — org connection alone gives no slate lift
    (5, 2),  # favored
    (6, 3),  # liked
    (7, 4),  # honored
    (8, 5),  # revered
)


class RegardTargetType(models.TextChoices):
    """Discriminator for what an ``NpcRegard`` row's opinion targets."""

    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
    SOCIETY = "society", "Society"


class SummonsStatus(models.TextChoices):
    """Lifecycle states for a directed offer summons (#2050)."""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"


# #2050 — affection drop per refused/expired summons. PLACEHOLDER magnitude;
# retunable by staff.
SUMMONS_REFUSAL_AFFECTION_DELTA = -5


class NpcRegardEventReason(models.TextChoices):
    """Typed cause categories for NpcRegardEvent (#2039).

    Each authoring path gets its own reason: the two combat reasons cite a
    resolved CombatRoundAction/CombatOpponentAction; SOCIAL_ACTION_RESOLVED
    cites the resolved Scene (structured-consequence path, #2039); STAKE_RESOLUTION
    cites the StakeResolution row that pre-authored it; GM_MANUAL_ADJUSTMENT may
    optionally cite any of the above; DISTINCTION_SEED cites nothing (chargen).
    """

    NPC_HARMED_PC_INTEREST = "npc_harmed_pc", "NPC harmed PC's interest"
    PC_FOILED_NPC_PLAN = "pc_foiled_npc", "PC foiled NPC's plan"
    SOCIAL_ACTION_RESOLVED = "social_action", "Social action resolved"
    STAKE_RESOLUTION = "stake_resolution", "Stake resolution fired"
    GM_MANUAL_ADJUSTMENT = "gm_manual", "GM manual adjustment"
    DISTINCTION_SEED = "distinction_seed", "CG distinction seed"


class RecordedProfileStatus(models.TextChoices):
    """Lifecycle of a Great Archive recorded profile (#2632).

    COMMISSIONED — the sitting is paid for; the write-up hasn't arrived.
    RECORDED — the profile text is finalized: it became the character's
    current description and lives in the Archive forever.
    """

    COMMISSIONED = "commissioned", "Commissioned"
    RECORDED = "recorded", "Recorded"


class ReactionMetric(models.TextChoices):
    """What a banded NPC reaction line keys off (#2632 reaction lines).

    Each metric resolves through ``reactions.METRIC_RESOLVERS`` — adding a
    metric is one enum member + one resolver function, never per-NPC code.
    ALLURE reads the character's total 'allure' modifier (the social-hotness
    axis); a fear-facing sibling joins when its name is ruled.
    """

    ALLURE = "allure", "Allure"
    MENACE = "menace", "Menace"
