# Tooling

**Status:** in-progress
**Depends on:** Areas, Items, Combat, Stories (for GM tools)

## Built (2026-10-15, #3657 tranche 0 — the three-layer test suite's tools)

The suite audit's first tranche builds the tools and changes the rules, and removes
nothing. `integration_tests.harness.JourneyCase` is the one journey harness (a typed
line through the real command handler, a web action through `dispatch_player_action`,
a signed-in REST client, `assertTold` for what each character was told);
`integration_tests/fuzz/` is the Hypothesis layer with `ci` and `dev` profiles;
`tools/journey_inventory.py` generates `docs/testing/journey-inventory.md` from the
action, command, router and frontend-route registries with the tests naming each
surface (555 actions, 269 commands, 537 API routes, 131 routes on 2026-10-15), and
`docs/testing/journeys.md` is the curated list; `tools/test_ledger.py` grades an
app's test modules J/F/X/U-keep/R as the first pass of its ledger;
`just coverage-journeys` and the weekly `journey-coverage` workflow report what no
journey reaches, as design input, never a gate. `django_notes.md`'s per-layer test
shape is replaced by the three layers; `test-layer-reviewer` reads every PR's tests.
ADR-3657. Tranche 1 (2026-10-15): the runner empties the identity map after every test,
forced (#4363); the `world.conditions` pilot adds eleven journeys
(`integration_tests/test_conditions_journeys.py`: break free, rally, treat and accept,
the sheet and treat-panel endpoints, the GM panel), the confirmed ledger
(`docs/testing/ledger/conditions.csv`, `confirmed` and `note` columns beside the
tool's), and the first removals: 34 tests of 576, all of them tests of Django's own
behaviour or a mock. Next by shard weight: actions, scenes, stories; then magic and
combat with TehomCD confirming their ledgers. Tranche 2 (actions) began 2026-10-15 with
journeys for organizations, the consent lists and carrying a body
(`integration_tests/test_membership_and_consent_journeys.py`); the first two found
`org invite` broken on telnet and invitees never told, both fixed in place, and the
journeys list now carries a "Gaps the journeys found" table. Its second step
(2026-10-16) adds journeys for hosting a gathering, rising and falling in a covenant,
keeping a vault, banking with the house and trading in the market square
(`integration_tests/test_gatherings_coffers_and_wares_journeys.py`); they found an
event invitee never told, the documented `vault access add/org` form unreachable, and
vault replies printing a persona's type and an organization's realm, all fixed in
place. Tranche 3 (scenes) began 2026-10-16 with journeys for running a scene,
speaking in the room, rolling at the table and reacting to a pose
(`integration_tests/test_playing_a_scene_journeys.py`); they found `scene start
<name>` dropping its name, a GM's `callcheck` never prompting a telnet target, and
`whisper` and `mutter` answering their speaker with nothing, all fixed in place. Its
second step (2026-10-17) adds journeys for wearing another face, keeping someone out,
turning down the noise, taking the floor and narrating in private
(`integration_tests/test_faces_silences_and_the_floor_journeys.py`); they found `page`
delivering to a player who had blocked the sender when the line came from a character
with no session, and `pemit` answering its narrator with nothing, both fixed in place.
Tranche 4 (stories) began 2026-10-17 with journeys for running a story (the player's
listing and beats while her Lead GM marks, resolves, promotes and completes), calling the
canon (impact, review-status, surrender) and opening a scene room
(`integration_tests/test_running_a_story_journeys.py`); they found `leaveroom` in an
ordinary room answering "no invitation", fixed in place. Its second step (2026-10-17)
adds journeys for protecting what a story needs and clearing another GM to touch it,
crossing two stories at one event, pacing a beat by its clock and a player's treasured
sign-off (`integration_tests/test_sharing_a_story_journeys.py`); they found a scene
started where anyone had already spoken going unseen (the room's cached "no scene" was
never cleared by `scene start` or an event start), fixed in place. Its third step
(2026-10-17) is the first removal of the stories tranche: every line the six hand-built
story command test modules typed by calling `Cmd.func()` (`test_story_command`,
`test_story_custody_command`, `test_story_clock_command`, `test_story_room_commands`,
`test_story_gm_lifecycle_e2e`, `test_canon_review_command`, 135 tests) is now typed
through the handler in the story journeys, which gained every subject kind, the
clearance fan-out, the staff canon queue (`canonreview`), the hidden beat, title
resolution and the twin-named scene rooms on the way; the event journey speaks before
`event start` to pin the cache fix on that path too. The ledger is
`docs/testing/ledger/commands.csv` (those six rows confirmed `R`; the rest still the
tool's proposal). Tranche 5 (2026-10-17) does the same for the scenes and gatherings
hand-built command tests: `test_scene_command`, `test_scene_round_journey_e2e`,
`test_react_command`, `test_places`, `test_event_command_journey`, `test_persona_command`
and `test_blocking_commands` (76 tests) are removed, `test_cmd_page` keeps only its web
form descriptor, and `test_scene_gm_enrollment_e2e` is held for the combat ledger; the
journeys gained the round pacing (mode, knobs, interpose, succor, the force-resolve
guard), the entrance reaction, event grandeur, persona name collisions and the page
rules (an unplayed character, the roster, `hide` and the allow-list both ways). The page
journey found a hidden player's allow-list never letting anyone through (the check
compared the puppeting character's pk against account ids), and the pacing journey
found a strict round that had seen one `scene interpose` or `scene succor` unable to
leave STRICT again (the guard counted the leftover rows the resolve sweep keeps by
design); both fixed in place. Tranche 6 (2026-10-18) opens the actions ledger
(`docs/testing/ledger/actions.csv`, 172 modules, the tool's proposal for every row) with the
gatherings, coffers and wares group: `test_covenant_actions`, `test_org_vault_actions`,
`test_market_sell_materials`, `test_events`, `test_currency_actions`, `test_trade_actions`,
`test_remove_condition_effect` (mock-pinned) and `test_treat_condition_action` (69 tests)
are removed after each test was read against the journeys; the gathering journeys gained
staff and the scene's GM running an event, a guild's invitation, a dormant banner, an equal's
kick, the web treasury verbs naming the covenant only, the bank's refusals and the collector's
`deliver_collection`, and the material sale's refusals; two new journey classes type the
coins (`withdraw coins`, `deposit`, `give <amount> to`, `steal`, `secure`) and the web trade,
and a third talks a berserker down with `restore_sense` so the remove-condition effect has a
journey instead of a mock. The coins journey found `secure` raising after it set the policy
(the room line was built from an item state with no key; the unit test had patched
`msg_contents`) and a bare `withdraw coins` falling to the container usage; both fixed in
place. Its second step (2026-10-18) rules the scenes group of the actions ledger:
`test_scene_actions`, `test_round_mode_action`, `test_places_actions` and
`test_scene_reactions` are removed, `test_round_actions` keeps only the row shapes no
player path stages (a pass over leftover immediate rows, a DANGER round) and
`test_scene_checks_actions` only the SENIOR `gm check` regression for the GM adjudication
group; the scene journeys gained the round's web verbs from an empty room through join,
pass, leave and end, a round ordered with a mode (owner, non-owner, staff defaults), a knob
on its own, a staged battle's room opening its own scene, staff granting GM, pacing and
finishing any scene, every verb typed from nowhere, the check band and invention firewalls,
a synthesized check for its owner alone, a call outside a scene, decline-then-answer, a
proposal's required parts, a roster-less reactor and a bare `places join`.
`test_scene_resolution` is held (its service has no production caller found; the function's
removal is its own ruling) and `test_round_context` is held for the combat ledger. Its third
step (2026-10-18) rules the stories group: `test_situations` and
`test_group_story_request_actions` are removed, `test_gm_story_actions` keeps only the
patched-boundary refusal and the party-sheet helper, `test_gm_story_clock` only the combat
leg, `test_story_builder_actions` stays (web-only canvas authoring whose tests already call
the dispatch seam with the canvas's own kwargs) and `test_gm_story_run_beat` is held for the
combat ledger; a new journey module stages a situation and a single challenge
(`integration_tests/test_staging_a_situation_journeys.py`), the story journeys gained staff
on every verb, the Assistant GM's mark and credit, a GM's own arc earning nothing, the plot
gate, routing by transition order, a story nobody is in, a group story advancing one table,
the clock's reuse and the one-beat-per-scene rule, and `declare_stakes`; the covenant journey
gained `covenant request-gm`, the GM queue, `gm claim` and `covenant withdraw-gm-request`.
Its fourth step (2026-10-18) rules the consent group: `test_consent_preferences` is removed,
`test_social_consent_enforcement` keeps only the no-actor branches and the batched sweep's
query budget, `test_consent_rivals_sweep` only the batched sweep, and
`test_block_target_exclusion` stays (the target picker's predicate over faces); the
body-handling journey gained `consent category` for every mode tried against the carry
(everyone, all-but-blacklist, friends with the owner's friendship counting and the actor's
not, rivals through `relationship declare` from both sides, the default), `consent off`/`on`,
and the web's tenure ownership, boolean and ended-tenure refusals. Tranche 7 (2026-10-18)
rules the GM adjudication group: `test_gm_adjudication_actions` (85 tests) and the held
`gm check` regression in `test_scene_checks_actions` are removed, and the hand-built
`commands/tests/test_gm_ops_adjudication` keeps only `gm dramatic` for the combat ledger; a
new journey module (`integration_tests/test_refereeing_the_table_journeys.py`) types `gm
check` (find, every band read back as a word, an edge or a setback with its reason, the
usage, the trust gates, the web's target by id and its invention-shaped kwargs ignored), `gm
award` (XP with the GM on the ledger, development, a Golden Hare and its deed kept to the
note's width, a stat signed with the granting tenure, a technique from a held gift, the usage,
the trust and seat gates, a staffer with no tenure) and `gm condition` (the note narrated to
the room and kept on the instance, a hidden condition's note to the bearer alone, the usage
and bounds, list and remove with a reason, a staffer standing nowhere, a prop by id, an
understanding condition opening an ear). No production code changed. Tranche 8 (2026-10-19)
rules the items group: `test_items_actions` (38 tests, every one a `.run()` or a
prerequisite's `is_met` by hand) and the hand-built `commands/tests/test_use_command` are
removed, and the nine typed-menu modules (`test_typed_*`, `test_staged_*`,
`test_target_menu_api`, `test_menu_item_resolution`, #4184) are re-graded J and kept: they
drive the dispatch and REST seams with the menu's own wire and are the contract layer for
the right-click menu, not a second copy of a player path. A new journey module
(`integration_tests/test_handling_your_things_journeys.py`) types `get`/`take`, `drop`,
`inventory`, `wear`/`remove`/`undress`, `put ... in`, `withdraw ... from` and `get ... from`,
`use`/`apply ... on`, `give ... to` and `grant_item`, with the web dispatches by row
(`menu_target`), and reads back the rows, the room's lines and the bearer's conditions. It
found one thing to fix in place: every mistyped name came back twice on telnet ("Could not
find 'x'." from Evennia's own search and again from the command's error) and once on the
web, which cannot place Evennia's untyped line; `ArxCommand.search_or_raise` now searches
quietly and raises once, wording several matches as Evennia's numbered list in the
command's own typed error. The hand-built command tests that mock `caller.search` return a
list now, as the quiet search does. The parity schema was also stale behind #4463
(`just build-test-schema`). Tranche 9 (2026-10-19) rules the first commands group: the
hand-built `test_dispatchers` (46 tests), `test_friends_commands`, `test_covenant_command`,
`test_gm_ops_command` and `test_gm_ops_catalog` are removed, and `test_consent_commands`
keeps only its action-key registry and pull-token parsing classes. Their lines moved onto
the harness: `look <name>'s <thing>`, `look <thing> in <bag>`, hidden bearers and
`wear outfit` (`LookingAtThings`, `DressingAndPacking`), `home`/`home/set`/`recall`
(`test_coming_home_journeys.py`), `friend`/`friends`/`unfriend`/`friend/all`
(`KeepingAFriendsList`), `intimidate`/`accept`/`deny`/`accept/<band>`/`deny/blacklist`
(`PressingSomeoneInAScene`), the covenant usages and `gm dashboard`/`gm claim`/`gmidle` in
the gathering journey, and `gm suggest` in the staging journey. One fix in place: a plain
`look <absent name>` still answered "Could not find" twice (the plain-look branch ran
Evennia's loud search before raising its own error; the tranche 8 fix had reached every
other verb), and `CmdLook` now resolves a plain look through `search_or_raise`. The
journeys recorded two consent gaps on #3657 (the blacklist bar holds only on the web
picker, and a telnet target is never told a request opened), and the parity schema was
stale again behind #4471. Tranche 10 (2026-10-19) rules the second commands group, the
hand-built modules whose verbs a journey already named: `test_setsituation_command`,
`test_grant_item`, `test_cmd_presence`, `test_social_consent_e2e`, `test_outfit` (every
action's `run` mocked) and `test_relationships_command` (29 tests) are removed. Their lines
moved onto the harness: the `outfit` namespace in full (`KeepingAWardrobe`, in the handling
journey) and the `relationship` namespace in full (a new
`integration_tests/test_keeping_ties_journeys.py`), `afk` and the unrostered `hide` in the
faces journey, `setsituation find` by kind and bare in the staging journey, a plain object
handed to `grant_item` in the handling journey. Three fixes in place, all the loud-search
shape: `CmdRelationship` resolved its target and its `show` argument loudly (two "Could not
find" lines), `CmdOutfit` searched its wardrobe and item dbrefs loudly ("Could not find
'#id'." before its own refusal), and `GrantItemAction` searched loudly and answered nothing
of its own, so the web got only Evennia's bare line. Each now searches quietly and the
journeys assert the one typed line. Tranche 11 (2026-10-19) rules the GM desk group:
`test_gm_prompt_commands` (15, with `get_active_scene` and `narrate_privately` patched),
`test_gmtrust_command` (17, every caller a `MagicMock`), `test_gmtable_command` (14),
`test_moment_command` (22) and `test_gemit_command` (5) are removed. A new journey module,
`integration_tests/test_minding_the_gm_desk_journeys.py`, types `gmtable` (create, list,
members, invite, kick, archive, transfer, every gate), `gmtrust` (show, evidence, promote with
the level-change row), `gm prompts` / `gm prompt send|dismiss|done` with `emit/prompt` and
`pemit/prompt` against the real scene and the real on-commit release, `moment`
(suggestions, confirm, dismiss, tag, tag list, the mute, the cap) and `gemit` behind the real
`perm(Admin)` lock. Two fixes in place: a prompt's authored room line released on close
reached the web feed only (`broadcast_scene_emit`'s scene-scoped push sent no text line;
a telnet onlooker heard nothing, the `callcheck` shape again), and `moment` sent every refusal
as a bare untyped line the web cannot place (its `func` override skipped the base command's
typed `error` and structured frame) while `moment tag <absent name>` sent only Evennia's bare
line (the loud-search shape); the override now refuses the way the base does and the search
is quiet. Tranche 12 (2026-10-19) rules the progression and journal groups:
`test_progression_commands` (36, every dispatch a mock), `test_journals_goals_journey_e2e`
(16, `Cmd.func()` by hand), `test_account_info_command` (11), `test_tidings_command` (10),
`test_progression_rewards_commands` (4), `test_progression_rewards_e2e` (1),
`test_gift_learning_command` (10) and `test_training_command` (9) are removed. A new journey
module, `integration_tests/test_earning_your_keep_journeys.py`, types `journal` (write, list,
edit, respond with the retort consent, disposition), `goal` (add, set, log, the weekly gate and
the cap), `kudos`, `nominate` (a real pose in a real scene), `randomscene` (a claim with real
scene evidence, a reroll), `pathintent`, `rest`, `training` (the shared weekly budget, another
player's row), `progression` (an unlock bought with real XP, the breakthrough refusals),
`learn` and `train` (a gift unlocked, a meter opened from Hobb's offer, the unconfigured
training check named), `tidings` (her circles, a mask, another face, the square's board and
crier) and `account` / `roster` through the puppet. Three fixes in place: Evennia's staff
`@accounts` carried an `@account` alias, and a cmdset merge treats a shared alias as the same
command, so the player's `account` (and with it `account email`, the telnet path to a verified
email) was "not available" to anyone puppeting a character; a kudos claim too small to pay
anything wrote the claim and rolled it back, which left the idmapper-shared balance short
until the cache flushed (the check now runs before any write); and an unknown id on
`training` or `progression unlock` answered with the ORM's own "matching query does not
exist" line (each is now a sentence of its own). Tranche 13 (2026-10-19) rules the
buildings group: `test_door` (7, every action's `run` mocked), `test_builder_stock_commands`
(18), `test_desc_command` (10), `test_portals_command` (4) and `test_functionary_command` (6,
a `MagicMock` caller) are removed. A new journey module,
`integration_tests/test_keeping_a_house_journeys.py`, types `lock`/`unlock` (a tenant and a
guest at a real gate, the guest kept out and let through), `pick` and `break` (the authored
Lockpicking check, the room lines, the deeds), `desc`, `desc/edit` through the real line
editor, `@set <obj>/desc`, `@name` on a room, a character, an item, a companion and an object,
`@sethome` with and without a tenancy, a player with no builder verb at all and Evennia's
retired `setdesc`/`@spawn`/`@copy`, `portal/install` and `portal/dissolve` with the purse,
the standing and the kinds, and `functionary` place/list/remove. One fix in place:
`functionary place|remove` asked `caller.check_permstring("Builder")`, which on a character
reads the character's own permissions, so a staff account puppeting an ordinary character
was refused; it now asks the account, the way a `perm()` lock does.

Tranche 14 moved the town onto the harness: `hire`, `game`, `craft`, `network`, `identify`
and `travel`. The seven hand-built modules (`test_hire_command`, `test_tavern_games`,
`test_crafting`, `test_network_command`, `test_identification`, `test_travel_command` and
`test_fatigue_command`, whose `rest` tranche 12 had already typed) are removed; the new
`integration_tests/test_working_the_town_journeys.py` types each verb through the handler
against real rows: a mission really issued by a barkeep, a hand of dice at a real Place
with real purses, the Enchanting recipes authored at a real bench, a task dispatched and
a listener posted and collected from, a mask rolled against with the seeded check, a
walk over real public rooms with the scheduler stood in for. Five fixes in place, every
one a line a player met: `hire` read `caller.session`, which a character does not have,
so every `hire` typed in play raised; `hire <role> as <npc>` could never find a persona
and greeted a named one by the role's name; bare `game` away from a Place and an ante a
purse could not cover both raised past the command; the craft verbs said nothing on
success or failure; agent names read "Wren (Established)" wherever `str(persona)` was
used, the tasking API included.

Tranche 15 moved the GM grants and staging group, the mission party and the house's domains
onto the harness: `setstage`, `grant_distinction`, `mission invite|accept|decline`,
`+grievance` and `domain`. The five hand-built modules (`test_setstage_command`,
`test_grant_distinction`, `test_mission_invite_command`, `test_grievance_command` and
`test_domain_command`) are removed; the new
`integration_tests/test_granting_and_staging_journeys.py` types each verb through the
handler against real rows: a position blueprint cloned into the room and restaged, a
distinction awarded with the character's own XP, a mission contract's invitation accepted
and declined, a learned secret answered with a real conflict swing, a house's holdings,
steward, projects and stature. Five fixes in place: `setstage` staged the room and said
nothing; `grant_distinction`, `mission invite` and `domain appoint` said Evennia's bare
"Could not find" and then nothing of their own; `grant_distinction` at a distinction's
highest rank charged XP and reported an award for a no-op; `domain offices` named the
house through `str(org)`; and `domain`'s usage line lost its "holding", "improve" and
"stature" to Evennia's colour codes on telnet (a bare `|h`, `|i` or `|s`), which the
tracing probe's stripped transcript showed as "officesoldingmprove".

## Built (2026-09-30, #4064 — the reviewed delete, and admin pages for domains and fealty)

Deleting an organization other rows protect stopped at Django's "cannot delete" page,
and `Domain` and `FealtyEdge` had no admin page to clear the block from.
`ReviewedDeleteMixin` (`web/admin/reviewed_delete.py`, on `OrganizationAdmin`) shows a
superuser the plan instead: the cascade, then every blocking row with a detach-or-delete
choice (detach only where the link is nullable and the row still validates), nothing
preselected, the name typed back, one transaction. A row added mid-review refuses the
confirm. `DomainAdmin` (owner autocomplete, holdings inline) and `FealtyEdgeAdmin`
(delete through `release_fealty`, so the tithe goes with the oath) are registered; the
society page's organization rows still refuse a ticked blocked delete, and the refusal
ends in a link to the review. ADR-0326.

## Built (2026-08-31, #3477 Tasks 3–7 — the Atlas and the documents)

The grid-first canvas front door is replaced by the two-surface builder the
spec ratified (`frontend/src/world-builder/atlas/` + `document/`; `AtlasPage`
is the routed page). **Atlas** (navigation): warrant-scoped index rail with
pins/recents (`IndexRail`, `useAtlasState`), folio ancestry crumb, `AreaPage`
ledger rows + the `Lattice` — one snapped grid at every altitude with
plot-then-realize planning squares, right-click carving/voids, edge growth,
drag-to-swap arranging (`staff_move_room`'s first dispatch), placing an unplaced
room by naming it on a planned square (rooms mode's `AddDialog` matches the
area's rooms with no grid position and dispatches `staff_place_room` instead of
a dig; 2026-09-09, the Wanderer's Rest could not be placed before this), the same
for an unplaced child area (areas mode matches child areas with no position and
dispatches `edit_area` with the square, #4084; areas made in the admin, or moved
under a parent by an insert, had no tile and no way to get one), a map view
(2026-09-09, the reviewer building Arx: the wheel zooms around the cursor between 25%
and 150%, dragging the ground pans, − / + / fit in the tools row, zoom and pan
remembered per area, kind labels hidden zoomed out; pressing a tile is still the swap
drag), the ladder made legible (2026-09-09, the reviewer expanded Arx in the rail
and saw nothing: areas mode's `AddDialog` is titled by the level a square becomes,
"New ward" / "Ward name"; a hint under the lattice names that level and the
city › ward › neighborhood › building › rooms ladder; the rail reads the manager
for every expanded node so a city's own squares list beside its wards, and an
expanded node with nothing under it says which level to plot on its map), the ladder
grown from either end (2026-09-09, the reviewer plotting Arx: "the city center isn't
inside a building, it just goes neighborhood › room, and room › buildings": areas
mode's `AddDialog` asks what a square is, an area at the next level down or any
lower one, or a room right here, and a building planned beside a room is given its
door in the same stroke, the dig of its first room and the link chained on the ids
`create_area` and `staff_dig_room` now return; the folio crumb carries a ⊕ between
two entries a level fits between, and `InsertLevelDialog` creates it at the lower
entry's spot on the upper's map and moves the lower inside, `staff_move_room` +
`staff_place_room` for a room, `edit_area` for an area, so "Arx City › The City
Center" becomes "Arx City › Central Ward › Central Neighborhood › The City Center"
from the room's own page), and WIP dimming from `published_at`. Cross-world search lands on the hit's parent grid with
the room highlighted. **Room Document** (`RoomDocument`): full-width drafted
name/prose (`useDraft`, per-room localStorage), Save/Publish/delete savebar
("Next unpublished" trance loop included), seasonal/day-night `VariantsPanel`
wiring the #3291 backend's first UI, exits band + `ExitEditorDialog`
(`staff_set_exit_detail`), the dig-trinity exit `AddDialog`, a 3×3 `Compass`,
and read-only `Marginalia` panels fed by the payload. **Area Document**
(`AreaDocument`): the same manuscript pattern per Dan's every-altitude ruling —
drafted area prose via `edit_area`, area marginalia, the reused #3269
`EditAreaDialog` as the metadata door, delete via `staff_remove_area` (its
first button). Room/area art resolves most-specific-wins up the ancestor chain
(`resolve_area_art`, Task 3) and ambient lines carry authorable conditions.
Art *authoring* landed in #3535: `art_id` on `staff_edit_room` (the room's
`ObjectDisplayData.thumbnail`) and `edit_area` (`Area.art`) — falsy takes it
down, absent leaves it untouched — with the `ArtDialog` door on both
documents' marginalia (library + upload reuse the roster media machinery).
Marginalia phase 2 (#3534) delivered the doors: Ambience (with the full
condition editor), People, Places & Things, Law & Danger, and Secrets &
Story headers open their systems' editors (the reused #3269 Phase B
sections via `CategoryDoorDialog`); the Resonance panels carry real cascade
readings (`room_resonance_readings`/`area_resonance_readings` +
`dominant_affinity`); builder reads opened to grant holders scoped to their
subtrees (`IsStaffOrGrantHolder` + `_covered_area_ids` + the `grants`
endpoint) and the atlas wears the warrant (grant rooting, ceiling-absent
planning, "3 of 8 rooms" budgets). Not built (later phases per the spec):
the Ownership door (the payload still carries no deed/tenancy fields), the
rest of the appendix gap-list burndown, the visitor lens, player permits.

## Built (2026-08-31, #3477 Task 2 — publish lifecycle)

A canvas-dug (`origin=AUTHORED`) room is now born unpublished:
`RoomProfile.published_at` defaults to `now()` (an ordinary PLAYER room, and
every pre-existing room via the migration backfill, is live immediately) but
`world.areas.grid_services.create_room` sets it to `NULL` for `origin=AUTHORED`.
An unpublished room does not exist in the live world — `ExitState.can_traverse`
refuses entry through any exit leading to one, and
`RoomStatePayloadSerializer` omits such an exit from the room-state payload
entirely — for anyone except a story-runner (GM/Staff, the `is_story_runner`
typeclass attribute); a story-runner can walk in and see the exit to review the
room before it goes live. The new `staff_publish_room` REGISTRY action
(kwarg `room_id`, gated by the same `BuildWarrantPrerequisite` as its siblings)
stamps `published_at=now()`; idempotent (a re-publish just refreshes the
stamp) — no unpublish verb, no separate "done" flag. The staff area-manager
payload (`WorldBuilderRoomSerializer`) gains a `published_at` field so the
canvas can show unpublished rooms distinctly. Not built this task: a canvas
UI affordance for the Publish action itself (a later task in the #3477 arc).

## Built (2026-08-31, #3478 — GM onboarding moves to the Hall; mint banner removed)

The staff-mint form the world-builder actor banner grew below (#3283) is gone.
`POST /api/world-builder/areas/mint-builder-character/` and its frontend caller
(`mintBuilderCharacter`, `frontend/src/world-builder/api.ts`) are deleted; a
role-aware `mint_gm_character` (`world.roster.services.staff_characters`) replaced
it at `POST /api/gm/profiles/character/`, onboarding both staff and approved GMs
(not staff alone) through the Hall's GM slot instead. The world-builder page's
no-actor banner (`WorldBuilderPage`, `data-testid="world-builder-actor-banner"`)
then just pointed at the Hall ("set up your GM Profile from the Hall" + a Link
to `/`) rather than minting inline — and `WorldBuilderPage` itself (banner and
all) was retired with the rest of the grid-first canvas in #3538, the Atlas
(#3477/#3533) having replaced it. See `docs/roadmap/gm-system.md`'s Phase 9 for
the full rundown.

## Built (2026-08-20, #3283 — field feedback: staff mint, breadcrumbs, room editor page)

First real authoring session on the deployed builder produced three fixes.
**Staff character mint**: `POST /api/world-builder/areas/mint-builder-character/`
(`world.roster.services.staff_characters.mint_staff_character`) creates the
whole working set — character + sheet + PRIMARY persona + NPC-shelf roster
entry + active tenure — in one transaction, skipping the CG wizard entirely;
the world-builder actor banner grew the create form, and actor resolution
falls back to the account's first owned character (dispatch checks ownership,
not puppeting), so the minted character works immediately. Player-GM OOC
characters ride the same service gated on GMProfile later; sheet free-editing
stays on the admin. **Hierarchy at a glance**: the manager payload and
room-detail endpoint carry an `ancestors` breadcrumb chain, rendered on the
canvas header and the room editor. **Full-page room editor**:
`/staff/world-builder/rooms/:id` gives one room the full width (identity +
every authoring section in responsive columns), deep-linkable via the
self-sufficient room-detail payload; the canvas side panel keeps an "Open
full editor" link for quick jumps.

## Built (2026-08-18, #3269 Phases B+C — full room authoring + area metadata)

Rooms are no longer hollow: the staff panel gained sections for ambient stats
(authored zero-decay modifiers by default; pin = the rare cascade-cutting
override, warned loudly), places, atmosphere (entry lines + gated linger
emits with minted keys), feature install/dissolve by fiat (the identical
per-kind strategy handlers, run through an instantly-completed audit
project; VAULT/SANCTUM refused), functionary staffing (web mirror of telnet
`functionary`), travel-hub flags, default tactical blueprints
(`PositionBlueprint` + nodes/edges join `CONTENT_MODELS` with natural keys +
credits), starting-room bindings (the last admin-only step before characters
could enter a new grid), exit kind/openness/alias editing (a WINDOW switch
auto-opens so a kind flip can't sever a live link), cross-area room
duplication, and corridor batch-digs. Grid bundles round-trip every one of
those surfaces (credited ambient emits freeze rather than overwrite, ADR-0201
pattern), so a live-server build is durable content. Phase C: `edit_area`
finally has a UI — realm/climate/dominant-society/description/colour/ward
permits, with effective-climate display (the below-REGION warning went with the
rung in #4085) — plus
the "Arrange children" canvas: child areas drag-to-place on the same grid,
one level up (the city map of wards). `PlaceViewSet`'s player-reachable POST
was removed (staff authoring only); `AmbientEmit` gained admin parity.

## Built (2026-08-18, #3269 Phase A — grid bootstrap, recoverability, navigation)

The world builder can now bootstrap a first grid and recover from mistakes.
**Relational dig** is the primary flow: a ghost-cell click passes its anchor +
direction to `staff_dig_room`, which derives the cell and auto-creates the
aliased exit pair (the `Direction` spec moved to `world.areas.constants`,
shared with buildings); an empty AUTHORED area offers "Dig first room" at the
origin; a `like` exemplar copies size + description cross-area; blank
descriptions default to the PLACEHOLDER stub and a "Needs prose (N)" list
tracks them. **Recoverability:** deletion gates on `RoomProfile.exported_at`
(stamped by `grid_export`; ADR-0220 — a fixture key alone no longer bricks a
room), `staff_remove_area` removes empty areas, area slugs stay re-sluggable
until a room fixture key bakes them in, and `staff_move_room` re-parents a
mis-dug room. **Navigation:** world canvas gets minZoom 0.05 + MiniMap +
refit-on-room-set-change; the phantom unplaced-room tray is replaced by a
side-panel list with click-to-place mode; a cross-area room search
(`room-search` endpoint + header box) answers "where did I put it". The
rename bug (db_key vs longname split-brain) is fixed in
`set_room_display_data`, `%r`/`%t` normalization now applies to web
description writes, occupant counts exclude exits in SQL, and the
`areas_areaclosure` refresh runs CONCURRENTLY so live readers never block
during bulk authoring. The builder shows an explicit actor banner instead of
silently no-oping when no character is played. Phases B (full room authoring:
stats/places/features/staffing/ambient/exits/travel/bindings) and C (area
metadata) remain — see #3269's spec.

## Built (2026-07-19, epic #2436 slice 4 / #2451 — discovery/portal authoring)

The last of the epic's authoring slices: staff can now place clues and portal
anchors from the world-builder canvas instead of Django admin. `RoomDetailPanel`
gains staff-only "Clues" and "Portal anchors" sections
(`PlaceClueDialog`/`PlacePortalAnchorDialog`); `WorldRoomNode` shows a combined
clue+trigger count badge; `WorldCanvas` renders paired same-kind `PortalAnchor`s as
dashed edges between rooms (`pairPortalAnchors` + `portalEdges` in
`map-canvas/edges.ts` — an unpaired anchor still shows, just with no edge). Six new
`world_builder`-category REGISTRY actions
(`staff_place_clue`/`staff_remove_clue`/`staff_place_clue_trigger`/
`staff_remove_clue_trigger`/`staff_place_portal_anchor`/`staff_remove_portal_anchor`,
`src/actions/definitions/world_builder.py`, `StaffOnlyPrerequisite`-gated, same as
slice 2's verbs) plus one new staff-authoring service,
`install_portal_anchor_as_staff` (`world.magic.services.portal_travel` — no
owner/tenant standing check, no `PORTAL_ANCHOR_INSTALL_COST` debit, still refuses a
duplicate active kind in the same room). `RoomClue`/`ClueTrigger`/`PortalAnchor` all
gain a nullable-unique `fixture_key` (same pattern as `RoomProfile.fixture_key`);
`Clue` gains a `NaturalKeyMixin` `slug` and joins `CONTENT_MODELS` — clues are now
lore-repo content, exported/imported by slug. The grid bundle format gains three
sidecar sections — `clues`/`clue_triggers`/`portal_anchors`, each keyed by
`fixture_key` — upserted by `grid_import.load_grid_bundles()`'s new 5th pass and
report-never-deleted (never hard-deletes a fixture-keyed row absent from a
reimported bundle). Ratified: reimporting an unchanged bundle always converges a
dissolved `PortalAnchor` back to active — see `docs/systems/magic.md`'s "Portal
travel" section for why this is intentional, not a bug. `WorldBuilderRoom`
(`world.areas.serializers`/`builder_views.py`) carries `clues`/`clue_triggers`/
`portal_anchors` arrays per room now, built via bulk queries. Epic #2436 is now
fully built except **#2452** (player building via projects, `needs-design`).

## Built (2026-07-17, epic #2436 slice 1 / #2448 — grid foundation + export/import)

Staff world-building has a durable content pipeline now, ahead of any authoring UI:
`Area`/`RoomProfile` carry a permanent `slug`/`fixture_key` identity plus a
`GridOrigin` (AUTHORED/STORY/PLAYER) marking who built each row, and
`core_management.grid_export`/`grid_import` round-trip authored areas (with their
rooms, exits, and authored sidecar values) to the private lore repo as reviewable
per-area JSON bundles — see `docs/roadmap/rooms-and-estates.md`'s matching "Built"
entry and ADR-0140 for the format and rejected alternatives. No staff-facing canvas
exists yet (Django admin + `@dig`/`@open`/`@link` remain the only way to author grid
content); that's slice 2. The epic's remaining slices are filed as separate
sub-issues, not designed here: **#2449** (staff world-builder canvas — the drag/drop
authoring surface this document's "GM dashboard UI" / "Staff world management" items
below actually need), **#2450** (GM story areas — `STORY`-origin, never exported),
**#2451** (discovery/portal authoring — clue placement + portal anchors from the
canvas), **#2452** (player room-building constraints — resolved: dig_room stays
instant, RoomEditAction widened to owner-or-tenant, player rooms confirmed never
touch the authored grid export).

## Built (2026-07-17, epic #2436 slice 2 / #2449 — staff world-builder canvas)

Slice 1's grid foundation now has an authoring surface: a staff-only drag-and-drop
canvas at `/staff/world-builder` (linked from the profile dropdown + Game Setup hub)
backed by eleven `world_builder`-category REGISTRY actions
(`create_area`/`edit_area`/`staff_dig_room`/`staff_edit_room`/`staff_link_rooms`/
`staff_unlink_rooms`/`staff_rename_exit`/`staff_place_room`/`staff_remove_room`/
`promote_room`/`promote_area`, `src/actions/definitions/world_builder.py`) and a
read-only `WorldBuilderViewSet` (`/api/world-builder/areas/`, `IsAdminUser`-gated).
Authority is the staff account flag alone — deliberately not a GM-ladder trust tier
(see ADR-0139); GM-level world-shaping (this document's "GM tools" section below)
stays a separate, still-unbuilt question. Backend substrate
(`world.areas.grid_services`) and frontend canvas primitives (`map-canvas/`) were
both extracted from the pre-existing building Room Builder (#670) so all three
canvas consumers (buildings, battles, this one) share one implementation — see
`docs/systems/INDEX.md`'s "Areas" section for the full surface and
`src/world/areas/tests/test_world_builder_journey.py` for the create-area →
dig → link → place → promote → export journey proving the canvas actually feeds
slice 1's `export_grid_bundles()` pipeline. Not built this slice: an `edit_area`
UI (the action exists; no canvas panel calls it yet), GM story areas
(#2450, see "Built" below), clue/portal layers (#2451, since built — see "Built"
above).

## Built (2026-07-18, epic #2436 slice 3 / #2450 — GM story areas & story rooms)

The first GM-trust-gated (not staff-flag-gated) consumer of slice 1/2's grid
substrate: a GM can author their own private `STORY`-origin area, dig/link/place/
remove rooms in it (mirroring the staff canvas's verb set, scoped to areas they
own via `StoryArea`), and grant specific characters consent-first access to join
(`StoryRoomGrant` — gates the join only; walking inside rides ordinary exits, see
ADR-0141) — or spin up a disposable temp scene room (`InstancedRoom.gm_owner`) for
a one-off beat and close it out afterward, returning every joined character. Caps
are per-`GMLevel` (`GMLevelCap.max_story_areas`/`max_story_rooms_per_area`,
staff-tunable). 13 GM-authored REGISTRY actions
(`category="story_builder"`, `src/actions/definitions/story_builder.py`) plus 2
player-side join/leave actions (`category="story_rooms"`, no GM standing
required); telnet play verbs only (`sceneroom`/`joinroom`/`leaveroom`,
`src/commands/story_rooms.py`) — canvas authoring stays web-only (epic Decision
2), landing on the `/gm/story-builder` frontend page and the read-only
`StoryBuilderViewSet` (`/api/gm/story-areas/`, `IsGMOrStaff`). Story areas/rooms
are excluded from the player-facing `AreaViewSet`/`RoomProfileViewSet` and never
publicly listed regardless of a room's own `is_public` flag — see
`docs/systems/INDEX.md`'s GM section ("Story areas & story rooms") for the full
model/service/action/API rundown. Clue/portal layers since built (#2451, see
"Built" above). Player room-building constraints resolved (#2452 — dig_room
stays instant; RoomEditAction opened to tenants).

## Overview
Tools for players, GMs, and staff to interact with and manage the game world. Player tools focus on building and customizing spaces. GM tools are granular and level-gated — GMs can only do what their trust level allows. Staff tools are unrestricted for the one staffer coordinating the entire game.

## Key Design Points
- **Player building tools:** Room creation, decoration, furnishing. Economic cost of construction (buying and building rooms IC). Decorations give room statistics and bonuses. Everything from a cozy apartment to a massive fortress with research labs
- **GM tools (level-gated):** NPC creation within limits, combat management for encounters they run, reward distribution within a scaled range based on GM level. Newbie GMs get basic tools; veteran GMs get powerful world-shaping abilities
- **Staff tools:** Unrestricted "do anything" capability. The general-purpose commands that only the coordinating staffer needs. Creating areas, setting world state, managing GM promotions, overriding any system
- **Room building:** Both the mechanical creation of rooms (exits, descriptions, properties) and the player-facing economic version (purchasing land, commissioning construction, decorating)
- **NPC management:** GMs creating, placing, and controlling NPCs for their stories and adventures
- **Reward tools:** GMs granting XP, items, codex entries, legend — all within their level-appropriate caps
- **World state tools:** Staff-level tools for managing the living grid, triggering world events, updating canon time

## What Exists
- **Commands:** Room building commands (door creation, exit commands, room descriptors), movement commands, perception commands, character switching/sheet commands
- **Staff frontend:** Staff application detail page, extensive Django admin configuration
- **Areas system:** Room creation infrastructure exists through the areas app;
  authored/runtime identity + grid export/import round-trip now exists (#2436/#2448,
  see "Built" above), and a staff-only drag-and-drop authoring canvas now sits on
  top of it (#2449, see "Built" above); a GM-trust-gated variant of that same
  canvas (story areas + story rooms, #2450) now sits alongside it, see "Built" above;
  the staff canvas now also authors discovery/portal content (clue placements,
  clue triggers, portal anchors — #2451), see "Built" above
- **GM dashboard** — see `docs/roadmap/gm-system.md` for GM-specific tooling
  (level-gated commands, story areas/rooms, the scenario catalog); this document's
  "GM tools" section below describes the still-open NPC/combat/reward tooling gap

## What's Needed for MVP
- GM command framework — level-gated command permissions scaling with GM trust
- GM NPC tools — creating, placing, customizing, and controlling NPCs within level limits
- GM combat tools — initiating encounters, managing combat flow, controlling enemy actions
- GM reward tools — granting XP, items, codex, legend within scaled caps
- Player room purchase flow — economic room acquisition with IC construction
- Decoration system — furnishing rooms with items that provide stats and bonuses
- Room stat calculation — how decorations and upgrades translate to room properties
- ~~Staff world management — tools for the coordinating staffer to manage world state~~
  built (#2449, staff world-builder canvas — see "Built" above)
- GM dashboard UI — web interface for GMs to manage their tables, NPCs, and active sessions
- Player building UI — web interface for room customization and decoration (#2452, needs-design)
- Builder documentation — in-game help for room creation and management

## Testing Infrastructure

### What Exists
- **Backend unit tests** — Django TestCase + DRF APITestCase per app, run via `arx test`
- **Frontend unit tests** — Vitest with React Testing Library, run via `pnpm test`
- **Production build smoke tests** — Playwright e2e tests that verify the built frontend loads,
  key routes render, no JS exceptions, and all chunks load. Run via `pnpm test:e2e`
- **Manual integration tests** — `arx integration-test` scaffolding for email verification flow
  (starts servers, creates test accounts, but human does the clicking)
- **Pre-commit hooks** — ruff, prettier, typecheck, custom linters

### What's Needed
- **Automated integration tests** — Replace the manual `arx integration-test` flow with Playwright
  tests that run the full stack (Django + frontend), log in, and exercise key user flows:
  - Registration and email verification
  - Character creation
  - Scene participation and interaction
  - Event creation and lifecycle
  - Codex browsing
- **CI pipeline** — Run backend tests, frontend tests, and e2e smoke tests on every PR.
  Integration tests can run on a schedule (nightly) since they need the full stack

### Coverage by System
| System | Backend Tests | Frontend Tests | E2E Smoke | Integration |
|--------|:---:|:---:|:---:|:---:|
| Events | yes | - | yes (route renders) | no |
| Scenes | yes | - | - | no |
| Roster/Characters | yes | - | - | no |
| Auth/Registration | yes | - | yes (login renders) | manual |
| Codex | yes | - | - | no |
| Stories | yes | - | - | no |

## Notes
