# Magic-Story Pipeline Slice — Design

**Status:** Draft (brainstorm complete 2026-05-14)
**Owner:** Tehom (magic + core infrastructure)
**Scope:** Single proof-of-concept slice — backend only

## Why this slice exists

Demonstrate, end-to-end on a fresh clone, that magic-in-stories works: an Abyssal-aligned
character with a reactive magical scar casts a technique in a Property-tagged location, a
reactive trigger forces a resist check, the check outcome branches to one of four reaction
conditions, the story routes accordingly, narrative messages publish, and achievement grants
fire including first-earner Discovery semantics.

The slice doubles as authored default seed content. Re-running `arx seed dev` will populate
the rows; the integration test asserts the slice works against that seed.

This is the wedge that validates the Scope 5.5 reactive-layer infrastructure (DONE on `design/reactive-layer`)
with real authored content rather than test-only factories, and proves the integration
shape between magic, conditions, stories, and achievements.

## Success criteria

1. `arx test integration_tests.test_magic_story_pipeline` passes on `--no-keepdb` with
   4 parametrized subtests + 1 explicit second-earner subtest.
2. Re-running `seed_magic_dev()` on an edited DB preserves edits (idempotency, never overwrites).
3. Applying the Hallowed Rejection marker condition to a character via the existing
   `apply_condition` service path automatically installs the reactive `Trigger` row with no
   per-content service function.
4. After the slice lands, authoring a second reactive scar requires zero new service code —
   only new seed rows (ConditionTemplates, FlowDefinition, TriggerDefinition, etc.).
5. After the slice lands, granting an achievement on "condition X is gained" requires only
   authoring a `StatDefinition`, an `Achievement`, an `AchievementRequirement`, and a
   `ConditionStatRule` bridge row — no service-layer code changes.

## Out of scope

- Full character-creation pipeline test (Phase 2 task 2T) — slice uses factory-built character.
- 2L FlowDefinition seed library for movement/look/speak — slice authors only its own reactive flow.
- 2Q CovenantRole seed — slice has no combat element.
- Production tuning of `ResultChart` rows (Phase 2 task 2F) — slice uses placeholder values
  sufficient only for `endure_hallowed_ground`.
- Session Outcomes model (brother's domain). Slice's destination episodes implicitly serve as
  outcomes via authored `Transition.connection_summary`; when Outcomes land, destination
  episodes are the natural attachment point for reward payloads.
- Compound predicates on `ConditionStatRule`. Bridge fires unconditionally on `(condition, event_type)`
  in this slice; sibling join table is the additive expansion path.
- Additional `ConditionEventType` values beyond `GAINED` (`REMOVED`, `STAGE_ADVANCED`,
  `SEVERITY_REACHED`) — added one TextChoices entry + matching service path per future use case.
- The other 9 authored-but-skipped Scope 5.5 reactive scenarios.
- Frontend. Backend-only proof of concept; existing story-feed UI surface displays the
  resulting NarrativeMessages.
- Story template cloning — slice mutates the seeded Story's `character_sheet` FK at test time.
- `holy_ground` as a flat Property is a deliberate simplification; the proper affinity-based
  room state model exists (`RoomAuraProfile` + `RoomResonance` M2M) and is a followup.

## Architecture

The slice is composed of seven units, each with one purpose:

1. `ConditionTemplate.reactive_triggers` M2M to `flows.TriggerDefinition` — auto-install
   plumbing from the original Scope 5.5 spec, finally landed.
2. `apply_condition()` extension: auto-install Trigger rows from `template.reactive_triggers`,
   and (separately) auto-increment any bridged StatDefinitions from `ConditionStatRule`.
3. `achievements.ConditionStatRule` bridge model with `ConditionEventType` discriminator —
   maps condition events to stat increments without coupling ConditionTemplate to
   achievement primitives.
4. Authored reactive content: marker condition (Hallowed Rejection), 5 reaction
   conditions (Tempered Against Light, Singed, Burning, Hallowed Burn, Cast Disrupted),
   1 Property (holy_ground), 1 CheckType (endure_hallowed_ground) + ResultChart with
   placeholder tuning, 1 FlowDefinition + steps, 1 TriggerDefinition, 1 Room.
5. Authored achievement content: 3 StatDefinitions, 3 ConditionStatRules, 3 Achievements +
   AchievementRequirements (CRITICAL_SUCCESS + SUCCESS + CRITICAL_FAILURE paths; Burning path
   gets no achievement).
6. Authored story content: 1 Story (CHARACTER scope), 1 Chapter, 4 Episodes, 4 Beats on
   Episode 1, 4 Transitions, 4 TransitionRequiredOutcomes.
7. Pipeline test + seed orchestrator `seed_starter_magic_story()` wired into `seed_magic_dev()`.

## Data Model Changes

Net schema change: ONE M2M field, ONE new model, ONE new TextChoices enum. Two migrations
(one per app).

### `world.conditions` — one M2M field

```python
# world/conditions/models.py — ConditionTemplate

reactive_triggers = models.ManyToManyField(
    "flows.TriggerDefinition",
    blank=True,
    related_name="installing_templates",
    help_text=(
        "TriggerDefinitions installed as Trigger rows on the bearer when an "
        "instance of this template is applied. Removed via Trigger.source_condition CASCADE."
    ),
)
```

No data migration; the M2M is empty for all existing rows. No clean() changes.

### `world.achievements` — one new model + one new TextChoices

```python
# world/achievements/constants.py
class ConditionEventType(models.TextChoices):
    GAINED = "gained", "Condition gained"
    # Future: REMOVED, STAGE_ADVANCED, SEVERITY_REACHED (add as use cases land)


# world/achievements/models.py
class ConditionStatRule(SharedMemoryModel):
    """Rule mapping a ConditionTemplate event to a StatDefinition increment.

    When the named event occurs to an instance of `condition` on a character,
    `stat` is incremented by `increment_amount` for that character. The
    achievements engine then evaluates requirements via the existing
    StatHandler.increment pipeline.

    Lives in achievements/ because achievements own the rule set; conditions
    know nothing about this table. Decoupling per the bridge-table pattern:
    producer (conditions) is unaware of consumer (achievements) concerns.
    """

    stat = models.ForeignKey(
        StatDefinition,
        on_delete=models.CASCADE,
        related_name="condition_rules",
    )
    condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        related_name="stat_rules_for",
    )
    event_type = models.CharField(
        max_length=32,
        choices=ConditionEventType.choices,
    )
    increment_amount = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stat", "condition", "event_type"],
                name="unique_condition_stat_rule",
            ),
        ]
```

## Service Layer Changes

### `apply_condition()` extension (~20 lines added)

Located at `src/world/conditions/services.py:558` (existing). The function's parameter for
the affected character is `target`; the function internally delegates to `_apply_single`
which writes the `ConditionInstance` and emits `_notify_stories_condition_applied(target,
result.instance)` at approximately line 625. The new code installs **after** that
notify call, gated on `result.success and result.instance is not None`, so that the
trigger install and stat increment happen only when an instance was actually created and
after the CONDITION_APPLIED event has propagated.

```python
# After _notify_stories_condition_applied; only when result.success and result.instance is not None:

# Auto-install reactive triggers from the template's M2M.
trigger_defs = list(template.reactive_triggers.all())
if trigger_defs:
    Trigger.objects.bulk_create([
        Trigger(
            trigger_definition=td,
            obj=target.objectdb,
            source_condition=result.instance,
        )
        for td in trigger_defs
    ])

# Auto-increment bridged stats per ConditionStatRule.
rules = ConditionStatRule.objects.filter(
    condition=template,
    event_type=ConditionEventType.GAINED,
).select_related("stat")
for rule in rules:
    target.sheet_data.stats.increment(rule.stat, amount=rule.increment_amount)
```

(`target.sheet_data.stats` is the existing access pattern used elsewhere in
`conditions/services.py`, e.g. lines 731 and 751 — confirm the import paths during planning.)

Trigger removal is already handled by `Trigger.source_condition`'s CASCADE on
ConditionInstance deletion — no removal code needed.

The `_check_achievements` pipeline, Discovery creation, and `on_achievement_earned`
reactivity hook all fire automatically through `StatHandler.increment`.

### `perform_check()` test-rig hook

Located at `src/world/checks/services.py:28` (existing). Add one optional keyword and
a context-managed thread-local for opt-in test override:

```python
# world/checks/services.py
def perform_check(
    *,
    character,
    check_type,
    difficulty=None,
    ...existing...,
    _forced_outcome: CheckOutcome | None = None,  # test only
) -> CheckResult:
    if _forced_outcome is None:
        _forced_outcome = _read_thread_local_override()
    if _forced_outcome is not None:
        _clear_thread_local_override()
        return CheckResult(outcome=_forced_outcome, ...)
    # ...existing resolution logic...
```

```python
# world/checks/test_helpers.py — NEW file

@contextmanager
def force_check_outcome(outcome: CheckOutcome) -> Iterator[None]:
    """Test-only: forces the NEXT perform_check call to return `outcome`.

    Uses a thread-local. perform_check reads and clears it. NOT a production
    code path — strictly opt-in via this context manager. Tests run sequentially
    in one Evennia test process, so thread-local collision is not a concern.
    """
    ...
```

This is the single test-only seam. No mocking of `apply_condition`, `evaluate_auto_beats`,
`_check_achievements`, or any other internal.

## Authored Content Inventory

All content lives in `src/integration_tests/game_content/magic.py` under a new
`seed_starter_magic_story()` function. Composed via `get_or_create(natural_key, defaults={...})`
per project seed rule.

### Magic-side rows

| # | Model | Row | Key fields |
|---|-------|-----|------------|
| 1 | `mechanics.Property` | `holy_ground` | category="Environment" or appropriate PropertyCategory |
| 2 | `checks.CheckType` | `endure_hallowed_ground` | stat=`resolve` (or similar), placeholder difficulty |
| 3 | `checks.ResultChart` + `ResultChartOutcome` rows | rank → CheckOutcome mapping | placeholder tuning; 4 outcomes mapped |
| 4 | `conditions.ConditionTemplate` | **Tempered Against Light** | narrative-only reaction (CRITICAL_SUCCESS) |
| 5 | `conditions.ConditionTemplate` | **Singed** | narrative reaction (SUCCESS) |
| 6 | `conditions.ConditionTemplate` | **Burning** | reaction (FAILURE) — reuse via `get_or_create(name="Burning")` |
| 7 | `conditions.ConditionTemplate` | **Hallowed Burn** | severe reaction (CRITICAL_FAILURE) |
| 8 | `conditions.ConditionTemplate` | **Cast Disrupted** | secondary penalty (CRITICAL_FAILURE only) |
| 9 | `flows.FlowDefinition` | **Hallowed Rejection reactive flow** | + FlowStepDefinition rows |
| 10 | `flows.TriggerDefinition` | **Hallowed Rejection — technique used in holy ground** | event_name=TECHNIQUE_USED, base_filter_condition={"location.has_property": "holy_ground"}, FK to #9 |
| 11 | `conditions.ConditionTemplate` | **Hallowed Rejection** | marker; `reactive_triggers=[#10]` via M2M |
| 12 | Room (`evennia_extensions.RoomProfile`) | **The Hallowed Threshold** | `holy_ground` Property attached |
| — | Technique | (no new row) | Reuse one cantrip from the 25-cantrip starter catalog (1.8 in Phase 1). Documented in seed code comment. |

### FlowStepDefinition steps for #9

Composed from existing FlowActionChoices (no new action choices required):

```
1. CALL_SERVICE_FUNCTION: perform_check(target=caster, check_type=endure_hallowed_ground)
   → flow variable "check_outcome"
2. CONDITIONAL on check_outcome == "critical_success":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Tempered Against Light")
3. CONDITIONAL on check_outcome == "success":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Singed")
4. CONDITIONAL on check_outcome == "failure":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Burning")
5. CONDITIONAL on check_outcome == "critical_failure":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Hallowed Burn")
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Cast Disrupted")
```

### Achievement-bridge rows

| # | Model | Row | Key fields |
|---|-------|-----|------------|
| 13 | `achievements.StatDefinition` | `conditions.tempered_against_light.gained` | counter slot |
| 14 | `achievements.StatDefinition` | `conditions.singed.gained` | counter slot |
| 15 | `achievements.StatDefinition` | `conditions.hallowed_burn.gained` | counter slot |
| 16 | `achievements.ConditionStatRule` | Tempered (#4) → stat #13 / GAINED / +1 | bridge |
| 17 | `achievements.ConditionStatRule` | Singed (#5) → stat #14 / GAINED / +1 | bridge |
| 18 | `achievements.ConditionStatRule` | Hallowed Burn (#7) → stat #15 / GAINED / +1 | bridge |
| 19 | `achievements.Achievement` | **Hallowed-Hardened** | hidden=True, notification_level=GAMEWIDE |
| 20 | `achievements.AchievementRequirement` | Hallowed-Hardened on stat #13, threshold=1, GTE | |
| 21 | `achievements.Achievement` | **Touched by Light** | hidden=True, notification_level=PERSONAL |
| 22 | `achievements.AchievementRequirement` | Touched by Light on stat #14, threshold=1, GTE | |
| 23 | `achievements.Achievement` | **Cast Out by the Light** | hidden=True, notification_level=GAMEWIDE |
| 24 | `achievements.AchievementRequirement` | Cast Out by the Light on stat #15, threshold=1, GTE | |

Burning intentionally gets no StatDefinition / ConditionStatRule / Achievement — common
failure mode, not noteworthy enough for an achievement.

### Story-side rows

| # | Model | Row | Key fields |
|---|-------|-----|------------|
| 25 | `stories.Story` | **The Hallowed Threshold** | scope=CHARACTER, character_sheet=null (test populates) |
| 26 | `stories.Chapter` | **First Trial** | |
| 27 | `stories.Episode` | **Stepping Into Light** | order=1; source episode |
| 28 | `stories.Episode` | **Tempered Walk** | order=2; destination (CRITICAL_SUCCESS) |
| 29 | `stories.Episode` | **Marked Path** | order=3; destination (SUCCESS and FAILURE share) |
| 30 | `stories.Episode` | **Cast Out** | order=4; destination (CRITICAL_FAILURE) |
| 31 | `stories.Beat` | Beat-Tempered | episode=#27, CONDITION_HELD #4, player_resolution_text="The light bends around you instead of burning. The wound your blood remembers has hardened to a callus." |
| 32 | `stories.Beat` | Beat-Singed | episode=#27, CONDITION_HELD #5, player_resolution_text="Light glances along your skin. A faint mark stings where the spell met sanctified air." |
| 33 | `stories.Beat` | Beat-Burning | episode=#27, CONDITION_HELD #6, player_resolution_text="The ground rejects you. Your skin burns where it meets the consecrated air, and the spell goes wide." |
| 34 | `stories.Beat` | Beat-Hallowed-Burn | episode=#27, CONDITION_HELD #7, player_resolution_text="The sanctified ground answers the spell with fire. You are flung from the working, burning, and the threads in your hands snap." |
| 35 | `stories.Transition` | #27 → #28 | order=1, connection_summary="You walked into hallowed ground and walked out unchanged. Some part of you is being remade." |
| 36 | `stories.Transition` | #27 → #30 | order=2, connection_summary="You broke against the threshold. Whatever was watching turned away. You will not try this again the same way." |
| 37 | `stories.Transition` | #27 → #29 | order=3, connection_summary="The light marked you. You carry the burn now — and a question about what you are." |
| 38 | `stories.Transition` | #27 → #29 | order=4, connection_summary="The light marked you. You carry the burn now — and a question about what you are." (same text; routed from Burning beat) |
| 39 | `stories.TransitionRequiredOutcome` × 4 | one per transition → its beat | required_outcome=SATISFIED |

Zero `EpisodeProgressionRequirement` rows on Episode 1 — the gate is open; routing is
beat-outcome-driven via TROs.

## Pipeline Test Structure

### File: `src/integration_tests/test_magic_story_pipeline.py`

EvenniaTest-derived class. `setUpTestData` invokes `seed_starter_magic_story()` once per
class (idempotent). Per-test `setUp` builds:

- A factory-generated Abyssal-affinity caster (CharacterSheetFactory + service call to
  apply the seeded Hallowed Rejection marker condition). The application auto-installs
  the reactive Trigger.
- Caster placed in the seeded **The Hallowed Threshold** room.
- Story #25's `character_sheet` FK populated to point at this caster (slice-level
  mutate-in-place; future "story template cloning" is a separate concern).
- StoryProgress row created pointing at Episode 1.

### Four parametrized subtests + one explicit second-earner subtest

```python
@parameterized.expand([
    ("critical_success", CheckOutcome.CRITICAL_SUCCESS, "Tempered Against Light", "Tempered Walk", "Hallowed-Hardened", True),
    ("success",          CheckOutcome.SUCCESS,           "Singed",                 "Marked Path",   "Touched by Light",  False),
    ("failure",          CheckOutcome.FAILURE,           "Burning",                "Marked Path",   None,                False),
    ("critical_failure", CheckOutcome.CRITICAL_FAILURE,  "Hallowed Burn",          "Cast Out",      "Cast Out by the Light", True),
])
def test_hallowed_threshold(
    self,
    name: str,
    outcome: CheckOutcome,
    expected_condition: str,
    expected_episode: str,
    expected_achievement: str | None,
    expected_discovery: bool,
):
    # T0: assert pre-state (Hallowed Rejection present, beats UNSATISFIED, no
    #     reaction conditions, no achievements, StoryProgress at Episode 1)
    # T1: with force_check_outcome(outcome): use_technique(caster, seeded_cantrip)
    # T2: assert expected_condition applied (+ Cast Disrupted on CRITICAL_FAILURE)
    # T3: assert evaluate_auto_beats flips the appropriate Beat, others remain UNSATISFIED;
    #     BeatCompletion ledger row exists for satisfied beat
    # T4: assert StoryProgress.current_episode.title == expected_episode;
    #     EpisodeResolution ledger row exists
    # T5: assert NarrativeMessage rows exist for both beat_completion (body matches
    #     player_resolution_text) and episode_resolution (body matches connection_summary)
    # T6: when expected_achievement is not None:
    #         assert CharacterAchievement exists for caster + expected_achievement;
    #         assert Discovery row exists;
    #         when expected_discovery: assert CharacterAchievement.discovery FK populated
    #     when expected_achievement is None (FAILURE path):
    #         assert no CharacterAchievement rows for caster
```

Plus one dedicated method `test_critical_success_when_discovery_already_exists` that
pre-populates a CharacterAchievement + Discovery for "Hallowed-Hardened" on a different
character, then runs the CRITICAL_SUCCESS subtest path, asserts the second character's
CharacterAchievement.discovery is None.

### Test rig hygiene

- All assertions use specific row counts and explicit FKs — no `assert character.has_achievement(...)`
  shortcuts.
- Only mock-style seam is `force_check_outcome` context manager.
- Subtests don't share state; each is fully self-contained from `setUp`.

## Seed Orchestration

`seed_starter_magic_story()` lives in `src/integration_tests/game_content/magic.py`.
Called from existing `seed_magic_dev()` after all current seed phases — last because it
references one cantrip from the starter catalog (Phase 1 task 1.8).

### Order of operations within `seed_starter_magic_story()`

Per FK dependencies:

1. Property + CheckType + ResultChart + 3 StatDefinitions (no FKs into slice content)
2. Five reaction ConditionTemplates (Tempered, Singed, Burning, Hallowed Burn, Cast Disrupted)
3. Three ConditionStatRule rows (FK to StatDef + ConditionTemplate)
4. Three Achievements + three AchievementRequirements (FK to StatDef)
5. FlowDefinition + FlowStepDefinition rows (FK to CheckType + reaction conditions)
6. TriggerDefinition (FK to FlowDefinition)
7. Marker ConditionTemplate (Hallowed Rejection) + wire `reactive_triggers` M2M to TriggerDefinition
8. Room (FK to Property)
9. Story + Chapter + 4 Episodes + 4 Beats + 4 Transitions + 4 TROs

### Natural keys for `get_or_create`

| Model | Natural key | Source |
|-------|-------------|--------|
| `Property` | `(name, category)` | existing unique constraint |
| `CheckType` | `name` | NaturalKeyMixin |
| `ResultChart` | TBD — verify in plan phase | |
| `StatDefinition` | `key` | existing unique |
| `ConditionTemplate` | `name` | existing unique |
| `ConditionStatRule` | `(stat, condition, event_type)` | new unique constraint on model |
| `Achievement` | `name` | existing unique |
| `AchievementRequirement` | `(achievement, stat)` | verify or add UniqueConstraint |
| `FlowDefinition` | `name` | existing unique |
| `FlowStepDefinition` | TBD — likely `(flow, parent, order)` — verify | |
| `TriggerDefinition` | `name` | existing unique |
| Room (ObjectDB) | `db_key` | verify acceptable |
| `Story` | `(title, scope)` for nullable character_sheet | verify |
| `Chapter` | `(story, order)` | existing unique_together |
| `Episode` | `(chapter, order)` | existing unique_together |
| `Beat` | `(episode, predicate_type, required_condition_template)` | NEW UniqueConstraint required |
| `Transition` | `(source_episode, target_episode, order)` | verify |
| `TransitionRequiredOutcome` | `(transition, beat)` | existing unique constraint |

Verifications flagged as TBD or NEW are plan-phase tasks.

### Idempotency regression test

In `src/integration_tests/game_content/tests/test_magic_seed.py`:

```python
def test_seed_starter_magic_story_idempotent(self):
    seed_starter_magic_story()
    counts_before = self._snapshot_relevant_counts()

    seed_starter_magic_story()
    counts_after = self._snapshot_relevant_counts()
    self.assertEqual(counts_before, counts_after)

    # Mutation preservation
    template = ConditionTemplate.objects.get(name="Hallowed Rejection")
    template.description = "edited"
    template.save()

    seed_starter_magic_story()
    template.refresh_from_db()
    self.assertEqual(template.description, "edited")
```

Mirrors Phase 1 task 1.9's idempotency pattern.

## Followups & Integration Shape

### Followups (not in scope, captured for future slices)

1. **Session Outcomes model (brother's domain).** Slice's destination episodes — Tempered
   Walk / Marked Path / Cast Out — are the natural attachment point for reward grants when
   Outcomes lands. The slice deliberately authors no reward payload on those episodes beyond
   achievements bridged via conditions.

2. **`ConditionEventType.REMOVED`** + matching `remove_condition` service query. Unlocks
   "Cured" / "Broke Free" / "Cleansed" style achievements. Add one TextChoices entry + ~5-line
   service extension + bridge rows authored. No schema change to `ConditionStatRule`.

3. **Compound predicates on `ConditionStatRule`.** Sibling join table
   `ConditionStatRuleRequirement(rule, predicate_type, config fields)` — mirrors how
   `AchievementRequirement` relates to `Achievement` today. Added when first authored content
   needs "increment only if X AND Y." Current rows keep firing unconditionally (no requirement
   rows = "fires always").

4. **Affinity-based room state replacing flat `holy_ground` Property.** The proper model
   already exists: `magic.RoomAuraProfile` (OneToOne to RoomProfile) + `magic.RoomResonance`
   M2M to `Resonance`, each FK'd to `Affinity` (Celestial / Primal / Abyssal). A "holy" room
   is one with at least one (or N) Celestial-affinity Resonances tagged. Granularity falls
   out naturally — more celestial tags = "holier." The reactive trigger filter DSL needs
   extending to query this (`{"location.has_affinity_count": {"affinity": "celestial", "min": 1}}`).
   Once that lands, the `holy_ground` Property row can be deprecated (or repurposed for
   non-magical "consecrated by tradition" semantics). This work is in Tehom's lane —
   pure magic + flows-filter infrastructure. **Future slices should ship with their own
   integration tests demonstrating the nuance** (different affinities in a place, severity
   based on intensity, etc.).

5. **Story template cloning service.** Proper "instantiate authored story per character"
   pattern. Slice avoids this by mutate-in-place on the seeded Story row. Cleaner long-term:
   a `clone_story_for_character(template_story, character_sheet)` service that copies the
   full Story → Chapter → Episode × 4 → Beat × 4 → Transition × 4 → TRO × 4 graph for a
   specific character. Brother's domain.

6. **The other 9 Scope 5.5 reactive scenarios.** Hallowed Threshold proves the pattern;
   remaining scenarios are content-only work.

7. **Production tuning of `endure_hallowed_ground` ResultChart.** Slice ships placeholder
   rank-to-outcome mapping. Phase 2 task 2F replaces these values when it lands.

### Plan-phase verifications

These are quick checks during plan-writing to confirm or fix natural keys / unique constraints:

- `ResultChart` natural key for `get_or_create`
- `FlowStepDefinition` natural key
- Room ObjectDB seed idempotency via `db_key`
- `Beat` UniqueConstraint on `(episode, predicate_type, required_condition_template)` — likely needs adding
- `Transition` natural key
- `AchievementRequirement` UniqueConstraint on `(achievement, stat)` — verify or add
- Existing factory-created `Burning` ConditionTemplate compatibility with the reactive flow's
  expectations (duration, stage progression, etc.). `get_or_create(name="Burning", defaults={...})`
  semantics protect us, but verify defaults are sane.
- `perform_check` actual signature and where `_forced_outcome` kwarg slots in.

### Integration shape for brother's eventual Outcomes work

The slice provides a clean test bed for Outcomes integration:

- Already authored: destination Episode `summary` + Transition `connection_summary` text (narrative half).
- Already authored: 3 Achievements + Discoveries on the condition-side (partial mechanical payload).
- Outcomes would add: Outcome rows attached to destination Episodes or Transitions, carrying
  reward grants beyond magic-bound achievements (general XP, kudos, codex unlocks for Marked
  Path lore, etc.).
- Outcomes service would fire reward grants alongside (or replacing) the existing
  NarrativeMessage emission on EpisodeResolution.

**Magic-side achievement grants stay condition-bridged, not Outcome-bridged.** Gaining the
Burning condition should grant any associated achievement whether or not the character is
in a story. The condition-side bridge is the right home for "achievements from observable
state changes." Outcome-side payloads are for "rewards from completing a session." Both
layers coexist; the slice's bridge correctly lives on the condition side.

## Design Principles Honored

This slice respects several previously-established design principles, captured here so the
plan-writer and reviewer can check the implementation against them:

- **No service functions for authored content.** Reactive content is data-driven (M2M +
  TriggerDefinition + FlowDefinition + FlowStepDefinition). Adding a second reactive scar
  requires zero new service code.
- **No new SlugField.** Achievement-bridge uses an explicit FK (via `ConditionStatRule`)
  rather than a slug-based string convention. ConditionTemplate gains no slug field.
- **Bridge tables over cross-system FKs.** `ConditionStatRule` lives in `achievements/`,
  the consumer side. ConditionTemplate stays unaware of stats/achievements.
- **GM authority is referee, not author.** All 4 outcomes pre-authored; routing is
  deterministic via CheckOutcome → TransitionRequiredOutcome. Zero GM-in-the-loop decision
  points within the session.
- **Avoid denormalization.** No redundant storage; the bridge model points at primitive rows
  via FKs.
- **Type annotations + SharedMemoryModel** on every new model. `ConditionStatRule` uses
  SharedMemoryModel for identity-map caching of the rule lookups in the `apply_condition`
  hot path.
- **Use FilterSets / proper Django patterns.** Not directly applicable to the slice (no new
  endpoints); the principle's nearest expression is "no `request.query_params` access" —
  N/A for backend-only slice.

## Open Questions Resolved During Brainstorm

For audit trail and future readers:

- "How does the trigger get installed when a marker condition is applied?" → `ConditionTemplate.reactive_triggers`
  M2M + auto-install in `apply_condition` (the spec's original promise, now landing).
- "How does the 4-outcome routing avoid an N×M predicate explosion?" → 4 sibling Beats on
  Episode 1 with single-template CONDITION_HELD predicates + 4 Transitions with
  TransitionRequiredOutcome routing. No predicate-type extensions needed.
- "How is narrative content delivered?" → Already-implemented `notify_beat_completion` +
  `notify_episode_resolution` in `world/stories/services/narrative.py` publish
  NarrativeMessage rows from authored `Beat.player_resolution_text` and
  `Transition.connection_summary`.
- "Where do achievements attach?" → Condition-side bridge (`ConditionStatRule`) using existing
  StatDefinition + Achievement + Discovery primitives. Reward semantics for story-level
  outcomes are deferred to brother's Session Outcomes design.
- "How does the test deterministically force outcomes?" → `force_check_outcome` context
  manager threading a thread-local override into `perform_check`. Documented test-only seam.

## File Surface

New / modified files this slice touches:

- `src/world/conditions/models.py` — add `reactive_triggers` M2M
- `src/world/conditions/migrations/NNNN_reactive_triggers.py` — new
- `src/world/conditions/services.py` — extend `apply_condition`
- `src/world/achievements/models.py` — add `ConditionStatRule`
- `src/world/achievements/constants.py` — add `ConditionEventType` TextChoices
- `src/world/achievements/migrations/NNNN_condition_stat_rule.py` — new
- `src/world/achievements/factories.py` — add `ConditionStatRuleFactory`
- `src/world/checks/services.py` — add `_forced_outcome` test-only kwarg + thread-local read
- `src/world/checks/test_helpers.py` — new file, `force_check_outcome` context manager
- `src/world/stories/models.py` — add Beat UniqueConstraint (if missing)
- `src/world/stories/migrations/NNNN_beat_unique_constraint.py` — new if needed
- `src/integration_tests/game_content/magic.py` — add `seed_starter_magic_story()`
- `src/integration_tests/test_magic_story_pipeline.py` — new pipeline test
- `src/integration_tests/game_content/tests/test_magic_seed.py` — add idempotency test for new seed function
- `docs/roadmap/seed-and-integration-tests.md` — update Phase 1 / Phase 2 status notes
- `docs/roadmap/magic.md` — note authored reference reactive-scar content shipped
