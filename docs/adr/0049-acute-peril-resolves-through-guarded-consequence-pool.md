# Acute peril resolves through a guarded consequence pool, never unconditional death

When a downed character's Bleeding-Out condition reaches terminal stage — or goes unrescued after an
abandonment window — the outcome is resolved through an authored `ConsequencePool` (`bleed_out_terminal`,
`abandonment_enemy`, `abandonment_pvp`, or `abandonment_environmental`) via the shared
`_resolve_peril_via_pool` core, never via an unconditional `_mark_dead`. A PC attacker structurally
cannot produce a death candidate (the `die` / `character_loss` consequence is excluded before selection
— ADR-0023 extended from encounter-creation to the death layer itself). Abandonment resolution is
action-driven: the N-beat grace window (`SceneRoundDefaultsConfig.abandonment_grace_rounds`) counts
elapsed `round_number` beats, never wall-clock time (ADR-0004 extended to the dying state). Plummeting
is exempt from the hold/abandonment logic — a fall is environmental and self-completing, so its
descent always advances; we rejected pulling it into the same involved-party-hold model as Bleeding Out
because no "hostile party" or "rescuer" concept applies to gravity.

> Status: accepted · Source: #1479 · Extends: ADR-0023, ADR-0004
