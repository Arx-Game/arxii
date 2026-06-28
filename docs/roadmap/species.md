# Species & Identity — Status

**Status:** "what you can BE" today = species **stat-bonuses** + **distinctions**. The entire
**supernatural-identity layer** (lineage powers, species abilities, species vulnerabilities) is
greenfield — **designed (ADR-0050) but unbuilt**.

Per-capability tiers live in [`player-capability-ledger.md`](player-capability-ledger.md) (BE pillar).
Code wins over this doc.

## What's PROVEN

- `Species` (stat-bonuses + name hierarchy), applied to traits at character finalize.
- `CharacterDistinction` (effects→modifiers, trust gating; can grant *rituals*).

## The design (ADR-0050): species abilities are Minor Gifts

khati (special blood → lineage / animal-feature abilities), vampires, lycans, and other species powers
are delivered as **species-granted Minor Gifts** — *not* a bespoke per-species system — so they inherit
techniques, threads, resonance, and progression through the existing gift pipeline. Strength in a
species ability grows by weaving a thread into its Minor Gift (ADR-0051); its affinity follows that
thread's resonance (ADR-0052); the same ability specializes per character via the one engine (ADR-0055).
Acquisition rides the XP-unlock contract (ADR-0053). See the gift/resonance economy ADRs (0050–0056) and
[`planned-systems.md`](planned-systems.md).

## Gaps

- **khati / vampire / lycan / lineage** — no model or data today (lore-only). → Minor Gifts (ADR-0050);
  the Major/Minor taxonomy keystone landed in #1577 (`Gift.kind`); species-grant plumbing remains.
- **Species abilities beyond stat-bonuses** — ❌ → DESIGNED as Minor Gifts (ADR-0050).
- **Species vulnerabilities** (e.g. vampire ↔ sunlight) + an immunity/vulnerability framework — ❌ ABSENT,
  **no ADR yet** (vulnerability is per-condition only, never tied to identity).
- **Racial languages** — `Language` model + a `grants_species_languages` flag exist, but nothing grants
  or stores them (no `CharacterLanguage`). 🟡 SUBSTRATE.

## Deeper detail

- Capability tiers: [`player-capability-ledger.md`](player-capability-ledger.md) (BE pillar)
- Decisions: [`../adr/README.md`](../adr/README.md) (0050–0056)
- Planned machinery: [`planned-systems.md`](planned-systems.md) (Species & racial framework; Gift & resonance economy)
