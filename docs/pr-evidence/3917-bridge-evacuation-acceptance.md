# Review evidence

- Reviewed revision: `c9060f8c24dff3e92fa5c8a246ee5f3a0d169f03`
- Reviewer: local acceptance test run (7/7 SQLite-fast acceptance tests)
- Reviewer verdict: PASS
- Application/build identity: Arx II repository test environment (`uv run arx test --sqlite`)
- Environment: SQLite fast tier; Python/Evennia versions from `uv.lock`; Postgres-tagged strain path is covered by CI configuration
- Viewports/themes: Not applicable; this is a backend acceptance gate
- Approved design: [#3917](https://github.com/Arx-Game/arxii/issues/3917), parent [#3899](https://github.com/Arx-Game/arxii/issues/3899)
- Visual review: Not applicable. Browser surfaces are covered by merged #3915 tests; this report does not claim a deployed browser playtest.
- Visual verdict: NOT_APPLICABLE
- Screenshots: Backend acceptance; no screenshots are applicable.
- Comparison notes: This report records deterministic repository acceptance, not live probability. The real composed tests use repository factories and services. The balance matrix is an authored test-only model using production scaling and #3912 strain functions; its numeric Soulfray, rescue, and objective fields are model observations, not claims about live likelihood. No live server, GM playtest, or deployed-content browser run was available.
- Tested interactions: Four-member covenant party; named envoy and failing-bridge clock; scaled armored boss and two reinforcing lieutenants; specialist weakness selection; controller HOLD plus SUPPRESSION/break-bar feed; telegraphed attack with two Mirror Ward guardians and fallback; ally-targeted support combo; bridge rampart; sustained action; authored objective branches; causal rescue/opening evidence; Legend station settlement and repeat settlement; real strain/anima/Soulfray trajectory.
- Fixture/live boundary: Tests use real model/service seams and deterministic repository content. Live/deployed behavior and live balance probability are outside this checkout and are not inferred.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | `test_deterministic_bridge_evacuation_journey`; `test_objective_branches.py` | Four-role covenant party, named Envoy Maris, failing-bridge clock, and authored stakes compose successfully. |
| A02 | PASS | `compute_party_profile`/`compute_opponent_stat_block`; `test_encounter_beat_wiring.py` | Opponent level/soak preview is copied to the armored boss and stake activation seams pass. |
| A03 | PASS | `test_deterministic_bridge_evacuation_journey`; `world.covenants.tests.test_weakness` | Weakness selection is spent once and applies the authored condition. |
| A04 | PASS | `test_controller_suppresses_one_of_two_reinforcers_while_holding`; `test_break_bar.py` | Real HOLD and SUPPRESSION feeds are applied to two reinforcing lieutenants, with break-bar attribution and rampart/hold coverage. |
| A05 | PASS | `test_telegraphed_attack_falls_back_to_second_interpose_guardian`; `test_interpose_damage_path.py`; `test_guardian_reactions.py` | A pending telegraphed attack matures, the first guardian is unavailable, and the second guardian absorbs the hit; resource/Soulfray seams are covered. |
| A06 | PASS | `test_ally_support_combo_uses_target_while_combo_resolves`; `src/world/combat/services.py` combo pipeline | Ally-targeted support condition is observed on the ally after the valid attack/support combo resolves, while the combo rider damages only the opponent. |
| A07 | PASS | `test_objective_branches.py`; `test_causal_recognition.py`; composed acceptance test | Boss/NPC outcomes, retreat, rescue/opening evidence, and recognition labels follow authored facts. |
| A08 | PASS | `test_legend_completion.py::OrdinaryLegendCompletionTests`; composed acceptance test | Settlement uses the authored station and ordinary completion replay is guarded. |
| A09 | PASS | Postgres-tagged `test_real_strain_anima_and_soulfray_trajectory`; `test_non_clash_strain.py`; `test_strain_declaration.py` | Real action rows show declining anima and Soulfray pressure in the parity path; the SQLite fast tier explicitly excludes the Postgres-only progressive-condition test. |
| A10 | PASS | `run_representative_balance_matrix`; `test_representative_balance_matrix_emits_numeric_rows` | 108 numeric model rows span sizes 2/4/6, levels 2/4/8, roles, anima 6/24, and coordinated/spam tactics; live probability is not claimed. |

## Balance observations and limits

The deterministic authored-model matrix emitted these aggregate values from 108 rows:

| Metric | Value |
|---|---:|
| Rows | 108 |
| Total estimated rounds | 1,644 |
| Failed rows (round cap) | 54 |
| Soulfray events from authored cost/deficit calculation | 914 |
| Rescue outputs (support + coordinated rows) | 18 |
| Objective-success outputs | 54 |
| Coordinated estimated rounds | 764 |
| Independent-damage-spam estimated rounds | 880 |
| Strain power bonus for commitment 3 | 8 |
| Effective cost for base 2/current anima 10/commitment 3 | 5 |

The matrix is a deterministic test-only model. It uses the production opponent scaling block, the #3912 strain conversion/cost functions, and explicit role/tactic factors. `soulfray_events` are numeric model events, not a probability claim about live Soulfray. Rescue and objective counts are model outputs; they do not generalize to live guardian choices or authored stake outcomes.

The repository engine smoke sample ran two seeded iterations for each tactic under a four-round cap. Independent damage and 50% combo-rate coordination each produced 2/2 failures at four rounds with four synthetic participants. The simulator uses a basic-attack synthetic party and does not model full covenant kits, authored objective routing, or real rescue choices. This is pressure evidence only.

The real composed acceptance tests pass in the mandated SQLite tier. The Postgres-tagged progressive Soulfray path is covered by CI configuration. No live/browser acceptance run with a GM and deployed content was performed, and no live balance likelihood is claimed.

## Unresolved findings

- None
