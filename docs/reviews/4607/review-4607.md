# Review evidence: #4607 NPCs move on the battle map, melee reach is real, and PCs and NPCs share a hop budget

- Reviewed revision: `b66d0331a4125327e31e64d046befd96fbac891f`
- Reviewer: Claude (Opus 5.5), following tools/skills/real-testing/SKILL.md; every screenshot read by eye against the slice 2 items of the #4576 spec
- Reviewer verdict: PASS
- Application/build identity: this worktree's own Evennia (`just start` with DATABASE_URL pointed at the throwaway database rt_4607; ports 4000-4002 were free and no other Evennia process was running, coordinated with the other session on this machine) serving the production bundle built by `pnpm --dir frontend build` from 3e7fbbb60 (rebased since as 21a532879); never the shared server
- Environment: devcontainer workstation (10 GB); throwaway Postgres database rt_4607 built by `tools/build_schema.py`, dropped afterwards; Playwright Chromium headless, one worker; telnet on port 4000 driven by a small socket script
- Viewports/themes: 1280x720 full-page captures, system (light) theme only
- Approved design: no demo for this issue; the approved design is the "Slice 2. Movement and reach" section and the slice 2 Verification list of the #4576 spec (`spec:approved`)
- Visual review: completed; the scene page's combat panel (Your Turn move list, combatants list, vital pools) and the scene feed, the surfaces this slice changes, read at each step of two rounds
- Visual verdict: PASS
- Screenshots: ![one hop left](docs/reviews/4607/1-one-hop-left.png) ![no movement left](docs/reviews/4607/2-no-movement-left.png) ![the wolf moved and bit](docs/reviews/4607/3-wolf-moved-and-bit.png) ![the wolf follows in round 2](docs/reviews/4607/4-wolf-follows.png)
- Comparison notes: the move list sits in Your Turn under "Move" with the line "1 hop left this round." while the round is open; after one move both remaining moves are greyed with "You have no movement left this round." under each; after the round resolves they read "You can move when the next round opens." Screenshot 3 still shows the enemy's attack line as "Grey Wolf (Mook)'s Grey Wolf bite", which this pass found and fixed in 21a532879; screenshot 4, taken after the fix and a server restart, reads "Grey Wolf's Grey Wolf bite strikes Hobb for 10 damage." In screenshot 4 the moves read "You have no movement left this round." rather than the between-rounds line: the move list polls every 10 seconds and the capture was taken right after the round resolved, so it still shows the round's own spent hop; screenshot 3 shows the between-rounds line after its poll. The combatants list updates on refresh, as everything after a resolved round does (the encounter polls every 10 seconds); the feed lines arrive live. The live pass ran on 3e7fbbb60 (then rebased as 21a532879). The commits after it are 62bad19de and b66d0331a, test files only (journeys tightened and two added, unit tests a journey covers dropped, the path fuzz given an independent oracle; `git show --stat` lists only files under `tests/`, `integration_tests/` and the fuzz), and the rebase onto main 0b49ba207, whose two new commits (#4631 admin refused-save restore, #4623 Almanach seating) touch no combat, positioning or combat-panel file. After the rebase the 25 journeys, the wall journeys, the admin registry guard and the migration check were rerun (OK).
- Tested interactions: log in on the React login page; open /game (puppets Hobb; "In world, In combat"); follow the room header's scene link; read the Your Turn move list; click "Move to Yard"; read the greyed moves; resolve the round as staff (`POST /api/combat/1/resolve_round/`, the GM panel's call); click Refresh; read the feed, health and positions. Round 2: open the round (`POST /api/combat/1/begin_round/`), click "Move to Gate" (it moved Hobb, so the hop came back), then over telnet `connect e2e_test_account ...`, `position`, `position Lane`; resolve the round; click Refresh.
- Fixture/live boundary: live server, throwaway database. Outside the pages, in `arx manage shell` on rt_4607 only, before the server started: the check charts and the movement capability seeded, the e2e test account made staff (so it can resolve the round), Hobb (played by that account, health 100), the room "The Causeway" with Lane - Gate - Yard - Hall - Tower joined by open edges, a combat encounter in round 1 declaring, and a bestiary entry "Grey Wolf" (2 hops, walks, one 10-damage bite, no defence check so the bite lands flat) spawned at the Tower through `spawn_from_creature_template`. Resolving the round went through the server's own REST endpoint, not the shell. Walls, climbers, fliers, wind-ups, the live PC reach fizzle and the RESOLVING refusal are proven by the journeys below, not here.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| V1-npc-moves-and-attacks | PASS | Live: the two-hop wolf at the Tower went to the Hall (beside Hobb at the Yard), the feed read "Grey Wolf moves to Hall." then the bite, and Hobb's health went 100 to 90 (3); in round 2 it followed him to the Yard and bit again, 90 to 80 (4). Journey `AnEnemyClosesIn.test_a_fast_wolf_runs_up_and_bites_in_the_same_round` in `src/integration_tests/test_npcs_close_in_journeys.py`. | none needed |
| V2-cooldown-and-preselected-still-move | PASS | Journeys `test_a_wolf_whose_bite_is_on_cooldown_still_closes_in` (no bite, still follows to the Gate) and `test_a_wolf_staff_gave_a_bite_still_moves_before_it_bites` (a bite created before the round still moves the wolf first; one attack row). | none needed |
| V3-melee-and-missile-reach | PASS | Journeys `test_a_bite_does_not_carry_across_the_room` (a one-hop wolf two away moves and deals nothing) and `test_an_archer_shoots_across_the_room_without_moving`. | none needed |
| V4-pc-move-table | PASS | Live: "1 hop left this round." (1); one move, then every move greyed with "You have no movement left this round." (2); after the round "You can move when the next round opens." (3); the hop came back in round 2 (Hobb moved to the Gate) and telnet `position Lane` answered "You have no movement left this round." Journeys `HobbMovesOneHopARound`: both seams, RESOLVING "Wait for the round to resolve.", BETWEEN_ROUNDS, the reset, and free moves after the fight. | none needed |
| V5-pc-strike-fizzles | PASS | Journey `HobbsStrikeFindsNoOne` (declared through the web; the archer force-moved away; "...'s strike finds no one in reach.", no damage, anima and fatigue unchanged) and `world.combat.tests.test_pc_live_reach` (area casts keep the targets in reach and fizzle only when none is left). | none needed |
| V6-refit-repick-or-skip | PASS | Journeys `ABruteWindsUp.test_the_blow_lands_on_the_weakest_still_in_reach_after_hobb_steps_away` (re-picked by the entry's lowest-health mode) and `test_the_blow_is_called_off_when_nobody_is_in_reach` ("Brute cannot reach anyone."). | none needed |
| V7-walls-and-traversal | PASS | Journeys `WallsOnTheCauseway`: a walker goes round a wall, a walker with no way round stays, a two-hop climber crosses a wall with a challenge and a one-hop climber cannot, a flier crosses a hard seal overhead and is stopped by an edge that blocks flight. | none needed |
| V8-aerial-gate | PASS | Journey `HobbCannotFly`: `position Above Gate` answers "You cannot fly." and costs no hop. | none needed |
| V9-windup | PASS | Journeys `test_a_brute_winding_up_does_not_move`, `test_a_brute_out_of_reach_closes_in_then_winds_up_then_lands_the_blow`, and the two matured-blow cases under V6. | none needed |
| V10-path-fuzz | PASS | `integration_tests.fuzz.test_path_service_fuzz`: random walled rooms; a returned path never crosses a closed edge and consecutive positions share an open edge; walker reachability matches `reachable_positions`. | none needed |
| M-migration-on-production | PASS | `just prod-migration-check --tables creaturetemplate,combatparticipant`: dump arxii-20261023T033018Z.sql.gz, forward 0282-0290, back to 0289, forward 0290, creature templates 2 before and after, RESULT PASS; migration-reviewer verdict PASS. | none needed |
| F-move-list-empty | PASS | Found in this pass: the combat panel handed Your Turn only COMBAT-backend actions, so its move list was always empty and moves were only possible by clicking the map. Fixed in 21a532879; `src/combat/__tests__/useAvailableActions.test.tsx` fails on the old filter. | none needed |
| F-attack-line-tier | PASS | Found in this pass: an enemy's attack line named it "Grey Wolf (Mook)". Fixed in 21a532879 (the line uses the opponent's name); the journey asserts the bite line starts with the wolf's name. | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Move list while declaring | "Move" with "1 hop left this round." and the two neighbouring moves | MATCH | 1-one-hop-left.png |
| Move list after the hop | Every move greyed with "You have no movement left this round." | MATCH | 2-no-movement-left.png |
| Feed after the round | "Grey Wolf moves to Hall." then the bite on Hobb; health 90/100; the wolf listed at the Hall | MATCH | 3-wolf-moved-and-bit.png |
| Move list between rounds | Moves greyed with "You can move when the next round opens." | MATCH | 3-wolf-moved-and-bit.png |
| Round 2 | "Grey Wolf moves to Yard." and the bite line naming the wolf without its tier; health 80/100 | MATCH | 4-wolf-follows.png |

## Findings fixed during this pass

1. The combat panel's move list was always empty because Your Turn received only COMBAT-backend actions (fixed in 21a532879).
2. An enemy's attack line named it with its tier, "Grey Wolf (Mook)" (fixed in 21a532879).
3. A brute whose only attack winds up, standing out of reach, declared a wind-up at someone it could only reach by moving, then stood still and repeated it every round (fixed in 32cc27bcf: a wind-up aims only at someone in reach from where it stands, and a matured blow does not chase).

## Unresolved findings

None
