# Species & Identity — Status

**Status:** "what you can BE" today = species **stat-bonuses** + **distinctions**. The entire
**supernatural-identity layer** (lineage powers, species abilities, species vulnerabilities) is
greenfield — **designed (ADR-0050) but unbuilt**.

Per-capability tiers live in [`player-capability-ledger.md`](player-capability-ledger.md) (BE pillar).
Code wins over this doc.

## What's PROVEN

- `Species` (stat-bonuses + name hierarchy), applied to traits at character finalize.
- `CharacterDistinction` (effects→modifiers, trust gating; can grant *rituals*).
- **Species-gift grant + provisioning (#1580)** [BUILT & WIRED]: `SpeciesGiftGrant`
  (through-model: `species → MINOR Gift + optional drawback_condition`) +
  `provision_species_gifts(sheet, *, resonance=None)` called from `finalize_magic_data`.
  Mints the `CharacterGift`, the latent GIFT thread (via `provision_latent_gift_thread`),
  and applies any drawback idempotently. GIFT anchor cap built: `path_stage × 10`.
  The gift's GIFT thread carries a tier-0 `ThreadPullEffect` with `effect_kind=RESISTANCE`
  that nets against the drawback vulnerability at the combat-damage seam (`apply_damage_to_participant`).
  ADR-0062. E2E: `world/magic/tests/integration/test_species_gift_e2e.py`.

## The design (ADR-0050): species abilities are Minor Gifts

khati (special blood → lineage / animal-feature abilities), vampires, lycans, and other species powers
are delivered as **species-granted Minor Gifts** — *not* a bespoke per-species system — so they inherit
techniques, threads, resonance, and progression through the existing gift pipeline. Strength in a
species ability grows by weaving a thread into its Minor Gift (ADR-0051); its affinity follows that
thread's resonance (ADR-0052); the same ability specializes per character via the one engine (ADR-0055).
Acquisition rides the XP-unlock contract (ADR-0053). See the gift/resonance economy ADRs (0050–0056) and
[`planned-systems.md`](planned-systems.md).

## Gaps

- **khati / vampire / lycan / lineage** — no game data yet (lore-only). The plumbing is now
  built (#1580: `SpeciesGiftGrant` + `provision_species_gifts`). Seed a MINOR Gift per species
  + an optional drawback `ConditionTemplate` to bring abilities live.
- **Species abilities beyond stat-bonuses** — [BUILT & WIRED] for the infrastructure (#1580);
  pending species data (no species → Minor Gift rows seeded yet; see ADR-0050).
- **Species vulnerabilities** (e.g. vampire ↔ sunlight) + broad immunity/vulnerability framework —
  minimum substrate built (#1580): `EffectKind.RESISTANCE` + `ConditionResistanceModifier` net
  at `apply_damage_to_participant`. Broad framework + environmental triggers (sunlight as a
  world-driven damage event) → **#1588** (ADR-0062).
- **Racial languages** — `Language` model + a `grants_species_languages` flag exist, but nothing grants
  or stores them (no `CharacterLanguage`). 🟡 SUBSTRATE.

## Deeper detail

- Capability tiers: [`player-capability-ledger.md`](player-capability-ledger.md) (BE pillar)
- Decisions: [`../adr/README.md`](../adr/README.md) (0050–0056)
- Planned machinery: [`planned-systems.md`](planned-systems.md) (Species & racial framework; Gift & resonance economy)
