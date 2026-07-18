# Canonical capability vocabulary is the 27-name union of wired + affordance sets

Two `CapabilityType` lists had grown independently and never reconciled: the 9 names
live combat/foundational code already wires by string literal (`endurance`,
`melee_attack`, `ranged_attack`, `awareness`, `movement`, `limb_use`, `defense`,
`support`, `leadership` — `world/conditions/constants.py`'s `FoundationalCapability`
plus `world/seeds/game_content/{magic,battles,covenant_roles}.py`), and the 19-name
affordance matrix ratified in `docs/architecture/capability-challenge-content.md`
(`generation`, `force`, `projection`, `manipulation`, `barrier`, `traversal`,
`movement`, `precision`, `suppression`, `transmutation`, `communication`,
`perception`, `intimidation`, `persuasion`, `deception`, `charm`, `inspiration`,
`analysis`, `exploitation`). TehomCD ruled (2026-07-18, #2503 spec phase 0) that the
canonical vocabulary is their union, deduped on the shared `movement` entry, for 27
names total. Rejected: picking one set (either orphans the live combat/foundational
consumers or discards the already-approved affordance design) and letting vocabulary
grow freely per-feature (the uncurated-sprawl failure mode this repo's
Anti-Reinvention rule exists to prevent). `awareness` (foundational passive
sense-gate, `innate_baseline=1`, zeroed by Unconscious) and `perception` (active,
supernormal sensing, `innate_baseline=0`, granted by techniques) are deliberately
kept as distinct terms, not merged. The old `stealth` name gets no successor in this
vocabulary — a capability is added only when a real consumer needs it, per the
curated-not-invented pattern used elsewhere for GM checks and gift/technique content.

> Status: accepted · Source: issue #2503 spec phase 0 (ruling 2026-07-18) ·
> Related: `docs/architecture/capability-challenge-content.md` (19-name affordance
> matrix), `docs/architecture/property-capability-action.md` (capability design
> principles), `world/conditions/constants.py` (`FoundationalCapability`)
