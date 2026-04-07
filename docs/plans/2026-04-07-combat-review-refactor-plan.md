# Combat Review Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove denormalized fields from combat models, make CharacterVitals the health authority, add Persona FK to CombatOpponent, and update all services/tests accordingly.

**Architecture:** CombatParticipant becomes a lightweight join table (encounter + character_sheet + covenant_role). Health/status/dying_final_round move to CharacterVitals. Speed is read from covenant_role directly. CombatEncounter drops derivable story/episode FKs. CombatOpponent gains optional Persona FK.

**Tech Stack:** Django models, FactoryBoy factories, combat service functions, Django admin

**Design doc:** `docs/plans/2026-04-07-combat-review-refactor-design.md`

---

### Task 1: Expand CharacterVitals Model

**Files:**
- Modify: `src/world/vitals/models.py`
- Modify: `src/world/vitals/constants.py` (no changes needed, already has WOUND_DESCRIPTIONS)
- Test: `src/world/vitals/tests/test_models.py`

**Step 1: Write failing tests for new CharacterVitals fields and properties**

Add to `src/world/vitals/tests/test_models.py`:

```python
class CharacterVitalsHealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_health_and_max_health_fields(self):
        vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet, health=80, max_health=100
        )
        assert vitals.health == 80
        assert vitals.max_health == 100

    def test_health_defaults_to_zero(self):
        vitals = CharacterVitals.objects.create(character_sheet=self.sheet)
        assert vitals.health == 0
        assert vitals.max_health == 0

    def test_dying_final_round_default(self):
        vitals = CharacterVitals.objects.create(character_sheet=self.sheet)
        assert vitals.dying_final_round is False

    def test_health_percentage_normal(self):
        vitals = CharacterVitals(health=75, max_health=100)
        assert vitals.health_percentage == 0.75

    def test_health_percentage_zero_max(self):
        vitals = CharacterVitals(health=0, max_health=0)
        assert vitals.health_percentage == 0.0

    def test_health_percentage_negative_clamped(self):
        vitals = CharacterVitals(health=-10, max_health=100)
        assert vitals.health_percentage == 0.0

    def test_wound_description_full_health(self):
        vitals = CharacterVitals(health=100, max_health=100)
        assert vitals.wound_description == "healthy appearance"

    def test_wound_description_half_health(self):
        vitals = CharacterVitals(health=50, max_health=100)
        assert vitals.wound_description == "seriously wounded"

    def test_wound_description_zero_health(self):
        vitals = CharacterVitals(health=0, max_health=100)
        assert vitals.wound_description == "incapacitated"
```

**Step 2: Run tests to verify they fail**

Run: `arx test vitals`
Expected: FAIL — fields don't exist yet

**Step 3: Add fields and properties to CharacterVitals**

In `src/world/vitals/models.py`, add to `CharacterVitals`:

```python
health = models.IntegerField(
    default=0,
    help_text="Current health points.",
)
max_health = models.PositiveIntegerField(
    default=0,
    help_text="Maximum health points. Recalculated when stats change.",
)
dying_final_round = models.BooleanField(
    default=False,
    help_text="Whether the character gets one final action before death.",
)

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
```

Add import at top: `from world.vitals.constants import WOUND_DESCRIPTIONS`

**Step 4: Generate migration**

Run: `arx manage makemigrations vitals`

**Step 5: Apply migration**

Run: `arx manage migrate vitals`

**Step 6: Run tests to verify they pass**

Run: `arx test vitals`
Expected: ALL PASS

**Step 7: Commit**

```
feat(vitals): add health, max_health, dying_final_round to CharacterVitals

Health is now the persistent source of truth, read/written by combat
and other damage sources. Properties health_percentage and
wound_description moved here from CombatParticipant.
```

---

### Task 2: Strip CombatParticipant Model

**Files:**
- Modify: `src/world/combat/models.py`
- Modify: `src/world/combat/factories.py`
- Modify: `src/world/combat/admin.py`
- Test: `src/world/combat/tests/test_models.py`

**Step 1: Update CombatParticipant model**

Remove from `CombatParticipant`:
- `health` field
- `max_health` field
- `base_speed_rank` field
- `speed_modifier` field
- `status` field
- `dying_final_round` field
- `effective_speed_rank` property
- `health_percentage` property
- `wound_description` property

Remove from top-of-file imports: `NO_ROLE_SPEED_RANK`, `CharacterStatus`, `WOUND_DESCRIPTIONS`

`CombatParticipant` should end up as:

```python
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
```

**Step 2: Update CombatParticipantFactory**

In `src/world/combat/factories.py`, strip to:

```python
class CombatParticipantFactory(factory_django.DjangoModelFactory):
    """Factory for CombatParticipant."""

    class Meta:
        model = CombatParticipant

    encounter = factory.SubFactory(CombatEncounterFactory)
    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
```

**Step 3: Update admin**

In `src/world/combat/admin.py`:

`CombatParticipantInline.fields`:
```python
fields = ["character_sheet", "covenant_role"]
```

`CombatParticipantAdmin.list_display`:
```python
list_display = ["character_sheet", "encounter", "covenant_role"]
```

Remove `list_filter = ["status"]` and `autocomplete_fields` from `CombatParticipantAdmin`.

**Step 4: Update test_models.py — CombatParticipantTests**

Rewrite `CombatParticipantTests` in `src/world/combat/tests/test_models.py`:

```python
class CombatParticipantTests(TestCase):
    def test_create_defaults(self):
        p = CombatParticipantFactory()
        assert p.encounter_id is not None
        assert p.character_sheet_id is not None
        assert p.covenant_role is None

    def test_str_with_role(self):
        role = CovenantRoleFactory(name="Sword")
        p = CombatParticipantFactory(covenant_role=role)
        assert "Sword" in str(p)

    def test_str_without_role(self):
        p = CombatParticipantFactory()
        assert str(p) == str(p.character_sheet)
```

Remove all `test_effective_speed_rank_*`, `test_health_percentage_*`, `test_wound_description_*` tests from this class (these now live in vitals tests).

**Step 5: Generate migration**

Run: `arx manage makemigrations combat`

**Step 6: Apply migration**

Run: `arx manage migrate combat`

**Step 7: Run model tests to verify they pass**

Run: `arx test combat.tests.test_models`
Expected: PASS (factory smoke tests may fail — fix in next step)

**Step 8: Fix FactorySmokeTest if needed**

`test_participant_factory` should still work since it just calls `CombatParticipantFactory()`. Update if it accesses removed fields.

**Step 9: Commit**

```
refactor(combat): strip CombatParticipant to join table

Remove health, max_health, status, dying_final_round, base_speed_rank,
speed_modifier. These now live on CharacterVitals or are derived from
covenant_role. CombatParticipant is now encounter + character_sheet +
covenant_role.
```

---

### Task 3: Remove Denormalized FKs from CombatEncounter

**Files:**
- Modify: `src/world/combat/models.py`
- Modify: `src/world/combat/admin.py`
- Modify: `src/world/combat/factories.py` (if story/episode were used)
- Test: `src/world/combat/tests/test_models.py`

**Step 1: Remove story and episode FKs from CombatEncounter**

In `src/world/combat/models.py`, remove from `CombatEncounter`:
```python
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
```

**Step 2: Update admin if needed**

Check `CombatEncounterAdmin` — story/episode are not in `list_display` or `list_filter`, so no admin changes needed.

**Step 3: Generate and apply migration**

Run: `arx manage makemigrations combat && arx manage migrate combat`

**Step 4: Run model tests**

Run: `arx test combat.tests.test_models`
Expected: PASS

**Step 5: Commit**

```
refactor(combat): remove denormalized story/episode FKs from CombatEncounter

Story and episode are derivable from scene. Keeping them was
denormalization that risks data integrity without meaningful gain.
```

---

### Task 4: Add Persona FK to CombatOpponent

**Files:**
- Modify: `src/world/combat/models.py`
- Modify: `src/world/combat/admin.py`
- Modify: `src/world/combat/factories.py`
- Test: `src/world/combat/tests/test_models.py`

**Step 1: Write failing test**

Add to `CombatOpponentTests` in `src/world/combat/tests/test_models.py`:

```python
def test_persona_nullable(self):
    opp = CombatOpponentFactory()
    assert opp.persona is None

def test_persona_linkage(self):
    from world.scenes.factories import PersonaFactory
    persona = PersonaFactory()
    opp = CombatOpponentFactory(persona=persona)
    assert opp.persona == persona
```

**Step 2: Run test to verify it fails**

Run: `arx test combat.tests.test_models -k test_persona`
Expected: FAIL

**Step 3: Add persona FK to CombatOpponent**

In `src/world/combat/models.py`, add to `CombatOpponent`:

```python
persona = models.ForeignKey(
    "scenes.Persona",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="combat_opponents",
    help_text="Links to a persistent NPC identity for story NPCs.",
)
```

**Step 4: Update admin**

In `CombatOpponentAdmin.list_display`, add `"persona"` after `"name"`.
In `CombatOpponentInline.fields`, add `"persona"` after `"name"`.

**Step 5: Generate and apply migration**

Run: `arx manage makemigrations combat && arx manage migrate combat`

**Step 6: Run tests**

Run: `arx test combat.tests.test_models -k test_persona`
Expected: PASS

**Step 7: Commit**

```
feat(combat): add optional Persona FK to CombatOpponent

Story NPCs can now be linked to their Persona identity, enabling
tracking of named NPCs across encounters. Generic opponents (bandits,
swarms) leave this null.
```

---

### Task 5: Update Combat Services — add_participant and add_opponent

**Files:**
- Modify: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_services.py`

**Step 1: Update tests for add_participant**

Rewrite `AddParticipantTest` in `test_services.py`:

```python
class AddParticipantTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.encounter = CombatEncounterFactory()
        cls.sheet = CharacterSheetFactory()
        cls.role = CovenantRoleFactory(speed_rank=3)

    def test_adds_participant(self):
        p = add_participant(self.encounter, self.sheet)
        assert p.encounter == self.encounter
        assert p.character_sheet == self.sheet
        assert p.covenant_role is None

    def test_adds_participant_with_covenant_role(self):
        p = add_participant(self.encounter, self.sheet, covenant_role=self.role)
        assert p.covenant_role == self.role
```

**Step 2: Update add_participant service**

```python
def add_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Create a CombatParticipant linking a PC to an encounter."""
    return CombatParticipant.objects.create(
        encounter=encounter,
        character_sheet=character_sheet,
        covenant_role=covenant_role,
    )
```

**Step 3: Run tests**

Run: `arx test combat.tests.test_services`
Expected: AddParticipantTest PASS, others may fail (addressed in later tasks)

**Step 4: Commit**

```
refactor(combat): simplify add_participant — no health/speed params

CombatParticipant is now a join table. Health lives on CharacterVitals,
speed comes from covenant_role.
```

---

### Task 6: Update Damage Services to Use CharacterVitals

**Files:**
- Modify: `src/world/combat/services.py`
- Modify: `src/world/combat/types.py`
- Test: `src/world/combat/tests/test_damage.py`

**Step 1: Update apply_damage_to_participant**

The function now takes a `CombatParticipant` but reads/writes health on `character_sheet.vitals`:

```python
def apply_damage_to_participant(
    participant: CombatParticipant,
    damage: int,
    *,
    force_death: bool = False,
) -> ParticipantDamageResult:
    """Apply damage to a PC via their CharacterVitals.

    Reads and writes health on the participant's CharacterVitals instance.
    Does NOT roll for knockout/death/wounds — only reports eligibility.
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
    )

    vitals.health -= damage
    health_after = vitals.health

    if vitals.max_health > 0:
        health_pct = max(0.0, health_after / vitals.max_health)
    else:
        health_pct = 0.0

    knockout_eligible = (
        health_pct <= KNOCKOUT_HEALTH_THRESHOLD and health_after > DEATH_HEALTH_THRESHOLD
    )
    death_eligible = health_after <= DEATH_HEALTH_THRESHOLD
    permanent_wound_eligible = damage > (vitals.max_health * PERMANENT_WOUND_THRESHOLD)

    update_fields = ["health"]
    if force_death:
        vitals.status = CharacterStatus.DYING
        vitals.dying_final_round = True
        update_fields.extend(["status", "dying_final_round"])

    vitals.save(update_fields=update_fields)

    return ParticipantDamageResult(
        damage_dealt=damage,
        health_after=health_after,
        knockout_eligible=knockout_eligible,
        death_eligible=death_eligible,
        permanent_wound_eligible=permanent_wound_eligible,
    )
```

**Step 2: Remove sync_vitals_from_combat function entirely**

Delete the `sync_vitals_from_combat` function from services.py.

**Step 3: Update test_damage.py — ApplyDamageToParticipantTest**

Tests need to set up CharacterVitals instead of relying on participant.health. Each test that creates a participant must also create vitals:

```python
class ApplyDamageToParticipantTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant = CombatParticipantFactory()

    def setUp(self):
        self.vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=self.participant.character_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        self.vitals.health = 100
        self.vitals.max_health = 100
        self.vitals.status = CharacterStatus.ALIVE
        self.vitals.save()

    def test_damage_reduces_health(self):
        result = apply_damage_to_participant(self.participant, 30)
        self.vitals.refresh_from_db()
        assert self.vitals.health == 70
        assert result.damage_dealt == 30

    def test_health_can_go_negative(self):
        result = apply_damage_to_participant(self.participant, 150)
        self.vitals.refresh_from_db()
        assert self.vitals.health == -50

    def test_knockout_eligible_below_20_percent(self):
        result = apply_damage_to_participant(self.participant, 85)
        assert result.knockout_eligible is True

    def test_not_knockout_eligible_above_20_percent(self):
        result = apply_damage_to_participant(self.participant, 50)
        assert result.knockout_eligible is False

    def test_death_eligible_at_zero(self):
        result = apply_damage_to_participant(self.participant, 100)
        assert result.death_eligible is True

    def test_permanent_wound_on_big_hit(self):
        result = apply_damage_to_participant(self.participant, 60)
        assert result.permanent_wound_eligible is True

    def test_no_permanent_wound_on_small_hit(self):
        result = apply_damage_to_participant(self.participant, 10)
        assert result.permanent_wound_eligible is False

    def test_force_death_sets_dying(self):
        apply_damage_to_participant(self.participant, 10, force_death=True)
        self.vitals.refresh_from_db()
        assert self.vitals.status == CharacterStatus.DYING
        assert self.vitals.dying_final_round is True
```

**Step 4: Run tests**

Run: `arx test combat.tests.test_damage`
Expected: PASS

**Step 5: Commit**

```
refactor(combat): damage services write to CharacterVitals

apply_damage_to_participant now reads/writes health on CharacterVitals
instead of CombatParticipant. Removes sync_vitals_from_combat — vitals
is the source of truth, no sync needed.
```

---

### Task 7: Update Resolution Order to Read from Vitals and CovenantRole

**Files:**
- Modify: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_resolution.py`

**Step 1: Update get_resolution_order**

The function now reads status from vitals and speed from covenant_role:

```python
def get_resolution_order(
    encounter: CombatEncounter,
) -> list[tuple[str, CombatParticipant | CombatOpponent]]:
    """Build the resolution order for a combat round.

    Speed rank comes from covenant_role.speed_rank (or NO_ROLE_SPEED_RANK).
    Status comes from character_sheet.vitals.
    """
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
        ).select_related("covenant_role", "character_sheet")
    )

    # Batch-fetch vitals for all participants
    sheet_ids = [p.character_sheet_id for p in participants]
    vitals_map: dict[int, CharacterVitals] = {
        v.character_sheet_id: v
        for v in CharacterVitals.objects.filter(character_sheet_id__in=sheet_ids)
    }

    ranked: list[tuple[int, str, CombatParticipant | CombatOpponent]] = []
    for p in participants:
        vitals = vitals_map.get(p.character_sheet_id)
        if vitals is None:
            continue
        status = vitals.status
        if status == CharacterStatus.ALIVE or (
            status == CharacterStatus.DYING and vitals.dying_final_round
        ):
            speed = p.covenant_role.speed_rank if p.covenant_role_id else NO_ROLE_SPEED_RANK
            ranked.append((speed, ENTITY_TYPE_PC, p))

    opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
        )
    )
    ranked.extend((NPC_SPEED_RANK, ENTITY_TYPE_NPC, o) for o in opponents)

    ranked.sort(key=lambda item: (item[0], item[2].pk))

    return [(entity_type, entity) for _, entity_type, entity in ranked]
```

**Step 2: Update test_resolution.py**

All resolution tests that set `participant.status` or `participant.dying_final_round` must now set those on `CharacterVitals` instead. Tests that set `base_speed_rank` or `speed_modifier` must now use `covenant_role.speed_rank`.

Key changes pattern — every test that creates a participant with specific status needs:

```python
# Before (old):
p = CombatParticipantFactory(encounter=enc, status=CharacterStatus.ALIVE, base_speed_rank=1)

# After (new):
p = CombatParticipantFactory(encounter=enc, covenant_role=CovenantRoleFactory(speed_rank=1))
CharacterVitals.objects.create(
    character_sheet=p.character_sheet,
    health=100, max_health=100, status=CharacterStatus.ALIVE,
)
```

For speed modifier tests: speed modifiers will come from conditions (future work). For now, remove `test_speed_modifier_adjusts_rank` or convert it to test condition-based modifiers if the conditions integration is straightforward. If not, leave a TODO and remove the test.

**Step 3: Run tests**

Run: `arx test combat.tests.test_resolution`
Expected: PASS

**Step 4: Commit**

```
refactor(combat): resolution order reads vitals and covenant_role

get_resolution_order now reads status from CharacterVitals and speed
from covenant_role.speed_rank instead of denormalized participant fields.
```

---

### Task 8: Update NPC Targeting and Round Orchestrator

**Files:**
- Modify: `src/world/combat/services.py`
- Test: `src/world/combat/tests/test_round_orchestrator.py`
- Test: `src/world/combat/tests/test_services.py` (SelectNpcActionsTest)
- Test: `src/world/combat/tests/test_defense.py`

**Step 1: Update select_npc_actions targeting filter**

In `select_npc_actions`, the active_participants filter currently checks `status=CharacterStatus.ALIVE` on the participant. Now it needs to check vitals:

```python
# Replace the active_participants query with:
from world.vitals.models import CharacterVitals  # noqa: PLC0415

alive_sheet_ids = set(
    CharacterVitals.objects.filter(
        status=CharacterStatus.ALIVE,
        character_sheet__combat_participations__encounter=encounter,
    ).values_list("character_sheet_id", flat=True)
)
active_participants = list(
    CombatParticipant.objects.filter(
        encounter=encounter,
        character_sheet_id__in=alive_sheet_ids,
    )
)
```

**Step 2: Update _resolve_npc_action**

The knockout/death processing currently writes to `participant.status`. Now it writes to vitals:

```python
# In _resolve_npc_action, replace knockout/death processing with:
vitals_obj = CharacterVitals.objects.get(
    character_sheet=target_participant.character_sheet,
)
if dmg_result.death_eligible and vitals_obj.status == CharacterStatus.ALIVE:
    vitals_obj.status = CharacterStatus.DYING
    vitals_obj.dying_final_round = True
    vitals_obj.save(update_fields=["status", "dying_final_round"])
elif dmg_result.knockout_eligible and vitals_obj.status == CharacterStatus.ALIVE:
    vitals_obj.status = CharacterStatus.UNCONSCIOUS
    vitals_obj.save(update_fields=["status"])
```

Remove all `sync_vitals_from_combat` calls.

**Step 3: Update _check_encounter_completion**

```python
def _check_encounter_completion(encounter: CombatEncounter) -> bool:
    """Return True if the encounter should be marked complete."""
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    all_opponents_down = not CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
    ).exists()

    participant_sheet_ids = CombatParticipant.objects.filter(
        encounter=encounter,
    ).values_list("character_sheet_id", flat=True)

    all_pcs_down = not CharacterVitals.objects.filter(
        character_sheet_id__in=participant_sheet_ids,
        status=CharacterStatus.ALIVE,
    ).exists()

    return all_opponents_down or all_pcs_down
```

**Step 4: Update dying final round consumption in resolve_round**

```python
# Replace the dying_participants block with:
from world.vitals.models import CharacterVitals  # noqa: PLC0415

participant_sheet_ids = CombatParticipant.objects.filter(
    encounter=encounter,
).values_list("character_sheet_id", flat=True)

dying_vitals = CharacterVitals.objects.filter(
    character_sheet_id__in=participant_sheet_ids,
    status=CharacterStatus.DYING,
    dying_final_round=True,
)
for vitals in dying_vitals:
    vitals.dying_final_round = False
    vitals.status = CharacterStatus.DEAD
    vitals.save(update_fields=["status", "dying_final_round"])
```

**Step 5: Update declare_action status check**

In `declare_action`, the status check reads from `participant.status`. Change to read from vitals:

```python
from world.vitals.models import CharacterVitals  # noqa: PLC0415

vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
is_alive = vitals.status == CharacterStatus.ALIVE
is_dying_final = vitals.status == CharacterStatus.DYING and vitals.dying_final_round
if not (is_alive or is_dying_final):
    msg = f"Cannot declare action: character status is '{vitals.get_status_display()}'."
    raise ValueError(msg)
```

**Step 6: Update all affected tests**

All tests that create participants with status/health need to create CharacterVitals instead. This affects:
- `test_round_orchestrator.py` — all test classes
- `test_services.py` — `SelectNpcActionsTest`, `DeclareActionTest`
- `test_defense.py` — `ResolveNpcAttackTests`
- `test_damage.py` — `KnockoutDeathProcessingTest`

Pattern for every test setUp that needs a "live" participant:
```python
self.vitals = CharacterVitals.objects.create(
    character_sheet=self.participant.character_sheet,
    health=100,
    max_health=100,
    status=CharacterStatus.ALIVE,
)
```

**Step 7: Run all combat tests**

Run: `arx test combat`
Expected: ALL PASS

**Step 8: Commit**

```
refactor(combat): services read/write CharacterVitals for all status/health

NPC targeting, round orchestration, declaration validation, and
encounter completion all read from CharacterVitals. No more
participant.status or sync_vitals_from_combat.
```

---

### Task 9: Clean Up Constants and Imports

**Files:**
- Modify: `src/world/combat/constants.py`
- Modify: `src/world/combat/models.py`
- Modify: `src/world/combat/services.py`

**Step 1: Update constants.py comment about denormalized speed**

Remove the comment block at lines 115-118 that says "Combat stores a denormalized base_speed_rank per participant". Replace with:

```python
# Speed ranks — lower means faster.
#
# Covenant roles define speed_rank (world.covenants). PCs without a role
# resolve at NO_ROLE_SPEED_RANK. NPCs resolve at NPC_SPEED_RANK.
```

**Step 2: Clean up unused imports across all modified files**

Run: `ruff check src/world/combat/ --fix`

**Step 3: Run all tests**

Run: `arx test combat vitals`
Expected: ALL PASS

**Step 4: Commit**

```
chore(combat): clean up constants comments and unused imports
```

---

### Task 10: Update Vitals Admin and Roadmap

**Files:**
- Modify: `src/world/vitals/admin.py`
- Modify: `docs/roadmap/combat.md`

**Step 1: Update vitals admin to show new fields**

```python
@admin.register(CharacterVitals)
class CharacterVitalsAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "health", "max_health", "status", "died_at"]
    list_filter = ["status"]
    search_fields = ["character_sheet__character__db_key"]
```

**Step 2: Update combat roadmap**

In `docs/roadmap/combat.md`, update the "What Exists" section to reflect:
- CharacterVitals is the health authority (health, max_health, dying_final_round)
- CombatParticipant is a lightweight join table
- CombatOpponent supports optional Persona linkage for story NPCs
- CombatEncounter no longer stores denormalized story/episode FKs

**Step 3: Run full test suite**

Run: `arx test combat vitals covenants`
Expected: ALL PASS

**Step 4: Commit**

```
docs(combat): update roadmap and admin for refactored models
```

---

### Task 11: Final Verification

**Step 1: Run ruff on all changed files**

Run: `ruff check src/world/combat/ src/world/vitals/`

**Step 2: Run full affected test suites**

Run: `arx test combat vitals covenants`
Expected: ALL PASS with no warnings

**Step 3: Verify migrations are clean**

Run: `arx manage makemigrations --check`
Expected: No new migrations needed

**Step 4: Final commit if any fixups needed**

---

## Task Dependency Graph

```
Task 1 (Vitals model) ──┐
                         ├── Task 5 (add_participant) ──┐
Task 2 (Strip participant) ┘                            │
                                                        ├── Task 8 (orchestrator + all services)
Task 3 (Remove story/episode) ── independent            │
                                                        │
Task 4 (Persona FK) ── independent                      │
                                                        │
Task 6 (Damage services) ──────────────────────────────┘
                                                        │
Task 7 (Resolution order) ─────────────────────────────┘
                                                        │
Task 9 (Cleanup) ──────────────────────────────────────┘
                                                        │
Task 10 (Admin + roadmap) ─────────────────────────────┘
                                                        │
Task 11 (Final verification) ──────────────────────────┘
```

Tasks 1+2 must come first (model changes). Tasks 3 and 4 are independent of each other and of 1+2.
Tasks 5-8 depend on 1+2 and build on each other. Tasks 9-11 are cleanup/verification at the end.
