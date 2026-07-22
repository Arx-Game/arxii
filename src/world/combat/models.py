"""Models for the combat system."""

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.achievements.models import DiscoverableContent

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.combat.handlers import EncounterCombatHandler

from world.combat.constants import (
    COMBO_MIN_SLOTS,
    DEFAULT_OPPONENT_MORALE,
    DEFAULT_PACE_TIMER_MINUTES,
    FLEE_BASE_DIFFICULTY,
    FLEE_COVER_BONUS,
    MAX_OPPONENT_MORALE,
    SCALING_CONFIG_BASELINE_PARTY_SIZE,
    SCALING_CONFIG_PER_AVG_LEVEL_PCT,
    SCALING_CONFIG_PER_EXTRA_MEMBER_PCT,
    ActionCategory,
    BreakContributionKind,
    ClashActionSlot,
    ClashFlavor,
    ClashResolution,
    ClashStatus,
    CombatAllegiance,
    CombatManeuver,
    ComboLearningMethod,
    DuelChallengeStatus,
    EncounterOutcome,
    EncounterType,
    EngagementLockStatus,
    LockBreakReason,
    LockInitiator,
    LockPcRole,
    OpponentStatus,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
    StrikeDelivery,
    SurgeTriggerKind,
    TargetingMode,
    TargetSelection,
)
from world.covenants.constants import RoleArchetype
from world.fatigue.constants import EffortLevel
from world.gm.constants import GMLevel
from world.magic.constants import EffectKind, VitalBonusTarget
from world.magic.models.commitments import CommittingDeclaration
from world.magic.types.aura import AffinityType
from world.scenes.round_models import AbstractRound

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
ACCOUNT_DB_MODEL = "accounts.AccountDB"
CHECK_TYPE_MODEL = "checks.CheckType"
CONSEQUENCE_POOL_MODEL = "actions.ConsequencePool"
CHARACTER_SHEET_MODEL = "character_sheets.CharacterSheet"
TECHNIQUE_MODEL = "magic.Technique"
COMBAT_PARTICIPANT_MODEL = "combat.CombatParticipant"
COMBAT_ENCOUNTER_MODEL = "combat.CombatEncounter"
OBJECTS_OBJECTDB_MODEL = "objects.ObjectDB"
POSITION_MODEL = "areas.Position"


class CombatEncounter(AbstractRound):
    """Top-level container for a combat encounter."""

    encounter_type = models.CharField(
        max_length=30,
        choices=EncounterType.choices,
        default=EncounterType.PARTY_COMBAT,
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.PROTECT,
        related_name="combat_encounters",
    )
    room = models.ForeignKey(
        OBJECTS_OBJECTDB_MODEL,
        on_delete=models.PROTECT,
        related_name="combat_encounters",
        null=True,
        blank=True,
        help_text="Room where the encounter takes place. Ephemeral CombatNPC "
        "ObjectDBs are placed here at creation.",
    )
    outcome = models.CharField(
        max_length=20,
        choices=EncounterOutcome.choices,
        blank=True,
        default="",
        help_text="Typed result recorded at completion (#876); empty until completed.",
    )
    risk_level = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        default=RiskLevel.MODERATE,
    )
    stakes_level = models.CharField(
        max_length=20,
        choices=StakesLevel.choices,
        default=StakesLevel.LOCAL,
    )
    pace_mode = models.CharField(
        max_length=20,
        choices=PaceMode.choices,
        default=PaceMode.TIMED,
    )
    pace_timer_minutes = models.PositiveIntegerField(
        default=DEFAULT_PACE_TIMER_MINUTES,
        help_text="Minutes before auto-resolving in timed mode.",
    )
    is_paused = models.BooleanField(default=False)
    escalation_curve = models.ForeignKey(
        "combat.EscalationCurve",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="encounters",
        help_text="Authored escalation ramp; null = this encounter does not escalate (#872).",
    )
    duel_winner = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duels_won",
        help_text="Recorded duel victor; null while ongoing or for an abandoned/mutual stop.",
    )
    is_champion_duel = models.BooleanField(
        default=False,
        help_text=(
            "True iff this DUEL encounter was opened by "
            "world.battles.services.open_champion_duel (#2536 slice 3 Battle wiring) — a "
            "PC Champion's duel against an enemy boss. Stamped exclusively there; every "
            "other DUEL creation path (world.combat.duels.create_lethal_duel's other "
            "callers, world.battles.services.open_siege_engine_encounter) leaves this "
            "False. Read by the Situation.CHAMPION_DUEL evaluator "
            "(world.covenants.perks.evaluators) for per-vow situational perk scoping."
        ),
    )
    opened_from_parley = models.BooleanField(
        default=False,
        help_text=(
            "True iff world.combat.cast_seed.seed_or_feed_encounter_from_cast CREATED "
            "this encounter from a hostile cast landing inside an active, non-Battle-"
            "backed Scene (#2536 slice 3, Task 4) — the same active-Scene classification "
            "the Situation.DURING_NEGOTIATION evaluator documents. Stamped only at "
            "CREATE time; feeding an existing encounter never flips it. v1 approximation "
            "(PR-body judgment call): stays True for the encounter's entire lifetime, not "
            "just its opening moment. Read by the Situation.COMBAT_OPENED_FROM_PARLEY and "
            "Situation.AMBUSH_UNDERWAY evaluators (world.covenants.perks.evaluators) for "
            "per-vow situational perk scoping."
        ),
    )
    on_chosen_ground = models.BooleanField(
        default=False,
        help_text=(
            "True iff, at CREATE time, this encounter's room held a "
            "world.room_features.models.PreparedGround whose preparer was physically "
            "present (#2646) — see world.combat.chosen_ground.compute_on_chosen_ground. "
            "Stamped exclusively at creation in the PC-vs-NPC seams "
            "(world.combat.cast_seed.seed_or_feed_encounter_from_cast, "
            "world.combat.duels.create_lethal_duel, "
            "world.battles.services.open_place_encounter); never mutated afterward. "
            "world.combat.duels.create_pvp_duel deliberately leaves this False (PvP is "
            "never lethal, so 'chosen ground' does not apply). Read by the "
            "Situation.ON_CHOSEN_GROUND evaluator (world.covenants.perks.evaluators) for "
            "per-vow situational perk scoping."
        ),
    )
    initiated_by_pc_side = models.BooleanField(
        null=True,
        blank=True,
        help_text=(
            "Who sprang this fight (#2623): True = a PC participant's action "
            "opened it, False = the opposing side did, NULL = unknown/undirected "
            "(duels, battles, staff-opened). Read by origin_side-parameterized "
            "situations. No NPC-initiated creation path exists yet — False is "
            "staff/admin-stampable until one lands."
        ),
    )
    story_beat = models.ForeignKey(
        "stories.Beat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolving_encounters",
        help_text=(
            "The one Beat this specific encounter resolves (#1760). When set, "
            "the ENCOUNTER_COMPLETED beat-wiring handler resolves only this "
            "beat with this encounter's own graded outcome — never every beat "
            "reachable from the scene. When unset, legacy find-all-on-scene "
            "behavior applies unchanged."
        ),
    )

    @cached_property
    def combat(self) -> "EncounterCombatHandler":
        """Handler for encounter-scoped combat state (clashes, actions, etc.).

        Single prefetched cache + list-comp subsets. Service-function bodies
        read from this rather than running their own raw queries. Mutation
        services call ``encounter.combat.invalidate()`` afterwards.
        """
        from world.combat.handlers import EncounterCombatHandler  # noqa: PLC0415

        return EncounterCombatHandler(self)

    @cached_property
    def is_lethal(self) -> bool:
        """Lethal iff the encounter's risk level is LETHAL. Derived, never stored."""
        return self.risk_level == RiskLevel.LETHAL

    def __str__(self) -> str:
        return (
            f"{self.get_encounter_type_display()} "
            f"(Round {self.round_number}, {self.get_status_display()})"
        )

    @property
    def forced_escape(self) -> bool:
        """True when an unbeatable Hero Killer is on the field (#875).

        Drives the "you must run" UI — victory is impossible; the party must
        flee. Cache-aware: uses prefetched ``opponents_cached`` when present
        so the detail serializer adds no query.
        """
        # Suppression justified: live combat state on identity-mapped encounter; (#2401)
        # context-over-cache.
        cached = getattr(self, "opponents_cached", None)  # noqa: GETATTR_LITERAL
        if cached is not None:
            return any(
                o.tier == OpponentTier.HERO_KILLER and o.status == OpponentStatus.ACTIVE
                for o in cached
            )
        return self.opponents.filter(
            tier=OpponentTier.HERO_KILLER, status=OpponentStatus.ACTIVE
        ).exists()


class ThreatPool(SharedMemoryModel):
    """Named collection of NPC actions."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class ThreatPoolEntry(SharedMemoryModel):
    """One possible action an NPC can take."""

    pool = models.ForeignKey(
        ThreatPool,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attack_category = models.CharField(
        max_length=20,
        choices=ActionCategory.choices,
    )
    base_damage = models.PositiveIntegerField(default=0)
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="threat_pool_entries",
        help_text="Damage type for resistance lookup. Null = untyped attack.",
    )
    weight = models.PositiveIntegerField(
        default=10,
        help_text="Selection weight",
    )
    targeting_mode = models.CharField(
        max_length=20,
        choices=TargetingMode.choices,
        default=TargetingMode.SINGLE,
    )
    delivery = models.CharField(
        max_length=10,
        choices=StrikeDelivery.choices,
        default=StrikeDelivery.MELEE,
        help_text="How this strike reaches its target — drives rampart interception (#2209).",
    )
    target_count = models.PositiveIntegerField(null=True, blank=True)
    target_selection = models.CharField(
        max_length=30,
        choices=TargetSelection.choices,
        default=TargetSelection.SPECIFIC_ROLE,
    )
    conditions_applied = models.ManyToManyField(
        "conditions.ConditionTemplate",
        blank=True,
        related_name="threat_pool_entries",
    )
    effect_properties = models.ManyToManyField(
        "mechanics.Property",
        blank=True,
        related_name="threat_pool_entries",
        help_text=(
            "Effect Properties this NPC attack carries. Drives clash-opposition "
            "matching against PC techniques' effect properties. Empty = attack "
            "cannot trigger or assist clashes."
        ),
    )
    on_hit_consequence_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Consequence pool fired unconditionally (no roll) whenever this attack "
            "lands with damage > 0 surviving Interpose. Distinct from clash_resolution_pool "
            "(clash-specific) — this fires on every successful hit. A MOVE_TO_POSITION/"
            "AWAY_FROM_ACTOR effect here is how a GM authors 'this attack knocks back.'"
        ),
    )
    defense_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="threat_pool_entries",
        help_text=(
            "CheckType the targeted PC rolls to evade/mitigate this attack. "
            "Null = flat base_damage with no defense roll (backward-compatible)."
        ),
    )
    minimum_phase = models.PositiveIntegerField(null=True, blank=True)
    cooldown_rounds = models.PositiveIntegerField(null=True, blank=True)
    requires_steady = models.BooleanField(
        default=False,
        help_text="If True, this entry is skipped when the opponent is faltering "
        "(morale_state FALTER). Lets designers author 'weakened' entries (#2015).",
    )

    # === Clash fields (Task 1.5) ===
    clash_capable = models.BooleanField(
        default=False,
        help_text="When True, this entry can initiate or sustain a Clash.",
    )
    is_lock_applying = models.BooleanField(
        default=False,
        help_text=(
            "When this attack lands on a PC, it opens a LOCK-flavor Clash — the PC must win "
            "a Break Free clash to escape. Requires `clash_break_free_force`."
        ),
    )
    is_sustained_attack = models.BooleanField(
        default=False,
        help_text=(
            "This attack is a sustained multi-round barrage that opens a WARD-flavor Clash — "
            "PCs endure it for `sustained_duration_rounds`. Distinct from `is_lock_applying`."
        ),
    )
    sustained_duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many rounds a sustained attack persists before the NPC must re-use it.",
    )
    clash_break_free_force = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The BREAK-clash PC win threshold for breaking free of a lock applied "
            "by this entry. Required when is_lock_applying=True."
        ),
    )
    clash_npc_pressure = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "NPC's per-round pressure contribution in a Clash initiated or sustained by this entry."
        ),
    )
    clash_resolution_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Consequence pool fired when a Clash initiated by this entry resolves.",
    )
    clash_per_round_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Optional per-round consequence pool fired each round of a Clash "
            "initiated by this entry."
        ),
    )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.is_lock_applying and self.clash_break_free_force is None:
            errors["clash_break_free_force"] = (
                "clash_break_free_force is required when is_lock_applying=True."
            )
        if self.is_sustained_attack and self.sustained_duration_rounds is None:
            errors["sustained_duration_rounds"] = (
                "sustained_duration_rounds is required when is_sustained_attack=True."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.pool.name}: {self.name}"


class CombatOpponent(SharedMemoryModel):
    """An NPC entity in a combat encounter."""

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="opponents",
    )
    tier = models.CharField(max_length=20, choices=OpponentTier.choices)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    health = models.IntegerField()
    max_health = models.PositiveIntegerField()
    soak_value = models.PositiveIntegerField(default=0)
    probing_current = models.PositiveIntegerField(default=0)
    probing_threshold = models.PositiveIntegerField(null=True, blank=True)
    current_phase = models.PositiveIntegerField(default=1)
    threat_pool = models.ForeignKey(
        ThreatPool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opponents",
    )
    status = models.CharField(
        max_length=20,
        choices=OpponentStatus.choices,
        default=OpponentStatus.ACTIVE,
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_opponents",
        help_text="Links to a persistent NPC identity for story NPCs.",
    )
    portrait = models.ForeignKey(
        "evennia_extensions.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_opponent_portraits",
        help_text="Direct portrait for persona-less (generic/ephemeral) NPCs. "
        "Persona-backed opponents resolve their portrait through the persona "
        "instead; this is the fallback when persona is None.",
    )
    objectdb = models.ForeignKey(
        OBJECTS_OBJECTDB_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_opponent_rows",
        help_text="The in-world ObjectDB representation. Set at creation; "
        "nulled if the ObjectDB is destroyed externally.",
    )
    objectdb_is_ephemeral = models.BooleanField(
        default=False,
        help_text="If True, the ObjectDB was created for this encounter only "
        "and will be cleaned up at encounter completion. Persona-bearing "
        "or pre-existing ObjectDBs MUST NOT be flagged ephemeral.",
    )

    # === Swarm fields (#875) — populated only for SWARM tier, null elsewhere ===
    swarm_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="SWARM tier only: bodies remaining. Damage clears bodies; "
        "DEFEATED at 0. Null for non-swarm tiers.",
    )
    max_swarm_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="SWARM tier only: bodies at encounter start.",
    )
    body_toughness = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="SWARM tier only: damage needed to kill one body. A landing "
        "attack clears max(1, raw_damage // body_toughness) bodies.",
    )
    bodies_per_attack = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="SWARM tier only: remaining-count → outgoing-attack ratio. The "
        "swarm makes ceil(swarm_count / bodies_per_attack) attacks/round, capped "
        "at the number of acting PCs.",
    )

    # === Duel fields (Task 2) ===
    mirrors_participant = models.ForeignKey(
        COMBAT_PARTICIPANT_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mirror_surface",
        help_text="If set, this opponent is a passive duel mirror of that PC participant.",
    )

    # === Foil duel fields (#2020) ===
    has_foil_behavior = models.BooleanField(
        default=False,
        help_text="Marks named NPCs that should pair off in foil duels. "
        "Informational; designers set a lower auto_lock_threshold for these.",
    )
    auto_lock_threshold = models.PositiveIntegerField(
        default=100,
        help_text="Threat value at which an autonomous engagement lock forms "
        "for this opponent. Lower for foils (e.g. 20); high default for mooks.",
    )

    # === Allegiance + summon fields (Task 1 / #1584) ===
    allegiance = models.CharField(
        max_length=10,
        choices=CombatAllegiance.choices,
        default=CombatAllegiance.ENEMY,
        help_text=(
            "Which side this combatant fights on. ENEMY (default) is hostile to "
            "PCs; ALLY fights for them (summons, charmed/switched-sides foes). "
            "Mutable — a charm flips it."
        ),
    )
    summoned_by = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="summoned_combatants",
        help_text="The character who summoned this ally; null for non-summons.",
    )
    bond_expires_round = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Encounter round_number at which a summon's bond lapses and it "
        "is dismissed; null = lasts until encounter end.",
    )

    # === Clash fields (Task 1.5) ===
    barrier_strength = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The BREAK-clash MAX threshold source; governs how hard it is for PCs "
            "to break through this opponent's barrier. PCs must accumulate this much "
            "progress in a BREAK Clash to breach the barrier (e.g. 10 = ten progress)."
        ),
    )
    barrier_break_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=("Consequence pool fired when PCs successfully break this opponent's barrier."),
    )
    aftermath_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Fired deterministically when the encounter completes in PC victory and "
            "this opponent is DEFEATED (#876). Author non-character-targeted effects."
        ),
    )
    wall_breaker_combo = models.ForeignKey(
        "combat.ComboDefinition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wall_breaker_for_opponents",
        help_text=(
            "#2051: the authored declaration of the combo intended to break this "
            "BOSS-tier opponent's wall. Required when aftermath_pool pays legend at "
            "risk ≥ LEGEND_RISK_FLOOR_TIER. Null for non-BOSS tiers or non-legend "
            "aftermath."
        ),
    )

    # === Morale fields (#2015) ===
    morale = models.PositiveSmallIntegerField(
        default=DEFAULT_OPPONENT_MORALE,
        help_text="Depletable resolve pool (#2015). Falter/break thresholds drive "
        "select_npc_actions; mindless opponents (tier template has_morale=False) "
        "resist morale checks, not immune to them.",
    )
    max_morale = models.PositiveSmallIntegerField(
        default=MAX_OPPONENT_MORALE,
        help_text="Ceiling for morale; RALLY restores toward it.",
    )

    # === Boss anatomy fields (#2016) ===
    actions_per_round = models.PositiveIntegerField(
        default=1,
        help_text="Runtime: stamped from tier template, updated on phase transition.",
    )
    damage_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Runtime: stamped from phase template at transition.",
    )
    break_bar_threshold = models.PositiveIntegerField(
        default=0,
        help_text="0 = no break bar; scaled by party_mult at spawn time.",
    )
    break_bar_current = models.PositiveIntegerField(
        default=0,
        help_text="Current bar progress (counts down toward 0 = broken).",
    )
    vulnerability_rounds_remaining = models.PositiveIntegerField(
        default=0,
        help_text="0 = not vulnerable; >0 = vulnerability window active.",
    )
    vulnerability_rounds = models.PositiveIntegerField(
        default=0,
        help_text="Authored window duration; stamped from BreakBarConfig at spawn.",
    )
    vulnerability_intensity_bonus = models.PositiveIntegerField(
        default=0,
        help_text="Intensity bonus during vulnerability window; from BreakBarConfig.",
    )

    # === Boss-fight structure: lieutenant gate (#2642) ===
    reinforces = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reinforced_by",
        help_text=(
            "Lieutenant->boss edge (#2642): set on a lieutenant opponent to the "
            "BOSS-tier opponent it reinforces. Read by assess_break_bar's "
            "lieutenant gate — an active, unsuppressed lieutenant slows the "
            "boss's break-bar depletion proportionally. Null for non-lieutenant "
            "opponents (including the boss itself)."
        ),
    )

    # === Affinity field (#2536 slice 3 Task 6) ===
    affinity = models.CharField(
        max_length=20,
        choices=AffinityType.choices,
        blank=True,
        default="",
        help_text=(
            "Authored magical affinity for non-persona NPCs (generic/ephemeral "
            "opponents carry no CharacterAura row to infer from). Blank = "
            "untyped/unauthored — the ATTACKER_AFFINITY situational-perk evaluator "
            "(world.covenants.perks.evaluators) falls back to a reachable "
            "ObjectDB's CharacterAura.dominant_affinity when this is blank."
        ),
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(persona__isnull=True) | Q(objectdb_is_ephemeral=False),
                name="persona_bearing_opponent_not_ephemeral",
            ),
            models.UniqueConstraint(
                fields=["encounter", "objectdb"],
                condition=Q(objectdb__isnull=False),
                name="combatopponent_unique_objectdb_per_encounter",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self._validate_wall_breaker_combo()
        if not self.objectdb_is_ephemeral:
            return
        from world.combat.services import (  # noqa: PLC0415
            has_persistent_identity_references,
            is_combat_npc_typeclass,
        )

        if self.objectdb is None:
            raise ValidationError({"objectdb": "Ephemeral CombatOpponent must have an ObjectDB."})
        if self.persona is not None:
            raise ValidationError(
                {"objectdb_is_ephemeral": ("Persona-bearing CombatOpponent cannot be ephemeral.")}
            )
        if not is_combat_npc_typeclass(self.objectdb):
            raise ValidationError(
                {
                    "objectdb_is_ephemeral": (
                        "Only CombatNPC-typeclass ObjectDBs can be marked ephemeral."
                    )
                }
            )
        if has_persistent_identity_references(self.objectdb):
            raise ValidationError(
                {
                    "objectdb_is_ephemeral": (
                        "ObjectDB has persistent identity references; cannot be marked ephemeral."
                    )
                }
            )

    def _aftermath_pays_legend(self) -> bool:
        """Return True if this opponent's aftermath_pool contains a LEGEND_AWARD effect (#2051)."""
        if self.aftermath_pool_id is None:
            return False
        from world.checks.constants import EffectType  # noqa: PLC0415
        from world.checks.models import ConsequenceEffect  # noqa: PLC0415

        return ConsequenceEffect.objects.filter(
            consequence__pool_entries__pool=self.aftermath_pool,
            effect_type=EffectType.LEGEND_AWARD,
        ).exists()

    def _validate_wall_breaker_combo(self) -> None:
        """Boss wall-breaker guard (#2051).

        A BOSS-tier opponent whose aftermath_pool pays legend requires a
        ``wall_breaker_combo`` that is set, active (not hidden or has at least
        one learning), and has ≥ COMBO_MIN_SLOTS slots. HERO_KILLER is
        unbeatable by design and not combo-gated.
        """
        if self.tier != OpponentTier.BOSS:
            return
        if not self._aftermath_pays_legend():
            return
        if self.wall_breaker_combo_id is None:
            msg = (
                "A BOSS-tier opponent with a legend-paying aftermath_pool requires "
                "a wall_breaker_combo (#2051)."
            )
            raise ValidationError({"wall_breaker_combo": msg})
        combo = self.wall_breaker_combo
        if combo is not None and combo.slots.count() < COMBO_MIN_SLOTS:
            msg = (
                f"wall_breaker_combo '{combo.name}' has fewer than {COMBO_MIN_SLOTS} "
                "slots — a wall-breaker must be a real multi-PC combo (#2051)."
            )
            raise ValidationError({"wall_breaker_combo": msg})

    @property
    def is_duel_mirror(self) -> bool:
        """True when this opponent is a passive duel-mirror surface for a PC participant."""
        return self.mirrors_participant_id is not None

    @property
    def health_percentage(self) -> float:
        if self.max_health == 0:
            return 0.0
        return max(0.0, self.health / self.max_health)

    @cached_property
    def current_position(self) -> "Position | None":
        """Return the Position this opponent's ObjectDB currently occupies, or None.

        Derived — never stored. Returns None if objectdb is null (ephemeral NPC
        whose ObjectDB was destroyed externally) or if the ObjectDB has no
        ObjectPosition row.
        """
        from world.areas.positioning.services import position_of  # noqa: PLC0415

        if self.objectdb_id is None:
            return None
        return position_of(self.objectdb)

    def __str__(self) -> str:
        return f"{self.name} ({self.get_tier_display()})"


class AbstractPhaseConfig(SharedMemoryModel):
    """Shared phase fields used by both BossPhase (runtime) and
    CreaturePhaseTemplate (authored bestiary).

    Concrete subclasses add their own owner FK (opponent or creature_template)
    and any runtime-only fields.
    """

    class Meta:
        abstract = True

    phase_number = models.PositiveIntegerField()
    threat_pool = models.ForeignKey(
        ThreatPool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    soak_value = models.PositiveIntegerField(default=0)
    probing_threshold = models.PositiveIntegerField(null=True, blank=True)
    health_trigger_percentage = models.FloatField(null=True, blank=True)
    description = models.TextField(blank=True)
    actions_per_round = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Phase override; null = inherit tier template default.",
    )
    damage_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Enrage damage multiplier for this phase.",
    )
    extra_actions = models.PositiveIntegerField(
        default=0,
        help_text="Additional actions beyond actions_per_round.",
    )
    reinforcement_template = models.ForeignKey(
        "CreatureTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="CreatureTemplate to spawn as adds on phase entry.",
    )
    reinforcement_count = models.PositiveIntegerField(default=0)


class BossPhase(AbstractPhaseConfig):
    """One stage of a boss fight (runtime row on a CombatOpponent)."""

    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    # Runtime break-bar fields — stamped from BreakBarConfig at spawn time.
    break_bar_threshold = models.PositiveIntegerField(
        default=0,
        help_text="Break-bar threshold; 0 = no bar for this phase.",
    )
    vulnerability_rounds = models.PositiveIntegerField(
        default=0,
        help_text="Window duration; stamped from BreakBarConfig at spawn.",
    )
    vulnerability_intensity_bonus = models.PositiveIntegerField(
        default=0,
        help_text="Intensity bonus during window; from BreakBarConfig.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opponent", "phase_number"],
                name="unique_phase_per_opponent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.opponent.name} Phase {self.phase_number}"


class ComboDefinition(DiscoverableContent, SharedMemoryModel):
    """Staff-authored combo that multiple PCs can trigger together."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    hidden = models.BooleanField(
        default=True,
        help_text="Hidden until learned by at least one PC.",
    )
    discoverable_via_training = models.BooleanField(default=True)
    discoverable_via_combat = models.BooleanField(default=True)
    discoverable_via_research = models.BooleanField(default=False)
    minimum_probing = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Probing counter required on target before this combo is available.",
    )
    bypass_soak = models.BooleanField(
        default=True,
        help_text="Whether combo damage bypasses the target's soak value.",
    )
    bonus_damage = models.PositiveIntegerField(
        default=0,
        help_text="Flat bonus damage added when the combo fires.",
    )
    discovery_first_body = models.TextField(
        blank=True,
        help_text=(
            "Gamewide announcement body for first-ever discovery. Must NOT name the "
            "discoverer. Example: 'For the first time, a covenant has unleashed "
            "Firestorm Fusion in battle.'"
        ),
    )
    discovery_personal_body = models.TextField(
        blank=True,
        help_text=(
            "Personal announcement body for repeat discovery. Example: "
            "'Your covenant has discovered Firestorm Fusion.'"
        ),
    )

    # === Clash fields (Task 1.5) ===
    required_clash_flavor = models.CharField(
        max_length=10,
        choices=ClashFlavor.choices,
        null=True,
        blank=True,
        help_text=(
            "If set, this combo is only available during a Clash of the specified flavor. "
            "Null means the combo is not clash-gated."
        ),
    )
    required_clash_window_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Clash-window gate: the target must have an active instance of this condition "
            "for the combo to be available. Null means no window condition is required."
        ),
    )

    def clean(self) -> None:
        """Validate the combo invariant: minimum 2 slots (#2051).

        Combos are structurally multi-PC — a solo player cannot fill 2+ distinct
        action slots. This check catches programmatic edits and raw ORM saves
        once slots exist. Admin creation is guarded separately by
        ``ComboSlotInline.min_num``.

        At creation time (before slots are saved), this is a no-op: Django's
        admin ``save_model`` → ``save_related`` ordering means slots are written
        after the definition, so ``self.pk`` may be set but ``slots`` is empty.
        The admin inline's ``min_num=2, validate_min=True`` is the creation-time
        guard; this ``clean()`` is the post-creation belt.
        """
        super().clean()
        if self.pk is not None:
            slot_count = self.slots.count()
            if slot_count < COMBO_MIN_SLOTS:
                msg = (
                    f"Combo '{self.name}' has {slot_count} slot(s); combos require "
                    "at least 2 slots (they are never solo — #2051)."
                )
                raise ValidationError({"slots": msg})

    def __str__(self) -> str:
        return self.name


class ComboSlot(SharedMemoryModel):
    """One required participant slot in a combo definition."""

    combo = models.ForeignKey(
        ComboDefinition,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    slot_number = models.PositiveIntegerField()
    required_action_type = models.ForeignKey(
        "magic.EffectType",
        on_delete=models.PROTECT,
        related_name="combo_slots",
        help_text="The EffectType the PC's focused action must match.",
    )
    resonance_requirement = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combo_slots",
        help_text="Required resonance on the technique's gift. Null means any.",
    )
    required_archetype = models.CharField(
        max_length=20,
        choices=RoleArchetype.choices,
        blank=True,
        default="",
        help_text=(
            "#2022: Required covenant role archetype for this slot's participant. "
            "Blank means any archetype. Lets authored combos require specific role "
            "composition (e.g. Slot 1: SWORD, Slot 2: SHIELD)."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["combo", "slot_number"],
                name="unique_slot_per_combo",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.combo.name} Slot {self.slot_number}"


class ComboLearning(SharedMemoryModel):
    """Record that a PC knows a particular combo."""

    combo = models.ForeignKey(
        ComboDefinition,
        on_delete=models.CASCADE,
        related_name="learnings",
    )
    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="combo_learnings",
    )
    learned_via = models.CharField(
        max_length=20,
        choices=ComboLearningMethod.choices,
    )
    learned_at = models.DateTimeField(auto_now_add=True)
    use_count = models.PositiveIntegerField(
        default=0,
        help_text="Times this combo has fired for this character.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["combo", "character_sheet"],
                name="unique_combo_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} knows {self.combo.name}"


class ComboSignature(SharedMemoryModel):
    """Authored narrative flourish for a covenant's repeated use of a combo.

    One row per (covenant, combo). Unlocks when the covenant's total member
    use_count meets unlock_threshold. Pure narrative — no mechanical rider.
    """

    covenant = models.ForeignKey(
        "covenants.Covenant",
        on_delete=models.CASCADE,
        related_name="combo_signatures",
    )
    combo = models.ForeignKey(
        ComboDefinition,
        on_delete=models.CASCADE,
        related_name="signatures",
    )
    signature_name = models.CharField(max_length=200)
    flourish_narrative = models.TextField(
        blank=True,
        help_text="Cosmetic clause appended to the finisher beat.",
    )
    unlock_threshold = models.PositiveIntegerField(
        default=3,
        help_text="Total covenant-member use_count required to unlock.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant", "combo"],
                name="unique_signature_per_covenant_combo",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.signature_name} ({self.covenant} / {self.combo})"


class CombatParticipant(SharedMemoryModel):
    """A PC in a combat encounter."""

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="combat_participations",
    )
    covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_participations",
    )
    status = models.CharField(
        max_length=20,
        choices=ParticipantStatus.choices,
        default=ParticipantStatus.ACTIVE,
    )
    insight_used = models.BooleanField(
        default=False,
        help_text=(
            "#2645: True once this participant has produced their once-per-encounter "
            "Insight (the Know need's ace). A per-encounter row needs no reset "
            "machinery — a fresh encounter mints a fresh CombatParticipant."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "character_sheet"],
                name="unique_participant_per_encounter",
            ),
        ]

    @property
    def available_strain(self) -> int:
        """Strain budget for the round — currently the character's anima pool.

        v1: returns CharacterAnima.current. The frontend's YourTurn strain
        slider reads this as the slider's max. Future iterations may move
        per-clash-strain-already-committed subtraction server-side; the
        current frontend manages that client-side.

        Returns 0 if the character has no CharacterAnima row (defensive).
        """
        try:
            return self.character_sheet.character.anima.current
        except AttributeError:
            return 0

    @cached_property
    def current_position(self) -> "Position | None":
        """Return the Position this participant's character currently occupies, or None.

        Derived — never stored. Returns None if the character has no ObjectPosition row.
        """
        from world.areas.positioning.services import position_of  # noqa: PLC0415

        obj = self.character_sheet.character
        return position_of(obj) if obj is not None else None

    def __str__(self) -> str:
        if self.covenant_role_id:
            return f"{self.character_sheet} ({self.covenant_role.name})"
        return f"{self.character_sheet}"


class CombatRoundAction(CommittingDeclaration, SharedMemoryModel):
    """A PC's declared actions for a round."""

    confirm_soulfray_risk = models.BooleanField(
        default=False,
        help_text="Player accepted the soulfray risk for this declared cast.",
    )
    from_entrance = models.BooleanField(
        default=False,
        help_text="True when this declared action originated as a dramatic technique "
        "entrance cast (#2183), stamped by seed_or_feed_encounter_from_cast so a later "
        "task can fire recognition when the declared cast resolves.",
    )
    participant = models.ForeignKey(
        CombatParticipant,
        on_delete=models.CASCADE,
        related_name="round_actions",
    )
    round_number = models.PositiveIntegerField()
    focused_category = models.CharField(
        max_length=20,
        choices=ActionCategory.choices,
        null=True,
        blank=True,
    )
    effort_level = models.CharField(
        max_length=20,
        choices=EffortLevel.choices,
        default=EffortLevel.MEDIUM,
    )
    focused_action = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        help_text="Null when player did not declare (passives only).",
    )
    is_ready = models.BooleanField(
        default=False,
        help_text="Player signals they are done with declaration and combo decisions.",
    )
    focused_opponent_target = models.ForeignKey(
        CombatOpponent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    focused_ally_target = models.ForeignKey(
        "CombatParticipant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    maneuver = models.CharField(
        max_length=20,
        choices=CombatManeuver.choices,
        null=True,
        blank=True,
        help_text=(
            "Special maneuver this declaration is "
            "(flee/cover/yield/interpose/use_item); null = normal action."
        ),
    )
    item_instance = models.ForeignKey(
        "items.ItemInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Item to use when maneuver == USE_ITEM.",
    )
    succor_resolution = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Cached graded outcome (0.0/0.5/1.0) of this round's Succor resolution, set on "
            "first dispatch and reused for every subsequent hazard row the same round (#1744)."
        ),
    )

    physical_passive = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    social_passive = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    mental_passive = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    combo_upgrade = models.ForeignKey(
        ComboDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="round_actions",
        help_text="If this action was upgraded to a combo, which combo.",
    )
    cast_destination = models.ForeignKey(
        POSITION_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Declared cast destination for single-position techniques "
            "(Phase Jump / Force Grip / zone hazards). Null when the cast "
            "targets no position. (#2206)"
        ),
    )
    cast_position_a = models.ForeignKey(
        POSITION_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="First endpoint of a declared position pair (Barricade). (#2206)",
    )
    cast_position_b = models.ForeignKey(
        POSITION_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Second endpoint of a declared position pair (Barricade). (#2206)",
    )
    redirect_opponent_target = models.ForeignKey(
        CombatOpponent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Declared redirect destination — a chosen-enemy CombatOpponent (#2210). "
            "Mutually exclusive with redirect_object_target; both null means 'away' "
            "(the universal fallback)."
        ),
    )
    redirect_object_target = models.ForeignKey(
        OBJECTS_OBJECTDB_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Declared redirect destination — a volatile object in the encounter room "
            "(#2210). ObjectDB is correct here (any object may be volatile), not a "
            "narrower model. Mutually exclusive with redirect_opponent_target; both "
            "null means 'away' (the universal fallback)."
        ),
    )
    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_round_actions",
        db_constraint=False,
        help_text=(
            "The ACTION-mode Interaction created when this round-action "
            "resolved. Null for unresolved declarations and for legacy rows "
            "predating this PR."
        ),
    )
    interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Denormalized from interaction.timestamp. Required because "
            "scenes_interaction is range-partitioned by timestamp — the composite "
            "FK constraint targets (interaction_id, interaction_timestamp). "
            "Populated atomically with interaction_id by create_action_interaction."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "round_number"],
                name="unique_action_per_participant_per_round",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.focused_opponent_target_id and self.focused_ally_target_id:
            msg = "Action cannot target both an opponent and an ally simultaneously."
            raise ValidationError(msg)
        if self.redirect_opponent_target_id and self.redirect_object_target_id:
            msg = "A redirect declaration cannot target both an enemy and an object."
            raise ValidationError(msg)

    def __str__(self) -> str:
        action_name = self.focused_action.name if self.focused_action else "passives only"
        return f"{self.participant} Round {self.round_number}: {action_name}"


class CombatRoundActionTarget(SharedMemoryModel):
    """Extra-target join table for AoE / multi-target CombatRoundActions (#1321).

    For AREA and FILTERED_GROUP techniques, every targeted ``CombatOpponent``
    gets one row here.  SINGLE and SELF techniques leave this table empty and
    read ``CombatRoundAction.focused_opponent_target`` directly (backward-compat).

    The primary opponent is ALSO stored here alongside the secondary targets so
    that AoE loops can iterate a single queryset without a union.

    No FK to ObjectDB — always FK to the typed ``CombatOpponent`` model.
    """

    action = models.ForeignKey(
        CombatRoundAction,
        on_delete=models.CASCADE,
        related_name="extra_targets",
        help_text="The round action that owns this target list.",
    )
    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="action_targets",
        help_text="Targeted opponent; null is reserved for future ally-AoE rows.",
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"CombatRoundActionTarget(action={self.action_id}, opponent={self.opponent_id})"


class CombatOpponentAction(SharedMemoryModel):
    """NPC action for a round."""

    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        related_name="round_actions",
    )
    round_number = models.PositiveIntegerField()
    threat_entry = models.ForeignKey(
        ThreatPoolEntry,
        on_delete=models.CASCADE,
        related_name="+",
    )
    targets = models.ManyToManyField(
        CombatParticipant,
        related_name="incoming_attacks",
    )
    opponent_targets = models.ManyToManyField(
        CombatOpponent,
        related_name="incoming_opponent_attacks",
        help_text="Opponent targets (#1584): an ALLY summon attacks ENEMY "
        "opponents. Exactly one of targets / opponent_targets is populated per "
        "action — the participant pool when it has hostile PCs, else this.",
    )

    def __str__(self) -> str:
        return f"{self.opponent.name} Round {self.round_number}: {self.threat_entry.name}"


# =============================================================================
# Resonance Pivot Spec A — Phase 6: CombatPull + CombatPullResolvedEffect
# Spec §2.1 lines 459-540, §3.8 lines 1016-1104.
# =============================================================================


class CombatPull(SharedMemoryModel):
    """Per-(participant, round) commit envelope for a thread pull in combat.

    Captures the resonance/tier/threads spent for a participant's pull in a
    specific round. Resolved effects are snapshotted into CombatPullResolvedEffect
    rows so that mid-round edits to authoring (or Thread.level) cannot
    retroactively change a committed pull. Spec §2.1 lines 459-466.
    """

    participant = models.ForeignKey(
        COMBAT_PARTICIPANT_MODEL,
        on_delete=models.CASCADE,
        related_name="combat_pulls",
    )
    encounter = models.ForeignKey(
        COMBAT_ENCOUNTER_MODEL,
        on_delete=models.CASCADE,
        related_name="combat_pulls",
    )
    round_number = models.PositiveIntegerField()
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="combat_pulls",
    )
    tier = models.PositiveSmallIntegerField()  # 1, 2, or 3
    threads = models.ManyToManyField(
        "magic.Thread",
        related_name="combat_pulls",
    )
    resonance_spent = models.PositiveIntegerField()
    anima_spent = models.PositiveIntegerField()
    committed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("participant", "round_number"),)
        indexes = [
            models.Index(fields=["encounter", "round_number"]),
        ]

    def __str__(self) -> str:
        return (
            f"CombatPull(participant={self.participant_id} "
            f"round={self.round_number} tier={self.tier})"
        )


class CombatPullResolvedEffect(SharedMemoryModel):
    """Frozen runtime snapshot of one resolved pull effect.

    Captured at pull-commit time. ``scaled_value`` is already multiplied by
    ``level_multiplier`` so subsequent changes to authoring rows or
    ``Thread.level`` cannot retroactively alter what a committed pull granted.

    Per spec §2.1 lines 530-533: clean() and CheckConstraints enforce that
    exactly one of scaled_value / granted_capability / narrative_snippet is
    populated per kind, mirroring ThreadPullEffect.clean().
    """

    pull = models.ForeignKey(
        CombatPull,
        on_delete=models.CASCADE,
        related_name="resolved_effects",
    )
    kind = models.CharField(max_length=32, choices=EffectKind.choices)
    authored_value = models.IntegerField(null=True, blank=True)
    level_multiplier = models.PositiveSmallIntegerField()
    scaled_value = models.IntegerField(null=True, blank=True)
    vital_target = models.CharField(
        max_length=32,
        choices=VitalBonusTarget.choices,
        null=True,
        blank=True,
    )
    source_thread = models.ForeignKey(
        "magic.Thread",
        on_delete=models.PROTECT,
        related_name="resolved_pull_effects",
    )
    source_thread_level = models.PositiveSmallIntegerField()
    source_tier = models.PositiveSmallIntegerField()  # 0..pull.tier
    granted_capability = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="combat_pull_grants",
    )
    narrative_snippet = models.TextField(blank=True)
    resistance_damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="combat_pull_resistances",
        help_text="Damage type a RESISTANCE effect mitigates. Null = all damage types (#1580).",
    )

    class Meta:
        # String literals match EffectKind.choices values; constraint coverage in
        # CombatPullResolvedEffectCheckConstraintTests guards against drift. Mirrors
        # ThreadPullEffect's pattern for consistency across pull-effect models.
        constraints = [
            # FLAT_BONUS: requires scaled_value, forbids capability/narrative/vital_target.
            models.CheckConstraint(
                check=(
                    ~models.Q(kind="FLAT_BONUS")
                    | (
                        models.Q(scaled_value__isnull=False)
                        & models.Q(granted_capability__isnull=True)
                        & models.Q(narrative_snippet="")
                        & models.Q(vital_target__isnull=True)
                    )
                ),
                name="combatpullresolvedeffect_flat_bonus_payload",
            ),
            # INTENSITY_BUMP: same shape as FLAT_BONUS.
            models.CheckConstraint(
                check=(
                    ~models.Q(kind="INTENSITY_BUMP")
                    | (
                        models.Q(scaled_value__isnull=False)
                        & models.Q(granted_capability__isnull=True)
                        & models.Q(narrative_snippet="")
                        & models.Q(vital_target__isnull=True)
                    )
                ),
                name="combatpullresolvedeffect_intensity_bump_payload",
            ),
            # VITAL_BONUS: requires scaled_value AND vital_target,
            # forbids capability/narrative.
            models.CheckConstraint(
                check=(
                    ~models.Q(kind="VITAL_BONUS")
                    | (
                        models.Q(scaled_value__isnull=False)
                        & models.Q(vital_target__isnull=False)
                        & models.Q(granted_capability__isnull=True)
                        & models.Q(narrative_snippet="")
                    )
                ),
                name="combatpullresolvedeffect_vital_bonus_payload",
            ),
            # CAPABILITY_GRANT: requires granted_capability, forbids scaled_value
            # / narrative / vital_target.
            models.CheckConstraint(
                check=(
                    ~models.Q(kind="CAPABILITY_GRANT")
                    | (
                        models.Q(granted_capability__isnull=False)
                        & models.Q(scaled_value__isnull=True)
                        & models.Q(narrative_snippet="")
                        & models.Q(vital_target__isnull=True)
                    )
                ),
                name="combatpullresolvedeffect_capability_grant_payload",
            ),
            # NARRATIVE_ONLY: requires non-empty snippet, forbids all other payloads.
            models.CheckConstraint(
                check=(
                    ~models.Q(kind="NARRATIVE_ONLY")
                    | (
                        ~models.Q(narrative_snippet="")
                        & models.Q(scaled_value__isnull=True)
                        & models.Q(granted_capability__isnull=True)
                        & models.Q(vital_target__isnull=True)
                    )
                ),
                name="combatpullresolvedeffect_narrative_only_payload",
            ),
            # RESISTANCE: requires scaled_value (resistance_amount × level_multiplier),
            # forbids capability/narrative/vital_target. resistance_damage_type is
            # optional (null = all damage types) (#1580).
            models.CheckConstraint(
                check=(
                    ~models.Q(kind="RESISTANCE")
                    | (
                        models.Q(scaled_value__isnull=False)
                        & models.Q(granted_capability__isnull=True)
                        & models.Q(narrative_snippet="")
                        & models.Q(vital_target__isnull=True)
                    )
                ),
                name="combatpullresolvedeffect_resistance_payload",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"CombatPullResolvedEffect(pull={self.pull_id} "
            f"kind={self.kind} src_tier={self.source_tier})"
        )

    def clean(self) -> None:
        super().clean()
        validators = {
            EffectKind.FLAT_BONUS: self._clean_flat_bonus,
            EffectKind.INTENSITY_BUMP: self._clean_intensity_bump,
            EffectKind.VITAL_BONUS: self._clean_vital_bonus,
            EffectKind.CAPABILITY_GRANT: self._clean_capability_grant,
            EffectKind.NARRATIVE_ONLY: self._clean_narrative_only,
            EffectKind.RESISTANCE: self._clean_resistance,
        }
        validator = validators.get(self.kind)
        if validator is not None:
            validator()

    def _require_scaled_value_only(self) -> None:
        """FLAT_BONUS / INTENSITY_BUMP shape: scaled_value populated; others empty."""
        if self.scaled_value is None:
            raise ValidationError({"scaled_value": "Required for this kind."})
        if self.granted_capability is not None:
            raise ValidationError({"granted_capability": "Must be null for this kind."})
        if self.narrative_snippet:
            raise ValidationError({"narrative_snippet": "Must be empty for this kind."})
        if self.vital_target:
            raise ValidationError({"vital_target": "Must be null for this kind."})

    def _clean_flat_bonus(self) -> None:
        self._require_scaled_value_only()

    def _clean_intensity_bump(self) -> None:
        self._require_scaled_value_only()

    def _clean_vital_bonus(self) -> None:
        if self.scaled_value is None:
            raise ValidationError({"scaled_value": "Required for VITAL_BONUS."})
        if not self.vital_target:
            raise ValidationError({"vital_target": "VITAL_BONUS requires vital_target."})
        if self.granted_capability is not None:
            raise ValidationError({"granted_capability": "Must be null for VITAL_BONUS."})
        if self.narrative_snippet:
            raise ValidationError({"narrative_snippet": "Must be empty for VITAL_BONUS."})

    def _clean_capability_grant(self) -> None:
        if self.granted_capability is None:
            raise ValidationError(
                {"granted_capability": "CAPABILITY_GRANT requires granted_capability."}
            )
        if self.scaled_value is not None:
            raise ValidationError({"scaled_value": "Must be null for CAPABILITY_GRANT."})
        if self.narrative_snippet:
            raise ValidationError({"narrative_snippet": "Must be empty for CAPABILITY_GRANT."})
        if self.vital_target:
            raise ValidationError({"vital_target": "Must be null for CAPABILITY_GRANT."})

    def _clean_narrative_only(self) -> None:
        # DB constraint only checks != "". clean() is stricter; bypassing clean() can
        # persist whitespace-only snippets.
        if not self.narrative_snippet.strip():
            raise ValidationError({"narrative_snippet": "NARRATIVE_ONLY requires snippet."})
        if self.scaled_value is not None:
            raise ValidationError({"scaled_value": "Must be null for NARRATIVE_ONLY."})
        if self.granted_capability is not None:
            raise ValidationError({"granted_capability": "Must be null for NARRATIVE_ONLY."})
        if self.vital_target:
            raise ValidationError({"vital_target": "Must be null for NARRATIVE_ONLY."})

    def _clean_resistance(self) -> None:
        # RESISTANCE shape mirrors FLAT_BONUS (scaled_value only); resistance_damage_type
        # is optional (null = all damage types) so it is not validated here (#1580).
        self._require_scaled_value_only()


# =============================================================================
# Consumer-owned bridge: one declared action per (encounter, round, participant)
# =============================================================================


class RoundChallengeDeclaration(SharedMemoryModel):
    """Consumer-owned bridge recording a participant's challenge declaration for a round.

    Mutually exclusive with CombatRoundAction for the same (encounter, round,
    participant) — ``CombatRoundContext.record_declaration`` enforces the invariant
    by deleting the competing row before writing this one, and vice versa.

    The combat app owns this bridge; the mechanics app gets no FK back into combat
    (project rule: bridge tables over cross-system FKs).
    """

    encounter = models.ForeignKey(
        COMBAT_ENCOUNTER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_declarations",
    )
    round_number = models.PositiveIntegerField()
    participant = models.ForeignKey(
        COMBAT_PARTICIPANT_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_declarations",
    )
    challenge_instance = models.ForeignKey(
        "mechanics.ChallengeInstance",
        on_delete=models.CASCADE,
        related_name="combat_declarations",
    )
    challenge_approach = models.ForeignKey(
        "mechanics.ChallengeApproach",
        on_delete=models.CASCADE,
        related_name="combat_declarations",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "round_number", "participant"],
                name="one_challenge_declaration_per_round",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"RoundChallengeDeclaration("
            f"encounter={self.encounter_id} "
            f"round={self.round_number} "
            f"participant={self.participant_id})"
        )


# =============================================================================
# Clash tuning singletons (Task 1.2)
# =============================================================================


class StrainConfig(SharedMemoryModel):
    """Singleton tuning surface (pk=1) for the anima→modifier diminishing-returns curve.

    ``conversion_base`` is the base unit for converting raw anima commitment
    into a modifier value.  ``diminishing_step`` controls how quickly successive
    units are worth less.  ``diminishing_floor`` is the minimum value any unit
    can contribute.
    """

    objects = ArxSharedMemoryManager()

    conversion_base = models.PositiveIntegerField(
        default=10,
        help_text="Base anima units required per +1 modifier step.",
    )
    diminishing_step = models.PositiveIntegerField(
        default=5,
        help_text="Additional anima required per step above the first (diminishing returns).",
    )
    diminishing_floor = models.PositiveIntegerField(
        default=1,
        help_text="Minimum modifier contribution any anima unit can produce.",
    )
    base_anima_fatigue_ratio = models.PositiveIntegerField(
        default=25,
        help_text=(
            "Percentage of non-strain anima spent that converts to fatigue "
            "(e.g. 25 = 25% = 0.25×). 0 = no fatigue from base casts."
        ),
    )
    strain_anima_fatigue_ratio = models.PositiveIntegerField(
        default=50,
        help_text=(
            "Percentage of strain_commitment anima that converts to fatigue "
            "(e.g. 50 = 50% = 0.50×). Set higher than base_anima_fatigue_ratio "
            "to make pushing harder proportionally more tiring."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="strain_config_updates",
    )

    def __str__(self) -> str:
        return f"StrainConfig(pk={self.pk})"


class ClashConfig(SharedMemoryModel):
    """Singleton tuning surface (pk=1) for clash contest math.

    ``affinity_tilt_coefficient`` scales how much affinity alignment shifts the
    final progress delta.  ``passive_anima_cap`` limits how much anima a passive
    contribution can commit.  ``break_abandon_idle_rounds`` controls how many
    consecutive zero-contribution rounds a BREAK clash tolerates before it
    auto-resolves as ABANDONED.  ``max_round_cap`` is the hard upper limit after
    which any CLASH resolves as MUTUAL.

    Power-formula knobs (used by ``outcome_to_delta`` in clash.py):
    - ``power_scale``: overall scalar applied to power before multiplying by quality.
    - ``quality_multiplier_*``: per-tier quality coefficients; use
      ``quality_multiplier_for(success_level)`` to look up the right one.
    - ``botch_backfire_fraction``: fraction of power fed back as a negative delta
      on a botch (handled by the caller, not by ``quality_multiplier_for``).
    """

    objects = ArxSharedMemoryManager()

    affinity_tilt_coefficient = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.25"),
        help_text="Fraction by which affinity alignment tilts the progress delta.",
    )
    passive_anima_cap = models.PositiveIntegerField(
        default=20,
        help_text="Maximum anima a passive contribution may commit per round.",
    )
    break_abandon_idle_rounds = models.PositiveIntegerField(
        default=2,
        help_text=(
            "Consecutive zero-contribution rounds before a BREAK clash resolves as ABANDONED."
        ),
    )
    max_round_cap = models.PositiveIntegerField(
        default=12,
        help_text="Round cap after which a CLASH auto-resolves as MUTUAL.",
    )
    decisive_overshoot = models.PositiveIntegerField(
        default=3,
        help_text=(
            "Minimum overshoot past a threshold for a resolution to be DECISIVE (vs MARGINAL). "
            "E.g. with default 3, crossing pc_win_threshold by 0-2 progress is MARGINAL; "
            "by 3+ is DECISIVE."
        ),
    )
    clash_min_intensity = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Minimum effective intensity for a clash to open. Prevents trivial "
            "round-1 clashes. Default 0 = no gate (legacy-permissive); seed "
            "content sets a real value (e.g. 4) once Properties are authored."
        ),
    )

    # Power-formula scaling knob.
    power_scale = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.5"),
        help_text="Overall scalar applied to power when computing progress delta.",
    )

    # Per-tier quality multipliers — looked up via quality_multiplier_for().
    quality_multiplier_critical = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.5"),
        help_text="Quality multiplier for success_level >= 3 (critical success).",
    )
    quality_multiplier_great = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.25"),
        help_text="Quality multiplier for success_level == 2 (great success).",
    )
    quality_multiplier_success = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Quality multiplier for success_level == 1 (success).",
    )
    quality_multiplier_partial = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.5"),
        help_text="Quality multiplier for success_level == 0 (partial success).",
    )
    quality_multiplier_failure = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.0"),
        help_text="Quality multiplier for success_level <= -1 (failure/botch).",
    )

    # Botch backfire fraction — how much power feeds back negatively on a botch.
    # The caller (outcome_to_delta) applies this; quality_multiplier_for() is not called for botch.
    botch_backfire_fraction = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.5"),
        help_text="Fraction of power returned as a negative delta on a botch.",
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clash_config_updates",
    )

    def quality_multiplier_for(self, success_level: int) -> Decimal:
        """Return the quality multiplier for the given success-level band.

        Banding:
          >= 3  → critical
          == 2  → great
          == 1  → success
          == 0  → partial
          <= -1 → failure (botch backfire is handled by the caller separately)
        """
        if success_level >= 3:  # noqa: PLR2004
            return self.quality_multiplier_critical
        if success_level == 2:  # noqa: PLR2004
            return self.quality_multiplier_great
        if success_level == 1:
            return self.quality_multiplier_success
        if success_level == 0:
            return self.quality_multiplier_partial
        return self.quality_multiplier_failure

    def __str__(self) -> str:
        return f"ClashConfig(pk={self.pk})"


class FleeConfig(SharedMemoryModel):
    """Singleton (pk=1): authored flee-check wiring (#878).

    Seeded authored content — services use cached_singleton() and let DoesNotExist
    propagate loudly (mirrors get_penetration_check_type's no-fabrication rule).
    """

    objects = ArxSharedMemoryManager()

    check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="CheckType rolled for flee attempts.",
    )
    base_difficulty = models.PositiveIntegerField(
        default=FLEE_BASE_DIFFICULTY,
        help_text="Flee difficulty before opponent-tier modifiers.",
    )
    consequence_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Pool for PARTIAL/FAILURE/BOTCH flee outcomes; null degrades to outcome-only.",
    )
    cover_bonus = models.PositiveIntegerField(
        default=FLEE_COVER_BONUS,
        help_text="Flat check bonus per ally covering the fleeing PC this round.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flee_config_updates",
    )

    def __str__(self) -> str:
        return f"FleeConfig(pk={self.pk})"


class FleeTierModifier(SharedMemoryModel):
    """Authored flee-difficulty modifier per opponent tier (#878).

    Encounter flee difficulty = FleeConfig.base_difficulty + max(modifier over
    active opponents' tiers); zero active opponents → base difficulty alone.
    """

    tier = models.CharField(max_length=20, choices=OpponentTier.choices, unique=True)
    difficulty_modifier = models.IntegerField(default=0)

    class Meta:
        ordering = ["tier"]

    def __str__(self) -> str:
        return f"FleeTierModifier({self.tier}: {self.difficulty_modifier:+d})"


class EncounterAftermathRule(SharedMemoryModel):
    """Authored aftermath wiring per (outcome, risk_level) cell (#876).

    Mirrors FleeConfig's authored-wiring pattern: check_type + base_difficulty
    drive a graded per-participant roll against consequence_pool. A missing
    cell means no aftermath for that combination; a null pool means the cell
    rolls nothing (outcome-only). Never an XP source — Legend awards are
    authored LEGEND_AWARD consequences inside the pool.
    """

    outcome = models.CharField(max_length=20, choices=EncounterOutcome.choices)
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices)
    check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="CheckType rolled per affected participant.",
    )
    base_difficulty = models.PositiveIntegerField(
        help_text="Authored difficulty for the aftermath check.",
    )
    consequence_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Pool for graded aftermath outcomes; null degrades to outcome-only.",
    )

    class Meta:
        ordering = ["outcome", "risk_level"]
        constraints = [
            models.UniqueConstraint(
                fields=["outcome", "risk_level"],
                name="unique_aftermath_rule_per_outcome_risk",
            ),
        ]

    def __str__(self) -> str:
        return f"AftermathRule({self.outcome} @ {self.risk_level})"


class EncounterOutcomeMapping(SharedMemoryModel):
    """Designer-tunable map from an encounter's (outcome, risk_level) to a graded CheckOutcome.

    Used by ``classify_battle_outcome`` to select the CheckOutcome tier for beat
    completion when an encounter resolves. VICTORY/DEFEAT rows map to
    success/failure CheckOutcomes (``success_level`` sign drives the derived
    BeatOutcome); a null ``check_outcome`` (or a missing row) signals the caller
    to resolve the beat to ``PENDING_GM_REVIEW`` rather than firing a consequence
    pool. Seeded with canonical tiers; GMs retune by editing rows.
    """

    outcome = models.CharField(max_length=20, choices=EncounterOutcome.choices)
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices)
    check_outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="encounter_outcome_mappings",
        help_text="CheckOutcome tier for this outcome×risk. Null = resolve to PENDING_GM_REVIEW.",
    )

    class Meta:
        ordering = ["outcome", "risk_level"]
        constraints = [
            models.UniqueConstraint(
                fields=["outcome", "risk_level"],
                name="unique_encounter_outcome_mapping",
            ),
        ]

    def __str__(self) -> str:
        tier = str(self.check_outcome) if self.check_outcome_id else "(review)"
        return f"{self.outcome} @ {self.risk_level} -> {tier}"


# =============================================================================
# Encounter scaling config models (#566)
# =============================================================================


class OpponentTierTemplate(SharedMemoryModel):
    """Authored baseline stats for each OpponentTier (#566).

    One row per tier (unique constraint). The scaling formula multiplies these
    values by the active RiskScalingModifier and party-size/level adjustments
    from EncounterScalingConfig. Null optional fields mean the stat is unused
    for that tier (e.g. swarm mechanics are off for MOOK/ELITE/BOSS).
    """

    tier = models.CharField(max_length=20, choices=OpponentTier.choices, unique=True)
    base_health = models.PositiveIntegerField(
        help_text="Base HP budget before scaling.",
    )
    base_soak = models.PositiveIntegerField(
        default=0,
        help_text="Base flat soak value.",
    )
    base_probing_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Probing threshold; null = tier does not use probing.",
    )
    base_swarm_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of swarm bodies; null = tier is not a swarm.",
    )
    body_toughness = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="HP per individual swarm body; null = tier is not a swarm.",
    )
    bodies_per_attack = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Bodies lost per outgoing swarm attack; null = tier is not a swarm.",
    )
    barrier_strength = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Ward barrier strength; null = authored per-fight, not template-driven.",
    )
    boss_phase_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of boss phases; 1 = single-phase (non-boss tiers).",
    )
    has_morale = models.BooleanField(
        default=True,
        help_text="False for mindless tiers (constructs). Adds "
        "MINDLESS_MORALE_RESISTANCE to morale checks against this opponent — "
        "not an immunity; a powerful enough roll breaks through.",
    )
    base_actions_per_round = models.PositiveIntegerField(
        default=1,
        help_text="Tier-level action economy. MOOK/ELITE=1; BOSS=2 or 3.",
    )

    class Meta:
        ordering = ["tier"]

    def __str__(self) -> str:
        return f"OpponentTierTemplate({self.tier})"


class CreatureTemplate(SharedMemoryModel):
    """Bestiary entry for a spawnable creature (#2016).

    Thin — does not duplicate stat blocks (those come from OpponentTierTemplate
    via the scaling formula). Authored phase data lives on CreaturePhaseTemplate.
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    tier = models.CharField(max_length=20, choices=OpponentTier.choices)
    threat_pool = models.ForeignKey(
        ThreatPool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="creature_templates",
    )
    soak_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Override soak; null = use tier template scaling.",
    )
    probing_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Override probing threshold; null = use tier template scaling.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CreaturePhaseTemplate(AbstractPhaseConfig):
    """Authored phase specification for a CreatureTemplate (#2016).

    Inherits shared phase fields from AbstractPhaseConfig. Adds
    creature_template FK instead of opponent. Cloned into BossPhase rows
    at spawn time via spawn_from_creature_template.
    """

    creature_template = models.ForeignKey(
        CreatureTemplate,
        on_delete=models.CASCADE,
        related_name="phase_templates",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["creature_template", "phase_number"],
                name="unique_phase_per_creature_template",
            ),
        ]
        ordering = ["creature_template", "phase_number"]

    def __str__(self) -> str:
        return f"{self.creature_template.name} Phase {self.phase_number}"


class BreakBarConfig(SharedMemoryModel):
    """Authored break-bar configuration for a CreaturePhaseTemplate (#2016).

    When present, the boss has a break bar. When absent, no bar (MOOK/ELITE).
    """

    boss_phase = models.OneToOneField(
        CreaturePhaseTemplate,
        on_delete=models.CASCADE,
        related_name="break_bar",
    )
    max_threshold = models.PositiveIntegerField(
        help_text="Bar capacity; scaled by party_mult at spawn time.",
    )
    vulnerability_rounds = models.PositiveIntegerField(default=2)
    intensity_bonus = models.PositiveIntegerField(
        default=2,
        help_text="Flat intensity bonus to PC techniques during the window.",
    )

    def __str__(self) -> str:
        return f"BreakBar({self.boss_phase})"


class RiskScalingModifier(SharedMemoryModel):
    """Authored multiplier per RiskLevel for the scaling formula (#566).

    One row per risk level (unique constraint). A multiplier of 1.00 is
    baseline; values below 1 reduce scaled stats, values above 1 increase them.
    """

    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, unique=True)
    multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Scaling multiplier applied to opponent stat budgets at this risk.",
    )

    class Meta:
        ordering = ["risk_level"]

    def __str__(self) -> str:
        return f"RiskScalingModifier({self.risk_level}: ×{self.multiplier})"


class StakesLevelRequirement(SharedMemoryModel):
    """Authored access requirements per StakesLevel (#566).

    One row per stakes level (unique constraint). The minimum_party_average_level
    and minimum_gm_level gate which GMs can run which stakes-level encounters.
    """

    stakes_level = models.CharField(max_length=20, choices=StakesLevel.choices, unique=True)
    minimum_party_average_level = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minimum average character level across the party.",
    )
    minimum_gm_level = models.CharField(
        max_length=20,
        choices=GMLevel.choices,
        default=GMLevel.STARTING,
        help_text="Minimum GMProfile.level required to run this stakes level.",
    )

    class Meta:
        ordering = ["stakes_level"]

    def __str__(self) -> str:
        return f"StakesLevelRequirement({self.stakes_level})"


class StakesEscalationModifier(SharedMemoryModel):
    """Authored stakes→escalation coupling (#2013).

    One row per StakesLevel (unique). Read by ``apply_escalation_tick`` (step
    bonus + one-shot initial surge) and by ``assign_default_escalation_curve``
    at encounter creation.
    """

    stakes_level = models.CharField(max_length=20, choices=StakesLevel.choices, unique=True)
    intensity_step_bonus = models.PositiveIntegerField(
        default=0,
        help_text="Added to the curve's intensity_step during each escalation tick.",
    )
    initial_surge = models.PositiveIntegerField(
        default=0,
        help_text=(
            "HIGH_STAKES-kind surge amount granted once to every ACTIVE PC "
            "participant. 0 = no initial surge."
        ),
    )
    default_curve = models.ForeignKey(
        "combat.EscalationCurve",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Curve auto-assigned at encounter creation when the encounter's "
            "escalation_curve is null and its stakes_level matches this row."
        ),
    )

    class Meta:
        ordering = ["stakes_level"]

    def __str__(self) -> str:
        return f"StakesEscalationModifier({self.stakes_level})"


class EncounterScalingConfig(SharedMemoryModel):
    """Singleton (pk=1): global scaling parameters for encounter budgets (#566).

    Seeded by seed_scaling_defaults() in factories.py. Services use get(pk=1)
    and let DoesNotExist propagate loudly (mirrors FleeConfig's no-fabrication
    rule). Updated via Django admin.
    """

    baseline_party_size = models.PositiveIntegerField(
        default=SCALING_CONFIG_BASELINE_PARTY_SIZE,
        help_text="Party size at which no per-member adjustment is applied.",
    )
    per_extra_member_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(SCALING_CONFIG_PER_EXTRA_MEMBER_PCT),
        help_text="Fractional budget increase per party member above baseline.",
    )
    per_avg_level_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(SCALING_CONFIG_PER_AVG_LEVEL_PCT),
        help_text="Fractional budget increase per point of average party level.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="encounter_scaling_config_updates",
    )

    def __str__(self) -> str:
        return f"EncounterScalingConfig(pk={self.pk})"


# =============================================================================
# Clash model (Task 1.3) — discriminator model for multi-round contested struggles
# =============================================================================


class Clash(SharedMemoryModel):
    """Central primitive for a Clash multi-round contest between PCs and an NPC opponent.

    ``flavor`` is the discriminator (CLASH / LOCK / WARD / BREAK). Three flavored
    fields have an iff coupling enforced at the application layer (``clean()``) and
    at the DB layer (``CheckConstraint``):

    - ``lock_pc_role`` is non-null iff ``flavor == LOCK``
    - ``npc_win_threshold`` is non-null iff ``flavor == CLASH``
    - ``ward_ends_on_round`` is non-null iff ``flavor == WARD``

    Mirrors the Thread discriminator pattern from world/magic/models/threads.py.
    """

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="clashes",
    )
    npc_opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.PROTECT,
        related_name="clashes",
    )
    initiator = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolution_consequence_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    per_round_consequence_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional per-round consequence pool fired each round for incremental feedback; "
        "omit for flavors with no per-round effects.",
    )

    flavor = models.CharField(
        max_length=10,
        choices=ClashFlavor.choices,
    )
    lock_pc_role = models.CharField(
        max_length=12,
        choices=LockPcRole.choices,
        null=True,
        blank=True,
        help_text="Set iff flavor=LOCK; null otherwise.",
    )
    progress = models.IntegerField(default=0)
    pc_win_threshold = models.IntegerField()
    npc_win_threshold = models.IntegerField(
        null=True,
        blank=True,
        help_text="Set iff flavor=CLASH; null otherwise.",
    )
    status = models.CharField(
        max_length=10,
        choices=ClashStatus.choices,
        default=ClashStatus.ACTIVE,
    )
    started_round = models.PositiveIntegerField()
    resolved_round = models.PositiveIntegerField(null=True, blank=True)
    resolution = models.CharField(
        max_length=15,
        choices=ClashResolution.choices,
        null=True,
        blank=True,
    )
    ward_ends_on_round = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Set iff flavor=WARD; null otherwise.",
    )
    triggering_threat_entry = models.ForeignKey(
        "combat.ThreatPoolEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The ThreatPoolEntry that opened this clash and is the NPC side of its contest "
            "(the sustained-attack entry for WARD, the lock-applying entry for LOCK, the "
            "big-attack entry for CLASH). Null for BREAK (NPC contributes nothing to the "
            "meter). Set at clash creation in Phase 5; Phase 3 reads it for the NPC "
            "per-round contribution."
        ),
    )
    rampart = models.ForeignKey(
        "areas.Rampart",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Set iff flavor=WARD and the sustained attack's PC target stands at a "
            "rampart-covered position (#2209) — the rampart drains alongside progress "
            "instead of the PC taking the strike directly."
        ),
    )

    class Meta:
        constraints = [
            # lock_pc_role is non-null iff flavor == LOCK
            models.CheckConstraint(
                name="clash_lock_role_iff_lock_flavor",
                check=(~Q(flavor=ClashFlavor.LOCK) | Q(lock_pc_role__isnull=False))
                & (Q(flavor=ClashFlavor.LOCK) | Q(lock_pc_role__isnull=True)),
            ),
            # npc_win_threshold is non-null iff flavor == CLASH
            models.CheckConstraint(
                name="clash_npc_threshold_iff_clash_flavor",
                check=(~Q(flavor=ClashFlavor.CLASH) | Q(npc_win_threshold__isnull=False))
                & (Q(flavor=ClashFlavor.CLASH) | Q(npc_win_threshold__isnull=True)),
            ),
            # ward_ends_on_round is non-null iff flavor == WARD
            models.CheckConstraint(
                name="clash_ward_round_iff_ward_flavor",
                check=(~Q(flavor=ClashFlavor.WARD) | Q(ward_ends_on_round__isnull=False))
                & (Q(flavor=ClashFlavor.WARD) | Q(ward_ends_on_round__isnull=True)),
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Clash<{self.flavor}>(encounter={self.encounter_id} "
            f"opponent={self.npc_opponent_id} status={self.status})"
        )

    def clean(self) -> None:
        """Validate the three iff couplings between flavor and flavored fields."""
        errors: dict[str, str] = {}

        # lock_pc_role iff LOCK
        if self.flavor == ClashFlavor.LOCK and self.lock_pc_role is None:
            errors["lock_pc_role"] = "flavor=LOCK requires lock_pc_role."
        elif self.flavor != ClashFlavor.LOCK and self.lock_pc_role is not None:
            errors["lock_pc_role"] = "lock_pc_role must be null for non-LOCK flavors."

        # npc_win_threshold iff CLASH
        if self.flavor == ClashFlavor.CLASH and self.npc_win_threshold is None:
            errors["npc_win_threshold"] = "flavor=CLASH requires npc_win_threshold."
        elif self.flavor != ClashFlavor.CLASH and self.npc_win_threshold is not None:
            errors["npc_win_threshold"] = "npc_win_threshold must be null for non-CLASH flavors."

        # ward_ends_on_round iff WARD
        if self.flavor == ClashFlavor.WARD and self.ward_ends_on_round is None:
            errors["ward_ends_on_round"] = "flavor=WARD requires ward_ends_on_round."
        elif self.flavor != ClashFlavor.WARD and self.ward_ends_on_round is not None:
            errors["ward_ends_on_round"] = "ward_ends_on_round must be null for non-WARD flavors."

        if errors:
            raise ValidationError(errors)


# =============================================================================
# ClashRound model (Task 1.4) — per-round record for a Clash contest
# =============================================================================


class ClashRound(SharedMemoryModel):
    """Per-round record of a Clash multi-round contest.

    One row is written at the end of each round of a ``Clash``.  The deltas
    record how much each side moved the progress meter this round, and
    ``progress_after`` snapshots the meter value after the round resolves so
    that the history is self-contained and does not depend on replaying all
    prior rounds.

    ``ClashContribution`` (Task 1.5) will hang off this model — one row per PC
    per round.
    """

    clash = models.ForeignKey(
        Clash,
        on_delete=models.CASCADE,
        related_name="rounds",
        help_text="The Clash this round belongs to.",
    )
    round_number = models.PositiveIntegerField(
        help_text="Which round of the Clash this row records (1-indexed, matches encounter round).",
    )
    pc_progress_delta = models.IntegerField(
        help_text="Net signed progress contribution from all PCs this round. "
        "Positive moves the meter toward the PC win threshold.",
    )
    npc_progress_delta = models.IntegerField(
        help_text="Net signed progress contribution from the NPC opponent this round. "
        "Negative moves the meter toward the NPC win threshold.",
    )
    progress_after = models.IntegerField(
        help_text="Clash progress meter value after this round's deltas are applied. "
        "Snapshot so history is self-contained without replaying all prior rounds.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clash", "round_number"],
                name="unique_round_per_clash",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"ClashRound(clash={self.clash_id} "
            f"round={self.round_number} progress={self.progress_after})"
        )


# =============================================================================
# ClashContribution model (Task 1.5) — per-PC-per-round audit record
# =============================================================================


class ClashContribution(SharedMemoryModel):
    """Per-PC per-round audit record of a single contribution to a Clash.

    One row is written for each PC each round that a ``ClashRound`` resolves.
    Captures what the PC committed, what technique was used, what the check
    produced, and how that translated into progress delta and any soulfray cost.
    The ``UniqueConstraint`` on ``(clash_round, character)`` enforces at most
    one contribution per character per round.
    """

    clash_round = models.ForeignKey(
        ClashRound,
        on_delete=models.CASCADE,
        related_name="contributions",
        help_text="The ClashRound this contribution belongs to.",
    )
    character = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The PC whose contribution this row records.",
    )
    action_slot = models.CharField(
        max_length=10,
        choices=ClashActionSlot.choices,
        help_text="Whether the PC committed their focused or passive action slot to this Clash.",
    )
    anima_committed = models.PositiveIntegerField(
        help_text="Anima the PC committed to the Clash this round.",
    )
    technique = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Technique the PC used in the focused action slot. "
            "Null when the PC contributed from the passive slot."
        ),
    )
    check_outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The check outcome tier the PC rolled this round.",
    )
    progress_delta = models.IntegerField(
        help_text=(
            "Signed progress contribution from this PC this round. "
            "Positive moves the meter toward the PC win threshold."
        ),
    )
    was_overburn = models.BooleanField(
        default=False,
        help_text="True if the PC overburned their anima commitment this round.",
    )
    was_audere = models.BooleanField(
        default=False,
        help_text="True if the PC triggered an Audere escalation this round.",
    )
    soulfray_severity_accrued = models.PositiveIntegerField(
        default=0,
        help_text="Soulfray severity the PC accrued as a result of this contribution.",
    )
    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clash_contributions",
        db_constraint=False,
        help_text=(
            "The ACTION-mode Interaction created when this clash contribution "
            "resolved. Null for legacy rows predating this PR."
        ),
    )
    interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Denormalized from interaction.timestamp. Required because "
            "scenes_interaction is range-partitioned by timestamp — the composite "
            "FK constraint targets (interaction_id, interaction_timestamp). "
            "Populated atomically with interaction_id by create_action_interaction."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clash_round", "character"],
                name="unique_contribution_per_character_per_round",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"ClashContribution(round={self.clash_round_id} "
            f"character={self.character_id} slot={self.action_slot})"
        )


# =============================================================================
# BreakBarContribution model (#2642) — per-round audit record of a boss
# break-bar feed. Mirrors ClashContribution's shape: one row per qualifying
# feed event, persisted where assess_break_bar previously discarded its
# ephemeral participant/effect_type sets.
# =============================================================================


class BreakBarContribution(SharedMemoryModel):
    """Per-round audit record of a single feed that chipped a boss's break bar.

    One row per qualifying feed event assessed by ``assess_break_bar`` each
    round: a damaging hit (DAMAGE), a landed combo (COMBO), a PC-side LOCK-clash
    win against the boss (HOLD), a new behavior-altering condition landed on the
    boss (DEBUFF), or a reinforcing lieutenant becoming suppressed (SUPPRESSION).
    Feeds the diversity-weighted depletion formula (distinct actor x kind pairs
    this round, novelty-doubled on each pair's first appearance in the
    encounter) and the break celebration's contributor naming.
    """

    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        related_name="break_contributions",
        help_text="The BOSS-tier opponent whose break bar this contribution chipped.",
    )
    participant = models.ForeignKey(
        COMBAT_PARTICIPANT_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="break_contributions",
        help_text=(
            "The PC credited with this contribution. Null for SUPPRESSION/DEBUFF "
            "rows whose triggering event has no single attributable actor — "
            "prefer non-null whenever the feed can be traced to one PC."
        ),
    )
    round_number = models.PositiveIntegerField(
        help_text="The encounter round this contribution was assessed in.",
    )
    kind = models.CharField(
        max_length=15,
        choices=BreakContributionKind.choices,
        help_text="Which feed produced this contribution.",
    )
    effect_type = models.ForeignKey(
        "magic.EffectType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The technique's effect type, when the feed carries one (DAMAGE/COMBO).",
    )
    amount = models.PositiveSmallIntegerField(
        default=1,
        help_text="This row's unit weight toward the round's depletion total.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round_number", "created_at"]
        indexes = [
            models.Index(fields=["opponent", "round_number"]),
        ]

    def __str__(self) -> str:
        return (
            f"BreakBarContribution(opponent={self.opponent_id} "
            f"round={self.round_number} kind={self.kind})"
        )


# =============================================================================
# ClashContributionDeclaration model (Task 5.3a) — per-round bridge for the
# clash post-pass
# =============================================================================


class ClashContributionDeclaration(CommittingDeclaration, SharedMemoryModel):
    """A PC's declared clash contribution for one round, awaiting resolve_round's post-pass.

    Written by Task 7.1's player-facing surface (``declare_clash_contribution``)
    and consumed by ``_resolve_clashes`` in services.py after all combat-action
    resolution for the round.  Deleted atomically after all clashes are processed.

    One PC can declare to multiple distinct Clashes in a round (e.g., participating
    in both a BREAK and a CLASH), but may only make ONE contribution per
    (clash, round) — enforced by the UniqueConstraint.

    ``npc_attack_affinity`` is NOT stored here — it is resolved at post-pass time
    from ``clash.triggering_threat_entry`` so the declaration is agnostic to the
    affinity resolution strategy.
    """

    encounter = models.ForeignKey(
        COMBAT_ENCOUNTER_MODEL,
        on_delete=models.CASCADE,
        related_name="clash_declarations",
        help_text="The encounter this declaration belongs to.",
    )
    round_number = models.PositiveIntegerField(
        help_text="The encounter round this declaration is for (1-indexed).",
    )
    participant = models.ForeignKey(
        COMBAT_PARTICIPANT_MODEL,
        on_delete=models.CASCADE,
        related_name="clash_declarations",
        help_text="The PC participant making this contribution.",
    )
    clash = models.ForeignKey(
        "combat.Clash",
        on_delete=models.CASCADE,
        related_name="declarations",
        help_text="The active Clash this contribution is directed at.",
    )
    action_slot = models.CharField(
        max_length=16,
        choices=ClashActionSlot.choices,
        help_text="Which action slot the PC commits: FOCUSED (primary) or PASSIVE (secondary).",
    )
    technique = models.ForeignKey(
        TECHNIQUE_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The Technique the PC is using for this clash contribution.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "round_number", "participant", "clash"],
                name="unique_clash_declaration_per_round_per_participant",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"ClashContributionDeclaration("
            f"encounter={self.encounter_id} "
            f"round={self.round_number} "
            f"participant={self.participant_id} "
            f"clash={self.clash_id})"
        )


class EncounterRiskAcknowledgement(SharedMemoryModel):
    """A character's on-record acknowledgement of an encounter's risk level.

    Recorded idempotently at voluntary entry points (self-join, hostile-cast
    initiation, consent-accept) — at most one row per character per encounter.
    Suppresses the #777 gate for that character in that encounter. GM placement
    via add_participant does NOT create one.
    """

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="risk_acknowledgements",
    )
    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="combat_risk_acknowledgements",
    )
    acknowledged_risk_level = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        help_text="The encounter's risk level at acknowledgement time.",
    )
    acknowledged_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["acknowledged_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "character_sheet"],
                name="unique_risk_acknowledgement_per_encounter",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.character_sheet_id} acknowledged {self.acknowledged_risk_level} "
            f"in encounter {self.encounter_id}"
        )


# =============================================================================
# Escalation Curve authored model (Task 3, #872)
# =============================================================================


class EscalationCurve(SharedMemoryModel):
    """Authored escalation ramp for opted-in encounters (#872).

    Referenced by ``CombatEncounter.escalation_curve``; null FK = the
    encounter does not escalate. Multiple curves are the authoring knob
    (boss fight vs. skirmish), so this is authored rows, not a singleton.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    start_round = models.PositiveIntegerField(
        default=2,
        help_text="First round the escalation tick fires (>=2 keeps round one calm).",
    )
    intensity_step = models.PositiveIntegerField(
        default=1,
        help_text="Intensity modifier added to each participant's engagement per tick.",
    )
    pace_check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="escalation_curves",
        help_text="Check rolled each tick to keep control in pace with intensity.",
    )
    pace_difficulty_base = models.PositiveIntegerField(
        default=0,
        help_text="Base difficulty of the pace check.",
    )
    pace_difficulty_per_level = models.PositiveIntegerField(
        default=0,
        help_text="Difficulty added per accumulated escalation level.",
    )
    control_step_on_success = models.PositiveIntegerField(
        default=1,
        help_text="Control modifier gained on a pace-check success (success_level >= 1).",
    )
    control_step_on_partial = models.PositiveIntegerField(
        default=0,
        help_text="Control modifier gained on a partial success (success_level == 0).",
    )
    control_step_on_botch = models.IntegerField(
        default=-1,
        help_text="Control modifier change on a botch (success_level <= -2); author negative.",
    )
    max_escalation_level = models.PositiveIntegerField(
        default=0,
        help_text="Tick stops raising pressure past this level. 0 = uncapped.",
    )
    spike_intensity_amount = models.PositiveIntegerField(
        default=2,
        help_text="Intensity spike applied to bonded co-combatants when an ally falls.",
    )
    spike_minimum_track_points = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Minimum developed_points on a spike-fueling relationship track "
            "for the bond to qualify."
        ),
    )
    tick_narration = models.TextField(
        blank=True,
        help_text="Narrative line surfaced to the combat panel on each tick.",
    )
    peril_spike_intensity_amount = models.PositiveIntegerField(
        default=3,
        help_text=(
            "Intensity spike applied to bonded co-combatants when an ally enters "
            "mortal peril (#2013)."
        ),
    )
    hated_foe_spike_intensity_amount = models.PositiveIntegerField(
        default=3,
        help_text="Intensity spike applied when a hated NPC foe enters the encounter (#2013).",
    )
    interference_spike_intensity_amount = models.PositiveIntegerField(
        default=0,
        help_text="Intensity spike for the locked duelist when a non-locked PC "
        "interferes with the duel (#2020).",
    )
    surge_narration = models.TextField(
        blank=True,
        help_text=(
            "Generic dramatic-surge narration template. Only the literal substring "
            "'{character}' is substituted (the surging PC's name) — never the bond, "
            "track, or subject, per the leak rule (#2013). Blank uses a built-in "
            "generic line."
        ),
    )

    class Meta:
        verbose_name = "Escalation Curve"
        verbose_name_plural = "Escalation Curves"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DramaticSurgeRecord(SharedMemoryModel):
    """Audit + dedup record for one dramatic-surge event (#2013).

    Created by ``apply_dramatic_surge``; a given (encounter, participant,
    trigger_kind, subject_sheet) tuple surges at most once — a bonded ally's
    peril surges you once per encounter; their later fall is a different
    trigger_kind and surges again. Two partial UniqueConstraints (mirroring
    the ``NpcRegard`` precedent, ``world/npc_services/models.py``) because
    Postgres never matches NULL=NULL — a single constraint spanning the
    nullable subject_sheet column would let subjectless (HIGH_STAKES)
    duplicates through.
    """

    encounter = models.ForeignKey(
        COMBAT_ENCOUNTER_MODEL,
        on_delete=models.CASCADE,
        related_name="dramatic_surges",
    )
    participant = models.ForeignKey(
        COMBAT_PARTICIPANT_MODEL,
        on_delete=models.CASCADE,
        related_name="dramatic_surges",
    )
    trigger_kind = models.CharField(max_length=20, choices=SurgeTriggerKind.choices)
    subject_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The bonded ally / hated foe this surge is about; null for HIGH_STAKES.",
    )
    amount = models.PositiveIntegerField()
    round_number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dramatic Surge Record"
        verbose_name_plural = "Dramatic Surge Records"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "participant", "trigger_kind", "subject_sheet"],
                condition=models.Q(subject_sheet__isnull=False),
                name="unique_surge_with_subject",
            ),
            models.UniqueConstraint(
                fields=["encounter", "participant", "trigger_kind"],
                condition=models.Q(subject_sheet__isnull=True),
                name="unique_surge_without_subject",
            ),
        ]

    def __str__(self) -> str:
        return f"DramaticSurgeRecord({self.trigger_kind}, +{self.amount})"


# =============================================================================
# DuelChallenge model (Task 4) — PC-vs-PC duel handshake
# =============================================================================


class DuelChallenge(SharedMemoryModel):
    """A PC-vs-PC duel challenge handshake record.

    Created when a challenger issues a duel request. Tracks the lifecycle
    from PENDING (awaiting response) through ACCEPTED/DECLINED/WITHDRAWN/EXPIRED.
    The partial unique constraint ensures at most one PENDING challenge exists
    per (challenger_sheet, challenged_sheet) pair at any time.
    """

    challenger_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="duel_challenges_issued",
        help_text="The PC who issued the challenge.",
    )
    challenged_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="duel_challenges_received",
        help_text="The PC who was challenged.",
    )
    room = models.ForeignKey(
        OBJECTS_OBJECTDB_MODEL,
        on_delete=models.PROTECT,
        related_name="duel_challenges",
        null=True,
        blank=True,
        help_text="Room where the duel was challenged.",
    )
    status = models.CharField(
        max_length=20,
        choices=DuelChallengeStatus.choices,
        default=DuelChallengeStatus.PENDING,
    )
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resulting_encounter = models.ForeignKey(
        COMBAT_ENCOUNTER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duel_challenge",
        help_text="The CombatEncounter opened when the challenge was accepted.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["challenger_sheet", "challenged_sheet"],
                condition=Q(status=DuelChallengeStatus.PENDING),
                name="unique_pending_duel_challenge_per_pair",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"DuelChallenge({self.challenger_sheet_id} → {self.challenged_sheet_id} "
            f"[{self.status}])"
        )


class ThreatRecord(SharedMemoryModel):
    """Per-(opponent, participant) threat score accumulated from real events (#2020).

    The substrate for NPC target selection: damage dealt by a PC to an opponent
    increments this, taunts (#2015) add to it, and the ``HIGHEST_THREAT`` /
    ``SPECIFIC_ROLE`` target-selection modes read it. An active
    ``EngagementLock`` overrides the locked pairing's threat to max.

    One row per (NPC, PC) pairing within an encounter.
    """

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="threat_records",
    )
    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        related_name="threat_records",
    )
    participant = models.ForeignKey(
        CombatParticipant,
        on_delete=models.CASCADE,
        related_name="threat_records",
    )
    threat_value = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Threat Record"
        verbose_name_plural = "Threat Records"
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "opponent", "participant"],
                name="unique_threat_record_per_pairing",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"ThreatRecord(opp={self.opponent_id}, pc={self.participant_id}: {self.threat_value})"
        )


class EngagementLock(SharedMemoryModel):
    """A declarable foil pairing between one PC and one opponent (#2020).

    While ACTIVE, the locked NPC's targeting is narrowed to just the locked PC
    (the provable-targeting guarantee). Lock formation/breaking emit flow events
    for narration. An optional ``clash`` FK links to the metered contest
    (Clash) when one opens between the locked pair — the lock orchestrates the
    pairing, the Clash is the struggle.

    Interference by a non-locked PC is a narrative payoff: the
    ``break_in_consequence_pool`` fires dramatic effects and a
    ``SurgeTriggerKind.INTERFERENCE`` surge fires for the locked duelist.
    """

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="engagement_locks",
    )
    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        related_name="engagement_locks",
    )
    participant = models.ForeignKey(
        CombatParticipant,
        on_delete=models.CASCADE,
        related_name="engagement_locks",
    )
    status = models.CharField(
        max_length=10,
        choices=EngagementLockStatus.choices,
        default=EngagementLockStatus.ACTIVE,
    )
    initiated_by = models.CharField(
        max_length=20,
        choices=LockInitiator.choices,
        default=LockInitiator.THREAT,
    )
    started_round = models.PositiveIntegerField()
    ended_round = models.PositiveIntegerField(null=True, blank=True)
    break_reason = models.CharField(
        max_length=15,
        choices=LockBreakReason.choices,
        null=True,
        blank=True,
    )
    clash = models.ForeignKey(
        "Clash",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="engagement_locks",
        help_text="Set when a metered contest (Clash) opens between the locked pair.",
    )
    break_in_consequence_pool = models.ForeignKey(
        CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="GM-authored dramatic effects fired when a non-locked PC interferes.",
    )

    class Meta:
        verbose_name = "Engagement Lock"
        verbose_name_plural = "Engagement Locks"
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "opponent"],
                condition=Q(status="active"),
                name="one_active_lock_per_opponent",
            ),
        ]

    def __str__(self) -> str:
        return f"EngagementLock(opp={self.opponent_id}→pc={self.participant_id} [{self.status}])"
