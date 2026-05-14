# Magic-Story Pipeline Slice — Design

**Status:** Draft (brainstorm complete 2026-05-14)
**Owner:** Tehom (magic + core infrastructure)
**Scope:** Single proof-of-concept slice — backend only

## Why this slice exists

Demonstrate, end-to-end on a fresh clone, that magic-in-stories works: an Abyssal-aligned
character with a reactive magical scar casts a technique in a room whose magical aura
includes Celestial-affinity Resonances, a reactive trigger forces a resist check whose
difficulty scales with the room's celestial intensity, the check outcome branches to one
of four reaction conditions, the story routes accordingly, narrative messages publish,
and achievement grants fire including first-earner Discovery semantics.

Crucially, the slice exercises affinity-based room state from the start — the reactive
trigger queries the room's `RoomAuraProfile.room_resonances` directly via a new filter
operator, and check difficulty derives from the count of Celestial-affinity resonances
tagged on the room. This reflects the actual state model Arx II will use, not a flat
boolean Property placeholder.

The slice doubles as authored default seed content. Re-running `arx seed dev` will populate
the rows; the integration test asserts the slice works against that seed.

This is the wedge that validates the Scope 5.5 reactive-layer infrastructure (DONE on `design/reactive-layer`)
with real authored content rather than test-only factories, and proves the integration
shape between magic, conditions, stories, and achievements.

## Success criteria

1. `arx test integration_tests.test_magic_story_pipeline` passes on `--no-keepdb` with
   8 parametrized subtests (4 outcomes × 2 intensity tiers) + 1 explicit second-earner subtest.
2. Re-running `seed_magic_dev()` on an edited DB preserves edits (idempotency, never overwrites).
3. Applying the Hallowed Rejection marker condition to a character via the existing
   `apply_condition` service path automatically installs the reactive `Trigger` row with no
   per-content service function.
4. After the slice lands, authoring a second reactive scar requires zero new service code —
   only new seed rows (ConditionTemplates, FlowDefinition, TriggerDefinition, etc.).
5. After the slice lands, granting an achievement on "condition X is gained" requires only
   authoring a `StatDefinition`, an `Achievement`, an `AchievementRequirement`, and a
   `ConditionStatRule` bridge row — no service-layer code changes.
6. After the slice lands, a reactive flow can query "this room has affinity X" via the
   filter DSL and scale check difficulty by affinity-tag count via a generic helper service
   function. Both are reusable for other reactive-content slices and require no further
   schema or DSL changes.

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
- Dynamic / time-varying room aura state (consecration that wanes with time-of-day,
  weather-driven aura, ritual-induced temporary attunement). Slice uses static
  RoomResonance rows on RoomAuraProfile.
- Multi-affinity rooms exercising more than one affinity simultaneously (a room that's
  Celestial + Primal, etc.). Slice uses single-affinity tagging (Celestial only) on test rooms.
- Per-affinity reaction severity authoring (e.g., abyssal-aligned takes 1.5× severity from
  celestial rooms while primal-aligned takes 0.5×). Slice uses uniform per-tag severity
  scaling on the test character only.
- Filter DSL operator generalization beyond `has_affinity_resonance` (e.g., a generic
  `count_relation_filtered` operator that works for any M2M-with-discriminator pattern).
  Slice ships one specific operator; generalization is a followup.

## Architecture

The slice is composed of nine units, each with one purpose:

1. `ConditionTemplate.reactive_triggers` M2M to `flows.TriggerDefinition` — auto-install
   plumbing from the original Scope 5.5 spec, finally landed.
2. `apply_condition()` extension: auto-install Trigger rows from `template.reactive_triggers`,
   and (separately) auto-increment any bridged StatDefinitions from `ConditionStatRule`.
3. `achievements.ConditionStatRule` bridge model with `ConditionEventType` discriminator —
   maps condition events to stat increments without coupling ConditionTemplate to
   achievement primitives.
4. **New filter DSL operator `has_affinity_resonance`** in `flows/filters/evaluator.py`
   + matching validator entry. Evaluates "does this room (resolved from the path) have at
   least one Resonance with the named Affinity tagged via RoomAuraProfile?" Reusable for
   any reactive content keyed on room aura state.
5. **New helper service function `compute_intensity_difficulty`** in
   `flows/service_functions/` — returns `base_difficulty + per_resonance_modifier * count`
   where count is the number of resonances of a named affinity tagged on the given room
   (0 if no aura profile). Generic helper; reusable for any flow needing intensity-scaled
   difficulty.
6. Authored reactive content: 3 Affinity rows (Celestial / Primal / Abyssal), 3
   Celestial-affinity Resonance rows, 2 Rooms (low and high celestial intensity), marker
   condition (Hallowed Rejection), 5 reaction conditions, 1 CheckType + ResultChart with
   placeholder tuning, 1 FlowDefinition + steps, 1 TriggerDefinition.
7. Authored achievement content: 3 StatDefinitions, 3 ConditionStatRules, 3 Achievements +
   AchievementRequirements (CRITICAL_SUCCESS + SUCCESS + CRITICAL_FAILURE paths; Burning path
   gets no achievement).
8. Authored story content: 1 Story (CHARACTER scope), 1 Chapter, 4 Episodes, 4 Beats on
   Episode 1, 4 Transitions, 4 TransitionRequiredOutcomes.
9. Pipeline test + seed orchestrators: `seed_canonical_affinities()`,
   `seed_canonical_resonances()`, and `seed_starter_magic_story()` wired into
   `seed_magic_dev()` in dependency order.

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

### `perform_check()` test-rig hook + capture

Located at `src/world/checks/services.py:28` (existing). Add one optional keyword for the
forced outcome and write the call's `difficulty` value to a capture object accessible
through the context manager:

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
    _record_capture(check_type=check_type, difficulty=difficulty)  # no-op outside test ctx
    if _forced_outcome is None:
        _forced_outcome = _read_thread_local_override()
    if _forced_outcome is not None:
        _clear_thread_local_override()
        return CheckResult(outcome=_forced_outcome, ...)
    # ...existing resolution logic...
```

```python
# world/checks/test_helpers.py — NEW file

@dataclass
class CheckCapture:
    check_type: CheckType | None = None
    difficulty: int | None = None

@contextmanager
def force_check_outcome(outcome: CheckOutcome) -> Iterator[CheckCapture]:
    """Test-only: forces the NEXT perform_check call to return `outcome`,
    and yields a CheckCapture object that records the difficulty / check_type
    the call was about to use. Tests assert on capture fields to verify
    intensity-scaled difficulty was computed correctly.

    Uses thread-locals (one for the outcome override, one for the capture).
    perform_check reads + clears the outcome override; capture is yielded
    through the manager so the test has direct access.

    NOT a production code path — strictly opt-in via this context manager.
    Tests run sequentially in one Evennia test process, so thread-local
    collision is not a concern.
    """
    ...
```

This is the single test-only seam. No mocking of `apply_condition`, `evaluate_auto_beats`,
`_check_achievements`, or any other internal.

### New filter DSL operator `has_affinity_resonance`

Located at `src/flows/filters/evaluator.py` (existing). Add an entry to the operator
dispatch table:

```python
OP_HAS_AFFINITY_RESONANCE = "has_affinity_resonance"

# In _apply_operator dispatch table:
OP_HAS_AFFINITY_RESONANCE: lambda r, v: _has_affinity_resonance(r, v),

def _has_affinity_resonance(room_obj: Any, affinity_name: str) -> bool:
    """True if room_obj (an ObjectDB / RoomProfile bearer) has at least one
    Resonance tagged on its RoomAuraProfile whose Affinity name matches.
    Returns False if room has no aura profile.
    """
    profile_data = getattr(room_obj, "db", room_obj)
    room_profile = getattr(profile_data, "room_profile", None)
    aura_profile = getattr(room_profile, "room_aura_profile", None)
    if aura_profile is None:
        return False
    return aura_profile.room_resonances.filter(
        resonance__affinity__name=affinity_name,
    ).exists()
```

Plus a matching entry in `src/flows/filters/validator.py` so authored filter JSON
validates the new operator.

The trigger's filter becomes:
```json
{"path": "location", "op": "has_affinity_resonance", "value": "Celestial"}
```

### New helper service function `compute_intensity_difficulty`

Located at `src/flows/service_functions/affinity.py` (new module — affinity-driven
helpers for reactive flows). Generic; not Hallowed-Rejection-specific.

```python
def compute_intensity_difficulty(
    *,
    room: ObjectDB,
    affinity_name: str,
    base_difficulty: int,
    per_resonance_modifier: int,
) -> int:
    """Compute a difficulty value that scales with a room's affinity intensity.

    Returns `base_difficulty + (count * per_resonance_modifier)` where count
    is the number of Resonance rows tagged on the room's RoomAuraProfile whose
    Affinity matches the given name. If the room has no RoomAuraProfile,
    `count` is 0 and `base_difficulty` is returned.

    Reusable across any reactive flow that wants intensity-scaled difficulty.
    """
    profile_data = getattr(room, "db", room)
    room_profile = getattr(profile_data, "room_profile", None)
    aura_profile = getattr(room_profile, "room_aura_profile", None)
    if aura_profile is None:
        return base_difficulty
    count = aura_profile.room_resonances.filter(
        resonance__affinity__name=affinity_name,
    ).count()
    return base_difficulty + (count * per_resonance_modifier)
```

Authored flows call this via `CALL_SERVICE_FUNCTION` and store the result in a flow
variable to pass as `difficulty` to `perform_check`.

## Authored Content Inventory

All content lives in `src/integration_tests/game_content/magic.py` under a new
`seed_starter_magic_story()` function. Composed via `get_or_create(natural_key, defaults={...})`
per project seed rule.

### Magic-side rows

**Canonical affinity/resonance content** (lives in their own seed helpers so other future
magic content can compose with them without depending on the magic-story seed):

| # | Model | Row | Key fields |
|---|-------|-----|------------|
| 1 | `magic.Affinity` | **Celestial** | seeded via `seed_canonical_affinities()` |
| 2 | `magic.Affinity` | **Primal** | seeded via `seed_canonical_affinities()` |
| 3 | `magic.Affinity` | **Abyssal** | seeded via `seed_canonical_affinities()` |
| 4 | `magic.Resonance` | **Light** | affinity=#1 (Celestial); seeded via `seed_canonical_resonances()` |
| 5 | `magic.Resonance` | **Sanctity** | affinity=#1 (Celestial); seeded via `seed_canonical_resonances()` |
| 6 | `magic.Resonance` | **Radiance** | affinity=#1 (Celestial); seeded via `seed_canonical_resonances()` |

**Story-specific magic content** (lives in `seed_starter_magic_story()`):

| # | Model | Row | Key fields |
|---|-------|-----|------------|
| 7 | `checks.CheckType` | `endure_hallowed_ground` | placeholder difficulty base |
| 8 | `checks.ResultChart` + `ResultChartOutcome` rows | rank → CheckOutcome mapping | placeholder tuning; 4 outcomes mapped |
| 9 | `conditions.ConditionTemplate` | **Tempered Against Light** | narrative reaction (CRITICAL_SUCCESS) |
| 10 | `conditions.ConditionTemplate` | **Singed** | narrative reaction (SUCCESS) |
| 11 | `conditions.ConditionTemplate` | **Burning** | reaction (FAILURE) — reuse via `get_or_create(name="Burning")` |
| 12 | `conditions.ConditionTemplate` | **Hallowed Burn** | severe reaction (CRITICAL_FAILURE) |
| 13 | `conditions.ConditionTemplate` | **Cast Disrupted** | secondary penalty (CRITICAL_FAILURE only) |
| 14 | `flows.FlowDefinition` | **Hallowed Rejection reactive flow** | + FlowStepDefinition rows below |
| 15 | `flows.TriggerDefinition` | **Hallowed Rejection — technique used near celestial aura** | event_name=TECHNIQUE_USED, `base_filter_condition={"path": "location", "op": "has_affinity_resonance", "value": "Celestial"}`, FK to #14 |
| 16 | `conditions.ConditionTemplate` | **Hallowed Rejection** | marker; `reactive_triggers=[#15]` via M2M |
| 17 | Room (`evennia_extensions.RoomProfile`) | **The Hallowed Threshold (Low)** | low-intensity test room |
| 18 | `magic.RoomAuraProfile` | for room #17 | OneToOne extension |
| 19 | `magic.RoomResonance` | aura #18 → resonance #4 (Light) | single tag; intensity=1 |
| 20 | Room (`evennia_extensions.RoomProfile`) | **The Hallowed Threshold (High)** | high-intensity test room |
| 21 | `magic.RoomAuraProfile` | for room #20 | OneToOne extension |
| 22 | `magic.RoomResonance` | aura #21 → resonance #4 (Light) | tag 1 of 3 |
| 23 | `magic.RoomResonance` | aura #21 → resonance #5 (Sanctity) | tag 2 of 3 |
| 24 | `magic.RoomResonance` | aura #21 → resonance #6 (Radiance) | tag 3 of 3; intensity=3 |
| — | Technique | (no new row) | Reuse one cantrip from the 25-cantrip starter catalog (1.8 in Phase 1). Documented in seed code comment. |

### FlowStepDefinition steps for #14

Composed from existing FlowActionChoices (no new action choices required). The first
step computes intensity-scaled difficulty; the second forces a check using it; subsequent
conditionals branch on the outcome:

```
1. CALL_SERVICE_FUNCTION: compute_intensity_difficulty(
       room=event.location,
       affinity_name="Celestial",
       base_difficulty=10,
       per_resonance_modifier=5,
   ) → flow variable "computed_difficulty"
2. CALL_SERVICE_FUNCTION: perform_check(
       target=caster,
       check_type=endure_hallowed_ground,
       difficulty=$computed_difficulty,
   ) → flow variable "check_outcome"
3. CONDITIONAL on check_outcome == "critical_success":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Tempered Against Light")
4. CONDITIONAL on check_outcome == "success":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Singed")
5. CONDITIONAL on check_outcome == "failure":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Burning")
6. CONDITIONAL on check_outcome == "critical_failure":
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Hallowed Burn")
   → CALL_SERVICE_FUNCTION: apply_condition(target=caster, template="Cast Disrupted")
```

Difficulty values are placeholder. For low-intensity room (1 celestial resonance):
`difficulty = 10 + 1 * 5 = 15`. For high-intensity room (3 celestial resonances):
`difficulty = 10 + 3 * 5 = 25`. Production tuning is a separate Phase 2 / Section 7 task.

### Achievement-bridge rows

| # | Model | Row | Key fields |
|---|-------|-----|------------|
| 25 | `achievements.StatDefinition` | `conditions.tempered_against_light.gained` | counter slot |
| 26 | `achievements.StatDefinition` | `conditions.singed.gained` | counter slot |
| 27 | `achievements.StatDefinition` | `conditions.hallowed_burn.gained` | counter slot |
| 28 | `achievements.ConditionStatRule` | Tempered (#9) → stat #25 / GAINED / +1 | bridge |
| 29 | `achievements.ConditionStatRule` | Singed (#10) → stat #26 / GAINED / +1 | bridge |
| 30 | `achievements.ConditionStatRule` | Hallowed Burn (#12) → stat #27 / GAINED / +1 | bridge |
| 31 | `achievements.Achievement` | **Hallowed-Hardened** | hidden=True, notification_level=GAMEWIDE |
| 32 | `achievements.AchievementRequirement` | Hallowed-Hardened on stat #25, threshold=1, GTE | |
| 33 | `achievements.Achievement` | **Touched by Light** | hidden=True, notification_level=PERSONAL |
| 34 | `achievements.AchievementRequirement` | Touched by Light on stat #26, threshold=1, GTE | |
| 35 | `achievements.Achievement` | **Cast Out by the Light** | hidden=True, notification_level=GAMEWIDE |
| 36 | `achievements.AchievementRequirement` | Cast Out by the Light on stat #27, threshold=1, GTE | |

Burning intentionally gets no StatDefinition / ConditionStatRule / Achievement — common
failure mode, not noteworthy enough for an achievement.

### Story-side rows

| # | Model | Row | Key fields |
|---|-------|-----|------------|
| 37 | `stories.Story` | **The Hallowed Threshold** | scope=CHARACTER, character_sheet=null (test populates) |
| 38 | `stories.Chapter` | **First Trial** | |
| 39 | `stories.Episode` | **Stepping Into Light** | order=1; source episode |
| 40 | `stories.Episode` | **Tempered Walk** | order=2; destination (CRITICAL_SUCCESS) |
| 41 | `stories.Episode` | **Marked Path** | order=3; destination (SUCCESS and FAILURE share) |
| 42 | `stories.Episode` | **Cast Out** | order=4; destination (CRITICAL_FAILURE) |
| 43 | `stories.Beat` | Beat-Tempered | episode=#39, CONDITION_HELD #9, player_resolution_text="The light bends around you instead of burning. The wound your blood remembers has hardened to a callus." |
| 44 | `stories.Beat` | Beat-Singed | episode=#39, CONDITION_HELD #10, player_resolution_text="Light glances along your skin. A faint mark stings where the spell met sanctified air." |
| 45 | `stories.Beat` | Beat-Burning | episode=#39, CONDITION_HELD #11, player_resolution_text="The ground rejects you. Your skin burns where it meets the consecrated air, and the spell goes wide." |
| 46 | `stories.Beat` | Beat-Hallowed-Burn | episode=#39, CONDITION_HELD #12, player_resolution_text="The sanctified ground answers the spell with fire. You are flung from the working, burning, and the threads in your hands snap." |
| 47 | `stories.Transition` | #39 → #40 | order=1, connection_summary="You walked into hallowed ground and walked out unchanged. Some part of you is being remade." |
| 48 | `stories.Transition` | #39 → #42 | order=2, connection_summary="You broke against the threshold. Whatever was watching turned away. You will not try this again the same way." |
| 49 | `stories.Transition` | #39 → #41 | order=3, connection_summary="The light marked you. You carry the burn now — and a question about what you are." |
| 50 | `stories.Transition` | #39 → #41 | order=4, connection_summary="The light marked you. You carry the burn now — and a question about what you are." (same text; routed from Burning beat) |
| 51 | `stories.TransitionRequiredOutcome` × 4 | one per transition → its beat | required_outcome=SATISFIED |

Zero `EpisodeProgressionRequirement` rows on Episode 1 — the gate is open; routing is
beat-outcome-driven via TROs.

## Pipeline Test Structure

### File: `src/integration_tests/test_magic_story_pipeline.py`

EvenniaTest-derived class. `setUpTestData` invokes `seed_canonical_affinities()`,
`seed_canonical_resonances()`, and `seed_starter_magic_story()` once per class
(all idempotent). Per-test `setUp` builds:

- A factory-generated Abyssal-affinity caster (CharacterSheetFactory + service call to
  apply the seeded Hallowed Rejection marker condition). The application auto-installs
  the reactive Trigger.
- Caster placed in the seeded room — `The Hallowed Threshold (Low)` or
  `The Hallowed Threshold (High)` per the parametrized intensity tier.
- Story #37's `character_sheet` FK populated to point at this caster (slice-level
  mutate-in-place; future "story template cloning" is a separate concern).
- StoryProgress row created pointing at Episode 1.

### Eight parametrized subtests + one explicit second-earner subtest

The 8 subtests cover 4 outcomes × 2 intensity tiers. Test_id field encodes
`<intensity>_<outcome>`; intensity selects which room the caster is placed in.

```python
LOW_INTENSITY_DIFFICULTY = 15   # base=10 + 1 resonance * 5
HIGH_INTENSITY_DIFFICULTY = 25  # base=10 + 3 resonances * 5

@parameterized.expand([
    # (test_id, intensity, outcome, expected_condition, expected_episode, expected_achievement, expected_discovery, expected_difficulty)
    ("low_critical_success",  "low",  CheckOutcome.CRITICAL_SUCCESS, "Tempered Against Light", "Tempered Walk", "Hallowed-Hardened",    True,  LOW_INTENSITY_DIFFICULTY),
    ("low_success",           "low",  CheckOutcome.SUCCESS,           "Singed",                 "Marked Path",   "Touched by Light",     False, LOW_INTENSITY_DIFFICULTY),
    ("low_failure",           "low",  CheckOutcome.FAILURE,           "Burning",                "Marked Path",   None,                   False, LOW_INTENSITY_DIFFICULTY),
    ("low_critical_failure",  "low",  CheckOutcome.CRITICAL_FAILURE,  "Hallowed Burn",          "Cast Out",      "Cast Out by the Light", True,  LOW_INTENSITY_DIFFICULTY),
    ("high_critical_success", "high", CheckOutcome.CRITICAL_SUCCESS, "Tempered Against Light", "Tempered Walk", "Hallowed-Hardened",    True,  HIGH_INTENSITY_DIFFICULTY),
    ("high_success",          "high", CheckOutcome.SUCCESS,           "Singed",                 "Marked Path",   "Touched by Light",     False, HIGH_INTENSITY_DIFFICULTY),
    ("high_failure",          "high", CheckOutcome.FAILURE,           "Burning",                "Marked Path",   None,                   False, HIGH_INTENSITY_DIFFICULTY),
    ("high_critical_failure", "high", CheckOutcome.CRITICAL_FAILURE,  "Hallowed Burn",          "Cast Out",      "Cast Out by the Light", True,  HIGH_INTENSITY_DIFFICULTY),
])
def test_hallowed_threshold(
    self,
    test_id: str,
    intensity: str,
    outcome: CheckOutcome,
    expected_condition: str,
    expected_episode: str,
    expected_achievement: str | None,
    expected_discovery: bool,
    expected_difficulty: int,
):
    # setUp placed caster in the room matching `intensity`.
    # T0: assert pre-state (Hallowed Rejection present, beats UNSATISFIED, no
    #     reaction conditions, no achievements, StoryProgress at Episode 1)
    # T1: with force_check_outcome(outcome) as capture:
    #         use_technique(caster, seeded_cantrip)
    # T2: assert capture.difficulty == expected_difficulty  # intensity-scaled
    # T3: assert expected_condition applied (+ Cast Disrupted on CRITICAL_FAILURE)
    # T4: assert evaluate_auto_beats flips the appropriate Beat, others remain UNSATISFIED;
    #     BeatCompletion ledger row exists for satisfied beat
    # T5: assert StoryProgress.current_episode.title == expected_episode;
    #     EpisodeResolution ledger row exists
    # T6: assert NarrativeMessage rows exist for both beat_completion (body matches
    #     player_resolution_text) and episode_resolution (body matches connection_summary)
    # T7: when expected_achievement is not None:
    #         assert CharacterAchievement exists for caster + expected_achievement;
    #         assert Discovery row exists;
    #         when expected_discovery: assert CharacterAchievement.discovery FK populated
    #     when expected_achievement is None (FAILURE path):
    #         assert no CharacterAchievement rows for caster
```

Plus one dedicated method `test_critical_success_when_discovery_already_exists` that
pre-populates a CharacterAchievement + Discovery for "Hallowed-Hardened" on a different
character, then runs the CRITICAL_SUCCESS path on the low-intensity room, asserts the
second character's CharacterAchievement.discovery is None.

The capture.difficulty assertion is the key end-to-end demonstration that intensity
matters: the same forced outcome on different-intensity rooms produces the same routing
but different computed difficulties, proving the room aura state genuinely feeds into
check resolution.

### Test rig hygiene

- All assertions use specific row counts and explicit FKs — no `assert character.has_achievement(...)`
  shortcuts.
- Only mock-style seam is `force_check_outcome` context manager.
- Subtests don't share state; each is fully self-contained from `setUp`.

## Seed Orchestration

Three seed helpers compose to populate the slice's content. The two new shared helpers
(`seed_canonical_affinities`, `seed_canonical_resonances`) live in
`src/integration_tests/game_content/magic.py` alongside the existing helpers; the
story-specific `seed_starter_magic_story()` lives there too.

Call order from `seed_magic_dev()`:

```
def seed_magic_dev():
    # ...existing calls (config, rituals, thread_pull, cantrips, etc.)...
    seed_canonical_affinities()        # NEW: 3 Affinity rows
    seed_canonical_resonances()        # NEW: 3 Celestial-affinity Resonance rows
    seed_starter_magic_story()         # NEW: rest of slice content
```

### Order of operations within `seed_canonical_affinities()`

Three `get_or_create(name=...)` calls. No FKs needed. Idempotent.

### Order of operations within `seed_canonical_resonances()`

Three `get_or_create(name=..., defaults={"affinity": celestial})` calls. FKs to Affinity
(seeded above). Idempotent. Other future magic content can call this independently to
ensure the Celestial resonances exist before authoring its own RoomResonances.

### Order of operations within `seed_starter_magic_story()`

Per FK dependencies:

1. CheckType + ResultChart + 3 StatDefinitions (no FKs into slice content)
2. Five reaction ConditionTemplates (Tempered, Singed, Burning, Hallowed Burn, Cast Disrupted)
3. Three ConditionStatRule rows (FK to StatDef + ConditionTemplate)
4. Three Achievements + three AchievementRequirements (FK to StatDef)
5. FlowDefinition + FlowStepDefinition rows (FK to CheckType + reaction conditions; uses
   the `has_affinity_resonance` filter + `compute_intensity_difficulty` service function)
6. TriggerDefinition (FK to FlowDefinition)
7. Marker ConditionTemplate (Hallowed Rejection) + wire `reactive_triggers` M2M to TriggerDefinition
8. Two Rooms (Low and High intensity) + their RoomAuraProfile + their RoomResonance rows
   (1 RoomResonance for Low, 3 for High)
9. Story + Chapter + 4 Episodes + 4 Beats + 4 Transitions + 4 TROs

### Natural keys for `get_or_create`

| Model | Natural key | Source |
|-------|-------------|--------|
| `Affinity` | `name` | NaturalKeyMixin |
| `Resonance` | `name` | NaturalKeyMixin |
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
| `RoomAuraProfile` | `room_profile` (primary key OneToOne) | model PK is the FK; idempotent via room_profile lookup |
| `RoomResonance` | `(room_aura_profile, resonance)` | existing unique constraint |
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

4. **Dynamic / time-varying room aura state.** Slice uses static RoomResonance rows.
   Future content may need aura that wanes with time-of-day (consecration at noon, waning
   at dusk), weather-driven aura (storms attune primal rooms), or ritual-induced temporary
   attunement. Likely modeled as a new join table layering on top of RoomResonance with
   `started_at` / `expires_at` fields, plus a query that returns "effective aura at time T."
   Trigger filter DSL would gain a "now-or-at-time" variant.

5. **Multi-affinity rooms.** Slice exercises Celestial-only rooms. The reactive content
   pattern naturally extends to multi-affinity rooms (a room that's both Celestial AND
   Primal). Authoring is straightforward (more RoomResonance rows of different affinities);
   the trigger filter DSL already supports AND/OR composition via the existing
   `{"and": [...]}` / `{"or": [...]}` operators.

6. **Per-affinity reaction severity authoring.** Slice uses one uniform per-tag severity
   scaling (5 difficulty per Celestial tag). A richer model would let authored content
   declare: "Abyssal-aligned takes 1.5× difficulty from Celestial rooms; Primal-aligned
   takes 0.5×." Probably modeled as a small lookup table or a method on Character that
   returns an affinity-interaction modifier. Not in slice scope.

7. **Filter DSL operator generalization.** Slice ships one specific operator
   (`has_affinity_resonance`). A generalized `count_relation_filtered` operator that
   works for any M2M-with-discriminator pattern would let future content express
   richer queries without one-off operators. Followup work; current operator is the
   minimum-viable starting point.

8. **Story template cloning service.** Proper "instantiate authored story per character"
   pattern. Slice avoids this by mutate-in-place on the seeded Story row. Cleaner long-term:
   a `clone_story_for_character(template_story, character_sheet)` service that copies the
   full Story → Chapter → Episode × 4 → Beat × 4 → Transition × 4 → TRO × 4 graph for a
   specific character. Brother's domain.

9. **The other 9 Scope 5.5 reactive scenarios.** Hallowed Threshold proves the pattern;
   remaining scenarios are content-only work.

10. **Production tuning of `endure_hallowed_ground` ResultChart.** Slice ships placeholder
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
- **The ObjectDB ↔ RoomProfile ↔ RoomAuraProfile traversal pattern used by both
  `_has_affinity_resonance` and `compute_intensity_difficulty`.** The spec sketches both as
  `getattr(room_obj, "db", room_obj).room_profile.room_aura_profile`. Verify against the
  actual Evennia idiom — RoomProfile may be reached via `obj.db.room_profile`,
  `obj.room_profile`, a manager, or a different relation entirely depending on how
  `evennia_extensions` exposes it. If the traversal is wrong, BOTH the filter operator and
  the helper silently return False / base_difficulty for every room, and the parametrized
  pipeline tests will all pass with identical difficulty values (silent failure mode that
  would not surface as a test error). Verify before writing either function.

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
- `src/world/checks/services.py` — add `_forced_outcome` test-only kwarg + thread-local read + capture-write
- `src/world/checks/test_helpers.py` — new file, `force_check_outcome` context manager + `CheckCapture` dataclass
- `src/flows/filters/evaluator.py` — add `has_affinity_resonance` operator + handler
- `src/flows/filters/validator.py` — register new operator
- `src/flows/filters/errors.py` — extend if new error types needed
- `src/flows/service_functions/affinity.py` — new module, `compute_intensity_difficulty` helper
- `src/world/stories/models.py` — add Beat UniqueConstraint (if missing)
- `src/world/stories/migrations/NNNN_beat_unique_constraint.py` — new if needed
- `src/integration_tests/game_content/magic.py` — add `seed_canonical_affinities()`, `seed_canonical_resonances()`, `seed_starter_magic_story()`
- `src/integration_tests/test_magic_story_pipeline.py` — new pipeline test
- `src/integration_tests/game_content/tests/test_magic_seed.py` — add idempotency tests for new seed functions
- `src/flows/tests/test_filters/test_has_affinity_resonance.py` — unit tests for the new operator
- `src/flows/tests/test_service_functions/test_affinity.py` — unit tests for `compute_intensity_difficulty`
- `docs/roadmap/seed-and-integration-tests.md` — update Phase 1 / Phase 2 status notes
- `docs/roadmap/magic.md` — note authored reference reactive-scar content shipped, plus the
  affinity-based room state operator landed
