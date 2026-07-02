# Signature motif bonus is an additive flourish, not a discovered TechniqueVariant

**Supersedes:** ADR-0056

A character may *sign* one of their TECHNIQUE-kind Threads by attaching a
`SignatureMotifBonus` — a staff-authored, facet/resonance-gated additive bonus that
applies on top of the signed technique whenever it is cast. The bonus is NOT a
`TechniqueVariant`, does NOT participate in the discovery ceremony
(`fire_variant_discoveries`), and does NOT change the technique's identity. It is a
cosmetic + mechanical flourish: your Motif bleeds into the casting.

## Context and problem

ADR-0056 described a "signature thread" as a `TargetKind.TECHNIQUE` Thread that carried
its own resonance, which could deliberately diverge from the Gift's resonance (a
*discordant signature*). The implementation was left as future work ("re-scope existing
`TargetKind.TECHNIQUE`"). When #1582 arrived, two concrete options competed:

1. **Resonance-divergence model (ADR-0056 literal):** The signature thread's resonance
   overrides the Gift's for that one technique — a discordant signature changes the
   technique's affinity. Requires re-scoping how `gift_resonances_for` resolves, teaching
   the specialization engine about a per-technique resonance override, and triggering
   `fire_variant_discoveries` when the override crosses a variant threshold. Complex
   interdependency with the specialization engine.

2. **Motif-bonus model (this ADR):** The character applies their Motif to the signed
   technique. A `SignatureMotifBonus` is a staff-authored catalog row gated on the
   character's existing Motif facet/resonance bindings. Attaching it to a TECHNIQUE Thread
   via `Thread.signature_bonus` (nullable FK) causes the bonus's additive payload
   (conditions, intensity delta, narrative snippet) to fire alongside the technique's own
   payload at cast time. No identity change, no discovery ceremony, no specialization
   engine entanglement.

## Decision

**We implement the motif-bonus model.** Signature = applying your Motif to one technique
above its Gift baseline. A signature bonus is an additive flourish on an existing
technique, not a new form of it.

**Four invariants that must hold forever:**

1. `SignatureMotifBonus` must NOT inherit `AbstractSpecializedVariant`. It is not a
   specialization variant and must not participate in variant resolution or discovery.

2. `Thread.signature_bonus` (FK to `SignatureMotifBonus`, nullable, PROTECT) may only be
   set when `thread.target_kind == TargetKind.TECHNIQUE` — enforced by `clean()` and a DB
   `CheckConstraint` (`thread_signature_bonus_technique_only`).

3. The bonus's conditions apply through the SAME `apply_technique_conditions` seam
   (via the optional `applied_condition_rows` param added in #1582) — no parallel
   condition-apply path. Because those conditions land on the resolved target, the
   consent decision (`technique_alters_behavior` / `cast_requires_consent`,
   `services/targeting.py`) MUST include the caster's active signature bonus's
   behavior-altering conditions (ADR-0024) — a benign technique signed with a
   behavior-altering bonus is consent-gated exactly as if the technique carried that
   condition; a non-behavior-altering signature condition (Entangled) stays
   consent-free. The cast routes thread `caster=` into the predicate.

4. The bonus's `flat_intensity_delta` folds into the resolved cast intensity via
   `signature_intensity_delta(character, technique)` added to `use_technique(power_intensity_bonus=…)`.
   It is ADDITIVE — it never replaces the technique's base intensity.

## Consequences

**What ships in #1582:**
- `SignatureMotifBonus` catalog (`world/magic/models/signature.py`) + three payload child
  rows inheriting the shared abstract bases: `SignatureMotifBonusCapabilityGrant`,
  `SignatureMotifBonusDamageProfile`, `SignatureMotifBonusAppliedCondition`.
- `Thread.signature_bonus` nullable FK (TECHNIQUE-kind only). Migrations 0068 + 0069.
- Selection service (`world/magic/services/signature.py`):
  `available_signature_bonuses`, `set_signature_bonus`, `clear_signature_bonus`,
  `signature_bonus_for`.
- Cast wiring (`world/magic/services/signature_effects.py`): `signature_intensity_delta`
  + `apply_signature_bonus_conditions` (uses the shared seam). Both cast paths
  (non-combat `request_technique_cast`, combat `CombatTechniqueResolver`) wired.
- Non-combat cosmetic narration: `signature_clause` + `render_cast_outcome_narration`
  extended in `world/magic/narration.py`.
- Three REGISTRY actions (`SignatureSetAction` / `SignatureClearAction` /
  `SignatureListAction`, `actions/definitions/signature.py`) and `CmdSignature`
  (`commands/signature.py`, key `"signature"`, `signature set/clear/list`).
- E2E journey test: `world/magic/tests/integration/test_signature_motif_e2e.py`.

**Deferred fast-follows (NOT done in #1582):**
- Signature `damage_profiles` are NOT applied at the combat cast seam (`_apply_damage`
  fold is a fast-follow).
- Signature `capability_grants` have no cast-time seam (the technique-authored capability
  grant seam does not exist anywhere yet).
- Combat cosmetic narration of the bonus (`NARRATIVE_ONLY`-style hook for the combat path
  is a fast-follow).
- Web selection surface (`SignatureViewSet`) — the management UI for players to pick their
  bonus from the web is deferred.

**Supersedes ADR-0056** (which described the resonance-divergence model). The discordant
resonance idea is closed; if the resonance override ever becomes desirable it must be
treated as a new, separate design question, not a resumption of ADR-0056.

> Status: accepted · Source: #1582 (2026-06-30) · Supersedes: ADR-0056
