I now have enough verified ground truth to write the critique. My code reads confirm the report is largely accurate but materially incomplete in several specific, high-value ways. Returning the prioritized gap analysis.

---

# Completeness Critique — Power vs. Intensity Research Report

The report is well-anchored and its verified code claims (the two functions, the `target_damage_type` FK, `EQUIPMENT_RELEVANT_CATEGORIES` membership, the discarded pre-cast payload) all check out against the code. But for a "range widely before committing" mandate it converges too early, misses an already-built precedent that changes the risk calculus, and under-states several tradeoffs. Prioritized gaps below.

## P0 — Must address before the design conversation

**1. The report misses an already-wired MODIFY_PAYLOAD read-back precedent that directly de-risks Issue 1 and informs the whole architecture.**
`world/magic/services/corruption.py:389-427` already does *exactly* the pattern the report frames as an open, unsolved gap: it builds a `CorruptionAccruingPayload`, emits `CORRUPTION_ACCRUING`, then **reads `pre_payload.amount` back** after dispatch, short-circuits on zero, and re-reads for partial absorption. This is the canonical "reactive subscriber reduces the landed value, not the channeled cost" mechanic — the user's exact ward-reduces-power invariant, already shipped for corruption. The report's Section 2.4 / Issue 1 treat the read-back as novel surgery. It is not; it is a copy of a working pattern.
*Concrete follow-up:* Add a section reconciling the new work against `corruption.py`'s pre-mutation-event idiom. This is itself a latent **parallel-implementation risk** the report failed to flag: if Issue 1 invents a *different* read-back convention than the corruption path, you get two divergent reactive-payload idioms in the same app. The design should adopt the corruption idiom or refactor both onto a shared helper.

**2. The "three scaling formulas" claim is wrong in count and wrong about consistency — and the discrepancy is load-bearing.**
There are **four** intensity-scaling sites, not three: `TechniqueCapabilityGrant.compute_value` (`models/techniques.py:468`), `TechniqueAppliedCondition.compute_severity` (`:657`) and `.compute_duration_rounds` (`:672`), and `TechniqueDamageProfile.compute_damage_budget` (`:736`) — four distinct multiplier fields (`intensity_multiplier`, `severity_intensity_multiplier`, `duration_intensity_multiplier`, `damage_intensity_multiplier`). More importantly: **capability grants already diverge from combat.** `compute_value` falls back to `self.technique.intensity` when `effective_intensity is None` (`:465-467`), and the combat resolver does *not* pass it an effective intensity. So capability magnitude today ignores combat pull bumps entirely — it is a *third* intensity-reading behavior, contradicting the report's clean "world-side family all reads `compute_effective_intensity`" picture (Section 3.2 lists the capability grant under world-side, but in code it's not wired to the combat function at all).
*Concrete follow-up:* Re-audit which of the four formulas actually receive `effective_intensity` from a live caller vs. silently fall back to `technique.intensity`. The intensity→power migration (Issue 2/3) must enumerate all four and confirm each call path, or the "atomic one-line swap" promised in Issue 2 will miss the capability path.

## P1 — Significant gaps that narrow the option space prematurely

**3. Converged too early on four "architectures" that are mostly the same decision dressed differently; missed genuinely distinct axes.**
Directions A/B/C are largely *the same mechanism* (route power through `CharacterModifier` + `get_modifier_breakdown`) differing only in *where the function lives*. Only D is conceptually distinct. The report presents four directions but the real decision tree has under-explored orthogonal axes it never separates:
   - **Where power is derived** (runtime-stats fn vs. combat fn vs. pipeline vs. model method) — what A/B/C actually vary.
   - **When power is computed** (snapshot at cast vs. re-derived) — raised only in passing for B/D; relevant to *all* of them.
   - **Whether power is a stored field, a transient computed value, or an event-payload value** — never cleanly posed.
   - **Whether power is scalar or vectored** (one number vs. per-facet like PoE Power Level fanning to magnitude/penetration/area separately) — the report cites PoE Power Level as supporting a single scalar, but the opposite reading (power as a small struct) is never offered as a candidate.
*Concrete follow-up:* Re-cast Section 5 as a decision matrix over these orthogonal axes rather than four pre-bundled packages. The bundling hides combinations (e.g., "scalar power as transient field on RuntimeTechniqueStats, re-derived, no penetration contest") that may dominate.

**4. The "no parallel implementations" constraint is applied to the two intensity functions but NOT to the four scaling formulas or the corruption precedent.**
The report correctly flags `get_runtime_technique_stats` vs `compute_effective_intensity`. But per the codebase's own anti-reinvention rule, the **four near-identical `base + mult × intensity` formulas** are a textbook parallel-impl smell that the report relegates to an "open question" (7.1 #3) rather than a constraint violation to resolve. And see P0#1 — the reactive read-back is a third parallel-impl exposure. Given the user's hard "no parallel implementations" stance, these should be P0/P1 *findings*, not optional refactors.

**5. Buffs-via-existing-modifier-system: the report endorses this but never verifies `get_modifier_breakdown` can express what power needs.**
Directions B and the PoE/GAS lessons require multiplicative and override ops. The report admits (B's cons, D) that the current breakdown is **additive-only** and that extending it is "its own design" — but never actually reads `get_modifier_breakdown` to confirm it's additive-only, nor checks whether amplification (mentioned at 2.3) already provides a multiplicative hook. If "buffs via existing modifier system" is a hard constraint and the existing system is additive-only, then "+50% power to fire" is **not currently expressible** and that is a gating finding, not a footnote.
*Concrete follow-up:* Read `get_modifier_breakdown` / `get_modifier_total` and the amplification logic. Determine concretely whether multiplicative power buffs are in-scope of the existing system or require extending it. This decides whether the "use the existing modifier system" mandate is even satisfiable for the multiplicative use cases.

## P2 — Tradeoffs stated too weakly; angles not consulted

**6. Direction D's double-counting risk is the most important tradeoff in the report and is hand-waved.**
D introduces a penetration-vs-resistance contest "that would interact with the existing check/clash and damage-budget systems (potential double-counting of 'defense')." This is stated as a one-line con but it's potentially **disqualifying** — Arxii already resolves defense three ways (checks, clash, damage budgets). The report should either rule D out on these grounds or do the work of showing how penetration coexists with clash. As written it lets D look more viable than the code supports.

**7. Game-design angles not consulted that would add value:**
   - **Failure/mishap as the reward-side of power, not just cost-side.** The report keeps Soulfray/mishap purely on the channeled axis (correct), but never explores whether *low landed power despite high channel* (warded-to-zero) should feed back into mishap/Soulfray narrative — WFRP/Shadowrun lessons are cited but only for cost-on-channel, not for the dramatically interesting "you overpaid and it bounced" state beyond D's outcome label.
   - **No consultation of the existing `clash` strain_commitment axis as a possible third lever.** Clash check rolls are driven by `strain_commitment`, not intensity (the report flags this as intensity-independent). But strain_commitment is conceptually adjacent to "how hard you're pushing" — the report never asks whether power should relate to strain_commitment at all, treating them as fully orthogonal without justification.
   - **Resonance/corruption attribution under amped power.** If a pre-cast amp raises landed power, does per-resonance corruption attribution (which the report keeps on intensity) still feel right narratively when an *external* amp did the work. Edge case worth a design opinion.

**8. Use cases not covered:**
   - **Multi-target / AoE power division** — does landed power split across targets, or apply per-target. None of the directions address it; the damage-budget path may already assume single-target.
   - **Power on healing / beneficial techniques** — every example is offensive (wards, damage, severity). "+power to fire spells" framing ignores whether power scales beneficial magnitude symmetrically, and whether a "ward" can ever *reduce a buff's* landed power (griefing vector).
   - **NPC/threat-pool side.** `ThreatPoolEntry.base_damage` and the NPC clash path (`clash.py:1185`) use authored values directly and bypass `compute_effective_intensity` entirely. The report's world-side classification implicitly assumes PC casters; it never states whether NPCs get a power axis or stay on flat authored damage. This is a real coverage hole for combat.
   - **Stacking limits / diminishing returns on power** — the report inherits additive stacking "for free" but never asks whether unbounded "+power" stacking is desirable, which is a balance question the existing modifier system may not gate.

**9. Terminology collision is identified but the report itself muddies it.**
Section 7.1 #2 correctly flags "power" is overloaded (`base_power`, `IntensityTier` "calculated power", `base_damage`). Good. But Sections 1–6 then use "power" pervasively as the new concept anyway, which will leak into the design conversation as exactly the confusion it warns about. Recommend the report adopt the disambiguated term (`landed_magnitude` / `effective_power`) *throughout* now, not defer it.

## Suggested follow-up research round (concrete)

1. Read `get_modifier_breakdown` + amplification logic; produce a definitive yes/no on whether multiplicative/override power buffs are expressible without extending it (gates P1#5).
2. Audit all four scaling-formula call sites for their actual intensity source (effective vs. fallback); confirm the capability-grant divergence (P0#2).
3. Document the `corruption.py` pre-mutation-event read-back idiom as the reference pattern for the pre-cast read-back; decide adopt-vs-refactor-to-shared-helper (P0#1).
4. Spike whether D's penetration contest can coexist with clash without double-counting, or formally rule D out (P2#6).
5. Add NPC/threat-pool, AoE, and beneficial-technique use cases to the coverage matrix (P2#8).
6. Re-pose Section 5 as orthogonal axes (where/when/storage/scalar-vs-vector), not four pre-bundled packages (P1#3).

Code anchors verified during this critique: `src/world/magic/services/corruption.py:389-427` (working read-back precedent the report omits), `src/world/magic/models/techniques.py:465-468` (capability grant falls back to `technique.intensity`, not wired to combat), `:657/:672/:736` + `:468` (four scaling formulas, not three), `src/world/combat/clash.py:1185` (NPC path bypasses `compute_effective_intensity`), `src/world/mechanics/constants.py:82-90` and `models.py:120-158` (report's verified claims confirmed accurate).
