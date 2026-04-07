# Party Combat System — Implementation Plan (Phase 1: Foundation)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the foundational models, constants, services, and tests for the Party Combat system — encounter lifecycle, NPC tiers, health/damage, round management, and threat pools.

**Architecture:** New `world.combat` app with SharedMemoryModel for lookup tables, standard Django models for runtime state. Services follow existing patterns (transaction.atomic, select_for_update for concurrency). Integrates with checks, fatigue, conditions, and magic apps via existing service functions.

**Tech Stack:** Django/Evennia (SharedMemoryModel), DRF (future API), FactoryBoy (test factories), existing `perform_check()` pipeline.

**Scope:** This plan covers Phase 1 — the data layer and core combat loop services. Phase 2 (combo system) and Phase 3 (API + frontend) are separate plans.

---

### Task 1: App Scaffold and Constants

**Files:**
- Create: `src/world/combat/__init__.py`
- Create: `src/world/combat/apps.py`
- Create: `src/world/combat/constants.py`
- Create: `src/world/combat/admin.py`
- Create: `src/world/combat/migrations/__init__.py`
- Create: `src/world/combat/tests/__init__.py`
- Modify: `src/server/conf/settings.py` (add to INSTALLED_APPS)

**Step 1: Create the app directory and boilerplate files**

```python
# src/world/combat/__init__.py
# (empty)

# src/world/combat/apps.py
from django.apps import AppConfig


class CombatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.combat"
    verbose_name = "Combat"

# src/world/combat/migrations/__init__.py
# (empty)

# src/world/combat/tests/__init__.py
# (empty)
```

**Step 2: Create constants.py with all enums**

```python
# src/world/combat/constants.py
"""Constants for the combat system."""

from django.db import models


class EncounterType(models.TextChoices):
    """Types of combat encounters."""

    PARTY_COMBAT = "party_combat", "Party Combat"
    OPEN_ENCOUNTER = "open_encounter", "Open Encounter"


class EncounterStatus(models.TextChoices):
    """Lifecycle states of a combat encounter."""

    DECLARING = "declaring", "Declaring Actions"
    RESOLVING = "resolving", "Resolving Actions"
    BETWEEN_ROUNDS = "between_rounds", "Between Rounds"
    COMPLETED = "completed", "Completed"


class RiskLevel(models.TextChoices):
    """Personal risk level of an encounter."""

    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    EXTREME = "extreme", "Extreme"
    LETHAL = "lethal", "Lethal"


class StakesLevel(models.TextChoices):
    """World-level stakes of an encounter."""

    LOCAL = "local", "Local"
    REGIONAL = "regional", "Regional"
    NATIONAL = "national", "National"
    CONTINENTAL = "continental", "Continental"
    WORLD = "world", "World"


class OpponentTier(models.TextChoices):
    """NPC combat tier determining mechanical treatment."""

    SWARM = "swarm", "Swarm"
    MOOK = "mook", "Mook"
    ELITE = "elite", "Elite"
    BOSS = "boss", "Boss"
    HERO_KILLER = "hero_killer", "Hero Killer"


class OpponentStatus(models.TextChoices):
    """Current state of an NPC in combat."""

    ACTIVE = "active", "Active"
    DEFEATED = "defeated", "Defeated"
    FLED = "fled", "Fled"


class ParticipantStatus(models.TextChoices):
    """Current state of a PC in combat."""

    ACTIVE = "active", "Active"
    UNCONSCIOUS = "unconscious", "Unconscious"
    DYING = "dying", "Dying"
    DEAD = "dead", "Dead"


class ActionCategory(models.TextChoices):
    """The three action categories for combat rounds."""

    PHYSICAL = "physical", "Physical"
    SOCIAL = "social", "Social"
    MENTAL = "mental", "Mental"


class TargetingMode(models.TextChoices):
    """How an NPC threat targets PCs."""

    SINGLE = "single", "Single Target"
    MULTI = "multi", "Multiple Targets"
    ALL = "all", "All Participants"


class TargetSelection(models.TextChoices):
    """How an NPC selects which PC(s) to target."""

    RANDOM = "random", "Random"
    HIGHEST_THREAT = "highest_threat", "Highest Threat"
    LOWEST_HEALTH = "lowest_health", "Lowest Health"
    SPECIFIC_ROLE = "specific_role", "Specific Covenant Role"


class CovenantRole(models.TextChoices):
    """Combat archetypes assigned via covenant ritual. Stub — values TBD."""

    # Speed ranks: lower = faster resolution order
    # Placeholder roles — exact names and rankings are future content
    VANGUARD = "vanguard", "Vanguard"  # Rank ~1
    STRIKER = "striker", "Striker"  # Rank ~2
    SENTINEL = "sentinel", "Sentinel"  # Rank ~4
    WEAVER = "weaver", "Weaver"  # Rank ~6
    WARDEN = "warden", "Warden"  # Rank ~8
    INVOKER = "invoker", "Invoker"  # Rank ~10


# Resolution rank mapping — covenant role to base speed rank
COVENANT_ROLE_SPEED_RANK: dict[str, int] = {
    CovenantRole.VANGUARD: 1,
    CovenantRole.STRIKER: 2,
    CovenantRole.SENTINEL: 4,
    CovenantRole.WEAVER: 6,
    CovenantRole.WARDEN: 8,
    CovenantRole.INVOKER: 10,
}

# Default rank for PCs without a covenant role
NO_ROLE_SPEED_RANK = 20

# Default rank for NPC actions
NPC_SPEED_RANK = 15

# Health threshold constants
PERMANENT_WOUND_THRESHOLD = 0.5  # Hit > 50% of max health
KNOCKOUT_HEALTH_THRESHOLD = 0.2  # Below 20% health remaining
DEATH_HEALTH_THRESHOLD = 0  # At or below 0 health

# Wound ladder descriptions (health percentage -> description)
WOUND_DESCRIPTIONS: list[tuple[float, str]] = [
    (0.9, "looks perfectly healthy"),
    (0.75, "has minor scratches and bruises"),
    (0.5, "is visibly battered and bleeding"),
    (0.25, "is severely wounded"),
    (0.1, "is barely standing, covered in wounds"),
    (0.0, "is on death's door"),
]
```

**Step 3: Create empty admin.py**

```python
# src/world/combat/admin.py
"""Django admin configuration for the combat system."""
```

**Step 4: Register the app in settings**

Add `"world.combat.apps.CombatConfig",` to `INSTALLED_APPS` in `src/server/conf/settings.py`.

**Step 5: Commit**

```bash
git add src/world/combat/ src/server/conf/settings.py
git commit -m "feat(combat): scaffold combat app with constants and enums"
```

---

### Task 2: Encounter and Participant Models

**Files:**
- Create: `src/world/combat/models.py`
- Modify: `src/world/combat/admin.py`
- Test: `src/world/combat/tests/test_models.py`

**Step 1: Write model tests**

```python
# src/world/combat/tests/test_models.py
"""Tests for combat models."""

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    CovenantRole,
    EncounterStatus,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
)


class CombatEncounterTest(TestCase):
    """Test CombatEncounter model."""

    def test_create_encounter(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        self.assertEqual(encounter.round_number, 0)
        self.assertEqual(encounter.status, EncounterStatus.BETWEEN_ROUNDS)

    def test_str(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        self.assertIn("Party Combat", str(encounter))


class CombatOpponentTest(TestCase):
    """Test CombatOpponent model."""

    def test_create_opponent(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        opponent = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            name="Shadow Dragon",
            max_health=500,
            health=500,
            soak_value=80,
            probing_threshold=50,
        )
        self.assertEqual(opponent.status, OpponentStatus.ACTIVE)
        self.assertEqual(opponent.current_phase, 1)
        self.assertEqual(opponent.probing_current, 0)

    def test_health_percentage(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        opponent = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            name="Goblin",
            max_health=20,
            health=10,
        )
        self.assertAlmostEqual(opponent.health_percentage, 0.5)

    def test_negative_health(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        opponent = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            name="Goblin",
            max_health=20,
            health=-5,
        )
        self.assertAlmostEqual(opponent.health_percentage, 0.0)


class CombatParticipantTest(TestCase):
    """Test CombatParticipant model."""

    def test_create_participant(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=sheet,
            max_health=100,
            health=100,
        )
        self.assertEqual(participant.status, ParticipantStatus.ACTIVE)
        self.assertIsNone(participant.covenant_role)
        self.assertFalse(participant.dying_final_round)

    def test_effective_speed_rank_no_role(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=sheet,
            max_health=100,
            health=100,
        )
        self.assertEqual(participant.effective_speed_rank, 20)

    def test_effective_speed_rank_with_role(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=CovenantRole.VANGUARD,
            max_health=100,
            health=100,
        )
        self.assertEqual(participant.effective_speed_rank, 1)

    def test_health_percentage(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=sheet,
            max_health=100,
            health=30,
        )
        self.assertAlmostEqual(participant.health_percentage, 0.3)

    def test_wound_description(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.PARTY_COMBAT,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=sheet,
            max_health=100,
            health=95,
        )
        self.assertIn("healthy", participant.wound_description)
```

**Step 2: Run tests to verify they fail**

Run: `arx test world.combat --keepdb`
Expected: FAIL (models don't exist yet)

**Step 3: Implement models**

```python
# src/world/combat/models.py
"""Models for the combat system."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.combat.constants import (
    COVENANT_ROLE_SPEED_RANK,
    NO_ROLE_SPEED_RANK,
    WOUND_DESCRIPTIONS,
    ActionCategory,
    CovenantRole,
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


class CombatEncounter(SharedMemoryModel):
    """A combat encounter — the top-level container for a fight."""

    encounter_type = models.CharField(
        max_length=20,
        choices=EncounterType.choices,
        default=EncounterType.PARTY_COMBAT,
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="combat_encounters",
    )
    round_number = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
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
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="combat_encounters",
    )
    episode = models.ForeignKey(
        "stories.Episode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="combat_encounters",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return (
            f"{self.get_encounter_type_display()} "
            f"(Round {self.round_number}, {self.get_status_display()})"
        )


class ThreatPool(SharedMemoryModel):
    """Named collection of NPC actions with weighted selection."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class ThreatPoolEntry(SharedMemoryModel):
    """One possible action an NPC can take from a threat pool."""

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
        help_text="Selection weight (higher = more likely)",
    )
    targeting_mode = models.CharField(
        max_length=20,
        choices=TargetingMode.choices,
        default=TargetingMode.SINGLE,
    )
    target_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of targets for MULTI mode",
    )
    target_selection = models.CharField(
        max_length=20,
        choices=TargetSelection.choices,
        default=TargetSelection.SPECIFIC_ROLE,
    )
    conditions_applied = models.ManyToManyField(
        "conditions.ConditionTemplate",
        blank=True,
        related_name="threat_pool_entries",
    )
    minimum_phase = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Only available in this phase or later",
    )
    cooldown_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cannot repeat for this many rounds",
    )

    def __str__(self) -> str:
        return f"{self.pool.name}: {self.name}"


class CombatOpponent(SharedMemoryModel):
    """An NPC entity in a combat encounter."""

    encounter = models.ForeignKey(
        CombatEncounter,
        on_delete=models.CASCADE,
        related_name="opponents",
    )
    tier = models.CharField(
        max_length=20,
        choices=OpponentTier.choices,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    health = models.IntegerField(
        help_text="Current health (can go negative)",
    )
    max_health = models.PositiveIntegerField()
    soak_value = models.PositiveIntegerField(
        default=0,
        help_text="Damage below this is absorbed but still probes",
    )
    probing_current = models.PositiveIntegerField(default=0)
    probing_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Points needed to unlock combos (null = no probing mechanic)",
    )
    current_phase = models.PositiveIntegerField(default=1)
    threat_pool = models.ForeignKey(
        ThreatPool,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="opponents",
    )
    status = models.CharField(
        max_length=20,
        choices=OpponentStatus.choices,
        default=OpponentStatus.ACTIVE,
    )

    @property
    def health_percentage(self) -> float:
        """Current health as a fraction of max (clamped to 0.0 minimum)."""
        if self.max_health == 0:
            return 0.0
        return max(0.0, self.health / self.max_health)

    def __str__(self) -> str:
        return f"{self.name} ({self.get_tier_display()})"


class BossPhase(SharedMemoryModel):
    """Defines one stage of a boss fight."""

    opponent = models.ForeignKey(
        CombatOpponent,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    phase_number = models.PositiveIntegerField()
    threat_pool = models.ForeignKey(
        ThreatPool,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="boss_phases",
    )
    soak_value = models.PositiveIntegerField(
        default=0,
        help_text="Soak value for this phase (overrides opponent default)",
    )
    probing_threshold = models.PositiveIntegerField(
        default=50,
        help_text="Probing points needed to unlock combos this phase",
    )
    health_trigger_percentage = models.FloatField(
        null=True,
        blank=True,
        help_text="Boss health percentage that triggers transition to this phase",
    )
    description = models.TextField(
        blank=True,
        help_text="Narrative description when this phase begins",
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
        max_length=20,
        choices=CovenantRole.choices,
        null=True,
        blank=True,
    )
    health = models.IntegerField(
        help_text="Current health (can go negative)",
    )
    max_health = models.PositiveIntegerField()
    speed_modifier = models.IntegerField(
        default=0,
        help_text="Added to base speed rank (positive = slower, negative = faster)",
    )
    status = models.CharField(
        max_length=20,
        choices=ParticipantStatus.choices,
        default=ParticipantStatus.ACTIVE,
    )
    dying_final_round = models.BooleanField(
        default=False,
        help_text="True if this PC gets one last round before death",
    )

    @property
    def effective_speed_rank(self) -> int:
        """Resolution rank: covenant role base + speed modifier."""
        base = COVENANT_ROLE_SPEED_RANK.get(self.covenant_role, NO_ROLE_SPEED_RANK)
        return max(1, base + self.speed_modifier)

    @property
    def health_percentage(self) -> float:
        """Current health as a fraction of max (clamped to 0.0 minimum)."""
        if self.max_health == 0:
            return 0.0
        return max(0.0, self.health / self.max_health)

    @property
    def wound_description(self) -> str:
        """Descriptive text based on current health percentage."""
        pct = self.health_percentage
        for threshold, description in WOUND_DESCRIPTIONS:
            if pct >= threshold:
                return description
        return WOUND_DESCRIPTIONS[-1][1]

    def __str__(self) -> str:
        role = f" ({self.get_covenant_role_display()})" if self.covenant_role else ""
        return f"{self.character_sheet}{role}"


class CombatRoundAction(SharedMemoryModel):
    """A PC's declared actions for a single round."""

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
        choices="world.fatigue.constants.EffortLevel.choices",
        default="medium",
    )
    # Technique FKs — focused action and passives.
    # These point to magic.Technique, which represents both magical and
    # mundane combat abilities (mundane techniques have zero anima cost).
    focused_action = models.ForeignKey(
        "magic.Technique",
        on_delete=models.CASCADE,
        related_name="+",
    )
    focused_target = models.ForeignKey(
        CombatOpponent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Target opponent (null for self-targeted abilities)",
    )
    physical_passive = models.ForeignKey(
        "magic.Technique",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    social_passive = models.ForeignKey(
        "magic.Technique",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    mental_passive = models.ForeignKey(
        "magic.Technique",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
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
    """An NPC's action for a single round (auto-selected from threat pool)."""

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
```

**Step 4: Fix CombatRoundAction effort_level field**

The `choices` field needs the actual import, not a string. Use the EffortLevel import:

```python
from world.fatigue.constants import EffortLevel

# In CombatRoundAction:
effort_level = models.CharField(
    max_length=20,
    choices=EffortLevel.choices,
    default=EffortLevel.MEDIUM,
)
```

**Step 5: Generate and apply migration**

Run: `arx manage makemigrations combat`
Run: `arx manage migrate combat`

**Step 6: Run tests**

Run: `arx test world.combat --keepdb`
Expected: All tests pass

**Step 7: Add admin registrations**

```python
# src/world/combat/admin.py
"""Django admin configuration for the combat system."""

from django.contrib import admin

from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    ThreatPool,
    ThreatPoolEntry,
)


class CombatOpponentInline(admin.TabularInline):
    model = CombatOpponent
    extra = 0


class CombatParticipantInline(admin.TabularInline):
    model = CombatParticipant
    extra = 0


@admin.register(CombatEncounter)
class CombatEncounterAdmin(admin.ModelAdmin):
    list_display = ["id", "encounter_type", "round_number", "status", "created_at"]
    list_filter = ["encounter_type", "status"]
    inlines = [CombatOpponentInline, CombatParticipantInline]


class BossPhaseInline(admin.TabularInline):
    model = BossPhase
    extra = 0


@admin.register(CombatOpponent)
class CombatOpponentAdmin(admin.ModelAdmin):
    list_display = ["name", "tier", "encounter", "health", "max_health", "status"]
    list_filter = ["tier", "status"]
    inlines = [BossPhaseInline]


@admin.register(CombatParticipant)
class CombatParticipantAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "encounter", "covenant_role", "health", "max_health", "status"]
    list_filter = ["status", "covenant_role"]


class ThreatPoolEntryInline(admin.TabularInline):
    model = ThreatPoolEntry
    extra = 1


@admin.register(ThreatPool)
class ThreatPoolAdmin(admin.ModelAdmin):
    list_display = ["name"]
    inlines = [ThreatPoolEntryInline]
```

**Step 8: Commit**

```bash
git add src/world/combat/
git commit -m "feat(combat): add encounter, opponent, participant, and threat pool models"
```

---

### Task 3: Test Factories

**Files:**
- Create: `src/world/combat/factories.py`
- Test: `src/world/combat/tests/test_models.py` (verify factories work)

**Step 1: Create factories**

```python
# src/world/combat/factories.py
"""Factory classes for combat models."""

import factory
import factory.django as factory_django

from world.combat.constants import (
    ActionCategory,
    EncounterType,
    OpponentTier,
    TargetingMode,
    TargetSelection,
)
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    ThreatPool,
    ThreatPoolEntry,
)


class CombatEncounterFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CombatEncounter

    encounter_type = EncounterType.PARTY_COMBAT


class ThreatPoolFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = ThreatPool

    name = factory.Sequence(lambda n: f"Threat Pool {n}")


class ThreatPoolEntryFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = ThreatPoolEntry

    pool = factory.SubFactory(ThreatPoolFactory)
    name = factory.Sequence(lambda n: f"Attack {n}")
    attack_category = ActionCategory.PHYSICAL
    base_damage = 10
    weight = 10
    targeting_mode = TargetingMode.SINGLE
    target_selection = TargetSelection.SPECIFIC_ROLE


class CombatOpponentFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CombatOpponent

    encounter = factory.SubFactory(CombatEncounterFactory)
    tier = OpponentTier.MOOK
    name = factory.Sequence(lambda n: f"Enemy {n}")
    health = 50
    max_health = 50
    threat_pool = factory.SubFactory(ThreatPoolFactory)


class BossOpponentFactory(CombatOpponentFactory):
    """Convenience factory for boss-tier opponents."""

    tier = OpponentTier.BOSS
    health = 500
    max_health = 500
    soak_value = 80
    probing_threshold = 50


class BossPhaseFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BossPhase

    opponent = factory.SubFactory(BossOpponentFactory)
    phase_number = factory.Sequence(lambda n: n + 1)
    threat_pool = factory.SubFactory(ThreatPoolFactory)
    soak_value = 80
    probing_threshold = 50


class CombatParticipantFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CombatParticipant

    encounter = factory.SubFactory(CombatEncounterFactory)
    character_sheet = factory.SubFactory(
        "world.character_sheets.factories.CharacterSheetFactory"
    )
    health = 100
    max_health = 100
```

**Step 2: Add a factory smoke test**

Add to `src/world/combat/tests/test_models.py`:

```python
class FactorySmokeTest(TestCase):
    """Verify all factories create valid instances."""

    def test_encounter_factory(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory()
        self.assertIsNotNone(encounter.pk)

    def test_opponent_factory(self) -> None:
        from world.combat.factories import CombatOpponentFactory

        opponent = CombatOpponentFactory()
        self.assertEqual(opponent.tier, OpponentTier.MOOK)

    def test_boss_factory(self) -> None:
        from world.combat.factories import BossOpponentFactory

        boss = BossOpponentFactory()
        self.assertEqual(boss.tier, OpponentTier.BOSS)
        self.assertEqual(boss.soak_value, 80)

    def test_participant_factory(self) -> None:
        from world.combat.factories import CombatParticipantFactory

        participant = CombatParticipantFactory()
        self.assertIsNotNone(participant.character_sheet)

    def test_threat_pool_factory(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory()
        self.assertEqual(entry.base_damage, 10)
```

**Step 3: Run tests**

Run: `arx test world.combat --keepdb`
Expected: All pass

**Step 4: Commit**

```bash
git add src/world/combat/factories.py src/world/combat/tests/
git commit -m "feat(combat): add FactoryBoy factories for all combat models"
```

---

### Task 4: Encounter Lifecycle Services

**Files:**
- Create: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_services.py`

**Step 1: Write service tests for encounter lifecycle**

```python
# src/world/combat/tests/test_services.py
"""Tests for combat service functions."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CovenantRole,
    EncounterStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatEncounter, CombatOpponentAction
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    select_npc_actions,
)


class AddParticipantTest(TestCase):
    def test_adds_participant_with_health(self) -> None:
        encounter = CombatEncounterFactory()
        sheet = CharacterSheetFactory()
        participant = add_participant(encounter, sheet, max_health=120)
        self.assertEqual(participant.health, 120)
        self.assertEqual(participant.max_health, 120)
        self.assertEqual(participant.status, ParticipantStatus.ACTIVE)

    def test_adds_participant_with_covenant_role(self) -> None:
        encounter = CombatEncounterFactory()
        sheet = CharacterSheetFactory()
        participant = add_participant(
            encounter, sheet, max_health=100, covenant_role=CovenantRole.VANGUARD
        )
        self.assertEqual(participant.covenant_role, CovenantRole.VANGUARD)


class AddOpponentTest(TestCase):
    def test_adds_mook(self) -> None:
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        opponent = add_opponent(
            encounter,
            name="Goblin",
            tier=OpponentTier.MOOK,
            max_health=20,
            threat_pool=pool,
        )
        self.assertEqual(opponent.health, 20)
        self.assertEqual(opponent.tier, OpponentTier.MOOK)

    def test_adds_boss_with_soak(self) -> None:
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        opponent = add_opponent(
            encounter,
            name="Dragon",
            tier=OpponentTier.BOSS,
            max_health=500,
            threat_pool=pool,
            soak_value=80,
            probing_threshold=50,
        )
        self.assertEqual(opponent.soak_value, 80)
        self.assertEqual(opponent.probing_threshold, 50)


class BeginDeclarationPhaseTest(TestCase):
    def test_advances_round_and_sets_status(self) -> None:
        encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=encounter)
        CombatOpponentFactory(encounter=encounter)

        begin_declaration_phase(encounter)

        encounter.refresh_from_db()
        self.assertEqual(encounter.round_number, 1)
        self.assertEqual(encounter.status, EncounterStatus.DECLARING)

    def test_subsequent_call_advances_to_round_2(self) -> None:
        encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=encounter)
        CombatOpponentFactory(encounter=encounter)

        begin_declaration_phase(encounter)
        # Simulate completing round 1
        encounter.status = EncounterStatus.BETWEEN_ROUNDS
        encounter.save(update_fields=["status"])

        begin_declaration_phase(encounter)
        encounter.refresh_from_db()
        self.assertEqual(encounter.round_number, 2)


class SelectNpcActionsTest(TestCase):
    def test_selects_action_for_each_opponent(self) -> None:
        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(
            encounter=encounter, covenant_role=CovenantRole.VANGUARD
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)

        encounter.round_number = 1
        encounter.save(update_fields=["round_number"])

        select_npc_actions(encounter)

        actions = CombatOpponentAction.objects.filter(
            opponent=opponent, round_number=1
        )
        self.assertEqual(actions.count(), 1)

    def test_skips_defeated_opponents(self) -> None:
        encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=encounter)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        opponent = CombatOpponentFactory(
            encounter=encounter, threat_pool=pool, status="defeated"
        )

        encounter.round_number = 1
        encounter.save(update_fields=["round_number"])

        select_npc_actions(encounter)

        actions = CombatOpponentAction.objects.filter(opponent=opponent)
        self.assertEqual(actions.count(), 0)
```

**Step 2: Run tests to verify they fail**

Run: `arx test world.combat.tests.test_services --keepdb`
Expected: ImportError

**Step 3: Implement services**

```python
# src/world/combat/services.py
"""Service functions for the combat system."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import (
    EncounterStatus,
    NPC_SPEED_RANK,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    TargetSelection,
    TargetingMode,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    ThreatPool,
    ThreatPoolEntry,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

logger = logging.getLogger("world.combat")


def add_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    max_health: int,
    covenant_role: str | None = None,
) -> CombatParticipant:
    """Add a PC to a combat encounter."""
    return CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
        health=max_health,
        max_health=max_health,
    )


def add_opponent(
    encounter: CombatEncounter,
    *,
    name: str,
    tier: str,
    max_health: int,
    threat_pool: ThreatPool,
    description: str = "",
    soak_value: int = 0,
    probing_threshold: int | None = None,
) -> CombatOpponent:
    """Add an NPC to a combat encounter."""
    return CombatOpponent.objects.create(
        encounter=encounter,
        tier=tier,
        name=name,
        description=description,
        health=max_health,
        max_health=max_health,
        soak_value=soak_value,
        probing_threshold=probing_threshold,
        threat_pool=threat_pool,
    )


@transaction.atomic
def begin_declaration_phase(encounter: CombatEncounter) -> None:
    """Advance to the next round and open the declaration phase."""
    encounter.round_number += 1
    encounter.status = EncounterStatus.DECLARING
    encounter.save(update_fields=["round_number", "status"])
    logger.info("Encounter %s: Round %d declaration phase", encounter.pk, encounter.round_number)


def _select_threat_entry(
    entries: list[ThreatPoolEntry],
    opponent: CombatOpponent,
) -> ThreatPoolEntry | None:
    """Select a threat pool entry by weight, filtering by phase and cooldown."""
    available = [
        e
        for e in entries
        if e.minimum_phase is None or e.minimum_phase <= opponent.current_phase
    ]
    # Filter cooldowns
    if opponent.round_actions.exists():
        recent_rounds = set(
            opponent.round_actions.filter(
                round_number__gt=opponent.encounter.round_number
                - max((e.cooldown_rounds or 0) for e in available if e.cooldown_rounds),
            ).values_list("threat_entry_id", flat=True)
        )
        available = [
            e
            for e in available
            if e.cooldown_rounds is None or e.pk not in recent_rounds
        ]
    if not available:
        return None
    weights = [e.weight for e in available]
    return random.choices(available, weights=weights, k=1)[0]  # noqa: S311


def _select_targets(
    entry: ThreatPoolEntry,
    participants: list[CombatParticipant],
) -> list[CombatParticipant]:
    """Select target PCs based on the threat entry's targeting mode."""
    active = [p for p in participants if p.status == ParticipantStatus.ACTIVE]
    if not active:
        return []

    if entry.targeting_mode == TargetingMode.ALL:
        return active

    if entry.targeting_mode == TargetingMode.SINGLE:
        count = 1
    else:
        count = min(entry.target_count or 1, len(active))

    if entry.target_selection == TargetSelection.LOWEST_HEALTH:
        active.sort(key=lambda p: p.health)
        return active[:count]
    if entry.target_selection == TargetSelection.RANDOM:
        return random.sample(active, min(count, len(active)))  # noqa: S311
    # Default: SPECIFIC_ROLE (tank) or HIGHEST_THREAT — pick by covenant role priority
    # For now, default to first active participant (tank role targeting TBD)
    return active[:count]


def select_npc_actions(encounter: CombatEncounter) -> list[CombatOpponentAction]:
    """Auto-select actions for all active opponents in the current round."""
    active_opponents = list(
        encounter.opponents.filter(status=OpponentStatus.ACTIVE)
        .select_related("threat_pool")
    )
    participants = list(
        encounter.participants.filter(status=ParticipantStatus.ACTIVE)
    )
    created_actions: list[CombatOpponentAction] = []

    for opponent in active_opponents:
        if not opponent.threat_pool:
            continue
        entries = list(opponent.threat_pool.entries.all())
        if not entries:
            continue

        entry = _select_threat_entry(entries, opponent)
        if entry is None:
            continue

        targets = _select_targets(entry, participants)
        action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=encounter.round_number,
            threat_entry=entry,
        )
        action.targets.set(targets)
        created_actions.append(action)

    return created_actions
```

**Step 4: Run tests**

Run: `arx test world.combat --keepdb`
Expected: All pass

**Step 5: Commit**

```bash
git add src/world/combat/services.py src/world/combat/tests/test_services.py
git commit -m "feat(combat): encounter lifecycle and NPC action selection services"
```

---

### Task 5: Damage Resolution Services

**Files:**
- Modify: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_damage.py`

**Step 1: Write damage resolution tests**

```python
# src/world/combat/tests/test_damage.py
"""Tests for damage resolution in combat."""

from django.test import TestCase

from world.combat.constants import OpponentTier, ParticipantStatus
from world.combat.factories import (
    BossOpponentFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import (
    apply_damage_to_opponent,
    apply_damage_to_participant,
)


class ApplyDamageToOpponentTest(TestCase):
    def test_damage_reduces_health(self) -> None:
        opponent = CombatOpponentFactory(health=50, max_health=50)
        apply_damage_to_opponent(opponent, 20)
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)

    def test_damage_below_soak_still_probes(self) -> None:
        boss = BossOpponentFactory(soak_value=80, probing_threshold=50)
        result = apply_damage_to_opponent(boss, 30)
        boss.refresh_from_db()
        self.assertEqual(boss.health, 500)  # No health damage
        self.assertGreater(boss.probing_current, 0)  # But probing incremented
        self.assertFalse(result.health_damaged)
        self.assertTrue(result.probed)

    def test_damage_above_soak_applies_and_probes(self) -> None:
        boss = BossOpponentFactory(soak_value=80, probing_threshold=50, health=500, max_health=500)
        result = apply_damage_to_opponent(boss, 100)
        boss.refresh_from_db()
        self.assertEqual(boss.health, 480)  # 100 - 80 soak = 20 damage
        self.assertGreater(boss.probing_current, 0)

    def test_zero_health_defeats_mook(self) -> None:
        opponent = CombatOpponentFactory(health=10, max_health=10, tier=OpponentTier.MOOK)
        apply_damage_to_opponent(opponent, 15)
        opponent.refresh_from_db()
        self.assertEqual(opponent.status, "defeated")

    def test_combo_damage_bypasses_soak(self) -> None:
        boss = BossOpponentFactory(soak_value=80)
        apply_damage_to_opponent(boss, 50, bypass_soak=True)
        boss.refresh_from_db()
        self.assertEqual(boss.health, 450)  # Full 50 damage applied


class ApplyDamageToParticipantTest(TestCase):
    def test_damage_reduces_health(self) -> None:
        participant = CombatParticipantFactory(health=100, max_health=100)
        apply_damage_to_participant(participant, 30)
        participant.refresh_from_db()
        self.assertEqual(participant.health, 70)

    def test_health_can_go_negative(self) -> None:
        participant = CombatParticipantFactory(health=10, max_health=100)
        apply_damage_to_participant(participant, 25)
        participant.refresh_from_db()
        self.assertEqual(participant.health, -15)

    def test_knockout_chance_below_20_percent(self) -> None:
        """At low health, there should be knockout risk (tested via result flag)."""
        participant = CombatParticipantFactory(health=15, max_health=100)
        result = apply_damage_to_participant(participant, 5)
        # At 10% health, knockout is possible
        self.assertTrue(result.knockout_eligible)

    def test_death_chance_at_zero(self) -> None:
        participant = CombatParticipantFactory(health=5, max_health=100)
        result = apply_damage_to_participant(participant, 10)
        participant.refresh_from_db()
        self.assertTrue(result.death_eligible)
        self.assertLess(participant.health, 0)

    def test_dying_status_on_lethal(self) -> None:
        """When death is rolled, PC enters DYING with final round flag."""
        participant = CombatParticipantFactory(health=5, max_health=100)
        # Force death by applying massive damage
        result = apply_damage_to_participant(participant, 200, force_death=True)
        participant.refresh_from_db()
        self.assertEqual(participant.status, ParticipantStatus.DYING)
        self.assertTrue(participant.dying_final_round)

    def test_permanent_wound_chance_on_big_hit(self) -> None:
        participant = CombatParticipantFactory(health=100, max_health=100)
        result = apply_damage_to_participant(participant, 60)
        # Hit > 50% of max health — wound eligible
        self.assertTrue(result.permanent_wound_eligible)
```

**Step 2: Create types.py for result dataclasses**

```python
# src/world/combat/types.py
"""Type definitions for the combat system."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpponentDamageResult:
    """Result of applying damage to an NPC."""

    damage_dealt: int
    health_damaged: bool
    probed: bool
    probing_increment: int
    defeated: bool


@dataclass(frozen=True)
class ParticipantDamageResult:
    """Result of applying damage to a PC."""

    damage_dealt: int
    health_after: int
    knockout_eligible: bool
    death_eligible: bool
    permanent_wound_eligible: bool
```

**Step 3: Implement damage services**

Add to `src/world/combat/services.py`:

```python
from world.combat.constants import (
    DEATH_HEALTH_THRESHOLD,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
)
from world.combat.types import OpponentDamageResult, ParticipantDamageResult


def apply_damage_to_opponent(
    opponent: CombatOpponent,
    raw_damage: int,
    *,
    bypass_soak: bool = False,
) -> OpponentDamageResult:
    """Apply damage to an NPC opponent, respecting soak and probing mechanics."""
    effective_soak = 0 if bypass_soak else opponent.soak_value
    damage_through = max(0, raw_damage - effective_soak)
    probing_increment = raw_damage if raw_damage > 0 else 0

    opponent.health -= damage_through
    opponent.probing_current += probing_increment

    defeated = opponent.health <= 0
    if defeated:
        opponent.status = OpponentStatus.DEFEATED

    opponent.save(update_fields=["health", "probing_current", "status"])

    return OpponentDamageResult(
        damage_dealt=damage_through,
        health_damaged=damage_through > 0,
        probed=probing_increment > 0,
        probing_increment=probing_increment,
        defeated=defeated,
    )


def apply_damage_to_participant(
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
) -> ParticipantDamageResult:
    """Apply damage to a PC participant, checking thresholds."""
    participant.health -= damage
    health_after = participant.health

    health_pct = max(0.0, health_after / participant.max_health) if participant.max_health else 0.0

    knockout_eligible = health_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_after > DEATH_HEALTH_THRESHOLD
    death_eligible = health_after <= DEATH_HEALTH_THRESHOLD
    permanent_wound_eligible = damage > (participant.max_health * PERMANENT_WOUND_THRESHOLD)

    if force_death or (death_eligible and participant.status == ParticipantStatus.ACTIVE):
        if force_death:
            participant.status = ParticipantStatus.DYING
            participant.dying_final_round = True

    participant.save(update_fields=["health", "status", "dying_final_round"])

    return ParticipantDamageResult(
        damage_dealt=damage,
        health_after=health_after,
        knockout_eligible=knockout_eligible,
        death_eligible=death_eligible,
        permanent_wound_eligible=permanent_wound_eligible,
    )
```

**Step 4: Run tests**

Run: `arx test world.combat --keepdb`
Expected: All pass

**Step 5: Commit**

```bash
git add src/world/combat/types.py src/world/combat/services.py src/world/combat/tests/test_damage.py
git commit -m "feat(combat): damage resolution services with soak, probing, and health thresholds"
```

---

### Task 6: Resolution Order Service

**Files:**
- Modify: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_resolution.py`

**Step 1: Write resolution order tests**

```python
# src/world/combat/tests/test_resolution.py
"""Tests for combat resolution ordering."""

from django.test import TestCase

from world.combat.constants import NPC_SPEED_RANK, CovenantRole
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import get_resolution_order


class GetResolutionOrderTest(TestCase):
    def test_covenant_roles_resolve_before_npcs(self) -> None:
        encounter = CombatEncounterFactory()
        vanguard = CombatParticipantFactory(
            encounter=encounter, covenant_role=CovenantRole.VANGUARD
        )
        opponent = CombatOpponentFactory(encounter=encounter)

        order = get_resolution_order(encounter)
        # Vanguard (rank 1) should be before NPC (rank 15)
        self.assertEqual(order[0], ("pc", vanguard))
        self.assertEqual(order[1], ("npc", opponent))

    def test_no_role_resolves_after_npcs(self) -> None:
        encounter = CombatEncounterFactory()
        norole = CombatParticipantFactory(encounter=encounter)
        opponent = CombatOpponentFactory(encounter=encounter)

        order = get_resolution_order(encounter)
        npc_idx = next(i for i, (t, _) in enumerate(order) if t == "npc")
        pc_idx = next(i for i, (t, _) in enumerate(order) if t == "pc")
        self.assertLess(npc_idx, pc_idx)

    def test_speed_modifier_adjusts_rank(self) -> None:
        encounter = CombatEncounterFactory()
        fast = CombatParticipantFactory(
            encounter=encounter,
            covenant_role=CovenantRole.SENTINEL,
            speed_modifier=-3,  # Rank 4 - 3 = 1
        )
        normal = CombatParticipantFactory(
            encounter=encounter,
            covenant_role=CovenantRole.SENTINEL,
        )

        order = get_resolution_order(encounter)
        fast_idx = next(i for i, (_, e) in enumerate(order) if hasattr(e, 'pk') and e.pk == fast.pk)
        normal_idx = next(i for i, (_, e) in enumerate(order) if hasattr(e, 'pk') and e.pk == normal.pk)
        self.assertLess(fast_idx, normal_idx)

    def test_unconscious_pcs_excluded(self) -> None:
        encounter = CombatEncounterFactory()
        active = CombatParticipantFactory(
            encounter=encounter, covenant_role=CovenantRole.VANGUARD
        )
        unconscious = CombatParticipantFactory(
            encounter=encounter, status="unconscious"
        )
        CombatOpponentFactory(encounter=encounter)

        order = get_resolution_order(encounter)
        pks = {e.pk for _, e in order if hasattr(e, 'character_sheet')}
        self.assertIn(active.pk, pks)
        self.assertNotIn(unconscious.pk, pks)

    def test_dying_pc_included_for_final_round(self) -> None:
        encounter = CombatEncounterFactory()
        dying = CombatParticipantFactory(
            encounter=encounter,
            covenant_role=CovenantRole.STRIKER,
            status="dying",
            dying_final_round=True,
        )
        CombatOpponentFactory(encounter=encounter)

        order = get_resolution_order(encounter)
        pks = {e.pk for _, e in order if hasattr(e, 'character_sheet')}
        self.assertIn(dying.pk, pks)
```

**Step 2: Implement resolution order service**

Add to `src/world/combat/services.py`:

```python
def get_resolution_order(
    encounter: CombatEncounter,
) -> list[tuple[str, CombatParticipant | CombatOpponent]]:
    """Build the resolution order for a round.

    Returns a list of (entity_type, entity) tuples sorted by speed rank.
    entity_type is "pc" or "npc".
    """
    entries: list[tuple[int, str, CombatParticipant | CombatOpponent]] = []

    # Active PCs (and dying PCs on their final round)
    for p in encounter.participants.all():
        if p.status == ParticipantStatus.ACTIVE:
            entries.append((p.effective_speed_rank, "pc", p))
        elif p.status == ParticipantStatus.DYING and p.dying_final_round:
            entries.append((p.effective_speed_rank, "pc", p))

    # Active NPCs
    for o in encounter.opponents.filter(status=OpponentStatus.ACTIVE):
        entries.append((NPC_SPEED_RANK, "npc", o))

    entries.sort(key=lambda e: e[0])
    return [(entity_type, entity) for _, entity_type, entity in entries]
```

**Step 3: Run tests**

Run: `arx test world.combat --keepdb`
Expected: All pass

**Step 4: Commit**

```bash
git add src/world/combat/services.py src/world/combat/tests/test_resolution.py
git commit -m "feat(combat): resolution order service with covenant rank sorting"
```

---

### Task 7: Update Roadmap and Final Commit

**Files:**
- Modify: `docs/roadmap/combat.md`

**Step 1: Update combat roadmap status**

Change the Party Combat section status from "designed, not yet built" to "Phase 1 complete — foundation models and services". List what was built.

**Step 2: Run full test suite for affected apps**

Run: `arx test world.combat world.checks world.fatigue world.magic --keepdb`
Expected: All pass

**Step 3: Run linting**

Run: `ruff check src/world/combat/`
Run: `ruff format src/world/combat/`

**Step 4: Final commit**

```bash
git add docs/roadmap/combat.md
git commit -m "docs(combat): update roadmap with Phase 1 completion status"
```

---

## What Phase 1 Delivers

After these 7 tasks, the combat app has:
- All core models: encounter, opponents (5 tiers), participants, boss phases, threat pools, round actions
- Constants and enums for the entire combat vocabulary
- FactoryBoy factories for all models
- Encounter lifecycle services (add participants/opponents, begin declaration phase)
- NPC action selection from weighted threat pools with targeting logic
- Damage resolution with soak, probing, bypass mechanics for NPCs
- PC damage with health thresholds (knockout, death, permanent wound eligibility)
- Resolution order service (covenant rank sorting with speed modifiers)
- Admin interface for all models
- Comprehensive tests for all of the above

## What Comes Next (Phase 2 — separate plan)

- **Combo system**: ComboDefinition, ComboSlot, ComboLearning models + detection/upgrade services
- **Full round resolution**: orchestrating the declaration → detection → resolution → consequence cycle
- **Defensive check integration**: PC defense rolls against NPC attacks using `perform_check()`
- **Boss phase transitions**: automatic phase advancement on triggers
- **DEAL_DAMAGE handler**: implementing the stubbed effect handler in mechanics app
- **API endpoints and frontend**: REST API + React combat UI
