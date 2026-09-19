# #3917 Bridge-evacuation acceptance evidence

- Reviewed revision: `55abb3368`
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

The acceptance fixture composes party, scaling, specialist choice, objective rows, causal evidence, and settlement. Focused sibling journeys remain the authority for mechanics that are intentionally not duplicated in this fixture.

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 real covenant party and named evacuation | PASS (composed) | `test_deterministic_bridge_evacuation_journey`; `test_objective_branches.py` | Four engaged roles, named Envoy Maris, failing-bridge clock, and authored stakes are composed. |
| A02 opponent level/soak and stakes activation | PASS (composed) | same test; `compute_party_profile`/`compute_opponent_stat_block`; `test_encounter_beat_wiring.py` | Preview values are copied into the armored boss; scaling and stake activation seams have focused coverage. |
| A03 specialist weakness choice | PASS (composed) | same test; `world.covenants.tests.test_weakness` | Selection is spent once and applies the authored condition. |
| A04 controller, hold, rampart, and break attribution | PASS (seam-supported) | `test_break_bar.py` suppression/hold/celebration journeys; rampart and sustained assertions in same test | Focused break-bar tests are the authority for suppression, hold, and named celebration contributors; the acceptance fixture carries the authored rampart/hold rows. |
| A05 guardian fallback and telegraph | PASS (seam-supported) | `test_reaction_economy.py::InterposeGuardianSelectionTests`; `test_interpose_damage_path.py`; `test_guardian_reactions.py` | Fallback, damage reduction, and guardian resource/Soulfray seams are covered by real repository journeys. |
| A06 ally support plus attack combo | PASS (seam-supported) | `test_combo_journey.py`; `test_focused_target_dispatch.py` | Combo resolution and ally-target dispatch are covered separately; the fixture records support/attack slots without claiming the opponent-target combo test proves ally preservation. |
| A07 objective branches and causal attribution | PASS (composed) | `test_objective_branches.py`; same test; `test_causal_recognition.py` | Boss/NPC outcomes, retreat, rescue/opening evidence, and recognition labels follow authored facts. |
| A08 Legend station and idempotency | PASS (seam-supported) | same test; `OrdinaryLegendCompletionTests.test_authored_award_is_reconciled_and_replay_is_idempotent` | Settlement attaches labels without changing value; ordinary completion replay is guarded. |
| A09 strain/resource behavior | PASS (seam-supported) | `test_non_clash_strain.py::StrainPushedNonClashCastTests`; `test_strain_declaration.py`; same test’s #3912 conversion assertions | The authored strain curve produces an 8-point power bonus for commitment 3 and effective cost 5; focused tests cover real cast audit/Soulfray rows. |
| A10 representative balance matrix | PASS (deterministic model sample) | `run_representative_balance_matrix`; `test_representative_balance_matrix_emits_numeric_rows` | 108 rows across sizes 2/4/6, levels 2/4/8, roles balanced/support-heavy/damage-heavy, anima 6/24, and coordinated/spam tactics. |

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

The matrix is a deterministic test-only model. It uses the production opponent scaling block, the #3912 strain conversion/cost functions, and explicit authored role/tactic factors. `soulfray_events` are numeric observed events in this model, not a probability claim about live Soulfray. `rescues` and `objective_outcomes` are scenario-model outputs, not live guardian or stake outcomes.

The separate repository engine smoke sample ran two seeded iterations for each tactic under a four-round cap: independent damage and 50% combo-rate coordination each produced 2/2 failures at four rounds with four synthetic participants. The simulator uses a basic-attack synthetic party and does not model the full covenant kits, authored objective routing, or real rescue choices. The result is pressure evidence only.

No browser run with a GM and deployed content was performed. The four required story-result paths remain covered by `test_objective_branches.py`, and focused guardian/combo/break/strain journeys are cited above rather than presented as one unverified mega-fixture. Soulfray incidence is recorded numerically for the deterministic model, but no claim is made that Soulfray is likely in live play.

## Unresolved findings

- No live/browser acceptance run was available in this checkout.
- The deterministic balance rows are model evidence, not live probability or deployed-content balance.
- The engine simulator does not model the full covenant role kits, guardian rescues, or authored objective outcomes; do not generalize its 4-round failures to live balance.
