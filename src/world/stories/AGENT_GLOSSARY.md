# Stories glossary

**Story / Chapter / Episode / Beat / Transition**:
The narrative hierarchy: a **Story** is a top-level campaign container with a scope and maturity; a **Chapter** is a major arc within it; an **Episode** is a node in the episode DAG; a **Beat** is a boolean predicate attached to an episode (the gateable unit of progress); and a **Transition** is a first-class directed edge between episodes, fired automatically or by GM choice. Episodes are nodes and Transitions are edges — a Story progresses by satisfying Beats to make Transitions eligible.
_Avoid_: campaign (Story), arc (Chapter), session/scene (Episode), objective/flag (Beat), branch/link (Transition).

**Era**:
A temporal metaplot tag (player-facing "Season N") that stories and events are stamped against, with exactly one ACTIVE era enforced at a time. It is a temporal label, not a parent in the Story/Chapter/Episode hierarchy.
_Avoid_: season, age, epoch.

**Story Maturity**:
The authoring-completeness of a single Story / Chapter / Episode node — `StoryMaturity`: PITCH, OUTLINE, or PLOT. Per-node and orthogonal to runtime progress status, with no cross-node ordering constraint; it is how finished the authoring is, not where play has reached.
_Avoid_: draft state, completeness, stage.

**Progress Status**:
The finer-grained state of a progress pointer (`ProgressStatus`: ACTIVE, WAITING_FOR_GM, RESTING, COMPLETED, FORECLOSED). `is_active` stays True for ACTIVE / WAITING_FOR_GM / RESTING; COMPLETED and FORECLOSED clear it.
_Avoid_: progress state, pointer status.

**FORECLOSED**:
The honest terminal `ProgressStatus` for a progress run still in flight when its story is concluded — distinct from COMPLETED (which means the run genuinely reached an ending). It exists so an unfinished thread is never falsely reported done, nor left orphaned in a live state.
_Avoid_: cancelled, abandoned, completed.

**Resting Conclusion**:
The player-facing `Episode.resting_conclusion` text shown when a progress pointer RESTS at that episode — a deliberately non-final pause-point ending. Required before an episode can be promoted to PLOT maturity.
_Avoid_: ending, pause text.

**Story Note**:
An append-only, never-player-visible OOC authorial note attached to a Story — general notes and future-idea seeds for the next author. Distinct from per-node pitch/`description` text; not promotable and not editable through the API.
_Avoid_: GM note, comment, pitch.

**Story Scope**:
Which kind of subject a Story progresses for — `StoryScope`: UNASSIGNED (the default, not yet placed), CHARACTER (personal), GROUP, or GLOBAL. It selects the progress-pointer type, and an UNASSIGNED story rejects progress creation until it is assigned a scope.
_Avoid_: level, reach, audience.

**Stake**:
One named wager on a Beat's stakes contract (`Stake` model, #1770) — what is actually at risk (a character, an NPC, a location, a faction relationship, an item, a campaign track, or a custom subject), authored with a `player_summary` shown to players at opt-in and a `severity` (`StakeSeverity`, SETBACK..REMOVAL) denormalized from a `StakeTemplate` at creation. Distinct from `Beat.risk` (the tier-level declaration a Stake concretizes) and from a `StakeResolution` (what happens to the Stake on a given outcome).
_Avoid_: wager, bet, consequence (use Stake for the thing at risk, StakeResolution for what happens to it).

**Stakes Contract**:
The full authored bundle backing a staked Beat: its `Beat.risk` + `Beat.target_level` declaration, one or more `Stake` rows, and each Stake's `StakeResolution` rows (WIN/LOSS/WITHDRAWAL branches). "The contract" is complete when `validate_stakes_readiness` reports it ready; see `docs/systems/stakes.md` for the full model and lifecycle.
_Avoid_: wager sheet, risk sheet.

**Severity**:
`StakeSeverity` (SETBACK/COSTLY/GRAVE/DIRE/REMOVAL, 1-5) — how bad losing (or how good winning) a single Stake is. `RiskCalibration.severity_ceiling` caps the worst severity any one Stake may carry at a given risk tier; `severity_floor_total` is the minimum summed severity across a beat's Stakes (no fake stakes). REMOVAL is the character-loss band.
_Avoid_: danger level, magnitude (Magnitude is a separate `societies` renown axis).

**Fuse / Chain Rule**:
The reachability rule (#1770) that a risk tier below EXTREME is only honest if losing the beat can plausibly cascade into a character-removal outcome, even when this beat doesn't stake removal directly. `RiskCalibration.max_fuse_hops` bounds how many failure-gated `Transition` hops the BFS walk (`_jeopardy_reachable`) may take to find a downstream beat that offers removal; EXTREME's `max_fuse_hops=0` means the beat itself must offer it. PITCH-maturity episodes never count toward the walk.
_Avoid_: escalation ladder (that's `StakeResolution.escalates_to_risk`, a related but separate authored field), removal chain.

**Effective Risk**:
What a stakes contract actually pays out on for the party currently running the scene — `compute_effective_risk(declared_risk, target_level, party_average_level)`, decaying an over-leveled party's declared risk toward NONE and giving an under-leveled party a bounded one-tier upgrade. Read via `effective_risk_for_beat(beat)`, which prefers the open `StakeContractActivation.effective_risk` and falls back to the raw `Beat.risk`. Distinct from `Beat.risk` (the GM's declared, unscaled risk).
_Avoid_: adjusted risk, scaled risk.

**Activation** (stakes contract):
The `StakeContractActivation` row locking a beat's stakes contract at scene start — snapshots `declared_risk`/`declared_target_level`/`party_average_level`, computes and freezes `effective_risk`, and (while `resolved_at IS NULL`) blocks any edit to the beat's Stakes/StakeResolutions. At most one open activation per beat (partial unique constraint). Not to be confused with activating/engaging a Covenant Role, or any other domain's "activation."
_Avoid_: lock (use Activation for the row; "lock" for the behavior it enforces), snapshot.

**Stake Outcome**:
The per-stake resolution audit + routing row (`StakeOutcome`, #1770 PR2) — which column a Stake resolved at, how it was decided (`StakeOutcomeMethod`: MACHINE grading in the completion tail, or a GM's Constrained Pick), and which authored `StakeResolution` branch fired (null when no branch was authored for the column). Exactly one StakeOutcome per stake (unique constraint) — transition routing reads it. Distinct from `BeatCompletion` (the beat-level ledger row) and from `StakeResolution` (the authored branch itself).
_Avoid_: stake result, stake completion.

**Constrained Pick**:
The GM's resolution move on a pending stake (`resolve_stake_by_gm_pick`, `POST /api/stakes/{id}/resolve/`): choosing one of the stake's *authored* resolution columns — never composing a consequence freehand at resolution time. The picked branch fires exactly like the machine path (pool + writers); the StakeOutcome records `GM_PICK`, the GM, and notes. One pick per stake.
_Avoid_: GM override, fiat resolution (pillar 12 forbids fiat; the pick is bounded by authorship).

**Withdrawal Column**:
The `StakeResolutionColumn.WITHDRAWAL` branch — what happens to a Stake when the party walks away from the wager instead of winning or losing it. Fired machine-side when a combat encounter ends FLED/ABANDONED (`withdrawal=True` through `record_outcome_tier_completion`); stakes without an authored WITHDRAWAL branch pend with the beat's PENDING_GM_REVIEW for a Constrained Pick. The beat itself still awaits GM adjudication.
_Avoid_: flee branch, retreat outcome.

**Reward Line**:
One authored win payout on a stake's branch (`StakeRewardLine`, #1770 PR3) — a `sink` (`StakeRewardSink`: MONEY or RESONANCE), an `amount` (a money-equivalent scalar paid to EACH completion participant, ALL_EQUAL), and a `resonance` FK when the sink is RESONANCE. Hangs off a `StakeResolution` (in practice the WIN column); paid by `_apply_stake_rewards` only under a ready, effective-risk-bearing Activation. Distinct from missions' `MissionDeedRewardLine` (deed-anchored; stakes deliberately reuse the sink *services*, not the deed router).
_Avoid_: reward row, payout entry, deed line.

**Reward Band**:
The per-tier `RiskCalibration.reward_floor`/`reward_ceiling` window (#1770 PR3) that the summed WIN-column Reward Line amounts across a beat's stakes must fall inside for the contract to be ready (`_reward_band_problems`). Out-of-band totals mark the contract UNREADY (auto-downgrade, pillar 7) — never an authoring rejection. `reward_ceiling == 0` means banding is unconfigured for that tier and both checks are skipped.
_Avoid_: reward cap (the band has a floor too), payout limit.
