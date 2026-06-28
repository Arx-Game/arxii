# Gift Specialization Engine — Design (#1578)

**Issue:** #1578 — *One specialization engine: resonance × {gift, path, role} → customized
techniques* (priority:now, epic:magic).
**Status:** Spec — draft for team review.
**Date:** 2026-06-28.
**ADRs:** generalizes ADR-0055; folds in the substrate of ADR-0051/0052 (gift-thread anchor +
`Gift.resonances` consumer refactor). Rejected-approach rationale: ADR-0016 (one shared base)
and ADR-0015 (no GenericFK / ContentType polymorphism).

## Goal

A character's specialized techniques and capabilities are resolved by combining an **entity**
they hold — a **Gift**, a **Technique**, or a **Covenant Role** — with their **resonance** (read
from the thread woven into that entity) at a **threshold** (the thread's `level`). One shared
specialization primitive does this; there are not three per-entity bespoke systems. The
combinatorial space (resonance × {gift, path, role}) **is the product** — a dazzling number of
unique builds players can discover (design tenet #2 / ADR-0055).

The single proven instance today is `resolve_effective_role` (covenant sub-roles,
`world/covenants/services.py:584`), the only working axis-combination in the codebase. We
generalize it. **Approach B (approved):** a shared `AbstractSpecializedVariant` abstract base +
per-entity concrete variant rows + one resolver function; the covenant side is refactored to
inherit the base as a **no-op migration** guarded by the existing covenant E2E test.

## Decisions (locked during brainstorming)

1. **Fold #1581's substrate in.** #1578 (priority:now) depends on the gift-thread substrate
   (#1581 / ADR-0051-0052, priority:next, OPEN). This PR builds the `TargetKind.GIFT` thread
   anchor + the `Gift.resonances` consumer refactor so #1578 is independently runnable and
   E2E-testable. This likely supersedes / closes #1581's anchor + read-seam scope; #1581 retains
   only the per-target-kind *cost tuning* (ADR-0051 "most expensive thread kind") as a
   follow-up.
2. **Per-resonance sub-technique rows** (mirror sub-roles). A `Technique` gets a self-FK
   `parent_technique` + variant rows keyed `(parent, resonance, unlock_thread_level)`, each its
   own name/intensity/payload + own discovery beat. Most combinatorial; consistent shape across
   Gift/Path/Role.
3. **Path selects the base technique set + an orthogonal casting-style flavor; it is NOT a
   second specialize-on-read axis.** The engine has **one** reshape axis — **resonance** —
   exactly like the proven sub-role pattern. Path does two things, both reusing existing
   structures:
   - **Base-set selector** — `TechniqueStyle.allowed_paths` M2M (5 styles ↔ 5 Prospect paths).
     A Steel-path and a Whispers-path mage learn different techniques from the same gift. This
     is membership, consumed at acquisition/learning time. This is the "dead `allowed_paths`"
     ADR-0055 names — already wired, not a new build.
   - **Casting style / manifestation** (chanting vs. singing vs. no visible casting) — read at
     narration time via the existing `TechniqueStyle` + `world/magic/narration.py` path. This is
     orthogonal to the technique's mechanical identity; **no new model**.
4. **Full wire + E2E.** Engine + the four cast-pipeline consumer refactors + ONE E2E journey
   test (north star: magic playable end-to-end).
5. **Latent level-0 GIFT thread.** Acquiring a gift implicitly grants a latent level-0 GIFT
   thread — "the fact you can do the gift at all means the thread exists." The thread starts at
   the resonance the player chose during CG (from the gift's supported set). Weaving (Rite of
   Weaving) commits a resonance to empower it; Imbuing raises the level; crossing
   `unlock_thread_level` (≈3) resolves the matching variant and fires the discovery beat.
   *Narrative framing:* acquiring a gift IS intuitively weaving a (latent) thread — the
   Glimpse/awakening moment. Future direction for #1587: post-CG acquisition = the same weave act.
6. **`Gift.resonances` is repurposed** from "the resonance a character casts at" → "the
   resonances this gift **supports**" (the set you may weave into it). It becomes a constraint
   on the weave, not the cast-time value. Not removed.
7. **One active GIFT thread per (owner, gift) for now.** Uniqueness mirrors
   `target_covenant_role` (one active thread per anchor). Multiple-resonance / choose-which-
   variant-to-cast is a **deferred follow-up** (flagged, not scoped here).

## Architecture

### The shared base — `AbstractSpecializedVariant`

New module: `world/magic/specialization/` (`models.py`, `services.py`).

`AbstractSpecializedVariant` (SharedMemoryModel, **abstract**) holds the shared columns + the
shared resolution + discovery behavior, written once:

- `resonance` → `magic.Resonance` (PROTECT) — the resonance this variant manifests.
- `unlock_thread_level` (PositiveIntegerField, default 0) — 0 = base/parent; ≥3 = variant.
- `discovery_achievement` → `achievements.Achievement` (PROTECT, null) — granted + global-first
  Discovery on first threshold crossing.
- `codex_entry` → `codex.CodexEntry` (PROTECT, null) — lore entry unlocked on manifestation.

Shared behavior (methods on the base):

- `@classmethod matching_variant(cls, parent, *, resonance, thread_level)` — the selection
  predicate lifted verbatim from `resolve_effective_role`'s loop: among the parent's variant
  rows, pick the one where `resonance_id == thread.resonance_id and unlock_thread_level <=
  thread.level`, highest matching `unlock_thread_level` wins, fallback to `parent`.
- `@classmethod newly_crossed_variants(cls, parent, *, resonance_id, starting_level, new_level)`
  — the threshold-crossing predicate lifted from `fire_subrole_discoveries`'s list-comp
  (`covenants/discovery.py:37-44`): the parent's variants where
  `starting_level < unlock_thread_level <= new_level` at `resonance_id`. The abstract base
  owns this; each concrete subclass binds its own `parent` FK name.
- `discovery_narrative(variant, *, is_first) -> tuple[recipients, body]` — the flavor copy
  for the NarrativeMessage (entity-specific prose: "sub-role" for covenant, "technique form"
  for gift). The abstract base declares it; each subclass implements it.

**Discovery ceremony is NOT rewritten** — `world/covenants/discovery.py:fire_subrole_discoveries`
already implements the full beat (grant `discovery_achievement` via `grant_achievement` →
`_unlock_codex` (codex KNOWN) → `_notify` (gamewide/personal NarrativeMessage), idempotent via
the `CharacterAchievement`-exists check). It is already called target-kind-agnostically from the
imbue seam (`world/magic/services/resonance.py:309`). **We generalize it**, not duplicate it:
rename to `fire_variant_discoveries(*, thread, starting_level, new_level)`, and instead of the
hard-coded `TargetKind.COVENANT_ROLE` early-return + `CovenantRole.objects.filter(...)` query,
dispatch to the variant model for the thread's `target_kind` and call its
`newly_crossed_variants` + `discovery_narrative`. The covenant path keeps working through the
same call site (it's the same function, now general); the gift path adds a `TargetKind.GIFT`
branch. See the anti-reinvention ledger below.

Each concrete subclass adds only its `parent` self-FK + its own override columns + a unique
constraint `(parent, resonance, unlock_thread_level)`. Single-depth only (no
variant-of-a-variant) — mirrors covenant `_clean_subrole`.

### Concrete subclasses

- **`TechniqueVariant`** (new, in `world/magic/specialization/models.py`) — inherits
  `AbstractSpecializedVariant`.
  - `parent_technique` → `magic.Technique` self-FK (PROTECT, `related_name="variants"`).
  - Override columns (nullable; null = inherit parent's value): `name_override` (CharField),
    `intensity_delta` (SmallIntegerField), `control_delta` (SmallIntegerField).
  - Payload via the **existing abstract bases** already in `world/magic/models/techniques.py`
    (`AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition`):
    `TechniqueVariantCapabilityGrant` / `TechniqueVariantDamageProfile` /
    `TechniqueVariantAppliedCondition` — same shape as `Technique`'s committed payload rows.
    A variant may *replace* the parent's payload (a different damage profile for the Celestial
    version) or *add to* it.
  - Unique constraint `(parent_technique, resonance, unlock_thread_level)` — identical shape to
    `covenant_subrole_unique_per_parent_resonance_level`.
- **`CovenantRole`** — refactored to inherit `AbstractSpecializedVariant`. Its existing
  `resonance` / `unlock_thread_level` / `discovery_achievement` / `codex_entry` columns already
  match the base, so the migration is a **schema no-op** (inherited columns stay on the same
  table). Its `parent_role` self-FK and unique constraint stay. One nuance: `resonance`'s
  reverse `related_name="covenant_subroles"` becomes `%(class)s_subroles`
  (→ `covenantrole_subroles`) on the hoisted base — but **no code reads the reverse accessor**
  (`grep '\.covenant_subroles'` is empty; only the migration declares it), so this is safe. **Existing covenant tests pass unchanged** —
  the faithfulness guard.

### The resolver

`resolve_specialized_variant(*, entity, character) -> entity` (free function in
`world/magic/specialization/services.py`):

1. Find the character's active thread anchored to this entity (`TargetKind.GIFT` thread on the
   gift; `TargetKind.COVENANT_ROLE` on the role). For a gift, the latent level-0 thread is
   guaranteed to exist (provisioned at CG) — so a gift always resolves.
2. If no thread (or thread below all thresholds), return the entity unchanged.
3. Call the entity's `matching_variant(resonance=thread.resonance, thread_level=thread.level)`
   → the variant (or parent).
4. **Derive-on-read** (ADR-0014): never snapshotted. A Fall/Redemption (ADR-0054) changes the
   thread's resonance → the next read resolves a different variant, instantly, with no
   regeneration step.

The existing `resolve_effective_role` becomes a one-line shim:
`return resolve_specialized_variant(entity=role, character=character)` — same callers, same
result, one engine.

## The GIFT thread substrate (ADR-0051/0052)

### Anchor

- Add `TargetKind.GIFT` to the `TargetKind` enum (`world/magic/constants.py`).
- Add `Thread.target_gift` (FK → `magic.Gift`, PROTECT) — the typed FK, mirroring
  `target_covenant_role` / `target_technique` / etc.
- Integrity layers mirroring `target_covenant_role`: `clean()` validation, per-kind
  `CheckConstraint`, partial `UniqueConstraint` `(owner, target_gift)` WHERE `retired_at IS NULL`
  — **one active GIFT thread per (owner, gift)** (decision 7).

### Latent thread provisioning (CG)

`world/character_creation/services.py:finalize_magic_data` → after
`CharacterGift.objects.create` (line 781), call a new service
`provision_latent_gift_thread(sheet, gift, *, resonance)` that creates the **latent level-0
GIFT thread** at the player's CG-chosen resonance.

**Required CG addition (small):** the magic stage must capture a chosen resonance from the
gift's supported set (`Gift.resonances`) and store it in `draft.draft_data`
(e.g. `selected_gift_resonance_id`). Today CG stores `glimpse_story` but no explicit gift
resonance — this is a genuine addition, not an existing field. `finalize_magic_data` reads it
and passes it to `provision_latent_gift_thread`. If absent (legacy/draft data), fall back to the
gift's first supported resonance with a logged warning.

### The resonance read seam (ADR-0052 — load-bearing refactor)

New helper in `world/magic/specialization/services.py`:

```python
def gift_resonances_for(character, gift) -> list[Resonance]:
    """The resonance(s) this gift manifests as FOR THIS CHARACTER — the resonance of
    their (latent or woven) GIFT thread. Derived on read. Never empty for an owned
    gift (the latent level-0 thread always exists)."""
```

These four cast sites switch from `technique.gift.resonances.all()` →
`gift_resonances_for(caster, technique.gift)`:

- `world/magic/services/power_terms.py:152`
- `world/magic/services/techniques.py:166` and `:221`
- `world/magic/services/resonance_environment.py:212`, `:255`, `:263`, `:362`

`Gift.resonances` (the authored M2M) is **repurposed** (decision 6) to "the resonances this
gift supports" — a constraint on the weave (`WeaveThreadAction` validates the chosen resonance
is in the set), not the cast-time value. No data migration touches it.

### Weaving / Imbuing for GIFT threads

- **Weaving** (Rite of Weaving / `WeaveThreadAction`): for a GIFT thread, operates on the
  pre-existing latent thread (commit/choose a resonance from `Gift.resonances`) rather than
  creating a new one — a GIFT-specific behavior, since the latent thread pre-exists. Other
  thread kinds still create-on-weave.
- **Imbuing** (Rite of Imbuing / `ImbueThreadAction` / `spend_resonance_for_imbuing`): raises
  the level. Crossing a variant's `unlock_thread_level` resolves the variant and fires the
  discovery beat (the same hook covenant sub-roles use).

### Deferred to #1581 (flagged)

- Per-target-kind thread **cost tuning** (ADR-0051 "most expensive thread kind"). A default
  cost is wired here so the anchor is usable; the tuning knob is #1581's.

## Data flow

1. **CG** — `finalize_magic_data` provisions the latent level-0 GIFT thread at the player's
   chosen resonance.
2. **Read** — `resolve_specialized_variant(entity=gift, character=caster)` finds the active
   GIFT thread (guaranteed), reads its `resonance` + `level`, and for each known technique of
   that gift finds the matching `TechniqueVariant` (highest `unlock_thread_level ≤ thread.level`
   at that resonance), else the parent technique.
3. **Cast** — the four refactored sites + the technique-resolution read path use the resolved
   variant's name/intensity/payload (base + delta) instead of the bare technique. When no
   variant matches (thread below threshold, or no variant authored for that resonance), the
   bare technique is used — **base form always castable**.
4. **Discovery** — first crossing of a variant's `unlock_thread_level` fires the generalized
   `fire_variant_discoveries` (achievement + codex KNOWN + gamewide NarrativeMessage), once per
   `(sheet, variant)`. The covenant path fires through the same generalized function (see
   "Discovery beat" below).
5. **Re-specialize** — a Fall/Redemption (ADR-0054) changes the thread's resonance; the next
   read resolves a different variant with no regeneration step.

## Discovery beat (generalized, not rewritten)

The discovery ceremony **already exists** as `world/covenants/discovery.py:fire_subrole_discoveries`
(BUILT & WIRED — called from the imbue seam `world/magic/services/resonance.py:309`,
target-kind-agnostically). It grants `discovery_achievement` (via `grant_achievement`, which
mints the global-first `Discovery` row), unlocks the codex entry (`_unlock_codex` → KNOWN),
and sends the gamewide/personal `NarrativeMessage` (`_notify`), idempotent via the
`CharacterAchievement`-exists check.

**We generalize it** into `fire_variant_discoveries(*, thread, starting_level, new_level)`:
the hard-coded `COVENANT_ROLE` early-return and `CovenantRole.objects.filter(parent_role_id=…,
resonance_id=…)` query become a dispatch on `thread.target_kind` to the variant model, which
supplies `newly_crossed_variants(...)` (the threshold predicate) and `discovery_narrative(...)`
(the flavor copy). The grant/unlock/notify ceremony body stays in `discovery.py` unchanged —
only the query + copy become entity-supplied. The covenant path keeps working (same function,
same call site); the gift path adds a `TargetKind.GIFT` branch. `test_subrole_discovery_beat.py`
and `test_resonance_subrole_flow.py` keep passing unchanged — the faithfulness guard.

## Testing

### ONE E2E journey test (north star: magic playable end-to-end)

In `world/magic/tests/` (or `world/magic/tests/integration/`), mirroring
`test_resonance_subrole_flow.py`:

1. CG-finalize a character with a gift + a CG-chosen resonance → assert the latent level-0
   GIFT thread exists at that resonance.
2. Author a `TechniqueVariant` for one of the gift's techniques at a resonance +
   `unlock_thread_level=3`.
3. Cast the technique at thread level 0 → assert it uses the **base** form (no variant
   resolved).
4. Imbue the GIFT thread past level 3 → cast again → assert it now uses the **variant's**
   name/intensity/payload (resolve-on-read picked it up with no regeneration step).
5. Assert the discovery beat fired: `CharacterAchievement` +
   `CharacterCodexKnowledge(KNOWN)` + a gamewide `NarrativeMessageDelivery`.
6. Re-run the existing covenant E2E test (`test_resonance_subrole_flow.py`) unchanged →
   covenant sub-role resolution + discovery still pass (the shared-base refactor did not
   regress the proven path).

### Targeted unit tests

- Resolver selection predicate: highest-match wins, fallback-to-parent, single-depth guard,
  thread-below-threshold returns parent.
- `provision_latent_gift_thread`: CG-chosen resonance honored, uniqueness enforced, soft-retire
  on gift loss.
- `gift_resonances_for`: returns the active GIFT thread's resonance; falls back correctly.
- GIFT-thread integrity: `clean()` + CheckConstraint + partial UniqueConstraint (one active
  per owner/gift).

### Test-tier notes (from memory)

- Run `just test-fast magic` + `just test-fast covenants` (covenant non-regression) on the
  SQLite fast tier; push and let CI's Postgres parity shard gate the rest.
- The existing `test_resonance_subrole_flow.py` is the canary for the no-op covenant refactor.

## Anti-reinvention ledger (code-verified 2026-06-28)

Verified against code (grep + open file + live caller), not docs/summaries. "Existing code is
the only source of truth; docs are stale hints."

| Proposed surface | Verdict | Evidence (file:line + caller) |
|---|---|---|
| `AbstractSpecializedVariant` abstract base | **ABSENT** | grep `AbstractSpecializedVariant` → 0 hits (the `specialization` hits are the unrelated `skills.Specialization` FK on `RitualCheckConfig`, `magic/admin.py:531`). Legitimately new. |
| `TechniqueVariant` + `parent_technique` self-FK | **ABSENT** | grep `parent_technique\|TechniqueVariant` → 0 hits. Legitimately new. |
| `resolve_specialized_variant(*, entity, character)` resolver | **ABSENT** | grep → 0 hits. Legitimately new; generalizes the proven instance below. |
| `resolve_effective_role` (the template to generalize) | **BUILT & WIRED** | `covenants/services.py:584`; called at `covenants/handlers.py:99` + `covenants/serializers.py:161`. Becomes a one-line shim. |
| `fire_subrole_discoveries` discovery ceremony | **BUILT & WIRED** | `covenants/discovery.py:21`; called target-kind-agnostically from the imbue seam `magic/services/resonance.py:309`. **Generalize, do not duplicate** — see "Discovery beat" above. |
| `grant_achievement` (grants ach + global-first Discovery) | **BUILT & WIRED** | `achievements/services.py` (called at `discovery.py:61`); reused as-is. |
| `_unlock_codex` / `_notify` ceremony helpers | **BUILT & WIRED** | `covenants/discovery.py:68`, `:95`; reused as-is. |
| `AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition` (payload bases) | **BUILT & WIRED** | `magic/models/techniques.py:445`, `:535`, `:472`; already shared by `Technique*` + `TechniqueDraft*` rows. Reused for `TechniqueVariant*` payload — no new payload base. |
| `TargetKind.GIFT` enum value | **ABSENT** | `magic/constants.py:84-92` has TRAIT/TECHNIQUE/FACET/RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE/COVENANT_ROLE/MANTLE/SANCTUM; no GIFT. (The `SECOND_GIFT` at `:307` and `weaving.py:145 _F_GIFT="unlock_gift"` are the unrelated ThreadWeavingUnlock catalog FK — the signature/weaving-unlock anchor, NOT the gift-thread itself; confirmed in memory `project-1577-gift-kind-on-gift-not-charactergift`.) |
| `Thread.target_gift` typed FK + integrity layers | **ABSENT** | grep `target_gift\b` in `threads.py` → 0 hits; the typed-FK + `clean()` + CheckConstraint + partial UniqueConstraint pattern mirrors `target_covenant_role`. |
| `Gift.resonances` cast consumers (4 sites to refactor) | **BUILT & WIRED** | `power_terms.py:152`, `techniques.py:166`+`:221`, `resonance_environment.py:212`+`:255`+`:263`+`:362` — all read `technique.gift.resonances.all()` today. Rewired to `gift_resonances_for()`. |
| CG finalize seam (latent-thread provisioning) | **BUILT & WIRED** | `character_creation/services.py:776-810` (`CharacterGift.objects.create` at `:781`) + `finalize_magic_data` at `:899` (incl. `glimpse_story` at `:931`). Latent-thread provisioning hooks in here. |
| `TechniqueStyle.allowed_paths` (Path base-set gate) | **BUILT & WIRED** | `magic/models/techniques.py:105-110`; the "dead `allowed_paths`" ADR-0055 names is already wired (5 styles ↔ 5 Prospect paths per cantrip notes). Consumed, not rebuilt. |
| `provision_latent_gift_thread` service | **ABSENT** | grep → 0 hits; new, called from `finalize_magic_data`. |
| `gift_resonances_for(character, gift)` helper | **ABSENT** | grep → 0 hits; new read seam. |

**Capability check (user-goal grep):** "resolve a resonance-specialized capability from an
entity×resonance combination, derived on read." Today only `resolve_effective_role`
(covenant sub-roles) does this; there is no gift/path equivalent — confirmed ABSENT by the
grep above. No second implementation of this goal exists to collide with. The engine
generalizes the one proven instance per ADR-0016.

**Deferrals verified:** the spec's flagged follow-ups (multi-resonance chooser, per-kind
cost tuning #1581, frontend picker) are each genuinely `[ABSENT]` (no chooser, no per-kind
cost column, no variant UI exists). They are stated as future surfaces, not asserted as
ready-to-build work; multi-resonance + frontend will be filed as `needs-design` questions
at PR time per the deferral rule, not feature issues.

## Out of scope (flagged follow-ups)

- **Multi-resonance / choose-which-variant-to-cast** (decision 7): multiple active GIFT
  threads per gift + a cast-time variant picker. The architecture does not preclude it
  (relax the uniqueness + make the resolver return a set); deferred to a follow-up issue.
- **Per-target-kind thread cost tuning** (ADR-0051) — #1581.
- **Full `Gift.resonances` consumer audit beyond the four cast sites** — checked, but the four
  cast sites are the load-bearing ones; any non-cast consumers migrated opportunistically.
- **Frontend variant picker UI** — out of scope; single-resonance-at-a-time needs no picker.
- **Post-CG gift acquisition (#1587)** as a weave act — future direction framing only.

## Docs to update in tandem (per "Docs Are Directives")

- `docs/systems/magic.md` + `docs/systems/INDEX.md` — new specialization engine + GIFT thread.
- `docs/systems/MODEL_MAP.md` — regenerate after the model additions.
- `docs/roadmap/player-capability-ledger.md` — flip the COMBINE pillar rows (specialization
  primitive, Gift×Path, resonance-differentiates, roles-grant-techniques) from ❌→DESIGNED to
  proven, with the E2E test as evidence.
- `docs/adr/0055-*.md` — mark the build realized (ADR stays; confidence line updates).
- `world/magic/CLAUDE.md` + `world/magic/models/` — Thread `target_gift` / `TargetKind.GIFT`;
  the latent-thread model; `Gift.resonances` repurposed to "supported set."
- `world/character_creation/CLAUDE.md` — the CG resonance-choice addition + latent-thread
  provisioning.
