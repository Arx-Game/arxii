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
| Joining and rising in an organization: `org invite`, the invitee is told and types `accept org`, then `org promote`, `org demote`, `org expel`; `org leave`; a rank-and-file member cannot promote the leader; an unknown organization is named back; the web invite is the same action (#3657 tranche 2). | handler + dispatch | `src/integration_tests/test_membership_and_consent_journeys.py` |
| Keeping hands off her body: an awake character cannot be carried; unconscious, her body-handling allowlist decides who may (`consent whitelist add/remove`), `carry_body` and `set_down_body` answer accordingly; the blacklist lines read back; an unknown category is named back (#3657 tranche 2). | handler + dispatch | `src/integration_tests/test_membership_and_consent_journeys.py` |
| Hosting a gathering: `event create`, `event invite` (the invitee is told, finds the invitation on `event show`, and types `event rsvp accept`), `schedule`, `start` (the scene opens), `complete` (it closes), `cancel`; a guest cannot run the host's event; only the invitee answers their invitation; a duplicate invite and an unknown event are named back; the web RSVP is the same action (#3657 tranche 2). | handler + dispatch | `src/integration_tests/test_gatherings_coffers_and_wares_journeys.py` |
| Rising and falling in a covenant: `covenant` lists the vow, `covenant rank` (refused below the managing rank), `kick`, `transfer` (command passes, the old commander drops to the base rank), `leave` (refused while it would strand the covenant without a manager), `engage`/`disengage`/`standdown`; `covenant deposit` from any member, `withdraw` by rank, the web deposit the same action; an outsider has no covenant to act in (#3657 tranche 2). | handler + dispatch | `src/integration_tests/test_gatherings_coffers_and_wares_journeys.py` |
| Keeping a vault: `vault status`, `vault access add <persona>` / `add/org <organization>` / `list` / `remove`; only the room's holder controls it; a room without one says so; an unknown persona is named back (#3657 tranche 2). | handler | `src/integration_tests/test_gatherings_coffers_and_wares_journeys.py` |
| Banking with the house (web only; no telnet verb): `vault_deposit` refused away from a bank and accepted at one, `vault_withdraw` by rank, `treasury_withdraw` by rank with the amount checked and the treasury's funds respected (#3657 tranche 2). | dispatch | `src/integration_tests/test_gatherings_coffers_and_wares_journeys.py` |
| Trading in the square: `market` browses the stalls, `market/buy` takes the coin and hands over the goods (refused broke, an unknown listing named back), `market/list` puts her own unfinished work on her bench, `market/buyware` moves it and the coin, `market/finish` names it once; no market in the parlour; `sell_materials` from anywhere (#3657 tranche 2). | handler + dispatch | `src/integration_tests/test_gatherings_coffers_and_wares_journeys.py` |
| Running a scene: `scene start <name>` opens it under that name with everyone present a co-owner, `scene` reads the status, a latecomer joins but cannot finish it, a co-owner's `scene finish` closes it; nothing to finish and an unknown subcommand show the usage; `scene gm <name>` names a present approved GM and refuses an absent character, one with no GM profile, and a non-owner; the web start and finish are the same actions (#3657 tranche 3). | handler + dispatch | `src/integration_tests/test_playing_a_scene_journeys.py` |
| Speaking in the room: `pose` and `emote` open with her name (semipose glue for `'s`), `emit` carries none, `whisper` reaches only its target (the whisperer sees her own line) and names a missing one back, `mutter` gives the room a fragment, the listener the whole line and the mutterer her echo, `places join` then `tt` speaks at the place and `places leave` leaves it; each line lands in the scene's feed under its mode; the web pose is the same action (#3657 tranche 3). | handler + dispatch | `src/integration_tests/test_playing_a_scene_journeys.py` |
| Rolling at the table: `check find` and bare `check` browse the catalog, `check <name> at <band>` narrates the roll to the room and the feed, an unknown check and an unknown band are named back; a Junior GM's `callcheck <name>=<a>,<b> at <band>` prompts each target with the two lines to type, `check answer` rolls once and `check decline` refuses once, a non-target has no call; a player without GM trust cannot call; `check propose` reaches staff; the web self check is the same action (#3657 tranche 3). | handler + dispatch | `src/integration_tests/test_playing_a_scene_journeys.py` |
| Reacting to a pose: `react favorite` and `react emoji` toggle on and off, `react kudos` opens the moment once per reactor and never for the poser, bare `react` lists the open moments; a wrong pose number, a poser with no poses, an unknown kind and an absent character are named back (#3657 tranche 3). | handler | `src/integration_tests/test_playing_a_scene_journeys.py` |
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
| Staff author a tradition's gift grants in the admin: a tradition with two gifts re-saves with only its description changed and keeps both grants and their techniques; the same gift on two rows is refused with the gift named and where its techniques go, and nothing is saved (#4380). | admin (test client) | `src/world/magic/tests/test_tradition_admin.py` |
| Starting with a keepsake: a distinction authored with an item grant puts that item in the finalized character's inventory once, reads "Comes with <item>" on the distinction list, and a distinction without one mints nothing (#4398). | services / finalize | `src/world/items/tests/test_distinction_item_grant.py` |

## Gaps to write first

### Gaps the journeys found (what a player meets; ruled or fixed on #3657)

| Gap | Found by | State |
|---|---|---|
| `org invite <person> in <org>` (and promote, demote, expel; favor and disfavor parse the remainder themselves and were fine) searched for a character named "invite <person>": the two-argument parser read the raw args, subverb included. Its unit tests set the parsed fields by hand and never saw it. | the organization journey | fixed in tranche 2 (`parse_two_args(text=...)`) |
| An invitee was never told an invitation was waiting; only typing `accept` revealed it. | the organization journey | fixed in tranche 2 (the invite action tells them) |
| Under an allowlist category (body handling, theft) `consent blacklist add` replies "X may no longer target you", but the gate consults only the whitelist in that mode, so a whitelisted X is still admitted (`test_blacklist_only_counts_under_all_but_blacklist` pins the rule). | the body-handling journey | open: a ruling on list precedence or on the reply's wording |
| On a deploy without the foundational capability rows authored, Unconscious does not stop anyone acting and a body can be neither protected nor carried (`can_act` degrades to True by design). | the body-handling journey | open: content, not code |
| An event invitee was never told an invitation was waiting; only reading `event show` revealed it (the org invite's gap again). | the gathering journey | fixed in tranche 2 (the invite action tells a persona invitee, with the two `event rsvp` lines) |
| `vault access add/org <organization>`, the documented form, fell to the usage line: `add/org` was read as one unknown subverb. The `/org` must be split off the subverb token; nothing had typed it. | the vault journey | fixed in tranche 2 (`CmdVault.func` splits the token) |
| The vault replies printed `str()` of a persona and of an organization: "Access granted to Hobb (Primary)." and "...The Lantern Guild (Arx)."; `vault status` named the founder the same way. | the vault journey | fixed in tranche 2 (the replies use `.name`) |
| The org vault and treasury actions (`vault_deposit`, `vault_withdraw`, `treasury_withdraw`, `deliver_collection`) have no telnet verb; the web client is their only face. The journey drives them through dispatch. | the banking journey | open: telnet is the secondary surface; whether it needs one is a product call |
| `scene start The Lantern Hour` opened a scene called "Scene at The Lantern": the command parsed the name and the action dropped it, on telnet and the web alike. | the scene journey | fixed in tranche 3 (`StartSceneAction` passes the name through) |
| A GM's `callcheck` told the caller and the web feed only; the narration carried no call id, so a telnet target was never prompted and had nothing to type into `check answer` (the invite gap a third time). | the table journey | fixed in tranche 3 (each target is told the call with the two lines to type; telnet bystanders get the narration on commit) |
| `whisper` and `mutter` answered the speaker with nothing on telnet: the listener heard the line and the room its fragment, the speaker saw an empty reply. | the room journey | fixed in tranche 3 (`You whisper to Hobb, "..."` / `You mutter to Hobb, "..."`, tagged as an interaction echo so the web drops the frame) |

From the inventory's `none` rows (2026-10-15): 61 commands, 79 API routes and 66
frontend routes are named by no test. The ledger (`tools/test_ledger.py`) sorts
each into a journey to write, a surface covered under another name, or a surface
to retire, app by app, starting with the tranche 1 pilot (`world.conditions`).
