# Capability magnitude curves geometrically with contextual power, uncapped

#2708 found that a capability's magnitude was flat with respect to power everywhere it
was granted. `TechniqueCapabilityGrant.calculate_value()` only ever added
`intensity_multiplier * technique.intensity` to a `base_value` — a linear bump that
never crosses an ADR-0164 ladder tier boundary no matter how strong the caster gets.
Thread-passive tier-0 `CAPABILITY_GRANT` rows were worse: `capability_grant_value`
didn't exist yet, so a granted capability was worth a hardcoded `1` regardless of the
granting thread's level. We decided **(D1) a geometric (doubling) curve, uncapped**:

```
value = round(base * 2 ** (sensitivity * power / power_per_doubling))
```

driven by a new staff-tunable singleton, `CapabilityPowerConfig` (`power_per_doubling`,
default 10). The ADR-0164 ladder's own tier anchors (5 mortal, ~10 gifted, 25 greater
supernatural, 100 mythic) are already roughly geometric — each tier is close to a
doubling of the one below it — so "every `power_per_doubling` power is one tier up the
ladder" falls out of the formula with no per-tier authoring. **Uncapped is deliberate,
not an oversight**: a stacked pull crossing power 100 and shrugging off a potent
(`-100`) block is the intended stark-power feel (see the vow-power-is-stark north star),
not a bug to clamp away. `apply_capability_curve` (`world/magic/services/
capability_curve.py`) never returns less than `base` — power is a pure empowerment
axis; impairment stays the conditions layer's job (a negative
`ConditionCapabilityEffect`), never this curve's.

**(D2) No `CapabilityPowerConfig` row = every consumer returns its pre-#2708 number,
bit-for-bit.** `TechniqueCapabilityGrant.calculate_value()` falls back to the old
`base_value + intensity_multiplier * power` shape; `ThreadPullEffect
.capability_grant_value` defaults to `1`, reproducing the old flat grant. The feature is
turned on by staff tuning a row into existence, not by this code deploying — so the
migration that ships this is inert on landing.

**(D3) `intensity_multiplier` is RETIRED as an additive term and repurposed as the
curve's exponent sensitivity.** Do not re-add an additive branch alongside the curve —
there is exactly one formula, and `intensity_multiplier` (on `TechniqueCapabilityGrant`)
/ `thread_level_multiplier(level)` (on thread-passive grants) is now "how responsive is
this grant to power," not "how much to add per point of power." A grant authored at the
default sensitivity of `0` is inert under the curve (`2**0 == 1`) and returns exactly
`base_value`, so every pre-#2708 row (all authored at the additive default) is
unaffected by config-row creation until a content author deliberately opts a grant into
scaling.

**(D4) Passive contribution requires demonstrable activation, not player assertion.**
Exercising a capability is itself an action — climbing a wall draws on power the same
way casting a technique does — so `get_effective_capability_value` accepts an optional
`action_ctx` and threads it down to `CharacterThreadHandler.contextual_thread_power`,
which sums a thread's tier-0 `INTENSITY_BUMP` only for threads
`_anchor_ambiently_active` confirms are genuinely engaged right now. This predicate is
deliberately a **separate function** from the pull predicate, `_anchor_in_action`, not a
shared one with an `ambient=` flag collapsing the two: a thread pull is paid for
(resonance + anima), so it is fair to let a player *assert* involvement for anchors with
no anchor in the action graph (GIFT, RELATIONSHIP_*) — that's what `_anchor_in_action`
does. A free passive capability contribution costs nothing, so assertion is not enough;
every arm of `_anchor_ambiently_active` tests real state instead (a GIFT thread checks
the involved technique's actual gift, a SANCTUM thread checks the character's actual
room, a FACET thread checks actually-worn items). The canonical failure this prevents: a
pyromancer's fire-gift thread must not raise their ability to climb a wall just because
the character "could" assert the gift is relevant.

**(D5) A thread may move a capability's value only if it GRANTS that specific
capability.** The curved contribution from a `ThreadPullEffect(effect_kind=
CAPABILITY_GRANT)` row is keyed to `row.capability_grant_id` — a fire-gift thread can
never inflate an unrelated capability's number; it can only curve the capabilities it is
explicitly authored to grant.

**(D6) Both capability oracles read the same power figure — combat's `eff_intensity` is
deliberately NOT threaded in.** `_technique_capability_values` derives power from
`technique.intensity + context_free_power + contextual_thread_power(...)`, never from
combat's per-round intensity bumps. A character's capability standing (can they still
see, can they still speak) must not flicker based on whether a combat encounter happens
to be running right now — capability is a standing fact about the character, not a
combat-round variable.

## Rejected alternatives

- **Linear scaling** (the pre-#2708 shape). Rejected: a linear bump never reaches a
  ladder tier boundary at any realistic power figure — the whole point of ADR-0164's
  ladder is that crossing a tier changes what a character can do, and a flat add-per-
  point never crosses it meaningfully.
- **Power-law scaling** (`value = base * power ** exponent`). Rejected: no clean mapping
  onto the ladder's tier anchors — tuning an exponent to land 5/10/25/100 at sensible
  power values is fragile and non-obvious to a staff tuner, unlike a doubling constant.
- **Authored breakpoint bands** (e.g. "power 0-9 = tier A, 10-24 = tier B, ..." as
  content rows). Rejected: the curve becomes invisible in code — a reader of
  `calculate_value` would see nothing but a band lookup, and every new capability would
  need its own authored band table instead of inheriting the shared formula.
- **Capped geometric curve** (same formula, clamped to some ceiling). Rejected: caps
  keep blocks meaningful forever, which is the opposite of the design intent — vow power
  is deliberately stark (see the north-star ruling), and a hard ceiling would mean no
  amount of investment ever lets a character shrug off a potent block, contradicting
  ADR-0164's own "uncapped above 100 on purpose" ladder design.

## Consequences

A `CapabilityPowerConfig` row is a real balance lever: once staff create one, every
non-zero-sensitivity grant across the game starts curving, all at once, off the same
`power_per_doubling` knob — this is a single global dial, not a per-grant one (aside
from each grant's own sensitivity). Content authors who want a grant to scale must
deliberately set its sensitivity above the `0` default; the vast majority of existing
rows (authored before this feature) stay flat until an author opts them in. The two
capability-value predicates (`_anchor_in_action` for paid pulls, `_anchor_ambiently_active`
for free passive contribution) must be maintained in parallel — a new `TargetKind` arm
added to one needs a deliberate decision about whether the other needs a matching arm,
not an assumption that one mirrors the other. The `ORGANIZATION` ambient arm is
deliberately deferred (`_anchor_ambiently_active` returns `False` for it) — its
ratified rule ("tied to organization missions or activities") needs a marker
`PullActionContext` does not carry yet; shipping an arm that can never fire would be
worse than omitting it, so it's tracked as a needs-design question off #2708 rather than
guessed at here.

> Status: accepted · Source: issue #2708 (should technique/capability grants scale with
> power); builds on ADR-0164 (capability value ladder + emergent blocking), ADR-0034
> (grant individuation by MAX); relates to ADR-0144 (one-oracle merge, #2504); supersedes
> nothing.
