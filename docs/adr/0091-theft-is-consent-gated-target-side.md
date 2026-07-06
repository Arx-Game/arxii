# Physical theft is consent-gated target-side; NPC holdings are always antagonism-allowed

`steal_permitted` (#1909, `flows.service_functions.inventory`) decides whether the deliberate
ownership-bypass Steal is even offered by checking the *target's* consent, never the thief's:
an NPC-owned item (no active `RosterTenure`) is always antagonism-allowed, while a player-owned
item gates on `world.consent.services.consent_blocks_targeting` against a new `theft_category()`
that defaults to `ALLOWLIST` (opt-in, default-deny) rather than the `EVERYONE` default every
other social-consent category uses. This follows the Golden Rule that no player should be
subjected to consequence-free trolling, while still giving players who want the crime-economy
fiction a sanctioned playground to opt into — every theft leaves a permanent `OwnershipEvent`
and a crime-tagged Legend deed, so consented theft still has narrative teeth (knowledge-driven
heat), it just never ambushes an unwilling victim. Rejected: a thief-side opt-in flag (e.g. "I
consent to committing crimes") — adds nothing the provenance ledger doesn't already provide,
since the thief always chose to steal. Also rejected: a flat ban on stealing from players — kills
the crime-economy fiction outright rather than gating it on consent.

> Status: accepted · Source: #1909
