"""Models for the combat system."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.combat.constants import (
    DEFAULT_PACE_TIMER_MINUTES,
    ActionCategory,
    ComboLearningMethod,
    EncounterStatus,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
    TargetingMode,
    TargetSelection,
)
from world.fatigue.constants import EffortLevel
from world.magic.constants import EffectKind, VitalBonusTarget


class CombatEncounter(SharedMemoryModel):
    """Top-level container for a combat encounter."""

    encounter_type = models.CharField(
        max_length=30,
        choices=EncounterType.choices,
        default=EncounterType.PARTY_COMBAT,
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_encounters",
    )
    room = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="combat_encounters",
        null=True,
        blank=True,
        help_text="Room where the encounter takes place. Ephemeral CombatNPC "
        "ObjectDBs are placed here at creation.",
    )
    round_number = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=30,
        choices=EncounterStatus.choices,
        default=EncounterStatus.BETWEEN_ROUNDS,
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
    round_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the current declaration phase began.",
    )
    is_paused = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return (
            f"{self.get_encounter_type_display()} "
            f"(Round {self.round_number}, {self.get_status_display()})"
        )


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
    weight = models.PositiveIntegerField(
        default=10,
        help_text="Selection weight",
    )
    targeting_mode = models.CharField(
        max_length=20,
        choices=TargetingMode.choices,
        default=TargetingMode.SINGLE,
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
    minimum_phase = models.PositiveIntegerField(null=True, blank=True)
    cooldown_rounds = models.PositiveIntegerField(null=True, blank=True)

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
    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_opponent",
        help_text="The in-world ObjectDB representation. Set at creation; "
        "nulled if the ObjectDB is destroyed externally.",
    )
    objectdb_is_ephemeral = models.BooleanField(
        default=False,
        help_text="If True, the ObjectDB was created for this encounter only "
        "and will be cleaned up at encounter completion. Persona-bearing "
        "or pre-existing ObjectDBs MUST NOT be flagged ephemeral.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(persona__isnull=True) | Q(objectdb_is_ephemeral=False),
                name="persona_bearing_opponent_not_ephemeral",
            ),
        ]

    def clean(self) -> None:
        super().clean()
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

    @property
    def health_percentage(self) -> float:
        if self.max_health == 0:
            return 0.0
        return max(0.0, self.health / self.max_health)

    def __str__(self) -> str:
        return f"{self.name} ({self.get_tier_display()})"


class BossPhase(SharedMemoryModel):
    """One stage of a boss fight."""

    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    phase_number = models.PositiveIntegerField()
    threat_pool = models.ForeignKey(
        ThreatPool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="boss_phases",
    )
    soak_value = models.PositiveIntegerField(default=0)
    probing_threshold = models.PositiveIntegerField(null=True, blank=True)
    health_trigger_percentage = models.FloatField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opponent", "phase_number"],
                name="unique_phase_per_opponent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.opponent.name} Phase {self.phase_number}"


class ComboDefinition(SharedMemoryModel):
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
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="combo_learnings",
    )
    learned_via = models.CharField(
        max_length=20,
        choices=ComboLearningMethod.choices,
    )
    learned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["combo", "character_sheet"],
                name="unique_combo_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} knows {self.combo.name}"


class CombatParticipant(SharedMemoryModel):
    """A PC in a combat encounter."""

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "character_sheet"],
                name="unique_participant_per_encounter",
            ),
        ]

    def __str__(self) -> str:
        if self.covenant_role_id:
            return f"{self.character_sheet} ({self.covenant_role.name})"
        return f"{self.character_sheet}"


class CombatRoundAction(SharedMemoryModel):
    """A PC's declared actions for a round."""

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
        "magic.Technique",
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

    physical_passive = models.ForeignKey(
        "magic.Technique",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    social_passive = models.ForeignKey(
        "magic.Technique",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    mental_passive = models.ForeignKey(
        "magic.Technique",
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

    def __str__(self) -> str:
        action_name = self.focused_action.name if self.focused_action else "passives only"
        return f"{self.participant} Round {self.round_number}: {action_name}"


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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opponent", "round_number"],
                name="unique_action_per_opponent_per_round",
            ),
        ]

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
        "combat.CombatParticipant",
        on_delete=models.CASCADE,
        related_name="combat_pulls",
    )
    encounter = models.ForeignKey(
        "combat.CombatEncounter",
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
