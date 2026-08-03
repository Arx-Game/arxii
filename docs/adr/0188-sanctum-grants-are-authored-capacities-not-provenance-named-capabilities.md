# ADR-0188: Sanctum grants are authored capacities, never provenance-named capabilities

**Status:** Accepted · **Date:** 2026-08-01 · **Issue:** #2736 (surfaced by #2724)

A ship's sanctum grants what the authored `ThreadPullEffect` catalog says it grants —
a capacity already in the capability vocabulary, at a magnitude on the ADR-0164 ladder —
and gameplay mints no capability of its own. Concretely: a tier-0 `TargetKind.SANCTUM`
row with `effect_kind=CAPABILITY_GRANT` names the capacity; a sibling row with
`effect_kind=VITAL_BONUS` and a `SHIP_HULL`/`SHIP_HANDLING`/`SHIP_ARMAMENT`
`vital_target` names the stat the vessel leans into. Both scale with thread depth, so
one row per resonance covers every level. A resonance with no authored row grants
nothing, and that is not an error.

**Why.** `battle_bridge.py` previously minted a `CapabilityType` named
`sanctum_<resonance>` per level-3 thread and attached it at a flat 1. Three things were
wrong with it, and only the first is a naming preference. (a) `sanctum_flame` names a
*provenance* — where a bonus came from — where all 33 authored capabilities name a
*capacity*, which is what the machinery in `world/battles/resolution.py` and
`world/military/models.py` is built to read. (b) A flat 1 carries no meaning on the
ADR-0164 ladder, where 5 is an unimpaired mortal, and is the binary-flag shape
[ADR-0164] exists to replace. (c) `conditions.capabilitytype` is in `CONTENT_MODELS`, so
a gameplay path was writing authored-looking rows into the exported content corpus —
rows named after *other* content, so the set could never be enumerated ahead of time.
That is the #2724 defect class; #2724 deliberately declined to paper over it with a
`CONFIG_PREREQUISITES` entry, correctly, since a data-derived set is not a
code-required row.

The mapping model already existed. `ThreadPullEffect` is keyed
`(target_kind, resonance, tier, min_thread_level)`, `TargetKind.SANCTUM` was already a
choice, and `world/ships/sanctum_bonus.py`'s own docstring already claimed the catalog
as its source — the bridge was simply ignoring the sibling it documented. Nothing new
was modelled here.

**Rejected.** *Authoring the `sanctum_<resonance>` capabilities in the lore repo, plus
`WeatherTypeCapabilityChallenge` rows referencing them.* That would make the shipped
code correct as written, at the cost of a permanent parallel vocabulary of
provenance-named capabilities the rest of the system cannot use. *A separate
`SHIP_STAT` effect kind for the stat half.* Cleaner vocabulary — a ship's hull is not a
"vital" — but it splits one authored mapping across two row shapes for no gain, and the
`SHIP_*` members are documented on `VitalBonusTarget` as the odd ones out. *Deleting the
placeholder and deferring.* There was nothing left to defer once the mapping table was
found to exist.

**Consequences.**

- **Two authored rows per resonance, not one.** The spec assumed one row could carry
  both effects; `threadpulleffect_lookup_key` admits a single row per
  `(target_kind, resonance, tier, min_thread_level)`, and `effect_kind` is one column.
  Content authors the stat row at `min_thread_level=0` and the capability row at
  `min_thread_level=3` — distinct keys, and the split coincides exactly with the
  existing gameplay semantic that a capability unlocks at depth 3.
- **The level-3 floor moved from code to content.** `ship_sanctum_capabilities`'
  hardcoded `level__gte=3` is gone; the authored `min_thread_level` is the gate. Keeping
  both would make an authored `min_thread_level=1` row silently inert, which is the
  failure this ADR is about.
- **A ship needs a power figure of its own.** `apply_capability_curve` is geometric in
  `power` and returns `base` unchanged when `power <= 0`, so thread depth (which enters
  as `sensitivity`) does nothing on its own. The ship uses the **sanctum's installed
  level** — the shrine's own strength, already the basis of the anchor cap
  (`feature_instance.level x 10`), and a property of the vessel rather than of whichever
  character consecrated it. Rejected: the consecrating character's `context_free_power`,
  since a ship is a shared object and there is no principled answer to *whose*.
- **A character-side guard is now required.** The weaver owns their `SANCTUM` thread
  personally, so ship-stat rows are reachable from
  `CharacterThreadHandler.passive_vital_bonuses`; it returns 0 for the three ship
  targets. No caller passes one today — the guard is against a future one, because the
  leak would be a wrong number rather than an error.
- **The corpus is fixed and enumerable again.** Deploying a threaded ship authors
  nothing, which `test_deploying_a_threaded_ship_mints_no_capability_type` pins.
- **The content does not exist yet.** Zero `magic.threadpulleffect` rows are authored.
  Until the lore repo carries them every sanctum grant is inert — deliberately, per the
  absent-row-means-inert rule the rest of the pull-effect catalog follows. Merge order
  is arxii first: `VitalBonusTarget` must accept the ship targets before rows naming
  them will load.

Supersedes the placeholder halves of ADR-0086's sanctum-snapshot paragraph (the
snapshot-at-materialize-time decision itself stands unchanged).
