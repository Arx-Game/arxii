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
- `StakesLevel` (`world/combat/constants.py`) gates GM *access scope* (who may run a
  LOCAL vs. WORLD-scale scene) — nothing to do with risk/reward by outcome.

We considered a new dedicated "stakes wager" model instead of reusing `Beat.risk`,
but `Beat` is already the universal junction point every scene/encounter/mission
outcome routes through via `BeatCompletion` (#1716's anti-reinvention pass), and
`Beat.risk` already existed as an unwired placeholder anticipating exactly this
work. A separate model would have duplicated that seam for no benefit.

> Status: accepted · Source: #1716

## Amended (2026-07-02, #1770)

`Beat.risk` remains the declared magnitude dial described above — GM-authored,
trust-gated, unchanged in meaning. It is now additionally: (1) validated for
readiness against the beat's stakes contract (`validate_stakes_readiness`,
`world/stories/services/stakes.py` — is the contract complete enough to run at
this declared tier), and (2) paid on through `StakeContractActivation.effective_risk`
rather than the raw declared value — the contract locks and prices itself for
the actual party at scene start (`activate_stakes_contract`), and Legend pays
on that effective figure (`effective_risk_for_beat`), not `Beat.risk` directly.
See ADR-0076 (chain rule), ADR-0077 (effective risk), and ADR-0078 (menu-first
calibration).
