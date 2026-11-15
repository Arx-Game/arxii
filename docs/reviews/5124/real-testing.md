# Real testing for #5124 (kindled resonances)

- Commit under test: `e344c71ce` (branch `feature-5124-what-stirs-a-resonance-the-situations-th`).
- Form B: my own server on a throwaway Postgres database `rt_5124`. The start script found no Evennia process and :4001/:4002 free. Web was :4001, websocket :4002.
- Accounts: `e2e_test_account` plays Mira Vale and Brannoc Hale. A second account, `kindled_second_player`, plays Tomas Reeve (the "second player" checks).
- Browser: Playwright (Chromium, one worker, 1600 px wide) against the built bundle (`just fe-build`). `just fe-e2e` could not launch: the pinned Playwright wants Chromium build 1254, which is not installed and cannot be downloaded in this sandbox. I ran the same backend config through `frontend/e2e.rt5124.config.ts`, which only adds the cached Chromium 1208 as the executable.
- Screenshots: `docs/reviews/5124/*.png`. Nothing is committed.
- Every database read-back below came from `arx manage shell` against `rt_5124` (script: scratchpad `readback.py`).

## Verdicts

| # | Scenario | Verdict |
|---|---|---|
| 1 | Screen 1, scene sidebar "Your resonances" | PASS |
| 2 | Screen 2, drawing strength and the give-in picker (in the combat rail, not telnet) | PASS |
| 3 | Screen 4, acting earns the resonance; only the actor is told (second player checked) | PASS |
| 4 | Screen 5, "Reflecting on" row, then a disowning pose | PASS |
| 5 | Screen 6, sheet aura card and the rite with an offering | PASS, with one defect found (the result box vanishes, see Bugs) |
| 6 | Failure case, rite with no qualifying offering | PASS |
| 7 | Telnet `resonances`, then `aura`, through the web command input | PASS |

## What I authored in the throwaway database

A fresh `build_schema` database holds none of this (migration 0413 seeds the strength tiers, and `build_schema` does not run migrations; the Kindling config, deed awards and rite config are staff-authored). All of it is written by `seed_kindled_resonances_spec` in `src/integration_tests/live_seeds.py`, built on the test factories, plus a few shell edits noted below.

- Rooms: The Overseers' Gate, The Ford. Scene "Standoff at the Gate" (active, Mira's account owns it, Tomas's account takes part).
- Characters: Mira Vale and Brannoc Hale (played by `e2e_test_account`), Tomas Reeve (played by `kindled_second_player`), Overseer Kell (a persona-backed combat opponent, no player).
- Affinities and pair conversion rows (`ensure_conversion_pairs`): Celestial, Primal, Abyssal, with Abyssal to Celestial at 0.5.
- Resonances: Fury (Primal, feeling = a "Furious" Property), Wonder (Primal), Domination (Abyssal), Dawnlight (Celestial).
- `KindledStrengthTier` x3: Faint (bond 1, severity 1, pull +20 levels, give-in depth 1, +10%, ease 1, dig deep 25%, earn 100%), Strong (2, 3, +20, depth 2, +25%, ease 2, 50%, 125%), Blazing (3, 5, +40, depth 3, +50%, ease 4, 100%, 150%).
- `KindlingSituation` x2: Fury, "someone a thread is tied to is present" (strength from the bond); Domination, "mission theme" with the theme "People held for what they are" (Faint). No `reason_text` was authored.
- `MissionTheme` "People held for what they are" with player text "This mission is about people held for what they are."
- `KindledDeedAward` x4: Failure 4, Partial Success 6, Success 8, Critical Success 12.
- Fury config: `FuryTier` x3 (Let it in depth 1 / 3 control, Give in depth 2 / 6, Lose yourself depth 3 / 9 with Berserk), `FuryConfig` with the Berserk condition, `FuryDegreeShare` per outcome (0, 0, 50, 100, 125 percent), and the strain config `intensity_per_control_surrendered` = 1.50.
- Mira: aura 100 percent Celestial (settled); resonances Dawnlight 170, Domination 60 (later edited by hand from 30 so Domination leads her unsettling), Fury 20, Wonder 10. A Fury relationship thread tied to Tomas (tier 3). A "Free the quarry" mission with an entry node, a done node, a check option "Bar the overseers' door" (Presence, carries the theme, routes for four outcomes) and a branch option "Watch from the shadows" (no theme). Assigned with `staff_assign_mission`.
- Brannoc: Fury 30, Wonder 30, anima 40, vitals 50. A Fury relationship thread tied to Overseer Kell (tier 2). Gift "Pyromancy" with a gift thread of two resonances (Fury 7, Wonder 3), technique "Cinder Lash", `ThreadPullCost` tier 1, and a flat +3 `ThreadPullEffect` for Fury and for Wonder. A combat encounter at The Ford, round 1 declaring, with Kell as the opponent.
- Rite of settling: `DriftCorrectionConfig` with the Rite of Drift Correction, check type "Composure", difficulty 0, cap 50 percent; `DriftCorrectionOutcomeShare` for every outcome (0, 0, 0.5, 1.0, 1.0). Without a share for every outcome row the rite says "not set up yet" (I first missed Critical Failure; added by hand, then in the seed).
- Offering: `seed_kindled_offering` put "Dawn-gold Thread" (tied to Dawnlight) in Mira's hands, only after the refusal check. Run twice (one per rite).
- Hand edits through the shell: Domination 30 to 60 on Mira; the Critical Failure share; a second `staff_assign_mission` run for Mira (see scenario 3); the Wonder row on Brannoc's gift thread (now in the seed).

## 1. Screen 1: "Your resonances" in the scene sidebar

- Did: logged in, entered the world as Mira in the live scene, opened the main game page, read the right sidebar. Evidence: `01-your-resonances-sidebar.png`.
- Expected (from spec decision 7 and the demo): each resonance with its affinity; a kindled one reads "Kindled, <word>" with its reason, the word being the staff-named strength; an unkindled one reads "Not kindled"; no numbers. Fury is tied to a person present, so blazing, reason naming him. Domination is kindled only by the mission theme at the strength I authored (Faint). Wonder and Dawnlight have no situation.
- Saw: Fury "Kindled, blazing" with "Tomas Reeve is here"; Domination "Kindled, faint" with "This mission is about people held for what they are."; Dawnlight "Not kindled"; Wonder "Not kindled". The Playwright check asserts the panel text holds no digit.
- Verdict: PASS.

## 2. Screen 2: drawing strength and giving in (combat rail)

- Did: entered as Brannoc, opened the Combat tab, picked Cinder Lash and Overseer Kell, opened Pull Threads, ticked the Pyromancy thread, then used "Give in to your Fury", then submitted the round. Combat setup was workable, so I did not need the telnet `cast` fallback. Evidence: `04-pull-payer-kindled.png`, `05-give-in-picker.png`, `05b-combat-rail-with-pull-and-give-in.png`, `06-after-submit.png`.
- Expected, worked out by hand before the run:
  - The combat rail panel reads Fury "Kindled, strong" (a tier 2 bond reaches the Strong row), reason "Overseer Kell is here"; Wonder "Not kindled".
  - The pull's perk is authored at +3. Fury is kindled Strong with 20 pull levels, which reads a level-0 thread at twice the perk (the arithmetic the journeys use): "Pay with Fury, Kindled, strong, +6". Wonder is unkindled, so "+3" and no tag.
  - The give-in picker offers only the kindled resonance, steps Hold steady, Let it in, Give in (depth up to 2), and not Lose yourself (depth 3 needs Blazing). The preview for Give in: 6 control given up; the most it can buy is 6 x 1.5 = 9, times 1.25 for the Strong bonus = 11.25, at the top outcome share of 125 percent = 14.06, so "Gain up to 14".
- Saw: exactly that. Panel: Fury "Kindled, strong", "Overseer Kell is here", Wonder "Not kindled". Pull dialog: Fury "Kindled, strong" "+6", Wonder "+3". Picker: one option "Fury (kindled, strong)", buttons Hold steady / Let it in / Give in only, line "Your Fury is strong: you can go as far as Give in.", preview "Give up 6 control · Gain up to 14 intensity · Control roll: Composure, eased by your strong Fury". Read back after submitting: one `CombatPullThread` with `kindled_strength` 2 (Strong); the round action holds `fury_resonance` Fury and the "Give in" tier; Fury balance 30 to 28 and anima 40 to 39 on screen.
- Note on how the pull got in: my first attempt picked the wrong "Overseer Kell" button (the room list, not the target), so the submit was refused ("That technique needs an opponent to target.") but the pull had already been committed; the second run, with the target set, got the toast "You have already pulled a thread this round." and went ahead with the give-in. The pull row and the give-in action are both from the real UI, from two runs.
- Not exercised: the round was submitted but I did not resolve it, so the intensity actually bought is unread. The depth cap, the preview and the saved declaration are what this scenario proves.
- Verdict: PASS.

## 3. Screen 4: acting earns, and only the actor is told

- Did: Mira (one browser) and Tomas (a second browser context on the second account, in the same room throughout). Mira opened Stories, expanded "Free the quarry", read both options, took "Bar the overseers' door". Evidence: `07-mission-option-feeds.png`, `08-mission-option-taken.png`, `09-tomas-view-after-mira-acts.png`.
- Expected: the option that carries the theme says "Your Domination is kindled: This mission is about people held for what they are."; the option with no theme says nothing of the kind. After the roll Mira earns Domination equal to the authored award for the result times the Faint row's 100 percent (Failure 4, Partial 6, Success 8, Critical 12), told only to her: "You earned N Domination."; Tomas sees nothing of it.
- Saw: the door option carried that kindled line; "Watch from the shadows" carried none. The roll was Success. Mira's feed gained "You earned 8 Domination." Tomas's whole page text contained neither "You earned" nor "Domination". Read back: `ResonanceGrant` 2, 8 Domination, source KINDLED_DEED, tied to the Domination situation row; Domination balance 68 to 76 on this run (60 to 68 on the first).
- Caveat: this is the second run. My first run was refused: "A fight is in progress; the scenario continues when it ends." (see Bugs: a mission paused by a disconnect never resumes). I assigned Mira a second run of the mission to carry the Tomas check, so Mira holds two Domination deeds of 8 (grants 1 and 2). Both runs rolled Success. The first run had Mira read "You earned 8 Domination." in her feed and I read the grant back; I did not have Tomas's page in view for that one, so the second-player evidence is the second run.
- Verdict: PASS.

## 4. Screen 5: the "Reflecting on" row, and a disowning pose

- Did: Mira on the main game page with Tomas watching. Read the row, picked the first deed and Disown, typed a pose, sent. Evidence: `10-reflecting-on-row.png`, `11-reflection-ready-to-post.png`, `12-pose-posted-reflection-recorded.png`, `13-tomas-sees-only-the-pose.png`.
- Expected: the row lists the unreflected deeds first and the resonance that is unsettling her last, with Embrace and Disown. After posting, the room sees only the pose text. The reflection is saved with the choice Disown, tied to that deed and that pose, with no rite yet (waiting). The deed leaves the list (a deed is reflected on once).
- Saw: options in order `deed, deed, resonance`: "Mission Theme · 8 Domination", "Mission Theme · 8 Domination", "Your Domination · unsettling you"; buttons Embrace and Disown. After Send, Mira got "Your reflection on Mission Theme is recorded. It waits with your other reflections for the rite of settling." with a "Settle your aura" button; the row then listed one deed. Tomas's page showed the pose `Mira Vale runs a thumb over the scorched bar and smiles. "They had it coming. All of them."` and nothing else (no "reflect", "Embrace", "Disown" or "Domination"). Read back: `Reflection` 1, choice DISOWN, grant 2, interaction 1 (the pose), rite empty.
- Note for the demo reviewer: the deed is named by its situation's stock label ("Mission Theme") because I authored no `reason_text`. The demo names the act ("Barred the overseers' door"); the code has no act name to show (the grant points at the situation row only).
- Verdict: PASS.

## 5. Screen 6: the sheet's aura card, and the rite with the offering

- Did: opened Mira's sheet (Magic tab), read the aura card; opened "Settle your aura"; after giving her the offering, performed the rite; reloaded. Evidence: `14-sheet-aura-card-waiting-reflection.png`, `16-rite-dialog-with-offering.png`, `17-rite-result.png`, `18-sheet-after-rite.png`, and the same three for the second rite (`...-second.png`), `20-sheet-after-both-rites.png`.
- Expected: the card lists the waiting reflection and one "Settle your aura" button, and the page has no Accept button. With an offering tied to Dawnlight (the main affinity's resonance): the reflection gets its `rite`, the offering is spent whatever the roll, and the disowned deed of 8 Domination converts toward the main affinity. Disowning a deed turns `disown_deed_percent` (75, the config default) times the outcome share of it: at a full share int(8 x 0.75) = 6 Domination, at Redemption 0.5 that is 3 Dawnlight; at Partial (0.5) 3 Domination and 1 Dawnlight; at Failure (0) nothing.
- Saw:
  - Card: "Your reflections: Pose · Disown Mission Theme", one "Settle your aura" button, "Not yet reflected on: Mission Theme · 8 Domination"; zero buttons matching /accept/i on the page. The dialog read "Domination turns toward Dawnlight, up to 6", matching the 6 worked out above.
  - Rite 1: the roll was Failure (share 0). Result: "You disown Mission Theme, but the rite turns nothing of it away." Read back: `SettlingRite` 1 (Failure, share 0.00), reflection 1 has rite 1, balances unchanged (Domination 76, Dawnlight 170), the offering item gone. This agrees with the authored table, and with "the offering is spent whatever the roll".
  - Rite 2 (a second pose disowning the other deed, a second offering): the roll was Success (share 1.00). Result: "Success. You disown Mission Theme: 6 Domination became 3 Dawnlight." Read back: `SettlingRite` 2, reflection 2 has rite 2, Domination 76 to 70, Dawnlight 170 to 173, one `ResonanceGrant` of 3 Dawnlight with source DRIFT_CORRECTION, the second offering gone. Exactly the hand-worked 6 and 3.
  - After both: the sheet shows no "Your reflections", no "Not yet reflected on" and no Settle button.
- Defect found in this scenario: after rite 2 the result box ("Success. You disown...") appeared and then vanished before I could close it. See Bugs.
- Verdict: PASS for the rite, the conversion, the spent offering and the card; the vanishing result box is a defect.

## 6. Failure case: the rite with no qualifying offering

- Did: before the offering was seeded, with the one waiting reflection, opened the rite dialog on the sheet and then asked the server directly (`POST /api/magic/settling-rite/` with the browser's session and CSRF) with no offering, and with an item id she does not carry. Evidence: `15-rite-dialog-no-offering.png`.
- Expected: the dialog says she carries nothing that counts and Perform is disabled; the server refuses both requests and writes nothing; the reflection stays waiting.
- Saw: the dialog said "You carry nothing that counts as the offering." with "Perform the rite" disabled. Server: `400 {"detail":"Ritual 'Rite of Drift Correction' requires 1x offering for Dawnlight that you don't have."}` for no offering, and `400 {"detail":"You are not carrying everything you offered."}` for item 999999. Read back: reflection 1 still had no rite, no `SettlingRite` row existed, balances unchanged; the reading endpoint still listed one waiting reflection.
- Verdict: PASS.

## 7. Telnet verbs in the web command input

- Did: as Mira, typed `/resonances`, then `/aura` (a leading slash sends the line as a command). Evidence: `02-telnet-resonances.png`, `03-telnet-aura.png`, `21-telnet-aura-after-rites.png`.
- Expected: `resonances` prints the same list as the panel; `aura` prints the aura line, the unsettled line, and "You have no reflections waiting." with none.
- Saw: `Domination (Abyssal) - Kindled, faint` / `This mission is about people held for what they are.` / `Dawnlight (Celestial) - Not kindled` / `Fury (Primal) - Kindled, blazing` / `Tomas Reeve is here` / `Wonder (Primal) - Not kindled`. Then `Your aura: Celestial (nearly all).` / `Your Domination has grown strong enough to make you unsettled.` / `You have no reflections waiting.` After both rites it said "You have no reflections waiting." again.
- Verdict: PASS.

## Bugs and observations (nothing fixed)

1. **Defect in #5124: the rite's result box vanishes when the rite used up the last thing the aura card listed.** `frontend/src/magic/components/AuraReflections.tsx` returns `null` when there are no waiting reflections, no unreflected deeds and no open chance, and it hosts `SettleAuraDialog` below that early return. A rite that takes the last reflection while no deed is left to list makes the card, and so the open dialog with its result, disappear. Smallest repro: Mira with exactly one waiting reflection and no unreflected deed (the second rite above); press "Perform the rite". The result showed ("Success. You disown Mission Theme: 6 Domination became 3 Dawnlight.", `17-rite-result-second.png`) and then Playwright reported the Close button "detached from the DOM" and could not click it. The first rite did not do this only because one deed was still unreflected. The effect is saved correctly; only the player's feedback is lost.
2. **Not #5124 (existing behaviour): a mission paused by a disconnect never resumes.** `maybe_pause_mission_for_disconnect` sets `is_paused` when the character leaves; the only place that clears it is the end of a fight (`encounter_option.py:190`). After a disconnect and reconnect, taking an option is refused with "A fight is in progress; the scenario continues when it ends." though no fight exists. Repro: assign a mission, enter as the character, leave (close the page), enter again, take an option. I cleared the flag by hand and restarted the server (its identity map held the old value) to carry on.
3. **Not #5124 (existing behaviour): the Pull Threads dialog lists the account's other character's threads.** `ThreadPullDialog.tsx` calls `useThreads()` with no character, so Brannoc's dialog listed "bond with Tomas Reeve", a thread owned by Mira (same account). The branch does not touch this file. Repro: one account, two characters with threads, open Pull Threads as one.
4. **Observation for the demo-fidelity reviewer:** deeds are named by the kindling situation's label ("Mission Theme · 8 Domination") unless staff author a `reason_text`; the demo shows the act's name ("Barred the overseers' door · 5 Domination").
5. **Observation:** Tomas counted as "here" for Mira's Fury while his player was not connected (he was listed under Objects, not Characters, in the room sidebar). Presence follows location, not a live session.
6. **Authoring requirements the screens depend on, as I hit them:** a fresh database has no strength tiers; the rite reads "not set up yet; tell staff" until a share exists for every outcome row (including Critical Failure). Both messages are the designed ones.
7. **Server log noise unrelated to #5124:** `/api/clock/` 503s while the server warms up; the `magic.anima_regen_daily` and roster activity sweeps fail on the empty database (missing Property and Roster rows); and a login auto-puppet `'NoneType' object has no attribute 'at_object_receive'` for factory-made characters with no home. No error appeared on any kindled, reflection, rite or pull request.
8. A scene ends when its last player leaves, so Screen 1's sidebar panel (which needs a live scene) only shows while someone is in the room; fine, but a later re-run needs a second player connected.

## Files created or changed (all uncommitted)

- `src/integration_tests/live_seeds.py` (changed: `KindledSeed`, `seed_kindled_resonances_spec`, `seed_kindled_offering`)
- `frontend/e2e/kindled-resonances-5124.spec.ts` (new; serial, one pass per seed because the scenarios consume state)
- `frontend/e2e.rt5124.config.ts` (new; the backend config with the cached Chromium)
- `docs/reviews/5124/real-testing.md` (this file)
- `docs/reviews/5124/01-your-resonances-sidebar.png`, `02-telnet-resonances.png`, `03-telnet-aura.png`, `04-pull-payer-kindled.png`, `05-give-in-picker.png`, `05b-combat-rail-with-pull-and-give-in.png`, `06-after-submit.png`, `07-mission-option-feeds.png`, `08-mission-option-taken.png`, `09-tomas-view-after-mira-acts.png`, `10-reflecting-on-row.png`, `11-reflection-ready-to-post.png`, `12-pose-posted-reflection-recorded.png`, `13-tomas-sees-only-the-pose.png`, `14-sheet-aura-card-waiting-reflection.png`, `15-rite-dialog-no-offering.png`, `16-rite-dialog-with-offering.png`, `16-rite-dialog-with-offering-second.png`, `17-rite-result.png`, `17-rite-result-second.png`, `18-sheet-after-rite.png`, `19-second-reflection-recorded.png`, `20-sheet-after-both-rites.png`, `21-telnet-aura-after-rites.png`
- Scratchpad (outside the repo): `start-rt.sh`, `wait-start.sh`, `kindled-seed.json`, `readback.py` under `/tmp/claude-1000/-workspaces-arxii/f9b72c8d-5420-462d-b7e2-0639e5112f77/scratchpad/`.

## State left behind

The server is running on `rt_5124` (:4001 and :4002). The database is not dropped. Account `e2e_test_account` / `TestPass123!` plays Mira and Brannoc; `kindled_second_player` plays Tomas (password in the seed JSON). Mira's two deeds are reflected and settled, her offerings are spent, and Brannoc's round 1 is declared and not resolved.
