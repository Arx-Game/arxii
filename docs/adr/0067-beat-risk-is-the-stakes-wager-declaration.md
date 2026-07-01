# Beat.risk is the stakes-wager declaration

`Beat.risk` (a `RenownRisk` choice: NONE/LOW/MODERATE/HIGH/EXTREME,
`world/stories/models.py`) is the canonical "what's at stake" signal for a story beat
— the GM's upfront declaration of how dangerous/consequential this beat is, made
before players commit to the scene. It drives the Legend award's base magnitude on
success (via `RISK_LEGEND_AWARDS`) and is trust-gated in the serializer (only staff
may author above `NONE`).

This is deliberately distinct from two same-shaped-but-different existing concepts,
named here to prevent future conflation:
- `combat.RiskLevel` (`world/combat/constants.py`) gates cast-pull *acknowledgement*
  UI (does the player need to confirm before casting) — nothing to do with stakes or
  reward.
- `StakesLevel` (`world/combat/models.py`) gates GM *access scope* (who may run a
  LOCAL vs. WORLD-scale scene) — nothing to do with risk/reward by outcome.

We considered a new dedicated "stakes wager" model instead of reusing `Beat.risk`,
but `Beat` is already the universal junction point every scene/encounter/mission
outcome routes through via `BeatCompletion` (#1716's anti-reinvention pass), and
`Beat.risk` already existed as an unwired placeholder anticipating exactly this
work. A separate model would have duplicated that seam for no benefit.

> Status: accepted · Source: #1716
