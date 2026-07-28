# Paid-pull CAPABILITY_GRANT snapshots at commit with context_free_power

#2730 found that a paid thread pull resolving a `CAPABILITY_GRANT` effect conferred
nothing — `CombatPullResolvedEffect.granted_capability` was written at commit time
but read by no consumer. #2708 had already taught the free, passive tier-0 path to
curve geometrically with thread level and power (ADR-0169), leaving the system
backwards: paying resonance and anima for a pull did less than owning the thread
passively. We decided **(D1) snapshot `capability_grant_value` at commit time**
using the same `apply_capability_curve` formula the passive path uses, with
`context_free_power` as the power figure:

```
capability_grant_value = apply_capability_curve(
    base=row.capability_grant_value,
    power=context_free_power,
    sensitivity=thread_level_multiplier(thread.level),
)
```

The frozen-snapshot invariant of `CombatPullResolvedEffect` is preserved — later
changes to authoring, thread level, or power cannot retroactively alter what a
committed pull granted. This mirrors how `scaled_value` freezes VITAL_BONUS and
RESISTANCE.

**(D2) The power figure is `context_free_power`, not combat `eff_intensity`.**
This extends ADR-0169 D6 to the paid-pull path: a character's capability standing
must not flicker based on whether combat is running. The passive path already
uses `context_free_power`; a paid pull uses the same figure.

**(D3) The pull value folds additively into `get_effective_capability_value`**
alongside `grant_floor` (passive grants) and `technique_value` (known-technique
grants): `max(0, baseline + modifiers + conditions + grant_floor +
technique_value + pull_value)`. Multiple pulls for the same capability in one
round fold via MAX within the pull term (ADR-0034). A paid pull is a transient
surge that costs resonance + anima — it stacks on top of the passive floor, not
replaces it.

**(D4) Combat-only; non-combat deferred.** CAPABILITY_GRANT is flagged `inactive`
in non-combat context, same as VITAL_BONUS and RESISTANCE already are. Non-combat
pulls are ephemeral (`ResolvedPullEffect` dataclass, not persisted), and threading
them into the capability oracle raises duration/scope questions (when does the
surge end? which capability checks see it?) that deserve their own design pass.

**(D5) Inert on landing.** When no `CapabilityPowerConfig` row exists,
`apply_capability_curve` returns `base` unchanged — `capability_grant_value`
snapshots to `row.capability_grant_value` (default 1), reproducing the pre-#2730
flat grant. The feature is inert until staff create the config row, same as #2708.

## Rejected alternatives

- **Derive at read time from existing columns.** Rejected: breaks the
  frozen-snapshot invariant — if authoring or thread level changes between commit
  and read, the value shifts. Requires re-querying `ThreadPullEffect` at read time,
  defeating the purpose of `CombatPullResolvedEffect`.
- **Use combat `eff_intensity` as the power figure.** Rejected: contradicts
  ADR-0169 D6 — capability standing must not flicker based on whether combat is
  running.
- **MAX against `grant_floor` (both thread-sourced).** Rejected: a paid pull is a
  transient surge that costs resonance + anima; it should stack on top of the
  passive floor, not replace it. The issue explicitly states the intent: "pulling
  a thread should make a character feel dramatically stronger."
- **Both combat and non-combat.** Rejected for now: non-combat raises
  duration/scope questions that deserve their own design pass. Combat has a clear,
  bounded lifecycle (pull persists for one round, capability check happens within
  that round).

## Consequences

A new `capability_grant_value` column on `CombatPullResolvedEffect` requires a
migration and CheckConstraint/clean() updates. The availability oracle
(`get_capability_sources_for_character`) is deliberately NOT modified — a combat
pull raises capability *values* for gate/requirement checks, not available
*actions* in the picker. If a future design wants pulls to surface new actions,
that would need a new `CapabilitySourceType.PULL` entry and a `_get_pull_sources`
function.

> Status: accepted · Source: issue #2730 (paid-pull CAPABILITY_GRANT confers
> nothing); builds on ADR-0169 (capability magnitude curve), ADR-0034 (grant
> individuation by MAX), ADR-0164 (capability value ladder); supersedes nothing.
