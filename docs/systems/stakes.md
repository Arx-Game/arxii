# Stakes Contract Engine

The GM-authored, player-visible "what's actually at risk" declaration for a story
`Beat` — a named, banded, two-column contract that says exactly what can be won or
lost before players commit to a scene, and scales the Legend payoff by how
dangerous the declared risk actually is *for this party right now*.

**Issue:** #1770 (PR 1 — data model, readiness/activation services, API;
PR 2 — per-stake resolution: machine grading, GM constrained pick, world-state
writers, stake-level transition routing; PR 3 — two-sided contract: authored
win-reward lines, reward banding, anti-farming payout gate; PR 4 — opt-in &
visibility surfaces + activation wiring). **ADR:**
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
| `reward_floor` | PositiveIntegerField (default 0) | **PR3.** Minimum summed WIN-column reward value (money-equivalent scalars) — a staked beat should pay *something* |
| `reward_ceiling` | PositiveIntegerField (default 0) | **PR3.** Maximum summed WIN-column reward value. `0` = reward banding unconfigured for this tier (both reward checks skipped) |

Seed values (`DEFAULT_RISK_CALIBRATIONS`, `world/stories/constants.py`; the
reward columns are starting values, designer-tunable rows — LOW's floor stays 0
so a zero-reward LOW contract remains ready):

| Risk | `severity_floor_total` | `severity_ceiling` | `max_fuse_hops` | `reward_floor` | `reward_ceiling` |
|---|---|---|---|---|---|
| LOW | 1 | COSTLY (2) | 3 | 0 | 200 |
| MODERATE | 2 | GRAVE (3) | 2 | 100 | 600 |
| HIGH | 4 | DIRE (4) | 1 | 300 | 1500 |
| EXTREME | 6 | REMOVAL (5) | 0 | 800 | 4000 |

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
| `subject_sheet` | FK → `character_sheets.CharacterSheet` (null, SET_NULL) | For `PERSONAL_JEOPARDY` / `NPC_FATE` subjects |
| `subject_item` | FK → `items.ItemInstance` (null, SET_NULL) | For `ITEM` subjects |
| `subject_society` | FK → `societies.Society` (null, SET_NULL) | For `FACTION` subjects (society-level) |
| `subject_organization` | FK → `societies.Organization` (null, SET_NULL) | For `FACTION` subjects (organization-level) |
| `subject_label` | CharField(200, blank) | Freeform subject name — `CUSTOM` / `CAMPAIGN_TRACK`, or flavor text on any kind |
| `player_summary` | TextField | Player-facing line shown at opt-in: what is wagered, how badly |
| `created_at` / `updated_at` | DateTimeField | |

Exactly one typed subject FK (or `subject_label` for `CUSTOM`) should be populated
per stake; enforcement lives in the serializer, not `clean()`. A stake is
story-significant data: it survives its subject's deletion — the subject FK
nulls out (SET_NULL, never CASCADE) and `subject_label` / `player_summary`
keep carrying the name for display.

### `StakeResolution`

The authored branch for one stake × one outcome column.

| Field | Type | Notes |
|---|---|---|
| `stake` | FK → `stories.Stake` (`related_name="resolutions"`, CASCADE) | |
| `column` | CharField (`StakeResolutionColumn` choices) | `WIN` / `LOSS` / `WITHDRAWAL` |
| `outcome_key` | CharField(40, blank, default `""`) | **#1760.** Open-vocabulary slug naming *this* branch within `column`'s polarity — e.g. two distinct LOSS branches `"destroyed"` and `"captured"`. Blank = the column's single plain/default branch (backward compatible: every pre-#1760 row has `outcome_key=""`). `column` stays the coarse WIN/LOSS/WITHDRAWAL axis every severity/reward/machine-grading rule keys off; `outcome_key` is a finer dimension *inside* it, not a replacement |
| `consequence_pool` | FK → checks `ConsequencePool` (null, SET_NULL) | Pool to fire when this column resolves (tier-aware) |
| `escalates_to_risk` | CharField (`RenownRisk` choices, blank) | The [fuse](#chain-rule--fuse-length) mechanic — the risk tier the situation spawned by this branch carries. Blank = no escalation declared |
| `narrative_summary` | TextField (blank) | What happens in the story when this branch fires (GM-authored) |
| `forfeits_subject_item` | BooleanField (default False) | **PR2 writer.** On fire, soft-forfeits the stake's `subject_item` (`forfeit_item_instance` — `destroyed_at` + a receiver-less `TRANSFERRED` `OwnershipEvent`; never hard-deleted). Requires an `ITEM` stake with `subject_item` set |
| `subject_standing_delta` | SmallIntegerField (default 0) | **PR2 writer, dispatch by `subject_kind` (#1760).** On fire: `NPC_FATE` calls `adjust_npc_affection` between `subject_sheet`'s primary persona and each completion participant persona (unchanged). `FACTION` calls `bump_society_reputation`/`bump_organization_reputation` (whichever of `subject_society`/`subject_organization` is set) for each participant's own persona. Requires an `NPC_FATE` stake with `subject_sheet` set, or a `FACTION` stake with `subject_society` or `subject_organization` set |
| `sets_subject_lifecycle` | CharField (`LifecycleState` choices, blank) | **PR2 writer.** On fire, `set_lifecycle_state(subject_sheet, value)`. **Pillar-12 gated:** only legal for `NPC_FATE` stakes whose subject sheet is not player-held |
| `machine_match_lifecycle_state` | CharField (`LifecycleState` choices, blank) | **#1760, generalizes the old NPC-vitals DEAD-only override.** On MACHINE grading, if an `NPC_FATE` stake's `subject_sheet.lifecycle_state` equals this value, THIS branch fires instead of the column's plain default — matched across *all* of the stake's authored branches, so it can fire even when its own `column` crosses the beat-outcome-derived WIN/LOSS polarity (intentional; matches the pre-#1760 "dead NPC always grades LOSS regardless of beat outcome" behavior, now generalized to the full `LifecycleState` ladder: ALIVE/CAPTURED/COMA/RETIRED/DEAD). Blank = no machine-match signal; falls back to the plain per-column default (`world.stories.services.stake_resolution._branch_for_column`) |

Unique constraint: `(stake, column, outcome_key)` — one resolution per stake per
named branch (#1760; was `(stake, column)` pre-#1760, i.e. exactly one branch
per column).

**Pillar 12 (no-fiat removal):** the writer payloads are validated in *both*
`StakeResolutionSerializer.validate` and `StakeResolution.clean` (shared
`stake_resolution_payload_problems`): a branch can never write lifecycle state
onto a player-held sheet — PC removal is mechanically mediated (route into peril
via `escalates_to_risk` + consequence pools → `process_damage_consequences` →
`_mark_dead`, which now also propagates `LifecycleState.DEAD` to the roster).
The writer itself re-checks the player-held gate at fire time (defense in
depth) and skips-and-logs instead of raising. Captivity of a PC is deliberately
**not** a branch payload — capture arrives via terminal consequence pools
(`EffectType.CAPTURE`), already wired.

### `StakeRewardLine` (PR3)

One authored win-reward payout on a stake's WIN branch — the contract's
reward side. Authored pre-scene alongside the branch it hangs off; WIN-column
resolutions only (enforced in `clean()` + serializer). When the branch fires
under a ready, effective-risk-bearing activation, **every** completion
participant receives each line's full amount (ALL_EQUAL semantics, mirroring
mission reward distribution).

| Field | Type | Notes |
|---|---|---|
| `resolution` | FK → `stories.StakeResolution` (`related_name="reward_lines"`, CASCADE) | Must be a WIN-column resolution |
| `sink` | CharField (`StakeRewardSink` choices) | `MONEY` / `RESONANCE` |
| `amount` | PositiveIntegerField (`MinValueValidator(1)`) | Money-equivalent scalar paid to EACH participant; banded by `RiskCalibration.reward_floor/reward_ceiling` |
| `resonance` | FK → `magic.Resonance` (null, SET_NULL) | Required iff `sink=RESONANCE` (enforced in `clean()` + serializer); must be null otherwise |

### `StakeOutcome` (PR2)

The per-stake resolution audit + routing row — mirrors `EpisodeResolution` (GM
narrative-decision audit) and `BeatCompletion` (append-only ledger).
**Exactly one row per stake** (`unique_outcome_per_stake` constraint) — a
stake's resolution fires once from the locked contract; the create paths catch
a losing concurrent create and return the winner's row (PR1's activation
pattern), with `.exists()` pre-checks as the fast path.

| Field | Type | Notes |
|---|---|---|
| `stake` | FK → `stories.Stake` (`related_name="outcomes"`, CASCADE) | |
| `activation` | FK → `stories.StakeContractActivation` (null, SET_NULL, `related_name="stake_outcomes"`) | Which locked contract this outcome resolved under (audit) |
| `resolution` | FK → `stories.StakeResolution` (null, SET_NULL) | The authored branch that fired; **null = no branch was authored for the column** (audit honesty — an unready contract that ran anyway) |
| `column` | CharField (`StakeResolutionColumn` choices) | |
| `method` | CharField (`StakeOutcomeMethod` choices) | `MACHINE` (completion-tail grading) or `GM_PICK` (constrained pick) |
| `resolved_by` | FK → `gm.GMProfile` (null, SET_NULL) | The picking GM; null for MACHINE |
| `gm_notes` | TextField (blank) | |
| `created_at` | DateTimeField (auto_now_add) | Ordering `["-created_at", "-pk"]` |

### `TransitionRequiredOutcome.stake` + `required_stake_column` (PR2)

Stake-level transition routing: when `stake` is set on a
`TransitionRequiredOutcome`, the requirement is satisfied iff the stake's
`StakeOutcome.column` equals `required_stake_column` (instead of the beat's
coarse outcome) — so one beat's stakes can route to different downstream
episodes. Exactly one predicate shape per row, enforced by `clean()` (mirrored
in `TransitionRequiredOutcomeSerializer` and the bulk-save
`OutcomeInputSerializer`): stake set ⇒ `required_stake_column` required, the
stake belongs to the requirement's beat, and `required_outcome` must be
**blank** (no misleading mandatory-but-ignored value); stake null ⇒
`required_outcome` required and column blank. Conditioned unique constraints
keep one beat-level row per `(transition, beat)` and one stake-level row per
`(transition, stake)`. In the fuse walk, a stake-level requirement counts as
failure-following iff it requires `LOSS`. The editor bulk-save
(`POST /api/transitions/save-with-outcomes/`) round-trips both shapes — its
delete-and-recreate path preserves stake-level rows.

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
- **`StakeOutcomeMethod`** (PR2): `MACHINE` (graded by the completion tail),
  `GM_PICK` (constrained pick among authored columns).
- **`StakeRewardSink`** (PR3): `MONEY`, `RESONANCE` — only sinks with a real,
  coherent delivery service. Legend is deliberately **not** a sink (it stays
  automatic on top via effective risk, pillar 6).
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

**Carve-out for war-scale Battle stakes (#1785, ADR-0080):** `activate_stakes_contract`
takes an additive `scale_by_party_level: bool = True` parameter. Battle activation
(`battles.beat_wiring.activate_stakes_for_battle`) passes `False` — a war's stakes
are fought over an objective, not diluted or inflated by which specific PCs
happen to be enlisted, unlike scene-level stakes. When `False`, a ready
contract's effective risk equals its declared risk unconditionally, skipping
the level-gap math above entirely; the readiness gate (unready → `NONE`) still
applies. Every other caller keeps the default `True` — this is Battle-only.

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
Additionally (PR3), `StakeResolutionSerializer` and `StakeRewardLineSerializer`
refuse any write once the beat has completed (`beat.outcome != UNSATISFIED`) —
contract editing ends at completion, closing the pending-GM-pick window the
open-activation lock alone would leave open.

`get_open_activation(beat)` is the single query both the lock check and
`effective_risk_for_beat` share.

**Activation wiring (PR4):** `activate_stakes_contract` is now called at
every commit surface — PvP/lethal duel entry, hostile cast seed/feed,
mission acceptance, and the freeform `declare_stakes` GM action; see the
[Activation wiring map](#activation-wiring-map-who-calls-activate_stakes_contract).
`resolve_open_activation` is wired into the beat-completion tail
(`world.stories.services.beats._create_completion_and_fire_pool`, after the
completion's consequence pool and the per-stake resolver run). Scene
*grading* rides #1748; the player-boundary registry behind
`check_stake_boundaries` shipped in #1771 — see
[Boundary seam](#boundary-seam-worldstoriesservicesboundaries) below and
`docs/systems/boundaries.md`.

## Resolution (PR2)

When a staked beat completes, `resolve_stakes_for_completion`
(`world.stories.services.stake_resolution`) runs inside the atomic completion
tail — between the beat-level pool fire and `resolve_open_activation`, so the
open activation is still readable for the `StakeOutcome.activation` audit FK.

**Machine grading (pillar 11 — grade off data where it exists):**

- Beat `SUCCESS` → `WIN` column; `FAILURE`/`EXPIRED` → `LOSS`.
- **Lifecycle-match override (#1760, generalizes the old NPC-vitals DEAD-only
  override):** for an `NPC_FATE` stake, `_branch_for_column` first checks the
  subject sheet's *actual* `lifecycle_state` against every authored branch's
  `machine_match_lifecycle_state` (not just branches under the beat-derived
  column) — a match wins outright, even crossing the WIN/LOSS polarity the
  beat outcome would otherwise imply. No match falls back to the beat-derived
  column's plain (`outcome_key=""`) branch. This is the same "a dead NPC
  always grades LOSS" behavior as before #1760, now expressed as authored data
  across the full ladder (ALIVE/CAPTURED/COMA/RETIRED/DEAD) instead of a
  hardcoded DEAD check.
- Within the resolved column, `outcome_key=""` is always the plain/default
  branch pick when no `machine_match_lifecycle_state` fires — machine grading
  never lands on a *named* branch (`outcome_key != ""`) on its own; named
  branches are reached only via a GM's Constrained Pick.
- The chosen column's authored branch fires its `consequence_pool` (tier-aware
  via `apply_pool_for_tier` when the completion carries an `outcome_tier`, else
  `apply_pool_deterministically`) with the **same guards and
  `ResolutionContext` construction as beat-level pools** (shared
  `beats._fire_pool_with_context`), then applies the writer payloads.
  **Deliberate asymmetry:** the machine path is tier-filtered (a branch pool
  with no consequence at the completion's tier fires nothing — the
  `StakeOutcome` is still recorded), while the GM-pick and withdrawal paths
  apply deterministically (there is no graded tier to filter on).
- A missing branch still writes a `StakeOutcome` with `resolution=None` (an
  unready contract that ran anyway is auditable, not invisible).
- Idempotent: stakes that already carry a `StakeOutcome` (e.g. an earlier GM
  pick) are skipped. Participant resolution happens inside the resolver,
  after the no-stakes/deferred early-returns — an unstaked completion never
  pays its cost.
- `PENDING_GM_REVIEW` (non-withdrawal) defers all stakes — they wait for the
  GM's pick or final mark.
- The aggregate-crossing tail (`_finalize_aggregate_crossing`) resolves stakes
  at `WIN` and closes the open activation, same as the shared tail.

**Withdrawal (combat FLED/ABANDONED):** the combat auto-wire
(`world.combat.beat_wiring.encounter_completed_beat_handler`) passes
`withdrawal=True` through `record_outcome_tier_completion` (legal only with
`force_outcome=PENDING_GM_REVIEW`). The withdrawal path is **structural**:
FLED/ABANDONED take it regardless of any authored `EncounterOutcomeMapping`
row for the pair — a mapped tier is ignored (withdrawal routes to withdrawal
branches by spec semantics, not data convention). Stakes **with** an authored
`WITHDRAWAL` resolution fire it immediately (method `MACHINE`); stakes without
one pend with the beat's `PENDING_GM_REVIEW` for the GM's constrained pick.
The beat outcome itself stays `PENDING_GM_REVIEW` (a GM still adjudicates the
beat). This resolves #1746's deferred withdrawal design.

**GM constrained pick:** `resolve_stake_by_gm_pick` /
`POST /api/stakes/{id}/resolve/` — the GM picks **among the stake's authored
resolution columns only** (never free composition; author the branch first).
**#1760:** the pick is by `(column, outcome_key)` pair, not column alone — a
GM constrained to a column with multiple named branches (e.g. LOSS/"destroyed"
vs. LOSS/"captured") must name the specific `outcome_key`; blank picks the
column's plain default branch, matching pre-#1760 authoring. The branch fires
exactly like the machine path (pool + writers); the
`StakeOutcome` records `method=GM_PICK`, `resolved_by`, and `gm_notes`.
Optional `participants` / `extra_participants` carry the personas the branch's
pool and affection writer credit (same semantics as the beat mark endpoint:
GROUP scope needs an explicit list for LEGEND_AWARD pools — the guard surfaces
as a 400, not a 500). One pick per stake (a second attempt is rejected; the
`unique_outcome_per_stake` constraint is the backstop). When a GM later
finally marks a pending beat, the completion tail's resolver auto-resolves the
*remaining* unresolved stakes at the marked column; picked stakes are
untouched (idempotency).

**Escalation:** `escalates_to_risk` stays recorded on the fired resolution and
is readable by authoring; there is no automatic scene-spawn in PR2 (the fuse
walk validates reachability; spawning the follow-up situation is GM/story
work).

## Two-sided Contract — Win Rewards (PR3)

The contract's reward side (pillar 6): alongside each loss branch's
consequences, the GM authors `StakeRewardLine` rows on the WIN branch — a
declared, player-visible "here is what winning pays." Legend stays automatic
on top (scaled by effective risk); the reward lines are the *named* payouts.

**Sink menu — reuse the sink services, not the deed router.** The #1770 spec
sketched routing win rewards through the missions deed pipeline
(`apply_deed_rewards`); that spec text is stale on two counts. First, the
"apply_deed_rewards is caller-less (#1753)" premise no longer holds — PR #1769
wired it into mission reporting (`_apply_style_payout`,
`world/missions/services/report.py`). Second, and structurally decisive: the
deed router is hard-anchored to `MissionDeedRecord` (it reads
`deed.reward_lines` and enqueues `MissionRewardQueue(deed=...)`), stakes have
no deed, and missions already FKs *into* stories — stories depending back on
missions would invert the dependency direction (ADR-0010). So stakes reuse the
SAME SINK SERVICES the router dispatches to, called directly:

- `MONEY` → `world.currency.services.deliver_mission_money(recipient_sheet,
  amount, ref=f"stake:{pk}", reason_label="stake reward")` — the audited mint
  faucet; the optional `reason_label` kwarg (default `"mission reward"`) keeps
  the ledger honest for non-mission callers.
- `RESONANCE` → `world.magic.services.resonance.grant_resonance(sheet,
  resonance, amount, source=GainSource.STAKE_REWARD)` — the same grant service
  the missions cron's `_grant_resonance` calls. `STAKE_REWARD` is a
  discriminator-only `GainSource` (the `MISSION_REPORT` shape: no typed source
  FK on `ResonanceGrant`; provenance lives on the stories side in
  `StakeOutcome` + `StakeRewardLine`).

No `LEGEND_POINTS` sink (Legend is automatic; the missions LP path is also
stub-sealed), no `BEAT` (circular from inside beat resolution), no
`RUMOR`/`CRIME_WATCH` (unbuilt, loss-flavored).

Reward lines attach to **WIN-column resolutions only** (enforced in `clean()`
and the serializer) — a "consolation" line on LOSS/WITHDRAWAL would be
silently inert and is refused as an authoring foot-gun.

**Reward banding is a readiness concern, not a hard block.**
`validate_stakes_readiness` sums the WIN-column line amounts across the beat's
stakes and compares against the tier's `reward_floor`/`reward_ceiling`
(`_reward_band_problems`). Out-of-band totals mark the contract UNREADY
(pillar-7 auto-downgrade — the scene runs at effective NONE and pays nothing);
the serializer never rejects an out-of-band line. `reward_ceiling == 0` means
banding is unconfigured for that tier and both checks are skipped.

**The banding bypass is closed at both ends** (PR3 review). Editing a
contract ends when its beat completes: `StakeResolutionSerializer` and
`StakeRewardLineSerializer` refuse any write once `beat.outcome !=
UNSATISFIED` — the open-activation lock alone would reopen editing in the
pending-GM-pick window (the completion tail closes the activation while
stakes can still pend). Independently, `_apply_stake_rewards` re-runs the
band check at pay time (`reward_band_problems_for_beat`,
`services/stakes.py`) — an out-of-band live total skips the payout with a
warning even if the activation's frozen `is_ready` verdict says otherwise.

**The anti-farming gate (pillars 4/7/8).** `_apply_stake_rewards`
(`services/stake_resolution.py`) fires from `_fire_branch_and_record` whenever
the WIN column's branch fires — machine grading and GM pick alike — but pays
ONLY when the activation it resolved under is present, was `is_ready=True`,
and carries `effective_risk != NONE`. No activation, an unready contract, or
an over-leveled party skips the payout with an info log. LOSS/withdrawal
consequences and pools keep firing regardless — reality doesn't care; only
the payout math does. Delivery is per line × participant (Persona →
`CharacterSheet` bridge), matching the PR2 writer contract: skip-and-log,
never raise.

**Claim-before-pay.** `_fire_branch_and_record` creates the `StakeOutcome`
row FIRST — winning the `unique_outcome_per_stake` constraint *is* the claim —
and only then fires the pool, writers, and rewards. A losing concurrent
create refetches the winner's row and returns it WITHOUT firing anything, so
two racing resolutions can never double-pay; the enclosing transaction still
rolls the claim and its effects back together on a genuine error.

**GM picks resolve under the pended activation.** A constrained pick uses
`_activation_for_gm_pick`: the most recent activation locked at-or-before the
beat's most recent `BeatCompletion` (falling back to the open activation,
then the most recent). A new activation opened after the stake pended (the
beat re-engaged) changes neither the pended stake's payout gate nor its
`StakeOutcome.activation` audit row.


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

## Opt-in & Visibility Surfaces (#1770 PR4)

Pillar 9 (what is wagered is visible; branch contents stay hidden) and pillar
10 (boundary screening) are wired at every commit surface:

### Stakes summary (the shared read shape)

`stakes_summary_for_beat(beat)` (`world.stories.serializers`) builds the one
player-visible payload — `{declared_risk, effective_risk, is_ready, stakes:
[{id, player_summary, severity, severity_label}]}` — via
`StakesSummarySerializer`/`StakeSummarySerializer`. `StakeResolution` branch
contents (pools, escalations, narrative) are deliberately never fields here.
Exposed at:

- **`GET /api/beats/{id}/stakes-summary/`** (`BeatViewSet.stakes_summary`,
  permission `CanViewBeatStakesSummary`: staff, the beat's story owner, or a
  participant of a scene linked to the beat's episode via `EpisodeScene` —
  pillar 9 is visibility *at opt-in*, not global enumeration; beats can be
  SECRET and an open wager list leaks GM plans).
- **`combat_stakes`** on `SceneActionRequestSerializer` and
  `SceneActionTargetSerializer` (`world.scenes.action_serializers`) — non-null
  only when the #777 risk-acknowledgement gate is active AND the scene carries
  staked UNSATISFIED beats; the React `ConsentPrompt` renders the wagered
  stakes + effective risk under the combat-risk warning.

### Boundary seam (`world.stories.services.boundaries`)

`check_stake_boundaries(stakes, character_sheets) -> StakeBoundaryReport`
(`world.stories.types`: `allowed`, `requires_signoff`,
`blocked_reason_private`, derived `cleared`) runs at authoring time
(`StakeSerializer` screens existing stakes plus the candidate write) and at
every activation/commit call site (the wiring-map rows below). Call sites
gate on `report.cleared` — allowed AND no pending sign-off — so the #1771
registry could start returning `requires_signoff` without any call-site change,
and now does. **Shipped in #1771**: a real per-player boundary registry
(`world.boundaries` — `ContentTheme`/`PlayerBoundary` hard lines,
`TreasuredSubject`/`TreasuredSignoff` requires-signoff), replacing the PR4
allow-all stub. `blocked_reason_private` is staff/audit only — a blocked
contract surfaces exclusively as a generic "stakes could not be presented"
failure (ADR-0033 privacy, extended by ADR-0086). Full model/service/API
detail: `docs/systems/boundaries.md`.

### Custody seam (`world.stories.services.custody`, #2001)

A **separate** screen from the boundary seam above (ADR-0098: custody is GM/story-declared
narrative-structure protection, distinct from player-declared boundaries) — a story can
declare a subject (`StoryProtectedSubject`, same typed-subject-FK shape as `Stake`)
load-bearing, blocking every *other* story's actors from appearing-with/harming/removing it
absent an active `CustodyClearance` at sufficient scope (APPEAR < HARM < REMOVE).
`check_subject_custody(subject_identity, scope, actor_account, acting_story) -> CustodyVerdict`
is the single seam every enforcement point funnels through (death guard, `StakeSerializer`
staking validation, `StakeResolution` writer fire-time recheck, `add_opponent` spawning) —
reuses the same `_subject_identity` comparison the boundary seam uses, so the two never drift
on subject-matching logic even though they answer different questions. A blocked verdict
discloses only `custodian_gm_username` (to route a clearance request) — never the protecting
story, beat, or reason (mirrors `blocked_reason_private`'s privacy posture above). Full
model/service/API/clearance-lifecycle detail: `docs/systems/custody.md`.

### Activation wiring map (who calls `activate_stakes_contract`)

| Commit moment | Wire point | Party |
|---|---|---|
| PvP duel entry | `combat.duels.create_pvp_duel` → `combat.beat_wiring.activate_stakes_for_scene` | both duelists' sheets |
| Lethal duel entry | `combat.duels.create_lethal_duel` → same | the PC's sheet |
| Hostile cast seed/feed | `combat.cast_seed.seed_or_feed_encounter_from_cast` → same | caster + target sheets |
| Mission acceptance | `missions.services.offer_handler.issue_mission` → `missions.services.beat.activate_stakes_for_instance` | accepting persona's sheet (no-op for a free run or an offer whose `MissionOfferDetails.source_beat` is null; live for a staked linked beat since #1780 — see ADR-0085) |
| Freeform scene | `declare_stakes` GM action (`actions/definitions/gm_stories.py`) | the scene's active participants' sheets |
| Battle round 1 opening | `battles.services.begin_battle_round` → `battles.beat_wiring.activate_stakes_for_battle` | all enlisted ACTIVE participants' sheets, `scale_by_party_level=False` (see [Effective Risk](#effective-risk)) |

`staked_unsatisfied_beats_for_scene(scene)` (`world.stories.services.stakes`,
re-exported from `combat.beat_wiring` for its existing caller) is the
Scene → EpisodeScene → Episode → Beat discovery helper (any predicate type;
risk above NONE; outcome UNSATISFIED). Activation stays idempotent while an
activation is open, so overlapping encounters/battles on one scene are safe.

### Mission risk gate (`world.missions`)

`MissionRiskAcknowledgement` (offer × persona, tier snapshot, unique pair —
the mission sibling of `EncounterRiskAcknowledgement`) gates `issue_mission`:
a template at/above `MISSION_RISK_ACK_TIER` (`world.missions.constants`, 3)
raises the typed `MissionRiskUnacknowledgedError` until the persona has a row.
The two-phase opt-in lives inside the `npc_resolve` action
(`acknowledge_risk=yes` kwarg; telnet `hire offer <id> acknowledge_risk=yes`,
web `POST /api/npc-services/interactions/resolve/` with
`acknowledge_risk: true`). `InteractionOfferSerializer.risk_tier` surfaces the
tier pre-accept.

Since #1780, the gate also fires when the offer's `MissionOfferDetails.source_beat` is itself
staked (`beat.risk != RenownRisk.NONE`), regardless of the template's own `risk_tier` — a
low-tier template attached to a high-stakes beat still requires acknowledgement.
`MissionRiskUnacknowledgedError` carries that beat's `player_summary` stake lines
(`beat.stakes.values_list("player_summary", ...)`) so the opt-in surface can show what is being
wagered before the player re-runs with `acknowledge_risk=yes`. See ADR-0085 for why the FK lives
on `MissionOfferDetails` rather than `NPCServiceOffer`.

### `declare_stakes` (GM action, key `"declare_stakes"`)

The opt-in moment for freeform play: resolves the beat (`beat_id` kwarg),
gates on beat-mark permission (Lead GM / staff / approved AGM) **or** the
scene's GM (`scene.is_gm`), screens boundaries, activates the contract for the
scene's active participants, and emits a room-visible declaration listing each
stake's severity label + `player_summary` and the locked effective risk.

## Services (`world.stories.services.stakes`)

| Function | Signature | Purpose |
|---|---|---|
| `risk_index` | `(risk: str) -> int` | Position of a `RenownRisk` value on `RISK_LADDER` |
| `compute_effective_risk` | `(declared_risk, target_level, party_average_level) -> str` | See [Effective Risk](#effective-risk) |
| `validate_stakes_readiness` | `(beat: Beat) -> StakesReadinessReport` | Readiness gate: target_level declared, ≥1 stake, every stake has WIN+LOSS resolutions, severity within calibration bands, WIN reward total within the tier's reward band (PR3; skipped when `reward_ceiling == 0`), removal reachable within `max_fuse_hops`, and (for WORLD impact-tier stories, #2003) a CLEARED `CanonReview`. Unstaked beats (`risk == NONE`) are trivially ready |
| `get_open_activation` | `(beat: Beat) -> StakeContractActivation \| None` | The single open activation for a beat, if any |
| `activate_stakes_contract` | `(beat, participants, *, scale_by_party_level=True) -> StakeContractActivation` | Idempotent lock — see [Lock Lifecycle](#lock-lifecycle-authoring--activation--completion); `scale_by_party_level=False` (Battle only, #1785) prices at declared risk unconditionally — see [Effective Risk](#effective-risk) |
| `effective_risk_for_beat` | `(beat: Beat) -> str` | Read seam: open activation's effective risk, else `beat.risk` |
| `resolve_open_activation` | `(beat: Beat) -> None` | Closes the open activation (sets `resolved_at`); called by the completion tail |
| `reward_band_problems_for_beat` | `(beat: Beat) -> list[str]` | Re-runnable reward-band check (PR3): the readiness path *and* `_apply_stake_rewards` at pay time both use it |

`StakesReadinessReport` (`world.stories.types`): `is_staked: bool`,
`is_ready: bool`, `problems: tuple[str, ...]`.

## Services (`world.stories.services.stake_resolution`, PR2)

| Function | Signature | Purpose |
|---|---|---|
| `resolve_stakes_for_completion` | `(*, beat, outcome, completion, progress, scope, explicit_participants=None, outcome_tier=None, withdrawal=False) -> list[StakeOutcome]` | Grade every open stake on a completing beat and fire the chosen branches — see [Resolution](#resolution-pr2). Called by `beats._create_completion_and_fire_pool` and `beats._finalize_aggregate_crossing` |
| `resolve_stake_by_gm_pick` | `(stake, *, column, outcome_key="", gm_profile, gm_notes="", participants=None, extra_participants=None) -> StakeOutcome` | The GM constrained pick — `outcome_key` narrows the pick to one named branch within `column` (#1760; blank = the column's plain default). Fires the authored branch like the machine path, records `GM_PICK` |
| `stake_resolution_payload_problems` | `(*, stake, forfeits_subject_item, subject_standing_delta, sets_subject_lifecycle) -> list[StakePayloadProblem]` | Shared pillar-12 payload validation (serializer + model `clean`) |
| `sheet_is_player_held` | `(sheet: CharacterSheet) -> bool` | The pillar-12 gate: RosterEntry with a current tenure |

Plumbing added in PR2: `record_outcome_tier_completion` gained
`withdrawal: bool = False` (legal only with `force_outcome=PENDING_GM_REVIEW`);
`beats._fire_pool_with_context` is the extracted shared pool-fire core;
`vitals.services._mark_dead` now propagates `LifecycleState.DEAD` to the
sheet's roster lifecycle (the single seam where combat death reaches the
roster).

## API

All six ViewSets live in `world.stories.views`, registered in
`world.stories.urls`.

| ViewSet | Base URL | Permission |
|---|---|---|
| `RiskCalibrationViewSet` | `/api/risk-calibrations/` | `IsStaffOrReadOnly` — every authenticated user reads, only staff writes |
| `StakeTemplateViewSet` | `/api/stake-templates/` | `IsStaffOrReadOnly` |
| `StakeViewSet` | `/api/stakes/` | `IsStakeBeatStoryOwnerOrStaff` (delegates to `obj.beat` → episode → chapter → story ownership, same chain as `BeatViewSet`). PR2: nested read-only `outcomes` list; `POST /api/stakes/{id}/resolve/` (permission `CanResolveStake` — the `CanMarkBeat` gate via `stake.beat`; input `ResolveStakeInputSerializer`; returns `StakeOutcomeSerializer` at 201) |
| `StakeResolutionViewSet` | `/api/stake-resolutions/` | `IsStakeResolutionBeatStoryOwnerOrStaff` (delegates via `obj.stake.beat`). PR3: nested read-only `reward_lines` list |
| `StakeRewardLineViewSet` (PR3) | `/api/stake-reward-lines/` | `IsStakeRewardLineBeatStoryOwnerOrStaff` (delegates via `obj.resolution.stake.beat`); serializer enforces the create-path ownership walk, the open-activation lock, and resonance-required-iff-`RESONANCE` |
| `StakeContractActivationViewSet` | `/api/stake-activations/` | Read-only; `IsStakeBeatStoryOwnerOrStaff` |
| `BeatViewSet.stakes_summary` (#1770 PR4) | `GET /api/beats/{id}/stakes-summary/` | `CanViewBeatStakesSummary` (staff / story owner / linked-scene participant); leaks only `player_summary`/severity + risk/readiness by design |

`StakeSerializer`, `StakeResolutionSerializer`, and `StakeRewardLineSerializer`
all enforce, in `validate()`
(DRF never calls `has_object_permission` on create, so the permission class alone
isn't enough on POST):

- the two-sided lock check (both old and new beat/stake on a re-point);
- the ownership gate (`user_owns_beat_story`, staff bypass) — again both sides on
  a re-point;
- the completed-beat refusal (PR3; `StakeResolutionSerializer` and
  `StakeRewardLineSerializer`): no writes once `beat.outcome != UNSATISFIED`;
- `StakeSerializer` additionally validates the beat's declared risk falls within
  `[template.min_risk, template.max_risk]` (by `risk_index`), and gates the
  template-null (custom) path to staff or a non-staff GM whose
  `GMLevelCap.allow_custom_stakes` permits it (#2000, ADR-0097), mirroring
  `BeatSerializer.validate`'s risk gate (also `GMLevelCap`-driven, via
  `_gm_max_risk`/`_gm_allows_custom_stakes` in `world/stories/serializers.py`);
- `StakeRewardLineSerializer` additionally refuses non-WIN-column resolutions
  and enforces the resonance/sink shape.

## PR Spine: Shipped & Remaining

The #1770 PR spine is fully shipped (PR1–4); what remains lives on sibling
issues:

| Surface | Status |
|---|---|
| Win-column reward wiring (reward lines, banding, anti-farming payout gate) | **SHIPPED in PR3** — see [Two-sided Contract](#two-sided-contract--win-rewards-pr3); deliberately does NOT route through `apply_deed_rewards` despite the spec text (reasons recorded there) |
| Opt-in player-facing surfaces + the scene-start activation triggers | **SHIPPED in PR4** — see [Opt-in & Visibility Surfaces](#opt-in--visibility-surfaces-1770-pr4) |
| Player-boundary registry backing `check_stake_boundaries` | **SHIPPED in #1771** — see `docs/systems/boundaries.md` |
| Scene *grading* | **#1748** |
| Battle (war-scale) activation + outcome grading | **SHIPPED in #1785** — see `world.battles.beat_wiring` |

## Test Coverage

- `src/world/stories/tests/test_models_stakes.py` — model constraints (unique
  bands, partial-unique open activation, `StakeResolution` column uniqueness)
- `src/world/stories/tests/test_services_stakes.py` — `compute_effective_risk`
  curve, `validate_stakes_readiness` (bands + fuse-walk BFS), `activate_stakes_contract`
  idempotency/race handling, `resolve_open_activation`
- `src/world/stories/tests/test_serializers_stakes.py` — lock gate (both sides of
  a re-point), ownership gate, template risk-band validation, custom-stake staff
  gate
- `src/world/stories/tests/test_services_stake_resolution.py` (PR2) — machine
  grading E2E (pool fire + audit rows + activation close), NPC-vitals LOSS
  override, withdrawal, GM constrained pick (service + endpoint), pillar-12
  serializer guard, writers (forfeit / affection / lifecycle + player-held
  refusal), stake-level transition routing
- `src/world/stories/tests/test_services_stake_rewards.py` (PR3) — win-reward
  E2E (money + resonance to each participant), anti-farming gate (unready /
  effective-NONE / no-activation pay nothing while loss pools still fire),
  GM-pick payout with/without participants, reward-line serializer gates
- `src/world/combat/tests/test_encounter_beat_wiring.py` (PR2) — FLED fires
  withdrawal-authored stakes, pends unauthored ones
- `src/world/battles/tests/test_beat_wiring.py` (#1785) — Battle conclusion
  classify/activate/resolve wiring, `scale_by_party_level=False` carve-out
- `src/world/vitals/tests/test_life_state.py` (PR2) — `_mark_dead` →
  `lifecycle_state DEAD` propagation
- `src/world/items/tests/test_usage_service.py` (PR2) — `forfeit_item_instance`
  soft-delete + `TRANSFERRED` event + idempotency
- `src/world/stories/tests/test_stakes_optin.py` — boundary-seam stub contract +
  authoring call site, stakes-summary endpoint (incl. the never-leak-branch
  privacy assertion)
- `src/world/combat/tests/test_stakes_activation.py` — activation at the three
  combat creation seams, idempotency across encounters, boundary blocking
- `src/world/missions/tests/test_risk_acknowledgement.py` — the
  `MISSION_RISK_ACK_TIER` gate, two-phase `npc_resolve` opt-in, activation at
  issue
- `src/actions/tests/test_gm_story_actions.py` (`DeclareStakesActionTests`) —
  the freeform-scene GM declaration
- `src/world/scenes/tests/test_scene_action_request_serializer.py` —
  `combat_stakes` gating on both consent-prompt serializers

## Integrates With

- **Stories** — `Beat.risk` / `Beat.target_level`; the fuse walk reads
  `Transition.cached_required_outcomes` and `Episode.maturity`
- **Societies** — `RISK_LEGEND_AWARDS` (`world.societies.constants`), consumed by
  `_legend_award`'s `effective_risk_for_beat` scaling. **#1760, read-side
  complement to the `FACTION` `subject_standing_delta` writer above:**
  `BeatPredicateType.FACTION_STANDING_AT_LEAST` (`world.stories.constants`) is
  a new Beat predicate — `Beat.required_society` / `required_organization`
  (exactly one set) + `Beat.required_standing` — letting a later beat gate on
  accumulated `SocietyReputation`/`OrganizationReputation.value` reaching a
  threshold (no row = implicit 0). Evaluator:
  `_evaluate_faction_standing_at_least` (`world.stories.services.beats`),
  reading the sheet's primary persona's reputation row. Full predicate-type
  field table lives in [stories.md](stories.md#beat)
- **Checks** — `Beat.failure_consequences` → `resolve_pool_consequences` for the
  `character_loss` reachability test; `StakeResolution.consequence_pool` FK
- **Mechanics** — `world.mechanics.effect_handlers._legend_award` reads
  `effective_risk_for_beat` for the graded beat-completion Legend award path
- **Character Sheets** — `Stake.subject_sheet`; party-average-level computation
  in `activate_stakes_contract` via `services/beats.py::_character_level`
- **Items / Societies (subject FKs)** — `Stake.subject_item` →
  `items.ItemInstance`; `Stake.subject_society` / `subject_organization` →
  `societies.Society` / `societies.Organization`
- **Custody (#2001)** — `StakeSerializer.validate` and `StakeResolution` writer
  fire-time recheck both funnel through `check_subject_custody`
  (`world.stories.services.custody`) before staking/resolving a subject another
  story protects — see [Custody seam](#custody-seam-worldstoriesservicescustody-2001)
  above and [custody.md](custody.md)
- **Currency** (PR3) — `deliver_mission_money` is the MONEY sink (audited mint
  faucet; `ref="stake:<pk>"`)
- **Magic** (PR3) — `grant_resonance(..., source=GainSource.STAKE_REWARD)` is
  the RESONANCE sink; `StakeRewardLine.resonance` → `magic.Resonance`;
  discriminator-only shape constraint `res_grant_stake_reward_shape` on
  `ResonanceGrant`
- **Combat** — the PR2 withdrawal wire (`encounter_completed_beat_handler`)
  and the PR4 activation seams (`activate_stakes_for_scene` at duel/cast
  entry); the *vocabulary* stays distinct — see the
  [disambiguation table](#three-concepts-named-riskstakes--disambiguation) above

## Source

`src/world/stories/`
- `models.py` (end of file) — `RiskCalibration`, `StakeTemplate`, `Stake`,
  `StakeResolution`, `StakeRewardLine`, `StakeContractActivation`,
  `StakeOutcome`; `Beat.target_level`; `TransitionRequiredOutcome.stake`
- `constants.py` — `StakeSeverity`, `StakeSubjectKind`, `StakeResolutionColumn`,
  `StakeOutcomeMethod`, `StakeRewardSink`, `RISK_LADDER`,
  `DEFAULT_RISK_CALIBRATIONS`
- `services/stakes.py` — readiness / activation / effective-risk services
  (incl. `_reward_band_problems`)
- `services/stake_resolution.py` — per-stake resolution, GM pick, writers,
  pillar-12 payload validation, `_apply_stake_rewards` (PR3)
- `services/boundaries.py` — the boundary seam (`check_stake_boundaries`,
  real registry since #1771) + sign-off grant/withdraw + `stake_availability`
- `types.py` — `StakesReadinessReport`, `StakePayloadProblem`
- `serializers.py` — the stake serializers (search `#1770`)
- `views.py` / `urls.py` — the ViewSets + `StakeViewSet.resolve`
- `permissions.py` — `IsStaffOrReadOnly`, `IsStakeBeatStoryOwnerOrStaff`,
  `IsStakeResolutionBeatStoryOwnerOrStaff`,
  `IsStakeRewardLineBeatStoryOwnerOrStaff`, `CanResolveStake`,
  `user_owns_beat_story`
- `factories.py` — `seed_default_risk_calibrations` + FactoryBoy factories

Cross-app (PR2): `world/combat/beat_wiring.py` (withdrawal wire),
`world/items/services/usage.py::forfeit_item_instance`,
`world/vitals/services.py::_mark_dead` (lifecycle propagation),
`world/npc_services/services.py::adjust_npc_affection` (reused, unchanged).
Cross-app (PR3): `world/currency/services.py::deliver_mission_money` (MONEY
sink, `reason_label="stake reward"`), `world/magic/constants.py::GainSource.STAKE_REWARD` +
`world/magic/models/grant.py::res_grant_stake_reward_shape` (RESONANCE sink
provenance).
Cross-app (PR4): `world/combat/beat_wiring.py::activate_stakes_for_scene` +
`staked_unsatisfied_beats_for_scene`, `world/missions` risk-acknowledgement
gate + `activate_stakes_for_instance`, `actions/definitions/gm_stories.py`
(`declare_stakes`).
