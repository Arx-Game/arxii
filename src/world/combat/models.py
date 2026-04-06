"""Models for the combat system."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.combat.constants import (
    NO_ROLE_SPEED_RANK,
    WOUND_DESCRIPTIONS,
    ActionCategory,
    EncounterStatus,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
    TargetingMode,
    TargetSelection,
)
from world.fatigue.constants import EffortLevel


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
    story = models.ForeignKey(
        "stories.Story",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_encounters",
    )
    episode = models.ForeignKey(
        "stories.Episode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="combat_encounters",
    )
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
    probing_threshold = models.PositiveIntegerField(default=50)
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
    covenant_role = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="Display label set by the covenant system. No choices constraint — "
        "role definitions live in the covenants app.",
    )
    health = models.IntegerField()
    max_health = models.PositiveIntegerField()
    base_speed_rank = models.PositiveIntegerField(
        default=NO_ROLE_SPEED_RANK,
        help_text="Base resolution rank set by the covenant system. Lower is faster.",
    )
    speed_modifier = models.IntegerField(
        default=0,
        help_text="Added to base speed rank",
    )
    status = models.CharField(
        max_length=20,
        choices=ParticipantStatus.choices,
        default=ParticipantStatus.ACTIVE,
    )
    dying_final_round = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "character_sheet"],
                name="unique_participant_per_encounter",
            ),
        ]

    @property
    def effective_speed_rank(self) -> int:
        return max(1, self.base_speed_rank + self.speed_modifier)

    @property
    def health_percentage(self) -> float:
        if self.max_health == 0:
            return 0.0
        return max(0.0, self.health / self.max_health)

    @property
    def wound_description(self) -> str:
        pct = self.health_percentage
        for threshold, description in WOUND_DESCRIPTIONS:
            if pct >= threshold:
                return description
        return WOUND_DESCRIPTIONS[-1][1]

    def __str__(self) -> str:
        if self.covenant_role:
            return f"{self.character_sheet} ({self.covenant_role})"
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
    )
    focused_target = models.ForeignKey(
        CombatOpponent,
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "round_number"],
                name="unique_action_per_participant_per_round",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.participant} Round {self.round_number}: {self.focused_action.name}"


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
