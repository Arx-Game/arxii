# Wound HP mends are double-bounded — once per healer per wound, and never to full

Ratified design (lore repo `design/covenant-vows-consolidated.md` §3.1) rewrote the old
no-healing-ever rule: heals exist, but the party must always be net-weaker for having fought.
#2644's audit found the load-bearing gap upstream of any mend mechanic — the permanent-wound
tier (`process_damage_consequences` → `_apply_wound_tier`, `world/vitals/services.py`) rolled and
recorded a graded outcome but `ensure_default_wound_pool` (`world/vitals/seeds.py`) authored every
outcome as an effect-free narrative label. A healer had nothing to tend: no condition ever landed
on the wounded character.

## Decision

**Wounds now apply real, mechanical `ConditionTemplate`s** (`ensure_wound_conditions` —
Lingering Ache / Crippling Wound / Bleeding Wound; vocabulary, not lore content, mirroring the
existing `Bleeding Out` precedent). `ensure_default_wound_pool`'s partial/failure outcomes wire
APPLY_CONDITION effects onto them. **Condition cleansing stays unrestricted** — technique
dispel/cleanse and severity-decay `TreatmentTemplate`s work on wound conditions with no cap;
"the wound remains; the suffering ends."

**HP mending is real but double-bounded**, composing two independent bounds:

1. **Once per healer, per wound, forever (scene-independent).** `TreatmentAttempt` gains a
   partial `UniqueConstraint` on `(helper, target_condition_instance)` guarded by a new
   `once_per_wound_guard` flag (denormalized from `TreatmentTemplate.once_per_wound_per_helper`
   at insert time — mirrors the existing `once_per_scene_guard` pattern exactly). An incompetent
   healer's one attempt cannot burn the wound's only chance for everyone else; each healer gets
   their own shot, but only one, ever — not once per scene.
2. **The never-to-full fraction.** `WoundDetails` (new model, `world/vitals/models.py`; OneToOne
   → `conditions.ConditionInstance`, CASCADE, FK direction specific→general per ADR-0010) stamps
   `damage_taken` (the debit that caused the wound) at the moment the wound tier applies the
   condition, and tracks `health_mended_total` — the running sum every `mend_wound()` call has
   ever restored on that wound, across every healer. `mend_wound(healer_sheet, target_sheet,
   wound_instance, amount) -> int` (`world/vitals/services.py`) caps the mend at
   `NEVER_TO_FULL_FRACTION x damage_taken - health_mended_total`, additionally clamped to
   `max_health`. `NEVER_TO_FULL_FRACTION` (`world/vitals/constants.py`, `Decimal("0.75")`) is a
   tunable plain constant — mirrors `PERMANENT_WOUND_THRESHOLD`'s precedent (a game-balance dial,
   not a per-deploy admin-config field). The remaining 25% of every wound's damage is permanent
   attrition, by design: the sum of every wound's remainder across a fight is the cost of having
   fought it.

`TreatmentTemplate` gains `mend_on_crit`/`mend_on_success`/`mend_on_partial` (PositiveSmallInt,
default 0 — every pre-existing severity-decay-only treatment is unaffected) and
`once_per_wound_per_helper` (bool, default False). `perform_treatment` routes any nonzero mend
amount through `mend_wound()` alongside its existing severity-decay path; the actual amount
mended (which may be less than `mend_on_*` — the fraction cap or `max_health` clamp may bite) is
recorded on a new `TreatmentAttempt.health_mended` field. Costs (action turn, resonance/anima)
ride the existing gates — heals are never free, never time-based, never passive; regeneration
stays forbidden to players (enemy anti-attrition, e.g. regenerating monsters, is legal and
explicitly out of this ADR's scope — it belongs with enemy-design content).

**Documented judgment calls** (both left open for a future content-authoring pass, not schema
changes):

- **Which wound each pool outcome applies:** the default wound pool's worst tier (failure)
  applies Crippling Wound, not Bleeding Wound. The pool-entry machinery supports a per-damage-type
  wound pool via `DamageType.wound_pool`, but authoring a *second* worst-tier consequence at the
  same tier would need weighted alternation, not a real per-hit pick — out of this pass's scope.
  Crippling was chosen as the single authored default because it applies universally (any damage
  type can cripple; not every damage type plausibly bleeds). Bleeding Wound is fully authored and
  available — a future slashing/piercing-specific wound pool can route to it with zero schema
  change.
- **Check type for wound treatments:** no Medicine/first-aid `CheckType` exists anywhere in the
  codebase's seeded content. `ensure_wound_treatment_content` reuses the vitals-owned `Endurance`
  CheckType (already seeded for the wound/knockout resist checks) rather than authoring a new
  stat+skill composition (a Medicine Skill/Trait plus its CheckType) — a bigger content lift than
  this mechanics-vocabulary pass calls for. `TreatmentTemplate.check_type` just gets repointed
  when a proper composition lands; no migration required.

## Rejected alternatives

- **Free/unbounded healing** — directly contradicts the ratified design's attrition invariant;
  would make every fight fully reversible with enough healers, eliminating the "net-weaker for
  having fought" cost the vow-power rework depends on.
- **Once-per-wound-total (not per-healer)** — the exact anti-pattern the ratified design calls
  out: a single incompetent or unlucky healer could burn the wound's *only* tending, locking out
  every other healer for the rest of the wound's life. Per-healer bounding fixes this without
  removing the fraction cap.
- **A config-field tunable for `NEVER_TO_FULL_FRACTION`** — considered for consistency with
  `VitalsConsequenceConfig`'s other tunables (`knockout_base_difficulty` etc.), but
  `PERMANENT_WOUND_THRESHOLD` (the sibling wound-tier threshold constant) is already a plain
  module constant, not a config field — matched that precedent rather than mixing conventions.
- **Reusing `ConditionInstance.severity` as the mend-cap basis** — severity already carries
  cleansing/dispel semantics (decays to 0 → resolved) and is a coarse tier label (1/2), not a
  damage-shaped quantity; a separate `WoundDetails.damage_taken` keeps the mend math anchored to
  the actual debit that caused the wound, independent of how severity gets tuned.

## Addendum (#3391, 2026-08-26)

Cast power now feeds a third input into the mend amount: `TreatmentTemplate
.mend_intensity_multiplier` (default 0) scales the outcome-tier mend by the caster's effective
intensity, added to `amount` strictly before `mend_wound()` is called. This does not reverse or
supersede this ADR — the two bounds above (once-per-healer-per-wound, and the never-to-full
fraction clamp inside `mend_wound()`) are unchanged and remain authoritative over whatever
`amount` is offered, however that amount was computed. Power scaling composes with the
double-bound; it cannot bypass either half of it.

> Status: accepted · Source: issue #2644 (lore repo `design/covenant-vows-consolidated.md` §3.1)
> · Related: ADR-0010 (FK direction specific→general), ADR-0007 (no JSON fields), ADR-0013 (no
> data migrations pre-production)
