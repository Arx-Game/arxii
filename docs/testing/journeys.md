# Journeys

The hand-curated list of the stories the suite protects (#3657): what a player or
staff member is trying to do, the surfaces they do it on, the seam the journey
drives, and the test that asserts the outcome they see. The generated
`journey-inventory.md` next door lists every surface the registries know and the
tests that name it; this file is the pruned answer to "which of those matter".

Kept in tandem (CLAUDE.md, "Docs Are Directives"): a PR that adds or changes a
player-facing path adds or updates its row here, and the PR's Verification names
the row. A row whose covering test is `none` is a gap, not a deletion candidate.

**Seams.** `handler`: the line goes through the real command handler
(`JourneyCase.telnet`) or `dispatch_player_action` (`JourneyCase.web`).
`Cmd.func() by hand`: a journey written before the harness, which builds the
command and calls its body directly, skipping cmdset membership and `parse`;
tranche 1 and later move these onto the harness app by app. `services /
dispatch`: a cross-system path driven through service functions.

## Journeys the suite already carries

Seeded from the files under `src/integration_tests/` on 2026-10-15; prune and
rename as the maintainer and TehomCD see fit. Gaps are the `none` rows the
inventory reports for commands, API routes and frontend routes.

| Journey | Seam | Covering test |
|---|---|---|
| A greeting is heard by the speaker and the room; an unknown line is refused; a typed /switch reaches its command (the harness's own journeys). | handler | `src/integration_tests/test_harness_journeys.py` |
| Shaking off a charm: `breakfree` weakens the hold, a second try is refused, `rally` grants the bonus her next attempt carries; nothing to fight says so (#3657 pilot). | handler | `src/integration_tests/test_conditions_journeys.py` |
| Treating a fever in a scene: `treat` lists candidates, the offer waits, `accept` applies the poultice and the feed shows it; the sheet and the treat panel read the same rows (#3657 pilot). | handler + API | `src/integration_tests/test_conditions_journeys.py` |
| A GM applies, lists and removes a condition from the panel; a player who is not the GM is refused (#3657 pilot). | dispatch | `src/integration_tests/test_conditions_journeys.py` |
| End-to-end pipeline tests for the magical alteration system. | services / dispatch | `src/integration_tests/pipeline/test_alteration_pipeline.py` |
| End-to-end pipeline tests for the daily anima regen tick. | services / dispatch | `src/integration_tests/pipeline/test_anima_regen_pipeline.py` |
| End-to-end pipeline test for the Audere offer surface (#873). | services / dispatch | `src/integration_tests/pipeline/test_audere_offer_pipeline.py` |
| Telnet E2E: accept/decline surge and path crossing via CmdAccept/CmdDecline (#1344). | Cmd.func() by hand | `src/integration_tests/pipeline/test_audere_telnet_e2e.py` |
| E2E (#4098, #4076): Audere unlocks ultimates, and Soulfray death waits for the encounter's end. | Cmd.func() by hand | `src/integration_tests/pipeline/test_audere_ultimates_e2e.py` |
| Telnet E2E: battle Surrounded peril/rescue journey (#1733). | services / dispatch | `src/integration_tests/pipeline/test_battle_peril_rescue_e2e.py` |
| Telnet E2E: GM battle-staging journey (#2010). | Cmd.func() by hand | `src/integration_tests/pipeline/test_battle_staging_telnet_e2e.py` |
| Telnet E2E: battle declare subverbs — the coverage gap (#1328 Bucket C). | services / dispatch | `src/integration_tests/pipeline/test_battle_subverbs_telnet_e2e.py` |
| Telnet E2E: battle lifecycle journey (#1592). | Cmd.func() by hand | `src/integration_tests/pipeline/test_battle_telnet_e2e.py` |
| E2E journeys for player-postable bulletin boards (#3286). | Cmd.func() by hand | `src/integration_tests/pipeline/test_boards_telnet_e2e.py` |
| Telnet-driven CHALLENGE dispatch E2E (#1336): DispatchCommand → resolve_challenge. | Cmd.func() by hand | `src/integration_tests/pipeline/test_challenge_dispatch_telnet_e2e.py` |
| End-to-end pipeline tests for the challenge system. | services / dispatch | `src/integration_tests/pipeline/test_challenge_pipeline.py` |
| Telnet-driven combat cast E2E (#1330 L0): cast command → resolve_round → use_technique. | Cmd.func() by hand | `src/integration_tests/pipeline/test_combat_cast_telnet_e2e.py` |
| Telnet-driven clash commit E2E (#1451): clash → ClashContributionDeclaration → resolve_round. | Cmd.func() by hand | `src/integration_tests/pipeline/test_combat_clash_telnet_e2e.py` |
| Telnet E2E: comfort glance journey (#1514/#1522). | Cmd.func() by hand | `src/integration_tests/pipeline/test_comfort_telnet_e2e.py` |
| Telnet E2E: intimidate -> accept resolves the consent flow (#1337). | Cmd.func() by hand | `src/integration_tests/pipeline/test_consent_telnet_e2e.py` |
| End-to-end pipeline tests for the per-cast corruption accrual hook (PR #403). | services / dispatch | `src/integration_tests/pipeline/test_corruption_per_cast_pipeline.py` |
| Telnet E2E: covenant membership lifecycle journey (#1346). | Cmd.func() by hand | `src/integration_tests/pipeline/test_covenant_telnet_e2e.py` |
| Building to neighborhood to domain progression (#696), one journey per gap. | services / dispatch | `src/integration_tests/pipeline/test_domain_progression_journey_e2e.py` |
| End-to-end user-journey tests for the Ritual of the Durance (#1352). | services / dispatch | `src/integration_tests/pipeline/test_durance_e2e.py` |
| Telnet E2E for the Ritual of the Durance — witnessed + site-assisted flows (#1700). | Cmd.func() by hand | `src/integration_tests/pipeline/test_durance_telnet_e2e.py` |
| SQLite-safe per-family E2Es for the three DAMAGE_PRE_APPLY reactive defenses (#1584). | services / dispatch | `src/integration_tests/pipeline/test_effect_reactive_families.py` |
| Telnet-driven E2E: cast Summon Spirit → ally joins combat → damages enemy NPC (#1584 DoD). | Cmd.func() by hand | `src/integration_tests/pipeline/test_effect_summon_telnet_e2e.py` |
| Telnet E2E: endorsement journey — poses / endorse pose+entry+style (#1340). | Cmd.func() by hand | `src/integration_tests/pipeline/test_endorsement_journey_e2e.py` |
| Telnet journey: calling on a being's favor (#4333 slice 1, walkthrough B). | Cmd.func() by hand | `src/integration_tests/pipeline/test_favor_invocation_telnet_e2e.py` |
| Telnet E2E: gossip rumor mill journey (#1572). | Cmd.func() by hand | `src/integration_tests/pipeline/test_gossip_telnet_e2e.py` |
| Telnet E2E: the whole Rite of Honors arc, including posthumous (#3466 Task 11). | Cmd.func() by hand | `src/integration_tests/pipeline/test_honors_telnet_e2e.py` |
| Telnet journey: missions — resolve beat, abandon, group pick + vote (#1349). | Cmd.func() by hand | `src/integration_tests/pipeline/test_missions_telnet_e2e.py` |
| Telnet-driven non-combat cast E2E (#1332 / #1351): cast command → use_technique. | Cmd.func() by hand | `src/integration_tests/pipeline/test_noncombat_cast_telnet_e2e.py` |
| Telnet E2E: organization membership lifecycle journey (#1511). | Cmd.func() by hand | `src/integration_tests/pipeline/test_organization_telnet_e2e.py` |
| Telnet E2E: persona switching end-to-end journey (#1347). | Cmd.func() by hand | `src/integration_tests/pipeline/test_persona_telnet_e2e.py` |
| Telnet E2E: project contribution journey (#1574). | Cmd.func() by hand | `src/integration_tests/pipeline/test_project_telnet_e2e.py` |
| Cross-context pull outcome E2E (#1455): pull changes the ACTION OUTCOME, not just the ledger. | Cmd.func() by hand | `src/integration_tests/pipeline/test_pull_outcome_cross_context_e2e.py` |
| Telnet E2E: reaction/favorite journey — react favorite/emoji/kudos (#1341). | Cmd.func() by hand | `src/integration_tests/pipeline/test_reaction_journey_e2e.py` |
| Telnet E2E: multi-participant ritual session lifecycle via CmdRitual (#1345). | Cmd.func() by hand | `src/integration_tests/pipeline/test_ritual_session_telnet_e2e.py` |
| Telnet E2E for ritual performance (#1331). | Cmd.func() by hand | `src/integration_tests/pipeline/test_ritual_telnet_e2e.py` |
| Telnet E2E: signature technique motif journey (#1582). | Cmd.func() by hand | `src/integration_tests/pipeline/test_signature_telnet_e2e.py` |
| End-to-end pipeline tests for the Situation system. | services / dispatch | `src/integration_tests/pipeline/test_situation_pipeline.py` |
| End-to-end pipeline tests for technique-enhanced social actions. | services / dispatch | `src/integration_tests/pipeline/test_social_magic_pipeline.py` |
| End-to-end pipeline tests for social actions. | services / dispatch | `src/integration_tests/pipeline/test_social_pipeline.py` |
| Telnet-driven E2E: charm one bandit, parley the other -> social VICTORY (#4091). | Cmd.func() by hand | `src/integration_tests/pipeline/test_social_victory_e2e.py` |
| Telnet E2E: form a Soul Tether via the ritual session lifecycle (#1449). | Cmd.func() by hand | `src/integration_tests/pipeline/test_soul_tether_telnet_journey_e2e.py` |
| Telnet journey: the seeded T1-T7 tutorial chain, start to finish (#1035). | Cmd.func() by hand | `src/integration_tests/pipeline/test_tutorial_chain_e2e.py` |
| Telnet E2E: 5-step weave/imbue/pull journey proves the full ceremony/finisher lifecycle. | Cmd.func() by hand | `src/integration_tests/pipeline/test_weave_imbue_pull_journey_e2e.py` |
| Telnet E2E: weaving a RELATIONSHIP_TRACK thread + imbuing it (#2033, #3957). | Cmd.func() by hand | `src/integration_tests/pipeline/test_weave_relationship_track_e2e.py` |
| Telnet E2E: ``weave`` creates a Thread identically to the web path (#1337). | Cmd.func() by hand | `src/integration_tests/pipeline/test_weave_telnet_e2e.py` |
| E2E journey test: 3-PC party vs a factory-composed boss (#2095). | services / dispatch | `src/integration_tests/test_boss_fight_journey.py` |
| End-to-end integration test for the Covenant Rite fire path (#516). | services / dispatch | `src/integration_tests/test_covenant_rite_flow.py` |
| End-to-end integration test for Covenants Slice D. | services / dispatch | `src/integration_tests/test_covenant_slice_d_flow.py` |
| E2E integration test: craft facet → wear item → pull on a FACET thread. | services / dispatch | `src/integration_tests/test_crafting_facet_pull.py` |
| End-to-end pipeline test for the magic-story slice. | services / dispatch | `src/integration_tests/test_magic_story_pipeline.py` |
| Survivability journey tests for issue #3450. | services / dispatch | `src/integration_tests/test_survivability_journey.py` |

## Gaps to write first

From the inventory's `none` rows (2026-10-15): 61 commands, 79 API routes and 66
frontend routes are named by no test. The ledger (`tools/test_ledger.py`) sorts
each into a journey to write, a surface covered under another name, or a surface
to retire, app by app, starting with the tranche 1 pilot (`world.conditions`).
