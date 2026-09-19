# #3917 Bridge-evacuation acceptance evidence

- Reviewed revision: `fa9b3f067`
- Reviewer: local acceptance test run
- Reviewer verdict: PASS for the deterministic model/service composition below; NOT PASS for live browser playtest or Soulfray probability
- Application/build identity: Arx II repository test environment (`uv run arx test --sqlite`)
- Environment: SQLite fast tier; Python/Evennia versions from `uv.lock`; no browser run
- Viewports/themes: Not applicable; this gate is backend/model acceptance
- Approved design: [#3917](https://github.com/Arx-Game/arxii/issues/3917), parent [#3899](https://github.com/Arx-Game/arxii/issues/3899)
- Visual review: Not applicable. Browser surfaces are covered by the merged #3915 tests; this report does not claim a browser playtest.
- Visual verdict: NOT_APPLICABLE
- Screenshots: None (backend acceptance gate)
- Tested interactions: deterministic four-member covenant party; named envoy and failing-bridge clock; scaled armored boss plus lieutenant; specialist weakness selection; support/attack combo scanner; bridge rampart; sustained action; authored objective branches; causal rescue/opening evidence; Legend station settlement and repeat settlement.
- Fixture/live boundary: Tests use repository factories and real service/model seams. No deployed server or live content was exercised.
- Overall outcome: PASS for the deterministic composition and scaling preview. Limitations and blockers are recorded below.

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 real covenant party and named evacuation | PASS | `test_deterministic_bridge_evacuation_journey` | Four engaged covenant roles, named Envoy Maris, authored failing-bridge clock/stakes. |
| A02 opponent level/soak and stakes activation | PASS | same test; `compute_party_profile`/`compute_opponent_stat_block` | Preview values are copied into armored boss; lieutenant is separately authored. |
| A03 specialist weakness choice | PASS | same test; `maybe_create_weakness_selection` + `resolve_weakness_selection` | Selection is spent once and applies the authored condition. |
| A04 cooperation surfaces | PASS | same test; `detect_available_combos`, rampart, `SustainedAction` | Support/attack slots, rampart integrity, and remaining commitment are persisted. Focused combo resolution is covered by `test_combo_journey.py`. |
| A05 objective-first results | PASS | `test_objective_branches.py` and same test | Existing tests cover boss/NPC outcomes, rescue-with-lost-objective, and secured-then-retreat. |
| A06 causal attribution and valid settlement | PASS | same test; `record_envoy_rescue`, `record_created_opening`, settlement adapter | Recognition labels attach to deeds without changing their value; settlement uses the authored station. |
| A07 idempotent settlement | PASS | same test; repeated `settle_legend_for_activation` | Repeat call does not mint duplicate entries. |
| A08 representative scaling matrix | PASS | `test_representative_balance_matrix_is_level_and_size_deterministic` | Party sizes 2/4/6 and average levels 2/4.25/8 produce deterministic health/soak/level previews. |
| A09 resource trajectories, failures, rescues, Soulfray incidence, coordinated-vs-spam comparison | NOT MEASURED | No claim | Existing simulator does not model the real covenant kits, rescue tactics, or Soulfray incidence. A live representative run is required before drawing balance conclusions. |

## Balance observations and limits

The acceptance matrix verifies the authored size/level scaling formula and records the Soulfray metric as `None`, rather than treating danger or anima cost as evidence of Soulfray. It is not a win-rate or fight-length sample. It does not claim Soulfray is likely.

The deterministic gate composes database rows and focused service seams. It does not replace a browser run with a GM and actual deployed content. The four story-result paths remain represented by the objective journey tests; this gate does not pretend one successful fixture proves every authored branch.

The merged dependency wave contains the #3912 overexertion specification, but no production ordinary-cast strain-power implementation. This report therefore does not claim the approved immediate-benefit tradeoff is live. A follow-up implementation and measurement are required before closing that criterion as a measured balance result.

## Unresolved findings

- No live/browser acceptance run was available in this checkout.
- Soulfray incidence and coordinated-vs-independent-damage balance remain unmeasured.
- #3912 approved overexertion behavior is spec-only on the reviewed base; do not infer an immediate strain benefit.
