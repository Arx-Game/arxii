# #3917 Bridge-evacuation acceptance evidence

- Reviewed revision: `f4a1ec73dad34e2823fa6f1ea9cf97d01df97e85`
- Reviewer: local acceptance test run
- Reviewer verdict: PASS for the deterministic model/service composition below; NOT PASS for live browser playtest or Soulfray probability
- Application/build identity: Arx II repository test environment (`uv run arx test --sqlite`)
- Full-suite verification: `just test-fast world.combat` passed 2,306 tests in 296.140s on the reviewed revision.
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
| A07 idempotent settlement | PASS | `src/world/stories/tests/test_legend_completion.py::OrdinaryLegendCompletionTests` | Ordinary completion replay is guarded; direct adapter remains a pure operation. |
| A08 representative scaling matrix | PASS | `test_representative_balance_matrix_is_level_and_size_deterministic` | Party sizes 2/4/6 and average levels 2/4.25/8 produce deterministic health/soak/level previews. |
| A09 engine pressure sample | PASS (limited) | `test_engine_balance_sample_records_failure_and_duration_metrics` | Seeded simulator sample: independent and 50% combo-rate tactics each ran 2 iterations, 4 rounds, and 2 failures; 4 participants. |
| A10 resource trajectories, failures, rescues, Soulfray incidence, coordinated-vs-spam comparison | NOT MEASURED | No claim | Existing simulator does not model the real covenant kits, rescue tactics, authored objective outcomes, or Soulfray incidence. A live representative run is required before drawing those conclusions. |

## Balance observations and limits

The acceptance matrix verifies the authored size/level scaling formula and records the Soulfray metric as `None`, rather than treating danger or anima cost as evidence of Soulfray. It is not a win-rate or fight-length sample. It does not claim Soulfray is likely.

The deterministic gate composes database rows and focused service seams. The engine sample uses the repository simulator with a synthetic basic-attack party and a four-round cap: independent damage and a 50% combo-rate comparison each ran 2/2 failures at 4 rounds. This is a pressure smoke sample, not a claim about real covenant kits. It does not replace a browser run with a GM and actual deployed content. The four story-result paths remain represented by the objective journey tests; this gate does not pretend one successful fixture proves every authored branch.

The merged dependency wave includes the #3912 ordinary-cast strain-power implementation. This gate does not claim the measured engine sample exercises every strain branch; focused #3912 tests cover that seam.

## Unresolved findings

- No live/browser acceptance run was available in this checkout.
- Soulfray incidence and coordinated-vs-independent-damage balance remain unmeasured.
- The engine simulator does not model the full covenant role kits, guardian rescues, authored objective outcomes, or ordinary-cast Soulfray pressure; do not generalize its 4-round failures to live balance.
