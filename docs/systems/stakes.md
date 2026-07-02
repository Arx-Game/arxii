# Stakes Contract Engine

The GM-authored, player-visible "what's actually at risk" declaration for a story
`Beat` — a named, banded, two-column contract that says exactly what can be won or
lost before players commit to a scene, and scales the Legend payoff by how
dangerous the declared risk actually is *for this party right now*.

**Issue:** #1770 (PR 1 — data model, readiness/activation services, API). **ADR:**
[ADR-0067](../adr/0067-beat-risk-is-the-stakes-wager-declaration.md) (why `Beat.risk`
is reused as the wager declaration rather than a new model).

## Architecture

`Beat.risk` (a `RenownRisk` choice — NONE/LOW/MODERATE/HIGH/EXTREME) is the
upfront "how dangerous is this" declaration a GM makes on a beat, unchanged in
shape from before #1770. What #1770 PR1 adds is the **contract** backing that
declaration: one or more named `Stake` rows (what is actually wagered), each
authored with a `StakeResolution` per outcome column (what happens on WIN vs.
LOSS vs. WITHDRAWAL), validated against designer-tunable `RiskCalibration` bands,
and locked into an audit row (`StakeContractActivation`) when the scene starts so
the contract can't be edited mid-play.

Two ideas thread the whole engine:

- **The contract prices itself for the party in front of it.** A HIGH-risk beat
  written for a level-4 party is not actually risky for a level-10 party — see
  [Effective Risk](#effective-risk) below.
- **Unready never blocks play** — a GM who declares risk but doesn't finish
  authoring the contract still gets to run the scene; the engine just refuses to
  pay out on an incomplete wager (activates at effective `NONE` instead). See
  [Lock Lifecycle](#lock-lifecycle-authoring--activation--completion).

## Models

All models use `SharedMemoryModel` and live in `world.stories.models` alongside
the rest of the narrative hierarchy.

### `Beat.target_level` (new field on the existing `Beat` model)

| Field | Type | Notes |
|---|---|---|
| `target_level` | PositiveSmallIntegerField (null) | The character level this beat's stakes are declared against (e.g. "EXTREME at level 4"). Required — via readiness validation, not `clean()` — when `risk != NONE`. |

### `RiskCalibration`

Designer-tunable calibration bands per risk tier. One row per `RenownRisk` value
above `NONE` (`risk` is unique).

| Field | Type | Notes |
|---|---|---|
| `risk` | CharField (`RenownRisk` choices, unique) | Which tier this row calibrates |
| `severity_floor_total` | PositiveSmallIntegerField | Minimum summed `StakeSeverity` a beat at this risk must wager — no fake stakes |
| `severity_ceiling` | PositiveSmallIntegerField (`StakeSeverity` choices) | Caps any single stake's severity — no "everyone dies" at LOW |
| `max_fuse_hops` | PositiveSmallIntegerField | The [chain rule](#chain-rule--fuse-length): how many failure-cascade hops may separate this tier from a reachable removal-from-play stake |
| `reward_floor` | PositiveIntegerField (default 0) | Reserved — consumed by PR3's win-column reward |
| `reward_ceiling` | PositiveIntegerField (default 0) | Reserved — consumed by PR3's win-column reward |

Seed values (`DEFAULT_RISK_CALIBRATIONS`, `world/stories/constants.py`):

| Risk | `severity_floor_total` | `severity_ceiling` | `max_fuse_hops` |
|---|---|---|---|
| LOW | 1 | COSTLY (2) | 3 |
| MODERATE | 2 | GRAVE (3) | 2 |
| HIGH | 4 | DIRE (4) | 1 |
| EXTREME | 6 | REMOVAL (5) | 0 |

Reading the ceiling column against `max_fuse_hops` is the calibration table's real
content: **only EXTREME may stake removal-from-play on the beat itself**
(ceiling=REMOVAL, hops=0). Every lower tier must reach removal-from-play through
the failure cascade instead — the table *is* the chain rule, not just a severity
band.

### `StakeTemplate`

The menu-first catalog a GM instantiates a `Stake` from (players should almost
never see a freeform stake).

| Field | Type | Notes |
|---|---|---|
| `name` | CharField(100, unique) | |
| `subject_kind` | CharField (`StakeSubjectKind` choices) | What kind of thing this template wagers |
| `severity` | PositiveSmallIntegerField (`StakeSeverity` choices) | |
| `min_risk` / `max_risk` | CharField (`RenownRisk` choices) | Which risk tiers may carry this template, compared by `RISK_LADDER` index (`services.stakes.risk_index`) |
| `player_summary_template` | TextField | Player-facing summary shown at opt-in; GM fills in specifics |
| `description` | TextField (blank) | |
| `is_active` | BooleanField (default True) | |

### `Stake`

One named wager on a beat's contract.

| Field | Type | Notes |
|---|---|---|
| `beat` | FK → `stories.Beat` (`related_name="stakes"`, CASCADE) | |
| `template` | FK → `stories.StakeTemplate` (null, SET_NULL) | Null only for trust-gated custom stakes |
| `subject_kind` | CharField (`StakeSubjectKind` choices) | Denormalized from template at creation (serializer) so a later template retune never rewrites live contracts |
| `severity` | PositiveSmallIntegerField (`StakeSeverity` choices) | Denormalized the same way |
| `subject_sheet` | FK → `character_sheets.CharacterSheet` (null) | For `PERSONAL_JEOPARDY` / `NPC_FATE` subjects |
| `subject_item` | FK → `items.ItemInstance` (null) | For `ITEM` subjects |
| `subject_society` | FK → `societies.Society` (null) | For `FACTION` subjects (society-level) |
| `subject_organization` | FK → `societies.Organization` (null) | For `FACTION` subjects (organization-level) |
| `subject_label` | CharField(200, blank) | Freeform subject name — `CUSTOM` / `CAMPAIGN_TRACK`, or flavor text on any kind |
| `player_summary` | TextField | Player-facing line shown at opt-in: what is wagered, how badly |
| `created_at` / `updated_at` | DateTimeField | |

Exactly one typed subject FK (or `subject_label` for `CUSTOM`) should be populated
per stake; enforcement lives in the serializer, not `clean()`.

### `StakeResolution`

The authored branch for one stake × one outcome column.

| Field | Type | Notes |
|---|---|---|
| `stake` | FK → `stories.Stake` (`related_name="resolutions"`, CASCADE) | |
| `column` | CharField (`StakeResolutionColumn` choices) | `WIN` / `LOSS` / `WITHDRAWAL` |
| `consequence_pool` | FK → checks `ConsequencePool` (null, SET_NULL) | Pool to fire when this column resolves (tier-aware) |
| `escalates_to_risk` | CharField (`RenownRisk` choices, blank) | The [fuse](#chain-rule--fuse-length) mechanic — the risk tier the situation spawned by this branch carries. Blank = no escalation declared |
| `narrative_summary` | TextField (blank) | What happens in the story when this branch fires (GM-authored) |

Unique constraint: `(stake, column)` — one resolution per stake per column.

Pillar 12 (no-fiat removal): this model deliberately carries **no direct
lifecycle/world-state payload** in PR1 — a branch only fires a consequence pool
and/or declares an escalation risk. Structured world-state writers (the actual
mechanism by which a WIN or LOSS *does something permanent*) arrive in PR2 with
validation that rejects direct lifecycle writes from this model.

### `StakeContractActivation`

The lock + audit row written when a staked scene starts.

| Field | Type | Notes |
|---|---|---|
| `beat` | FK → `stories.Beat` (`related_name="stake_activations"`, CASCADE) | |
| `locked_at` | DateTimeField (auto_now_add) | |
| `resolved_at` | DateTimeField (null) | Set by the completion tail; null = open |
| `party_average_level` | PositiveIntegerField | Rounded mean of participants' character levels at activation |
| `declared_target_level` | PositiveIntegerField (default 0) | `Beat.target_level` snapshot at activation (0 = unset) |
| `declared_risk` | CharField (`RenownRisk` choices) | `Beat.risk` snapshot at activation |
| `effective_risk` | CharField (`RenownRisk` choices) | What Legend actually pays on — see [Effective Risk](#effective-risk) |
| `is_ready` | BooleanField | Readiness verdict at activation; `False` forces `effective_risk = NONE` |
| `readiness_notes` | TextField (blank) | `"; "`-joined human-readable reasons when not ready |

Constraint: partial unique `(beat)` where `resolved_at IS NULL` — **at most one
open activation per beat**. This is the actual lock backstop (see
[Lock Lifecycle](#lock-lifecycle-authoring--activation--completion)).

## Constants (`world.stories.constants`)

- **`StakeSeverity`** (IntegerChoices 1–5): `SETBACK`, `COSTLY`, `GRAVE`, `DIRE`,
  `REMOVAL` (5 — the character-loss band; a stake at this severity satisfies the
  chain rule's reachability requirement by itself).
- **`StakeSubjectKind`**: `PERSONAL_JEOPARDY`, `NPC_FATE`, `LOCATION`, `FACTION`,
  `ITEM`, `CAMPAIGN_TRACK`, `CUSTOM` (trust-gated).
- **`StakeResolutionColumn`**: `WIN`, `LOSS`, `WITHDRAWAL`.
- **`RISK_LADDER`**: `["none", "low", "moderate", "high", "extreme"]` — index order
  matters; `services.stakes.risk_index` positions a `RenownRisk` value on it.
- **`DEFAULT_RISK_CALIBRATIONS`**: seed values for the four non-`NONE`
  `RiskCalibration` rows (table above), idempotently created by
  `factories.py::seed_default_risk_calibrations` (staff-tunable in admin
  afterwards).

## Chain Rule / Fuse Length

"Fuse" (equivalently, "the chain rule") is the reachability requirement backing
every risk tier below EXTREME: **a beat's declared risk is only honest if losing
this beat can plausibly *lead to* a character-removal outcome**, even if this
specific beat doesn't stake removal directly. `RiskCalibration.max_fuse_hops`
bounds how many failure-cascade hops that reach may take:

- **Hop 0** (EXTREME only) — the beat itself must offer removal: either a
  `Stake` at `StakeSeverity.REMOVAL`, or its `failure_consequences` pool contains
  a consequence with `character_loss=True`.
- **Hop N** (`N = max_fuse_hops`) — the engine BFS-walks the episode graph
  outward from the beat's episode, following only **failure-gated Transitions**
  (a `Transition` with no required outcome on this episode's beats is treated as
  unconditioned and also counted; otherwise at least one required outcome must be
  `FAILURE`). At each hop it checks whether *any* beat on the downstream episode
  offers removal (same test as hop 0). The walk stops as soon as it finds one, or
  once it exhausts `max_fuse_hops` hops.
- **PITCH-maturity episodes never count** — an unauthored idea downstream can't
  be the thing that makes a HIGH-risk beat honest; only `OUTLINE` or `PLOT`
  maturity nodes participate in the walk.

Implementation: `world.stories.services.stakes._jeopardy_reachable` (BFS),
`_beat_offers_removal` (the hop-0/per-hop removal test), both called from
`_calibration_band_problems` inside `validate_stakes_readiness`.

## Effective Risk

"Highly risky to level 4 is not risky at all to level 10 — no chance they'd lose,
so no stakes." `compute_effective_risk` (`world.stories.services.stakes`)
converts the *declared* risk into what the contract actually pays for *this*
party, given the gap between `Beat.target_level` and the activating party's
average character level:

```
LEVELS_PER_TIER = 2          # every 2 levels of gap shifts one risk tier
UNDER_LEVEL_MAX_UPGRADE = 1   # under-leveled parties upgrade at most one tier

gap = party_average_level - target_level
if gap >= 0:
    shift = -(gap // LEVELS_PER_TIER)              # over-leveled: decays toward NONE
else:
    shift = min(UNDER_LEVEL_MAX_UPGRADE, (-gap) // LEVELS_PER_TIER)  # under-leveled: bounded upgrade

effective_risk = RISK_LADDER[clamp(risk_index(declared_risk) + shift, 0, len(RISK_LADDER)-1)]
```

`NONE` is a fixed point (never shifts). A party 4+ levels over target decays a
HIGH-risk beat to MODERATE; a party 2 levels under target can push it up to
EXTREME at most (the one-tier upgrade cap keeps under-leveling from being
strictly better for reward than playing at level).

`effective_risk_for_beat(beat)` is the read seam other systems should call: it
returns the open `StakeContractActivation.effective_risk` if one exists, else
falls back to `beat.risk` unchanged (so pre-#1770 callers keep their old
behavior). This is what `world.mechanics.effect_handlers._legend_award` reads —
when both `context.beat` and `context.outcome_tier` are present, the Legend award
scales as `RISK_LEGEND_AWARDS[effective_risk_for_beat(beat)] × tier_multiplier`,
floored by the effect's authored `legend_base_value` (an author's explicit
override never scales down).

## Lock Lifecycle (authoring → activation → completion)

```
  AUTHORING                    ACTIVATION (lock)              COMPLETION (resolve)
  ────────────                 ───────────────────             ─────────────────────
  GM declares Beat.risk +      activate_stakes_contract()      _create_completion_and_
  target_level, authors        called at scene start:            fire_pool()
  Stake + StakeResolution        1. idempotent — an open           (services/beats.py)
  rows (blocked while an          activation already exists?       after firing the
  open activation exists)         return it unchanged             completion's
                                                                     consequence pool:
                                2. validate_stakes_readiness()    resolve_open_activation()
                                3. ready?  -> effective_risk        sets resolved_at,
                                   computed via compute_          re-opening authoring
                                   effective_risk()                 edits on the beat
                                   not ready? -> effective
                                   forced to NONE (scene runs,
                                   nothing pays)
                                4. StakeContractActivation
                                   row created (unique-open-
                                   per-beat constraint is the
                                   real concurrency backstop)
```

While an activation is open (`resolved_at IS NULL`), `StakeSerializer` and
`StakeResolutionSerializer` reject **any** write (create or update) to a stake or
resolution whose beat is locked — checked on both sides of a re-point, so you
can't dodge the lock by re-pointing a stake onto or off of a locked beat. This is
"lock-not-copy": the contract is edited in place before activation, then frozen;
there is no separate versioned/snapshotted copy of the `Stake` rows themselves
(only the activation row snapshots `declared_risk` / `declared_target_level`).

`get_open_activation(beat)` is the single query both the lock check and
`effective_risk_for_beat` share.

**Known PR1 gap:** `activate_stakes_contract` has no production call site yet —
it is fully built and unit-tested but nothing currently calls it at scene start.
`resolve_open_activation` **is** wired, into the beat-completion tail
(`world.stories.services.beats._create_completion_and_fire_pool`, called after
the completion's consequence pool fires). Wiring the actual scene-start triggers is
#1770's own remaining PR spine (PR2 combat encounter start, PR3 mission issue,
PR4 GM scene action — scene *grading* specifically rides #1748). The separate
sibling #1771 owns only the player-boundary registry behind
`check_stake_boundaries`, not activation wiring.

## Three Concepts Named "Risk"/"Stakes" — Disambiguation

Three same-shaped-but-unrelated concepts share vocabulary; do not conflate them.

| Concept | Model | Governs | Unrelated to |
|---|---|---|---|
| `Beat.risk` + stakes contract | `stories.Beat.risk` (`RenownRisk`) + this engine | The GM's upfront wager declaration on a story beat; drives Legend award magnitude via `effective_risk_for_beat` | Combat UI acknowledgement; GM access scope |
| `combat.RiskLevel` | `world.combat.constants.RiskLevel` | Whether a hostile cast pulling a target into an encounter requires the target's explicit acknowledgement before proceeding (only `EXTREME`/`LETHAL` gate) | Reward, Legend, stakes contracts |
| `combat.StakesLevel` | `world.combat.constants.StakesLevel` | The narrative *scope* of an encounter's consequences (LOCAL…WORLD) — a GM access-scope tag, not a danger/reward axis | Danger, Legend, stakes contracts |

(Codified in [ADR-0067](../adr/0067-beat-risk-is-the-stakes-wager-declaration.md).)

## Player Visibility

Per the mechanics app's **risk transparency** tenet
(`src/world/mechanics/CLAUDE.md`): *players must always know the risk level
before committing to an action, and if character loss is possible in the
consequence pool, the UI must communicate this before the player acts.* The
stakes contract engine is the structured backing for that tenet at the
beat/scene level: `Stake.player_summary` (and `StakeTemplate.player_summary_template`
before GM customization) is the player-facing line shown *at opt-in*, naming what
is wagered and how badly, before the player commits to the staked scene. Whether
a stake carries `StakeSeverity.REMOVAL` — i.e. character loss is on the table —
is derivable from the same `Stake.severity` field the UI reads to build that
summary; nothing about the reachability/fuse math needs to be shown to players,
only the plain-language wager.

## Services (`world.stories.services.stakes`)

| Function | Signature | Purpose |
|---|---|---|
| `risk_index` | `(risk: str) -> int` | Position of a `RenownRisk` value on `RISK_LADDER` |
| `compute_effective_risk` | `(declared_risk, target_level, party_average_level) -> str` | See [Effective Risk](#effective-risk) |
| `validate_stakes_readiness` | `(beat: Beat) -> StakesReadinessReport` | Readiness gate: target_level declared, ≥1 stake, every stake has WIN+LOSS resolutions, severity within calibration bands, removal reachable within `max_fuse_hops`. Unstaked beats (`risk == NONE`) are trivially ready |
| `get_open_activation` | `(beat: Beat) -> StakeContractActivation \| None` | The single open activation for a beat, if any |
| `activate_stakes_contract` | `(beat, participants) -> StakeContractActivation` | Idempotent lock — see [Lock Lifecycle](#lock-lifecycle-authoring--activation--completion) |
| `effective_risk_for_beat` | `(beat: Beat) -> str` | Read seam: open activation's effective risk, else `beat.risk` |
| `resolve_open_activation` | `(beat: Beat) -> None` | Closes the open activation (sets `resolved_at`); called by the completion tail |

`StakesReadinessReport` (`world.stories.types`): `is_staked: bool`,
`is_ready: bool`, `problems: tuple[str, ...]`.

## API

All five ViewSets live in `world.stories.views`, registered in
`world.stories.urls`.

| ViewSet | Base URL | Permission |
|---|---|---|
| `RiskCalibrationViewSet` | `/api/risk-calibrations/` | `IsStaffOrReadOnly` — every authenticated user reads, only staff writes |
| `StakeTemplateViewSet` | `/api/stake-templates/` | `IsStaffOrReadOnly` |
| `StakeViewSet` | `/api/stakes/` | `IsStakeBeatStoryOwnerOrStaff` (delegates to `obj.beat` → episode → chapter → story ownership, same chain as `BeatViewSet`) |
| `StakeResolutionViewSet` | `/api/stake-resolutions/` | `IsStakeResolutionBeatStoryOwnerOrStaff` (delegates via `obj.stake.beat`) |
| `StakeContractActivationViewSet` | `/api/stake-activations/` | Read-only; `IsStakeBeatStoryOwnerOrStaff` |

`StakeSerializer` and `StakeResolutionSerializer` both enforce, in `validate()`
(DRF never calls `has_object_permission` on create, so the permission class alone
isn't enough on POST):

- the two-sided lock check (both old and new beat/stake on a re-point);
- the ownership gate (`user_owns_beat_story`, staff bypass) — again both sides on
  a re-point;
- `StakeSerializer` additionally validates the beat's declared risk falls within
  `[template.min_risk, template.max_risk]` (by `risk_index`), and gates the
  template-null (custom) path to staff only, mirroring `BeatSerializer.validate`'s
  risk staff-gate.

## PR2–4: Planned, Not Yet Built

The following are explicitly **out of scope for PR1** and marked `[ABSENT]` —
they do not exist in code yet:

| Planned surface | Target PR | Notes |
|---|---|---|
| Structured world-state writers for `StakeResolution` (the actual mechanism by which a WIN/LOSS *does something permanent* to the named subject) | PR2 | Pillar 12 — validated to reject direct lifecycle writes |
| `apply_deed_rewards` WIN-column reward wiring (consuming `RiskCalibration.reward_floor`/`reward_ceiling`) | PR3 | These two fields exist on `RiskCalibration` now, unused until PR3 |
| Opt-in player-facing surfaces (frontend: viewing/accepting a stakes contract before committing to a scene) + the scene-start activation triggers | #1770 PR4 (scene grading: #1748) | Includes wiring the currently-uncalled `activate_stakes_contract` to real scene-start seams; the boundary-registry *backing store* for `check_stake_boundaries` is sibling #1771 |

## Test Coverage

- `src/world/stories/tests/test_models_stakes.py` — model constraints (unique
  bands, partial-unique open activation, `StakeResolution` column uniqueness)
- `src/world/stories/tests/test_services_stakes.py` — `compute_effective_risk`
  curve, `validate_stakes_readiness` (bands + fuse-walk BFS), `activate_stakes_contract`
  idempotency/race handling, `resolve_open_activation`
- `src/world/stories/tests/test_serializers_stakes.py` — lock gate (both sides of
  a re-point), ownership gate, template risk-band validation, custom-stake staff
  gate

## Integrates With

- **Stories** — `Beat.risk` / `Beat.target_level`; the fuse walk reads
  `Transition.cached_required_outcomes` and `Episode.maturity`
- **Societies** — `RISK_LEGEND_AWARDS` (`world.societies.constants`), consumed by
  `_legend_award`'s `effective_risk_for_beat` scaling
- **Checks** — `Beat.failure_consequences` → `resolve_pool_consequences` for the
  `character_loss` reachability test; `StakeResolution.consequence_pool` FK
- **Mechanics** — `world.mechanics.effect_handlers._legend_award` reads
  `effective_risk_for_beat` for the graded beat-completion Legend award path
- **Character Sheets** — `Stake.subject_sheet`; party-average-level computation
  in `activate_stakes_contract` via `services/beats.py::_character_level`
- **Items / Societies (subject FKs)** — `Stake.subject_item` →
  `items.ItemInstance`; `Stake.subject_society` / `subject_organization` →
  `societies.Society` / `societies.Organization`
- **Combat** — deliberately *not* integrated in PR1; see the
  [disambiguation table](#three-concepts-named-riskstakes--disambiguation) above

## Source

`src/world/stories/`
- `models.py` (end of file) — `RiskCalibration`, `StakeTemplate`, `Stake`,
  `StakeResolution`, `StakeContractActivation`; `Beat.target_level`
- `constants.py` — `StakeSeverity`, `StakeSubjectKind`, `StakeResolutionColumn`,
  `RISK_LADDER`, `DEFAULT_RISK_CALIBRATIONS`
- `services/stakes.py` — all service functions above
- `types.py` — `StakesReadinessReport`
- `serializers.py` — the five serializers (search `#1770 PR1`)
- `views.py` / `urls.py` — the five ViewSets
- `permissions.py` — `IsStaffOrReadOnly`, `IsStakeBeatStoryOwnerOrStaff`,
  `IsStakeResolutionBeatStoryOwnerOrStaff`, `user_owns_beat_story`
- `factories.py` — `seed_default_risk_calibrations` + FactoryBoy factories
