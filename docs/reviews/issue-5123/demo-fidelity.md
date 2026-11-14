# Demo fidelity review: #5123 "A character with several resonances" (round 2, after the fixes)

**Verdict: PASS** for everything rendered. All six defects from round 1 (F1 to F6) are
fixed and re-checked on screen, and the two divergences the fixes were meant to close
(the settled ring, the Gift thread in the Pull Threads dialog) now match the demo. What is
left is four open scope questions for the human (S1 to S4 below) and the BLOCKED items in
"Not exercised"; none of them is a rendered defect the fixes could have closed.

## Identity of what was reviewed

| Item | Value |
|---|---|
| Reviewed commit | `02979e9ea1d0f14612e5e703c4a63287213dbf2b` (branch `feature-5123-a-character-with-several-resonances-mixe`). It is the first parent of this evidence commit. Round 1 reviewed `29881d52b`; the fixes are `291592a07` and `02979e9ea`, on top of round 1's own evidence commit `4bf61de4b`. |
| Approved design | Demo, round 3: https://claude.ai/artifact/CghH6yiEwjFns6E8nLrs1Y (linked from the issue body). Read from the local copy of the published source, `issue-5123-several-resonances.html` (493 lines, read in full in round 1; re-rendered unchanged this round). |
| Issue rulings read | Issue body and comments (`gh issue view 5123`): spec rulings 15-18 and the Frontend list. No comment overrides the demo on any item below. The fix notes (`.superpowers/sdd/plan-5123/demo-fix-report.md`) were read for what was changed, not trusted for what renders. |
| Environment | Local workstation. Chromium headless shell (Playwright 1.65 driving the installed 1208 build). vite dev server on :5199 serving the real app code at the reviewed commit. No Evennia server, nothing on :4001/:4002, no database created (`rt_5123` was never made). |
| Viewport and theme | 1280 x 900, light theme, for the demo and the app. One dark pair for the unsettled aura. 390 x 900 for one Settle dialog shot. Web fonts could not load (no network), so serif/sans fallbacks stand in on **both** sides. |
| Fixture versus live | **Everything the app drew was fixture data**: every `/api/**` call answered by Playwright route fixtures shaped like the serializers (types from `frontend/src/generated/api.d.ts`; the CG fixtures are the repo's own `character-creation/__tests__/fixtures.ts`). The frontend code, CSS, routing, providers and React Query were real. No live backend answered any UI shot. |
| Real pages versus harness | Screen 1: the real `/characters/create` page, Gift stage. Screen 3 and the Accept-only dialog: the real `/characters/1` sheet, Magic section. Screen 2 (Pull Threads dialog, Pull picker) and Screen 4's scene dialog (Atone + Accept): **a throwaway harness** mounting the real `ThreadPullDialog`, `ThreadPullPicker` and `SettleAuraDialog` under the app's real providers and `index.css`, because those are reached in play only through combat or a live scene. |
| Capture sources | `capture-spec.ts.txt`, `capture-harness.tsx.txt`, `capture-config.ts.txt` in this directory (renamed `.txt` so no linter or runner picks them up). To rerun: copy the spec to `frontend/e2e/evidence/review-5123.spec.ts`, the harness to `frontend/src/review5123.tsx` plus a root `review5123.html` that loads it, start `pnpm exec vite --port 5199`, run Playwright with the config. |
| Backend check (Screen 5) | Not re-run this round: the fixes touch frontend files only (`git diff 4bf61de4b..HEAD --stat` lists no backend file). Round 1's run of `world.character_creation.tests.test_weighted_resonances` (16 tests, OK) stands for the rows. |
| Screenshots | All 37 PNGs in this directory were deleted and re-captured at the reviewed commit. `demo-*.png` come from the demo's own page, `app-*.png` from the app. The dialog Gift-thread case is in them: the fixture now offers the Gift thread and the spec ticks it. |

## Round 1 defects, re-checked

| # | Was | Now | Evidence |
|---|---|---|---|
| F1 | Sineater sentence read "Nearly all celestial, a tenth abyssal" beside a halo of about half celestial | **FIXED.** Reads "Half celestial, a tenth abyssal. A third of what you have gained came from the Mire." Same fixture (Celestial 56, Abyssal 44, a third from the Mire). The sentence now agrees with the halo; the key "your own / from the Mire" is under it. | `app-screen3-sineater.png` |
| F2 | Atone: the "turns to Fury" line below the halo and cramped; Begin the rite a right-aligned solid button | **FIXED.** The card opens "Perform the rite of atonement. The Domination you gained turns to Fury." in one paragraph; "Cap remaining 4" is a small muted line; "Begin the rite" is a left-aligned rust outline button (shown pale here because no component is picked, so it is disabled). The rite's controls are still between the halo and the button, ruled justified in round 1. | `app-screen4-scene-atone-and-accept-1280.png`, `-390.png` |
| F3 | Lone Accept card filled half of a two-column grid | **FIXED.** From the sheet the Accept card spans the dialog. With both exits they sit two-up at 1280 and stack at 390. | `app-screen4-sheet-accept-only.png`, `app-screen4-scene-atone-and-accept-*.png` |
| F4 | Accept and Not now black and neutral | **FIXED.** Accept is solid rust, Not now and Begin the rite are rust outlines, on the sheet route with no realm set (the state that failed). | `app-screen4-sheet-accept-only.png`, `app-screen4-sheet-after-accept.png` |
| F5 | "Your aura" below the sentence; sentence upright | **FIXED.** "YOUR AURA" is a small caps label above an italic sentence. | `app-screen1-resonance-step.png` |
| F6 | Plain text perk rows | **FIXED.** Each perk is a shaded bar, label left, value right-aligned, the narrative snippet a second line inside the bar. Applies in the dialog and the picker. | `app-screen2-dialog-fury-pays.png`, `app-screen2-picker.png` |
| S1 | `ThreadPullDialog` never offered a Gift thread | **FIXED.** The Pull Threads dialog lists "Pyromancy" (a Gift thread) with the other threads, and ticking it shows its Pay with list (Fury, Domination, Wonder) with the perks per resonance, the makeup line "Level 3 - mostly Fury, some Domination", Inspect perks, and the cost line. The request carried the payer (`payers: {"1": 13}`). | `app-screen2-dialog-initial.png`, `-fury-pays.png`, `-domination-pays.png`, `-inspect-perks.png` |
| S2 | Settled ring drawn in the settled affinities' colours | **FIXED.** One thin neutral dashed ring, as in the demo; while unsettled it is tinted in the glow of the affinity unsettling the character (the pink-violet ring in the unsettled frame, as in the demo's). Neutral on the settled and faded halos. | `app-screen3-*.png`, `app-dark-screen3-unsettled.png` |

## Open scope questions for the human (not counted as FAIL)

- **S1. The demo's "Lasts" row.** The Inspect perks panel in the demo shows "Lasts: until
  the end of the round" under a perk. The build has no such row, and `ResolvedPullEffect`
  carries no duration field. The issue never mentions it. It is an unbuilt demo
  affordance nobody wrote down: either add the field and the row or strike it from the
  approved design. (The panel also shows "Amount" where the demo says "Strength", and
  adds a "Worked out: 2 x 1" row; the demo flags its copy as placeholder.)
- **S2. Pull Threads dialog colours with no realm.** The dialog's selected tier and its
  confirm button render near-black in the harness, where the demo draws them rust. The
  dialog's primary is the realm's, and nothing sets a realm in the harness (the same
  cause as F4, which the fixes closed for the Settle dialog only). Whether a real game
  session has a realm set is not visible from here. If one can reach the dialog with none, it
  needs the same fallback.
- **S3. Step label on Screen 1.** Ruled acceptable in round 1 and still the case: the
  step is "Your Resonance" with the tag "Step 4 of 5" in the funnel; the demo's "IV -
  Resonance" label and separate h3 are not drawn. Not recorded in the spec.
- **S4. Atone preview.** The Atone card's mini halo draws who the character is, the best
  case of a full atonement; the rite's real result depends on the check. The demo draws
  the same picture. Noted.

## Visual checklist

`MATCH` = compared by eye, demo and app, same viewport and theme, and the same. `DIFF` =
differs (reason noted). `N/A` = demo annotation, not UI.

### Screen 1: Character creation, Gift stage (demo `demo-frame-01.png`, `demo-screen1.png`; app `app-screen1-10of10-1280.png`, `app-screen1-resonance-step.png`, `app-screen1-9of10-1280.png`, `app-screen1-complete-step-closed-1280.png`)

| Demo element | Result |
|---|---|
| Player-screen frame bar | N/A (demo chrome) |
| "IV - Resonance" step label | DIFF, ruled acceptable (S3): the app's step tag reads "Step 4 of 5" |
| "Your Resonance" heading | MATCH in words; it is the funnel entry name (S3) |
| Intro paragraph 1 ("Resonance is what powers your magic ...") | MATCH, word for word |
| Intro paragraph 2 ("Most people are moved by more than one thing ...") | MATCH |
| Budget line "10 of 10 placed" | MATCH (reads "9 of 10 placed" mid-spread) |
| Fury row: name, PRIMAL tag, - button, six pips, + button | MATCH (the buttons are grey outlines, not rust outlines; cosmetic, same as round 1) |
| Wonder row: one pip | MATCH |
| Domination row: ABYSSAL, three pips | MATCH |
| Mercy row: CELESTIAL, only a + button | MATCH (+ greyed at a full budget, a state the demo does not show) |
| Row description and codex line | MATCH (the demo says it left them out for space and "as today") |
| Halo, primal/abyssal with glow edges | MATCH (same proportions, colours, ring thickness) |
| "Your aura" label above the sentence | MATCH (F5 fixed) |
| Sentence "Mostly primal, a third abyssal." | MATCH, italic |

Tested interactions: from 9 of 10 placed (Fury 6, Wonder 1, Domination 2) pressed "More
Domination": the draft PATCH carried the new weights, the line read "10 of 10 placed", the
aura sentence moved from "a fifth abyssal" to "a third abyssal", the + buttons locked, and
the step closed itself as done; reopened by pressing the step name. No page errors.

### Screen 2: Pulling threads (demo `demo-frame-02.png`, `demo-frame-03.png`, `demo-screen2.png`; app `app-screen2-dialog-*.png`, `app-screen2-inspect-*.png`, `app-screen2-picker.png`)

| Demo element | Result |
|---|---|
| Title "Cast - Pull threads" | DIFF in wording only: "Pull Threads" (existing dialog title) |
| Tier 1 / 2 / 3, tier 2 selected | MATCH in behaviour; labels read "Tier 1", "Tier 2" |
| Gift thread "Pyromancy" with "Level 3 - mostly Fury, some Domination" | MATCH in the dialog and in the picker (S1 round 1 fixed) |
| "Pay with" label and three payers, starting on the leading one | MATCH (Fury selected first) |
| Payer row: radio, name, "3 Fury - you have 22" | MATCH, word for word |
| Fury perks: Bonus to this cast +4; Intensity +2 with its snippet | MATCH, shaded bars with right-aligned values (F6 fixed) |
| Domination perks: Cowed, Bonus +2 with snippet | MATCH; "Grants Cowed 2" where the demo says "Grants Cowed against your target 2" (placeholder copy) |
| Wonder: "No perks on this thread", no Inspect link | MATCH |
| "Inspect perks" link on Fury and Domination only | MATCH |
| Rival thread: "Pays with Domination", "3 Domination", "+3" | MATCH (fixed payer, no choice, shaded bar) |
| Preview line "3 Fury, 3 Domination - 4 anima" | DIFF in form: "Resonance cost: 3 Fury, 3 Domination   Anima cost: 4" (existing panel; amounts agree); with Domination chosen, "6 Domination" |
| Cancel / Pull | MATCH in layout; the confirm button reads "Select Pull"; colours DIFF (S2) |
| Inspect panel title "Domination through Pyromancy" | MATCH |
| Inspect rows: Strength, From, Thread level used, Lasts | DIFF: "Amount" for "Strength"; no "Lasts" row (S1) |
| Inspect "Thread level used: 2 (thread is 3; Domination is its second resonance)" | DIFF in wording: "(thread is 3; Domination is not its leading resonance)"; same facts |
| Inspect "From: Domination pull perk for Gift threads, tier 2" | MATCH |
| (not in demo) "Worked out: 2 x 1" row | Extra row the demo does not have |

Tested interactions: ticked the Gift thread and the Relationship thread; the mixed thread
expanded to the Pay with list and the one-resonance thread to "Pays with Domination" with
no choice; chose Domination; the next preview request carried `"payers":{"1":13}` and the
cost line moved from "3 Fury, 3 Domination" to "6 Domination"; opened Inspect perks on
Domination. Picker: tier 2 on the Gift thread shows the same Pay with list. No page errors.

### Screen 3: Character sheet, aura (demo `demo-frame-04..07.png`, `demo-screen3.png`; app `app-screen3-*.png`, `app-screen3-*-page-1280.png`, `app-dark-screen3-unsettled.png`, `demo-dark-frame-unsettled.png`)

| Demo element | Settled | Unsettled | Faded | Sineater |
|---|---|---|---|---|
| Halo, approved colours, glow edges | MATCH | MATCH | MATCH | MATCH (gold, violet, murk in the demo's order) |
| Dashed "who you are" ring | MATCH (thin neutral) | MATCH (tinted pink-violet, as the demo) | MATCH | MATCH |
| Words | MATCH "Mostly primal, a third abyssal." | MATCH, the ruled Unsettled line | MATCH "Nearly all primal, a trace of abyssal." at 94/6 (the demo's picture is 82/18, which its own thresholds would call "a fifth"; a demo inconsistency, not the build's) | MATCH in agreement with the halo (F1 fixed); wording "a tenth abyssal" where the demo says "a little abyssal of your own" |
| "Unsettled" status pill | n/a | MATCH | n/a | n/a |
| "Settle your aura" button | n/a | MATCH, rust (amber in dark) | n/a | n/a |
| Restless halo | n/a | MATCH (animated; none under reduced motion) | n/a | n/a |
| Key "your own / from the Mire" | n/a | n/a | n/a | MATCH |
| Sentence typeface | italic serif (F5 fixed) | same | same | same |

Colours: MATCH. The running pages resolve Celestial `#e6c55a`, Primal `#2f8a74`, Abyssal
`#5b2a6f`, Mire `#4b4a35`, with the demo's glows (`#fff1b8`, `#7fd1b9`, `#b0559a`,
`#8a8660`), read off `getComputedStyle(:root)`; the CG halo's computed `background-image`
is a conic gradient in `rgb(47,138,116)`, `rgb(91,42,111)` and `rgb(127,209,185)`. The
tokens reach both pages because `AuraHalo` imports `sheet.css`.

Dark theme (unsettled): halo, ring, pill and amber button MATCH the demo's dark frame.
Tested interactions: opened the sheet's Magic section for four auras; the Unsettled aura's
button opens the dialog.

### Screen 4: Settle your aura (demo `demo-frame-08.png`, `demo-screen4.png`; app `app-screen4-scene-atone-and-accept-1280.png`, `-390.png`, `app-screen4-sheet-accept-only.png`, `app-screen4-sheet-after-accept.png`)

| Demo element | Result |
|---|---|
| Dialog heading, the Unsettled sentence | MATCH |
| Atone card heading "Atone" | MATCH |
| "Perform the rite of atonement. The Domination you gained turns to Fury." | MATCH (F2 fixed; one paragraph) |
| Mini halo and "Mostly primal, a third abyssal." in the Atone card | MATCH, italic |
| "Begin the rite" outline button, left | MATCH in position and style (F2 fixed) |
| Rite controls (not in the demo) | Present: cap remaining, source chip, amount, component pills, rate line. Today's rite; justified |
| Accept card heading "Accept the changes to your Aura" | MATCH |
| "You become more abyssal." | MATCH |
| Mini halo with the accepted aura and its sentence | MATCH ("Mostly primal, half abyssal." where the demo says "much of it abyssal"; the words come from the shared thresholds) |
| "Accept" solid rust button, left | MATCH (F4 fixed) |
| "Not now" rust outline, bottom right | MATCH (F4 fixed) |
| Outside a scene: Accept and Not now only | MATCH (F3 fixed: the Accept card is full width) |
| Exit arrangement | Two-up at 1280, stacked at 390; the demo's frame stacks them (the demo's own grid is auto-fit) |

Tested interactions: from the sheet pressed "Settle your aura": only the Accept exit
shows; pressed Accept: one POST to `/api/magic/character-auras/42/accept/` and the result
line "You settle into who you have become." showed. The fixture does not change the aura
after accept, so the redraw to a settled halo is **not** evidenced here. In the scene
harness both exits show.

### Screen 5: What creation and play write (data)

Unchanged by the fixes (no backend file in the diff since round 1). Round 1's result
stands: creation writes one `CharacterResonance` per pick at balance 0 plus a
`CHARACTER_CREATION` ledger row each; a `CharacterAuraShare` per affinity with the settled
share equal to the weights (Primal 70/70, Abyssal 30/30); and a Gift thread at level 0
holding a zero-amount `ThreadResonance` row per pick, heaviest leading. **MATCH**, with the
round 1 notes (the ledger row and the zero-amount rows are not in the demo's table).
Imbuing, Pull, Sineating, Atone and Accept rows were not reviewed here.

## Mandatory criteria

| Criterion | Verdict |
|---|---|
| Exact reviewed commit named | PASS |
| Approved design reachable and read in full | PASS |
| Rendered the built surfaces (not source reading) | PASS (fixture data; see boundary table) |
| Screenshots committed beside this report | PASS (37 PNGs, all re-captured at the reviewed commit) |
| Rules reach the page (finding 1): approved aura colours; halo, ring and dialog CSS | PASS. Tokens resolved on the running pages; the Settle dialog's rust now reaches the page with no realm set. Run on the vite dev server, not the production bundle. |
| Host CSS contract (finding 2) | PASS for CG (`cg.css`), the sheet and the Settle dialog. The Pull Threads dialog's colours with no realm are S2. |
| Layout the demo shows (finding 3) | PASS (F2, F3, F6 fixed) |
| Approved copy dropped (finding 4) | PASS with notes: intro, "Pay with", cost lines, "No perks on this thread", the Unsettled line, the Atone/Accept headings, the Atone opening line are all present. The remaining wording differences are placeholder-flagged ("against your target", "Strength", "second resonance", "Pull"). |
| Demo affordance silently unbuilt (finding 5) | OPEN: the "Lasts" row (S1), unrecorded in the spec. The Gift thread in the dialog is now built. |
| Divergence the build got right (finding 6) | Accepted: funnel step label (S3), the rite's controls |
| Screen 1 verdict | **Matches** (cosmetic gaps only) |
| Screen 2 verdict | **Matches with noted gaps** (S1, S2; placeholder wording) |
| Screen 3 verdict | **Matches** |
| Screen 4 verdict | **Matches** (the rite's own controls are extra, justified) |
| Screen 5 verdict | **Matches** |

## Not exercised (BLOCKED, never inferred as pass)

- **BLOCKED: live backend.** No Evennia server was started; no UI shot used a real API
  response. The wire shapes come from the generated types and the repo's fixtures.
- **BLOCKED: the live scene and game pages.** The pull dialog (combat) and the Settle dialog
  with an open Atone offer (scene page via `DriftConversionOfferGate`) were mounted in a
  harness. The auto-open strip ("Settle your aura" call-out) was not drawn.
- **BLOCKED: production bundle.** The vite dev server was used.
- **BLOCKED: post-Accept redraw** (the fixture does not change the aura).
- Telnet `aura`, `aura atone`, `aura accept` are not UI and were not compared.
- Fonts: Cinzel and EB Garamond could not load, so type sizes were compared, not faces.

## Proposed mechanical companions

- The round 1 proposals stand and the fixes added the first two as vitest cases
  (Sineater sentence equals `shareInWords` of the halo's part; the lone Accept exit not in a
  two-column grid), per the fix notes. Not re-run here.
- A style test that, for every `--aura-*` token and every `aura-halo*` / `resonance-*` /
  `aura-settle-dialog` class the three surfaces emit, asserts a rule exists in the CSS reached
  from the rendered page's imports (the shape of `BuilderStylingTest`).
- If S2 is confirmed, a test that renders `ThreadPullDialog` outside any realm and asserts
  the confirm button's computed colour is the folio primary, not the shadcn default.
