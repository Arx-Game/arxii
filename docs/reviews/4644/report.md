# Review evidence: #4644 Battle map shows another fighter's move only on its 10-second refresh

- Reviewed revision: `96294c5cf`
- Reviewer: Claude (Opus 5.5), following tools/skills/real-testing/SKILL.md; every screenshot read by eye against the issue's Expected section
- Reviewer verdict: PASS
- Application/build identity: this worktree's own Evennia (`just start` with DATABASE_URL pointed at the throwaway database; ports 4000-4002 were free, no other Evennia process was running, and the other session on this machine was told before and after) serving the production bundle built by `just fe-build` from ea43784fc; never the shared server
- Environment: devcontainer workstation (10 GB); throwaway database rt_4644 (dropped afterwards); Playwright Chromium headless, one worker, two browser contexts logged in as two accounts
- Viewports/themes: 1400x1000, light theme only
- Approved design: no demo for this issue; the expected behavior is the issue's "Expected" section (a lightweight bug fix)
- Visual review: completed; Ada's Map tab in the combat rail, read at each step
- Visual verdict: PASS
- Screenshots: ![Ada before the round](docs/reviews/4644/1-ada-before-the-round.png) ![Ada sees the wolf at the Yard](docs/reviews/4644/2-ada-sees-the-wolf-at-the-yard.png) ![Ada sees Hobb at the Lane](docs/reviews/4644/3-ada-sees-hobb-at-the-lane.png) ![Ada sees the wolf at the Gate](docs/reviews/4644/4-ada-sees-the-wolf-at-the-gate.png) ![Ada sees Hobb at the Gate](docs/reviews/4644/5-ada-sees-hobb-at-the-gate.png)
- Comparison notes: the map's avatars show initials (G for Grey Wolf, H for Hobb); the map is small in a full-page shot and Ada's own node (the Lane) sits at its left edge. The pass ran on ea43784fc. The one commit after it, 96294c5cf, changes only tests and the journeys doc (`git diff --stat ea43784fc 96294c5cf`: `docs/testing/journeys.md`, `handleCombatEncounterStatePayload.test.ts`, `test_battle_map_live_journeys.py`), so no code the pass exercised changed.
- Tested interactions: two browsers, each logging in on the React login page, opening /game and following the room header's scene link. Hobb's browser resolved the round through the endpoint the GM's Resolve button calls (`POST /api/combat/1/resolve_round/`), opened the next round (`POST /api/combat/1/begin_round/`), and clicked "Move to Lane" (round 2) and "Move to Gate" (round 3) in its Your Turn panel. Ada's browser opened the Map tab once and was never refreshed or reloaded; Playwright waited at most 9 seconds (under the 10-second poll) for each change to appear on her map, timed it, and recorded every `combat_encounter_state` frame her socket received.
- Fixture/live boundary: live server, throwaway database. Outside the pages, in `arx manage shell` on rt_4644 only: the e2e test account (staff, so it may resolve rounds) playing Hobb at the Gate, a second account e2e_watcher (given a verified email) playing Ada at the Lane, both given the playable puppet lock, the room "The Causeway" (Lane - Gate - Yard - Hall - Tower, open edges), a DECLARING encounter in round 1 with both as participants, and a Grey Wolf spawned from a bestiary entry with 2 hops at the Tower.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| E1-npc-move-live | PASS | Pass 1: the resolve request took 1126 ms; Ada's map showed G at the Yard 7 ms after the response and none at the Tower (screenshot 2, beside "Grey Wolf moves to Yard."). Pass 2: the response came at T+1000 ms, Ada's socket got the ping at T+889 ms (after the round committed, before the HTTP response returned), and her map showed the wolf at the Gate at T+1370 ms (screenshot 4). Journey `AWatcherSeesTheEnemyArrive` (no ping before the commit, exactly one after, then the REST read has the wolf at the Yard). | none needed |
| E2-pc-move-live | PASS | Pass 1: Ada's map showed H at the Lane 409 ms after Hobb's click (screenshot 3). Pass 2: Hobb clicked at T+7616 ms, the ping reached Ada at T+7725 ms, her map showed H at the Gate at T+8024 ms (screenshot 5). Journey `AWatcherSeesAFriendStep`. | none needed |
| E3-one-ping-per-change | PASS | Pass 2 recorded exactly two frames, `{"encounter_id": 1, "round_number": 2}` after the round and `{"encounter_id": 1, "round_number": 3}` after the move; opening round 3 sent none. The journeys assert exactly one ping for a round in which the wolf moved, for the round that ends the fight (`TheLastRound`), and for an effect's forced move (`AShoveWhileDeclaring`), and none for a step after the fight (`AfterTheFight`). | none needed |
| E4-wire-name | PASS | The live frames above carry the name the client handles; `web.tests.test_message_type_parity` (fails when a server message type is missing from `types.ts`) passes. | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Before the round | Wolf at the Tower, Hobb at the Gate | MATCH | 1-ada-before-the-round.png |
| After round 1, no reload | Wolf at the Yard, gone from the Tower | MATCH | 2-ada-sees-the-wolf-at-the-yard.png |
| After Hobb's move, no reload | Hobb at the Lane, gone from the Gate | MATCH | 3-ada-sees-hobb-at-the-lane.png |
| After round 2, no reload | Wolf at the Gate | MATCH | 4-ada-sees-the-wolf-at-the-gate.png |
| After Hobb's move, no reload | Hobb at the Gate | MATCH | 5-ada-sees-hobb-at-the-gate.png |

## Findings fixed during this pass

None. The setup needed a verified email and the playable puppet lock for the second account's character; both are test-data steps, not product changes.

## Unresolved findings

None
