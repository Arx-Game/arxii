# Real-testing report: #4418 (GMs and Guides play major NPCs), round 2

**Form:** B, my own server and a real browser.
- Some steps went through the REST or dispatch endpoint the UI itself calls, from the signed-in browser. Each one is named below.
- Commit: `999ef9688`.
- Database: `rt_4418`, a throwaway built with `tools/build_schema.py` and the seed clusters (`ARXII_SEED_SAMPLE_CONTENT=1`). I dropped it at the end.
- I built the frontend first (`pnpm --dir frontend install`, `just fe-build`).
- I started the server only after both section-2 checks came back empty: `DATABASE_URL=... just start`, then a second `evennia start` because the first launcher timed out on the portal. I stopped it with `just stop`.
- Browser: Playwright Chromium, one worker. The temporary specs are deleted; a copy is at `/tmp/rt4418/rt-4418-round2.spec.ts.bak`.
- Run: 2026-10-19 03:06 to 03:36.
- Accounts:
  - `rt_staff`
  - `rt_gm`, a JUNIOR GM whose GM character is Ravenna
  - `rt_gm2`, a JUNIOR GM whose GM character is Corvin
  - `rt_guide`, PC Ilsa
  - `rt_player`, PCs Ysmay and Bram
- Rooms: Low Gate and The Lantern.
- Setup notes:
  - I made the accounts through `arx manage shell`, because `seed_test_account` fails as a management command in this container. That failure is old and not on this branch.
  - The factory PCs carried a Developer-only puppet lock, so I gave them the minted characters' lock.
  - An encounter with 3 Gate Guard mooks was made with factories, because `add_opponent` has no `OpponentTierTemplate` in the seed.
  - To keep the scene open between test runs, I kept Corvin connected in Low Gate the whole time (an "anchor" session).

## Round 1 in short

Round 1 (commit `b4aad49b8`) found ten bugs:
1. The cast panel never loaded: the endpoint answers a bare list and the panel read `.results`.
2. Describing a voiced crowd did not change the description shown.
3. A borrower's poses were recorded as written by the owner.
4. The room's live scene dropped out of `/game`. This hid the resist card and the NPC response card there.
5. After a loan ended, the Guide's page went stale and a new offer was hidden.
6. A JUNIOR GM could mint only one NPC.
7. The stat block list returned 500.
8. The owner had no screen to answer borrow requests or change settings.
9. A scene owner could not offer an NPC.
10. A played NPC left the room when its player disconnected.

The consent ruling, the resist card on `/scenes/<id>`, the lethality rule, the offer card, posing as a lent NPC and the roster all passed in round 1.

## Round 2 results

### Bug 1, the cast panel loads unmodified: PASS
- **Did:** as Ravenna, opened `/scenes/1` with nothing patched.
- **Saw:** the Cast section listed Captain Vael · Ravenna and Sergeant Mira · Ravenna (both NPC, with descriptions), and the crowd "Gate Guard · 3 · mooks" with Add crowd voice and Rename or describe.
- **Offer:** "Offer to Ilsa the Guide" on Mira gave the toast "Sergeant Mira is offered for Scene at Low Gate.", and the row then read "Sergeant Mira · Offered to Ilsa the Guide". Screenshot: `2-cast-panel-offered.png`.
- **New problem:** the panel sits in the scene page's narrow side column, and the NPC names are cut off. See new bug B.

### Bug 2, describing a crowd: PASS
- **Did:** Add crowd voice "The Gate Watch" (toast "The Gate Watch has a voice."). Then Rename or describe: name "The Low Gate Watch" and the description "Three tired guards in dented helms. / They look to Mira, not the captain."
- **Saw:** after a reload the crowd row read "The Low Gate Watch · 3 · mooks / Three tired guards in dented helms. / They look to Mira, not the captain."

### Bug 3, who is recorded as writing a lent NPC's lines: PASS (database read)
I read `Interaction.writer_account` in a shell:

| Pose | Played by | `writer_account` |
|---|---|---|
| Sergeant Mira, lent to the Guide | `rt_guide` | `rt_guide` |
| The Low Gate Watch, lent to the Guide | `rt_guide` | `rt_guide` |
| Captain Vael, borrowed by Corvin's player | `rt_gm2` | `rt_gm2` |
| Ilsa | `rt_guide` | `rt_guide` |
| Ysmay | `rt_player` | `rt_player` |

### Bug 4, the room keeps its scene on `/game`: PASS
- Ravenna pressed Start Scene. Her header showed "Scene: Scene at Low Gate / End".
- When Ysmay entered the room, the header was still there for all three viewers (GM, Guide-as-Mira, player).
- After "Create and add to scene" placed Vael and Mira, the headers were unchanged.
- **Server restart:** I stopped and started the server with Ravenna's page open. After it reloaded, her header still read "Scene: Scene at Low Gate", and the scene was still active in the database.
- **Resist card on `/game`:** PASS. Mira's deceive (sent by the Guide through the REST endpoint) came back pending, `resist_only: true`, check Con.
  - Ysmay's `/game` showed "Sergeant Mira acts against you. Resist? You roll Con." with the effort menu, Roll and "Believe Sergeant Mira". There were no Deny or Refuse buttons.
  - A Deny sent through the API was refused with 400 "You can resist this, but not refuse it."
  - Roll resolved it ("Sergeant Mira attempts to deceive Ysmay: Success").
  - Screenshots: `4a-player-resist-card.png`, `4b-player-after-roll.png`.
- **Romance:** Mira's flirt came back pending, `resist_only: false`. `/game` offered Deny, Deny & block, Accept and the difficulty buttons (`4c-player-romance-card.png`). Deny gave `denied`.
- **NPC response card:** FAIL. See new bug A.

### Bug 5, the Guide's page after take-back: PASS
- **Did:** the Guide had Mira's tab open and stayed connected. Ravenna pressed Take back in the cast panel; the toast said "Sergeant Mira is back with their owner."
- **Saw (within 35 seconds, no reload):**
  - The Guide's character list was "Ilsa" and the NPC tag was gone.
  - The page had moved to Ilsa and was still in world (`6-guide-after-take-back.png`). A leftover "Sergeant Mira" conversation tab stays in the session tab row; that is cosmetic.
- **New offer:** when Ravenna offered Mira again, the offer card appeared on the Guide's open page with no reload. It also appeared on a fresh `/game` visit, with the Guide in world as Ilsa (`6b-guide-sees-new-offer-after-loan-ended.png`).

### Bug 6, a JUNIOR GM mints two NPCs: PASS
- Ravenna, a JUNIOR GM (cap 2) with a GM character, made Captain Vael (Quick) and Sergeant Mira (Detailed).
- The second mint was not refused.
- "My NPCs (2)" lists only the two NPCs, not Ravenna.

### Bug 7, the stat block list: PASS
- `GET /api/roster/npc-presets/` returned 200 with 4 presets.
- The Detailed form's Stat block list showed "— | Courtier | Guard | Innkeeper | Investigator".
- My first read happened before the list loaded, so `1b-npc-form-detailed.png` shows "—".

### Bug 8, the owner's Manage panel: PASS
- **Settings:** on the GM dashboard, "Manage Captain Vael" opened the owner panel. I ticked "List on the NPC roster", set "Me, and anyone I lend them to" and "Any GM or Guide", and pressed Save settings. Toast: "Saved the settings for Captain Vael."
- **Borrow request:** as Corvin's player, on `/gm/npcs`, Ask to borrow Vael gave "Asked to borrow Captain Vael."
- **Approval:** the owner's panel then showed "Corvin asks to borrow Captain Vael" with Approve and Decline (`1d-owner-manage-panel.png`). Approve gave "Captain Vael is lent out."
- **Playing:** the borrower's list held Corvin and Captain Vael, and Corvin's player posed as Vael from the CV tab (`1c-borrower-plays-vael.png`).
- **Roster:** `1c-npc-roster.png` shows both NPCs with "Owner Ravenna · lends on request to GMs and Guides".
- **Copy as new:** copying Mira as "Sergeant Olwen" made an NPC owned by Corvin, with empty notes.

### Bug 9, a scene owner can offer: PASS
Ravenna started the scene with the normal Start Scene button and was not made its GM. Her offers from the cast panel succeeded.

### Bug 10, NPCs stay in the room and empty scenes finish: PARTLY PASS
- **NPCs stay:** PASS. After take-back, and after every borrower and owner disconnected, Mira, Vael and The Low Gate Watch were all still in Low Gate. They stayed in the cast list.
- **Played NPC keeps the scene open:** PASS. The Guide was playing Mira and the GM left; the scene stayed active.
- **Only unplayed NPCs left:** FAIL in one case; see new bug C.
  - When the last person to leave is the Guide letting go of Mira, the scene stays active even though only unplayed NPCs remain.
  - Control, PASS: a PC (Ysmay) entering and leaving afterwards finished it (`is_active: false`).
  - The scene-scoped loans (Mira, the crowd) ended, and all three NPCs stayed in the room.

### Other behaviours
- **1. No consent wait for NPCs:** PASS (REST). Persuade at Sergeant Mira (Guide-played) came back `resolved` (requests 4 and 5).
  - I could not use the persona menu; see new bug D.
- **3. Killing:** PASS, by calling the service in a shell while both loans were active:

  | Victim | Attacker | Death allowed |
  |---|---|---|
  | Sergeant Mira | Ysmay | True |
  | Captain Vael | Ysmay | True |
  | Ysmay | Ilsa | False |
  | Ysmay | Sergeant Mira | True |
  | Ravenna (GM character) | Ysmay | False |

  BLOCKED in combat: the seed has no `OpponentTierTemplate`.
- **4/5. Hand-off and parallel play:** PASS.
  - The offer card read "Sergeant Mira, offered by Ravenna", the scene title, both paragraphs of notes, and Accept and Decline (`3a-guide-offer-card.png`).
  - After Accept the Guide had Ilsa and Sergeant Mira, and Mira's tab carried the NPC tag and the notes card.
  - The Guide started a scene in The Lantern and posed as Ilsa there (`5a-...`), then posed as Mira in the Low Gate scene (`5b-...`). Each pose was saved in its own scene.
  - Scene end returns the NPC (the loans above ended when the scene finished).
- **7. NPC form:** PASS, apart from the portrait.
  - Quick and Detailed both worked, including the section "Copy from" and the notes and lending fields (`1a-...`, `1b-...`).
  - Save as template by a plain JUNIOR GM gave "Saved as a template."
  - Portrait upload: BLOCKED: external service. It would upload to the real Cloudinary account, so I did not upload.
- **8. Crowd:** PASS.
  - The crowd offer card showed. After Accept the Guide had Ilsa, Sergeant Mira and The Low Gate Watch, with NPC and CROWD tags (`3d-guide-crowd-tab.png`).
  - The Guide posed as the crowd (`8-guide-poses-as-crowd.png`), and `writer_account` recorded `rt_guide`.
  - Screenshot `2-cast-panel-npcs-and-crowd.png`.
- **Required content dashboard:** PASS. Before staff set the resist checks, Deceive and Flirt were listed under "Resist checks for NPC-started actions". After, they were gone.

## New bugs found in round 2

**A. The NPC response card never appears in real play.**
- `pendingNpcResponse` looks for a row that has `action_links` and also lists the NPC's persona in `target_persona_ids`. No row ever has both:
  - The resolved action rows (here interactions 7 and 8, "Ysmay attempts to persuade Sergeant Mira") do target Mira, but they have no `action_links`.
  - The player's next pose carries those actions as attachments: the composer showed "Attaching: Ysmay attempts to persuade Sergeant Mira", and `InteractionAction` linked pose 9 to actions 7 and 8. That pose has `target_personas = []`.
- Repro:
  1. Lend an NPC and have the Guide open its tab.
  2. A PC persuades the NPC, then posts a pose.
  3. The Guide's `npc-response-card` count is 0. I saw this in three runs.
- Screenshot `3b-guide-npc-tab-notes-response.png` shows the NPC tab and the notes card, with no response card.

**B. The cast panel's NPC names are unreadable in the scene page's side column.**
- At its real width (about 360px) the row's name is cut to nothing ("C", or blank for Mira).
- The "Played by" control takes most of the row, and descriptions wrap one word per line (`2-cast-panel-offered.png`).
- The demo's Screen 2 shows names and players side by side. This is a layout fix.

**C. A scene where only unplayed NPCs are left does not finish when the last person to leave was playing an NPC.**
- Story NPCs no longer leave the grid on unpuppet, so `maybe_finish_empty_scene` never runs when a borrower lets go.
- Repro:
  1. The encounter has ended, the GM has left, and the Guide is playing Mira in the scene.
  2. The Guide disconnects.
  3. The scene stays `is_active: true`, with only Mira, Vael and the crowd voice in the room.
- It closes only when some PC later leaves the room.
- The empty-scene check should also run when a story NPC is unpuppeted.

**D. Older than this branch: the persona menu's social actions do nothing on `/game`.**
- Persona menu → Persuade → "Default (pose)" posts `{"scene":1,"action_key":"persuade","target_persona":7}`.
- The server answers 400 `{"detail":"initiator_persona is required."}`, and the UI shows no error.
- The check is `action_views.py:398`, from #2228 (July), and this branch does not touch it.
- A player can't start persuade, deceive and the rest from the menu, so I sent those actions through the REST endpoint.

Minor:
- After take-back, a stale "Sergeant Mira" conversation tab is left in the Guide's session tab row.
- The renamed crowd's bodies still show as "Gate Guard" in the room's object list.

## BLOCKED
- Portrait upload: BLOCKED: external service (the real Cloudinary account).
- A killing blow in combat: BLOCKED: content (no `OpponentTierTemplate` seeded). I checked the death rule with the service instead.

## Evidence files (this folder, all from round 2)

1a-npc-form-quick.png, 1b-npc-form-detailed.png, 1c-npc-roster.png, 1c-borrower-plays-vael.png,
1d-owner-manage-panel.png, 2-cast-panel-offered.png, 2-cast-panel-npcs-and-crowd.png,
3a-guide-offer-card.png, 3b-guide-npc-tab-notes-response.png (no response card: bug A),
3d-guide-crowd-tab.png, 4a-player-resist-card.png, 4b-player-after-roll.png, 4c-player-romance-card.png,
5a-guide-as-ilsa-lantern.png, 5b-guide-as-mira-low-gate.png, 6-guide-after-take-back.png,
6b-guide-sees-new-offer-after-loan-ended.png, 8-guide-poses-as-crowd.png, admin-grant-guide.png.

---

# Round 3 (targeted), commit `4c45dc6c5`

This round re-checked the round-2 bugs A to D and the minor items.

**How:** Form B with my own server and a real browser.
- Database `rt_4418`, rebuilt and dropped at the end.
- I rebuilt the frontend with the working tree clean.
- I started the server after both section-2 checks were empty, and stopped it with `just stop`.
- I made the encounter bodies with factories in a shell while the test waited.
- The temporary spec copy is at `/tmp/rt4418/rt-4418-round3.spec.ts.bak`.
- Run: 2026-10-19 03:52 to 04:05.

**A note on the commit:** when I started, the bug-A fix (`pendingNpcResponse.ts`, `NpcResponseCard.tsx` and their tests) was edited in the worktree but not committed. It was committed as `4c45dc6c5` before I built, so this round tested committed code. `rt-fix-b-report.md` names `999ef9688` for this fix, but that commit does not contain it.

## Results

**A. The NPC response card on `/game`: PASS.**
- The Guide accepted Mira, opened her tab and posed as Mira.
- Ysmay used the persona menu on `/game`: Persuade, then "Default (pose)".
- The Guide's sidebar then showed a card headed "Ysmay attempts to persuade Sergeant Mira: Partial Success", with a "Pose as Sergeant Mira" button (`3b-guide-npc-tab-notes-response.png`).
- Pose as filled the composer. After the Guide posted as Mira, the card count went from 1 to 0 (`3c-guide-replied-as-mira.png`).

**B. The cast panel in the side column: PASS.**
- At the panel's real width (360px), every row shows the full name and who plays it: "Captain Vael · Ravenna", "Sergeant Mira · Offered to Ilsa the Guide", "The Low Gate Watch · 3 · mooks".
- The play select sits under the name (`2-cast-panel-offered.png`).

**C. A Guide playing a lent NPC is the last player and disconnects: PASS.**
- Ravenna started a new scene and lent Mira. The Guide accepted and opened Mira's tab, and Ravenna disconnected. The scene stayed active, which is right because Mira was being played.
- When the Guide disconnected, the scene finished (`is_active: false`). The loan was `ended`, and Mira stayed in Low Gate.
- My first attempt did not test this. The seed had left Corvin, a GM character nobody was playing, standing offline in Low Gate, and he counts as a PC. Once Corvin logged in and out, he left the grid, and the scene ended at once (only unplayed NPCs were left). I then ran the clean case above.

**D. Persona-menu Persuade on `/game`: PASS.**
- The menu now posts with `initiator_persona`. The server answered 201: `persuade` from Ysmay to Sergeant Mira, `resolved`.
- No refusal came up, so the new error toast was not exercised.

**Minor: stale tab after take-back: PASS.** About 35 seconds after Take back, the Guide's page had no "Sergeant Mira" tab or button left, and showed Ilsa in The Lantern (`6-guide-after-take-back.png`).

**Minor: the renamed crowd's bodies: PASS on the server, not shown in the browser.**
- After Rename or describe ("Gate Wardens"), all three `CombatOpponent` bodies have `ObjectDB.key = "Gate Wardens"`.
- I could not show the room list using the new name. The bodies were made by factories outside the server process, so the room list either showed their old names or did not list them. A real `add_opponent` call needs an `OpponentTierTemplate`, and the seed has none.

**1b screenshot.** Retaken after the Stat block list loaded ("— | Courtier | Guard | Innkeeper | Investigator"), with Guard selected (`1b-npc-form-detailed.png`).

## New finding (round 3)

**E. In the Guide's `/game` feed, each pose shows twice.**
- On Mira's tab, every pose appears once as the pose line and again just below it as a "✦" note line. For example, "Mira plants herself in front of the gate..." and "Ysmay holds up the forged orders..." each appear twice.
- "This happened to you." and the persuade outcome also appear as notes (`3b-guide-npc-tab-notes-response.png`).
- The round-2 shot of the same view (taken before `30d0fa35d` and `4c45dc6c5`) did not show the doubled pose lines.
- I did not find the cause. It may be the lent NPC's session receiving the plain-text copy that non-web sessions get. Repro: lend an NPC to a Guide, have the Guide open its tab, have anyone pose in the room, then look at the Guide's feed.

---

# Round 4 (screenshots for the demo-fidelity re-check), commit `5f0a8ab8d`

**How:** Form B, with my own server on `rt_4418` and a fresh frontend build. I started the server after both section-2 checks were empty and stopped it with `just stop`, then dropped the database. Pages were captured with Playwright at 1400x1000 in the light theme. A copy of the spec is at `/tmp/rt4418/rt-4418-round4.spec.ts.bak`.

**Extra seed data, made in a shell:**
- Two personality traits:
  - Proud: "Flattery about their rank lands; slights do not.", which eases Persuasion.
  - Greedy: "Coin talks; principle does not."
- A staff character, Warden Osk, so staff could run `py` and `who`.
- The encounter, made with factories while the test waited.

Staff granted the Guide role on the rebuilt add form, which has no "Granted by" field; it is set on save.

## Screenshots retaken (all from this run)

- **1a-npc-form-quick.png:** the Quick form with a name and a description.
- **1b-npc-form-detailed.png:** the Detailed form after the Stat block list had loaded ("— | Courtier | Guard | Innkeeper | Investigator"), with Guard picked.
  - The Copy Description from field is set to Captain Vael.
  - Powers is filled: strength 3, presence 3, wits 2, and Melee Combat 2 and Performance 2 in Skills. The Path list has no paths because the seed has no magic content.
  - "What works on them" shows Easier: Proud with its note ("Flattery about their rank lands; slights do not. Eases Persuasion."), and Harder: Greedy ("Coin talks; principle does not.").
  - Notes, roster listing and lending are filled in.
  - After saving, the NPC's detail returns both preferences.
- **1c-npc-roster.png:** the roster as seen by Corvin's player.
- **1c-borrower-plays-vael.png:** the borrower's GM character tab "C" (Corvin) has no NPC tag. Only Captain Vael's tab has one. PASS.
- **1d-owner-manage-panel.png:** "Corvin asks to borrow Captain Vael" with Approve and Decline.
- **2-cast-panel-offered.png** (Mira "Offered to Ilsa the Guide") and **2-cast-panel-lent.png**: lent rows with Take back placed under the name.
- **3b-guide-npc-tab-notes-response.png:** the NPC tab with the notes card, and the response card "Ysmay attempts to persuade Sergeant Mira: Partial Success" with "Pose as Sergeant Mira". Each pose shows once.
  - The card has no excerpt line under the heading. The heading is the resolved action's own text.
- **4a-player-resist-card.png:** the resist card with Roll and Believe, and no Deny.
- **4c-player-romance-card.png:** the romance card. Its buttons now wrap onto a second row ("No way" drops below). PASS.
- **admin-guide-profile.png:** the Guide's change page.
  - "Right now: Sergeant Mira · Ravenna · Scene at Low Gate · Return to GM".
  - "Last 30 days: 2 accepted, 1 declined, 1 taken back early".

The older screenshots not listed here (3a, 3c, 3d, 4b, 5a, 5b, 6, 6b, 8, 2-cast-panel-npcs-and-crowd, admin-grant-guide) are from earlier rounds and still match.

## Doubled lines check

- **Poses:** each pose appears exactly once on every web session. I counted on the Guide (Mira tab), the player and the GM: "Mira plants herself..." 1 each, "Ysmay holds up the forged orders..." 1 each. PASS.
- **Server sessions while the Guide's Mira tab was open,** listed with `py` as staff:
  `[(15, 'websocket', 'rt_guide', 'Sergeant Mira'), (16, 'websocket', 'rt_staff', 'Warden Osk')]`.
  The Guide has one websocket session puppeting Sergeant Mira. There is no telnet session.
- **Still doubled: the action outcome.** On the Guide's Mira tab, the outcome shows once as the "THIS HAPPENED TO YOU" block. It shows again as two "✦" note lines, "This happened to you." and "Ysmay attempts to persuade Sergeant Mira: Partial Success" (`3b`).
  - The player's page shows the same outcome as the action block and again as a "✦" note (`4c`).
  - Every session here was websocket, so these notes are text frames sent to web sessions. They are not a telnet copy.
  - This affects the target's and the initiator's pages alike. See new bug G.

## New bugs found (round 4)

**F. Answering an offer from an NPC tab is refused with 403.**
- While the Guide has a lent NPC's tab active, the offer card's Accept or Decline posts to `/api/actions/characters/<the NPC's character id>/dispatch/`.
- The server answers 403 "You do not have permission to perform this action." The card stays, and the toast shows that message.
- From the Guide's own PC tab, the same Decline works.
- Repro: lend NPC A to a Guide and have them open A's tab. Offer them NPC B, then press Decline or Accept on B's card.

**G. A resolved action is also sent to web sessions as "✦" text notes.**
- The outcome already shows as the action block. The extra notes are "This happened to you." (to the target's player only) and the outcome line.
- I saw this on the target's page (the Guide on Mira's tab) and on the initiator's page (Ysmay).

**H. The cast panel calls a GM borrower a Guide.**
- Vael's row reads "Captain Vael · Corvin (Guide)". Corvin borrowed Vael from the roster as a GM and has no Guide role.
- `playedByText` appends "(Guide)" to every loan.

---

# Round 5 (short), commit `b9c745f76`

**How:**
- Form B, with my own server on `rt_4418` and a fresh frontend build.
- I started the server after both section-2 checks were empty, stopped it with `just stop`, and dropped the database.
- Playwright ran in the light theme at 1400x1000. A copy of the spec is at `/tmp/rt4418/rt-4418-round5.spec.ts.bak`.
- For the telnet check I used a raw socket client on port 4000. It logged in as `rt_player`, ran `ic Ysmay`, and recorded every byte to `/tmp/rt4418/telnet2.log`.

The same seed as round 4 was used. Ravenna is a JUNIOR GM, which allows 2 story NPCs, so staff raised her to experienced in GMProfile admin before she minted a third NPC, "Watchman Pell". The round-4 shots 1a, 1b, 1c and 1d were retaken in this run at the same commit and show the same things.

## Results

**F. Answering an offer while a lent NPC's tab is active: PASS.**
- The Guide was on Sergeant Mira's tab when Ravenna offered Watchman Pell, and the offer card showed there.
- Decline posted `/api/actions/characters/7/dispatch/`, which is Ilsa, the account's own character. The answer was 200 "You turn down Watchman Pell." with status `declined`, and the card went away.
- Pell was offered again and Accept, from the same tab, gave 200 "You take up Watchman Pell." with status `active`. The Guide's list became Ilsa, Sergeant Mira and Watchman Pell.

**G. A resolved action shows once on web pages, and telnet still gets the text: PASS.**
- After Ysmay's persuade landed on Mira, each page had **no "✦" note lines**.
  - Guide (Mira tab): 0 "This happened to you" notes. The one count is the "THIS HAPPENED TO YOU" block heading. The outcome text shows twice, once in the action block and once as the response card heading.
  - Player: the outcome shows once, in the action block.
  - GM: the outcome shows once, in the action block.
- The telnet session playing Ysmay (logged in as `rt_player`, in the same room) received the line `Ysmay attempts to persuade Sergeant Mira: Failure`, then `Ravenna (GM) has left the game.`

**H. The cast panel labels each borrower by role: PASS.**
The lent rows read:
- "Captain Vael · Corvin (GM)", borrowed from the roster.
- "Sergeant Mira · Ilsa the Guide (Guide)"
- "Watchman Pell · Ilsa the Guide (Guide)"

Each lent row has Take back under it (`2-cast-panel-lent.png`).

**3b, the response card's excerpt: FAIL (new bug I).** The card shows "Ysmay attempts to persuade Sergeant Mira: Partial Success" and "Pose as Sergeant Mira", but `npc-response-excerpt` was not rendered (count 0). See `3b-guide-npc-tab-notes-response.png`.
- That shot shows two "Mira plants herself..." lines. Those are two separate posts I made in two runs, not a doubled line.

## New bug (round 5)

**I. The response card's excerpt never appears on the Guide's live page.**
- The database has the link: `InteractionAction(pose 5 → action 4)`. Pose 5 is Ysmay's text pose, "Ysmay holds up the forged orders... / She sets them on the barrier where Mira can read the seal.", and action 4 is the persuade aimed at Mira.
- On the Guide's open `/game` page (Mira's tab), Ysmay's pose came in with no attached-action chip, and the card had no excerpt.
- `poseCarryingAction` looks for a row whose `action_links` names the action. That pose's links seem to be missing from the payload the Guide's session received.
- The player's own page did show the attachment chip on that pose in earlier rounds.
- I did not try reloading the Guide's page; the scene had ended before I could.
- Repro:
  1. Lend an NPC to a Guide and have the Guide open its tab.
  2. A player uses Persuade on the NPC from the persona menu ("Default (pose)").
  3. The player posts a pose with text; it carries the attachment.
  4. On the Guide's page the response card has no excerpt.

---

# Round 6 (very short), commit `9cb5c729b`

This round re-checked bug I: the excerpt on the Guide's response card, and the attached-action chip arriving live on other viewers' pages.

**How:** Form B, my own server on `rt_4418` and a fresh frontend build. Playwright ran in the light theme at 1400x1000. I stopped the server with `just stop` and dropped the database. A copy of the spec is at `/tmp/rt4418/rt-4418-round6.spec.ts.bak`.

**Container note:**
- My first server came up at 06:52 and was gone a minute later. Another session (`feature-4473`) ran `evennia start` at the same time.
- When I started again at 07:04, the two launches overlapped and neither came up cleanly.
- I then waited until both section-2 checks had been empty for a full 60 seconds, and started at 07:12 without trouble.

## Results

**Bug I: PASS.** I ran the round-5 repro:
1. Ravenna lent Sergeant Mira to the Guide from the cast panel.
2. The Guide accepted, opened Mira's tab and posed as Mira.
3. Ravenna had `/game` open and was not reloaded after this point.
4. Ysmay chose Persuade, then "Default (pose)", from the persona menu on Mira's pose. She then posted a two-paragraph pose that carried the action.

What I saw:
- **The Guide's response card**, without a reload, had:
  - the heading "Ysmay attempts to persuade Sergeant Mira: Failure";
  - the excerpt (`npc-response-excerpt`, count 1): "Ysmay holds up the forged orders. "The captain signed these." / She sets them on the barrier where Mira can read the seal.";
  - "Pose as Sergeant Mira".

  Screenshot: `3b-guide-npc-tab-notes-response.png`. It also shows the notes card and the NPC tab, and each pose appears once.
- **The GM's page**, also without a reload, showed the attached-action chip "Ysmay attempts to persuade Sergeant ..." on Ysmay's pose, above its text. The outcome appeared once as the action block.

**No new bugs.**

---

# Round 7 (screenshots and a fight), commit `c9b0a2483`

**How:**
- Form B, with my own server on `rt_4418` and a fresh frontend build.
- I started the server after the container had been fully free for 60 seconds, stopped it with `just stop`, and dropped the database.
- Playwright ran in the light theme at 1400x1000. A copy of the spec is at `/tmp/rt4418/rt-4418-round7.spec.ts.bak`.

**Extra seed, made in a shell before the server started:**
- `OpponentTierTemplate` rows:
  - mook: 10 health
  - swarm: 40 health, 8 bodies
  - elite: 1 health, so a single hit can finish the elite
- `DamageSuccessLevelMultiplier` rows at 1.00 for success levels -3 to 5.
- Two threat pools, "Gate Guard Pool" and "Rioter Pool".
- Ysmay made ready to fight: vitals, anima, fatigue, engagement, and a technique "Gate-breaker Strike" (effect power 30, rolled on Melee Combat).

**Done through the real paths:**
- Ravenna (scene GM via `/scene gm Ravenna`) dispatched `create_encounter`, then `add_opponent` three times for the "Gate Guard" mooks and once for "Rioters" (a swarm).
- Sergeant Mira was added as a persona-backed opponent by staff (Warden Osk). As the GM, the server refused with "Sergeant Mira is not a named NPC this story uses.": only a persona the encounter's story uses may stand, except for staff. This is the #4373 rule and is not part of this branch.

## Screenshots

- **E1 `4a-player-resist-card.png`:**
  - The Guide, as Mira, sent Deceive at Ysmay; the request was pending and resist-only.
  - Ysmay's `/game` shows "Sergeant Mira acts against you. Resist?", "You roll Con.", the effort menu, Roll, and "Believe Sergeant Mira". Deny buttons: 0.
  - Roll resolved it.
- **E2 `2-cast-panel-crowds.png`:** the 360px cast panel. No toast covers it; I waited for the toasts to clear. It shows:
  - Captain Vael · Ravenna
  - Sergeant Mira · Offered to Ilsa the Guide
  - the voiced mook crowd "The Low Gate Watch", with a "3 · mooks" chip and Offered to Ilsa the Guide
  - the swarm row "Rioters", with a "swarm · 8 bodies" chip and Add crowd voice / Rename or describe
- **E3 `3d-guide-crowd-tab.png`:**
  - The Guide accepted the crowd. The active tab is "The Low Gate Watch" with the CROWD tag and "Low Gate" under the name.
  - The other tabs show Ilsa (The Lantern) and SM (NPC).
  - The Guide's pose as the crowd is in the feed.
- **Kill `4d-pc-kills-npc.png`:** Mira, lent to and played by the Guide, stood as an elite opponent.
  - Ysmay joined (`/api/combat/2/join/`) and declared Gate-breaker Strike on her (`cast_technique`, deferred into the round). The GM began and resolved the rounds.
  - Round 1: "Ysmay's Gate-breaker Strike misses Sergeant Mira." and "Sergeant Mira (Elite)'s Spear thrust strikes Ysmay for 10 damage."
  - Round 2: "Ysmay's Gate-breaker Strike strikes Sergeant Mira for 30 damage, defeating them." Then "The field falls silent — victory. Sergeant Mira will trouble no one further. Ysmay stand victorious." and "Aftermath: Victory."
  - **Mira is defeated, not killed:**
    - The opponent row is `defeated` at -29 health, and the encounter ended in `victory`.
    - Mira's sheet `lifecycle_state` stayed `ALIVE`.
    - This matches the known behaviour on `main`: combat defeat never kills an NPC (the journey docstring says so). It is not caused by this branch. `death_is_permitted` for this pair is True (round 1).
  - The screenshot is the scene page (`/scenes/1`) scrolled to the defeat line. The `/game` feed did not stay at the bottom when captured.
- **`1b-npc-form-detailed.png`:** retaken. Stats read "Agility, Charm, Intellect, Presence, Stamina, Strength, Willpower, Wits" (title-cased), and skills show in full ("Melee Combat", "Performance", "Persuasion"). The stat block list was loaded (Guard picked), and the preference notes are visible.

## New findings (round 7)

**J. Any PC standing in the room when a scene starts becomes a co-owner, so a plain player gets the GM's cast panel.**
- On `/scenes/1`, the plain player `rt_player` saw the GM tools (Call Check, Award, Condition and so on), the Story Rail, and the Cast panel with the lend selects and Take back.
- The panel also showed the error "Could not load Guides.", because `/api/gm/guides/` refuses a non-GM.
- `SceneParticipation` for scene 1: `rt_player is_owner=True`. Ysmay was standing in Low Gate when Ravenna pressed Start Scene, and `add_present_as_co_owners` makes every present character with an account a co-owner.
- Co-ownership is older than this branch. What this branch adds is that the cast panel and its tools (crowd voice and describe, and offers since the round-2 owner ruling) now follow that same `viewer_can_gm` and co-owner gate.
- I did not try a player-run lend. `offer_npc` still requires the NPC's owner.
- Needs a call on whether the cast panel should be for scene GMs only. If players keep it, the panel should not show an error to them.

**K. "Aftermath: Victory." shows twice on the player's `/game`.** It appears once as the line and once as a "✦" note: "Aftermath: Victory. / ✦ / Aftermath: Victory.". This is the same kind of double as round 4's G, but for the encounter aftermath, which the G fix did not cover. The scene page shows it once.

Small, older than this branch: "Ysmay stand victorious." should read "stands".
