# Demo fidelity review: #5123 "A character with several resonances"

**Verdict: FAIL** (defects below; no BLOCKED criterion hides a pass). Nothing here is a
rewrite of the design: every FAIL is a place where the built surface disagrees with the
approved demo and nothing later in the issue overrides the demo.

## Identity of what was reviewed

| Item | Value |
|---|---|
| Reviewed commit | `29881d52b78db8efb8619966e3282e4539794f8d` (branch `feature-5123-a-character-with-several-resonances-mixe`, rebased on origin/main). This is the first parent of the evidence commit. |
| Approved design | Demo, round 3: https://claude.ai/artifact/CghH6yiEwjFns6E8nLrs1Y (linked from the issue body, "Demo (approved direction, round 3)"). Read from the local copy of the published source, `issue-5123-several-resonances.html` (493 lines, read in full). |
| Issue rulings read | Issue body and comments (`gh issue view 5123`). Spec rulings 15-18 (intro text, spec'd halo, Unsettled wording) and the Frontend list. No comment overrides the demo on any item below. |
| Environment | Local workstation, Chromium headless shell (Playwright 1.65 driving the installed 1208 build), vite dev server on :5199 serving the real app code at the reviewed commit. No Evennia server, no :4001/:4002, no database created (`rt_5123` was never made; `dropdb --if-exists` confirmed). |
| Viewport and theme | 1280 x 900, light theme, for the demo and the app. One dark-theme pair for the unsettled aura. Web fonts could not load (no network), so serif/sans fallbacks stand in on **both** sides. 390 x 900 for one Settle dialog shot. |
| Fixture versus live | **Everything the app drew was fixture data.** Every `/api/**` call was answered by Playwright route fixtures shaped like the serializers (types from `frontend/src/generated/api.d.ts`; the CG fixtures are the repo's own `character-creation/__tests__/fixtures.ts`). The frontend code, CSS, routing, providers and React Query were real. No live backend was exercised for any UI shot. |
| Real pages versus harness | Screen 1: the real `/characters/create` page, Gift stage. Screen 3 and the Accept-only dialog: the real `/characters/1` sheet, Magic section. Screen 2 (Pull Threads dialog, Pull picker) and Screen 4's scene dialog (Atone + Accept): **a throwaway harness** that mounts the real `ThreadPullDialog`, `ThreadPullPicker` and `SettleAuraDialog` under the app's real providers and `index.css`, because those are reached in play only through combat or a live scene. See "Not exercised". |
| Capture sources | `capture-spec.ts.txt`, `capture-harness.tsx.txt`, `capture-config.ts.txt` in this directory (renamed `.txt` so no linter or test runner picks them up). To rerun: copy the spec to `frontend/e2e/evidence/review-5123.spec.ts`, the harness to `frontend/src/review5123.tsx` plus a root `review5123.html` that loads it, start `pnpm exec vite --port 5199`, run Playwright with the config. |
| Backend check (Screen 5) | `just test-fast world.character_creation.tests.test_weighted_resonances`: 16 tests, OK, run at the reviewed commit. Its assertions, not its pass count, are what is compared below. |

Screenshots are committed beside this report. Demo images are rendered from the demo's
own page at the same viewport and theme (`demo-*.png`); app images are `app-*.png`.

## Defect list (FAIL items)

| # | Screen | Finding | Where |
|---|---|---|---|
| F1 | 3 (Sineater) | The aura sentence contradicts the halo it sits beside. Fixture: Celestial 56, Abyssal 44, a third of everything from the Mire. The halo draws half celestial, a little own-abyssal, a big Mire stretch (correct). The sentence says "Nearly all celestial, a tenth abyssal. A third of what you have gained came from the Mire." The demo says "Half celestial. A little abyssal of your own, and a darker share taken from the Mire." Cause: `AuraHalo` lifts the Mire out of the Abyssal share (`splitMire`), then builds the sentence from the shares left over (`auraSentence(own)`), so every share is read against a smaller whole than the halo uses. | `frontend/src/magic/components/AuraHalo.tsx` (`splitMire`, `split`), `frontend/src/magic/aura.ts` (`auraSentence`) |
| F2 | 4 (Atone card) | The Atone exit puts the line "The Domination you gained turns to Fury." **after** the halo and squeezes it into a 5-line column beside "Cap remaining 4"; the demo makes it the second sentence of the exit's opening line. "Begin the rite" is a right-aligned solid button (greyed until a component is picked); the demo draws it as a left-aligned outline button. Wording, order and cramp are the defect. (See ruling R4: the rite's controls themselves are not.) | `SettleAuraDialog.tsx` (`CapBlock`, the `settle-exit-atone` section) |
| F3 | 4 (opened from the sheet) | With only the Accept exit, its card fills the left half of a two-column grid and the right half is empty. The demo's frame shows the exit full width. | `SettleAuraDialog.tsx` (`grid gap-3 sm:grid-cols-2` with one child) |
| F4 | 4 (colour of actions) | In the Settle dialog "Accept" and "Not now" render near-black / neutral, while the demo draws rust (`Accept` solid rust, `Not now` rust outline) and the sheet's own "Settle your aura" button beside it is rust. The dialog portals outside `.refsheet`, which carries the rust fallback ("the sheet route never establishes a realm", `sheet.css`), so a visitor with no realm set reaches this. | `SettleAuraDialog.tsx`, `character_sheets/sheet.css` (`:root:not([data-realm]) .refsheet`) |
| F5 | 1 (aura label) | "Your aura" sits **below** the halo sentence; the demo puts it above, as a small caps label over an italic sentence. The sentence is also upright where the demo's is italic. Ruled below (R1): defect, small. | `ResonanceWeights.tsx` (label passed as `children`, which `AuraHalo` renders after the words) |
| F6 | 2 (perk rows) | Perk rows are plain text lines. The demo draws each as a shaded bar with the value right-aligned and the narrative snippet as a second line inside it. Values sit next to the label instead of in a right column, so a column of values does not read down. | `PayerOptions.tsx` (`PerkRows`) |

## Scope questions for the human (not counted as FAIL)

- **S1. The Pull Threads dialog never offers a Gift thread.** The demo's Screen 2 example is
  "Gift thread - Pyromancy", reached in "Cast - Pull threads". `ThreadPullDialog.tsx`
  `isThreadEligible` (unchanged by this PR) offers only relationship, facet and covenant
  threads, plus trait/technique threads in combat. A Gift thread in the fixture is absent from
  the dialog (`app-screen2-dialog-initial.png`: two threads listed, no Pyromancy). The
  picker (`ThreadPullPicker`, scenes) does show it with the full Pay with choice
  (`app-screen2-picker.png`). So the Gift thread, the one thread every mixed character
  starts with, cannot be pulled with a payer choice from the dialog. The spec lists both
  files; it does not say the dialog may stay narrower. Decide: widen the dialog or write down
  that casting reaches Gift threads only through the picker.
- **S2. Settled ring colours.** The demo draws "who the character is" as one thin neutral
  dashed ring (abyssal-tinted only in the unsettled state). The build draws it as dashed arcs
  in the settled affinities' own colours. It reads well and carries more (a faded streak's
  purple arc survives, `app-screen3-faded.png`), but it is not what was approved, and no
  ruling records it. The approved colours themselves are exact (see R3).
- **S3. Atone preview.** The Atone exit's mini halo draws the settled shares ("who you
  are"), which is the best case of a full atonement. The rite's actual result depends on
  the check, so the preview is an upper bound. The demo shows the same picture, so this is
  noted, not a defect.
- **S4. Exit arrangement.** The demo's dialog frame stacks the two exits; the build puts them
  side by side from the `sm` breakpoint (stacked at 390 wide, `app-screen4-scene-atone-and-accept-390.png`).
  The demo's own `.exits` grid is auto-fit, so side by side is a fair reading. Noted.

## Rulings on the divergences named in the brief

- **R1. Screen 1 step label and heading.** The build renames the funnel step "Your
  Resonance" (rendered as the entry name, with the tag "Step 4 of 5") and drops the demo's
  "IV - Resonance" label and the separate h3. The funnel is an existing five-entry grammar
  (`GiftStage.tsx` `FunnelStep`: Tradition, Gift, Techniques, Your Resonance, Anima Check,
  each tagged "Step n of 5"), so a roman-numeral stage label on one step would be the odd one
  out. The words "Your Resonance" are present; the intro copy is present word for word.
  **Ruling: acceptable, not a defect.** It is not recorded in the spec; the human may
  want it written down. The "Your aura" label placement **is** a defect (F5).
- **R2. Screen 3 colours.** MATCH. `sheet.css` defines the approved tokens on `:root` and the
  rendered page resolves them: Celestial `#e6c55a`, Primal `#2f8a74`, Abyssal `#5b2a6f`,
  Mire `#4b4a35`, with the demo's glows (`#fff1b8`, `#7fd1b9`, `#b0559a`, `#8a8660`). Read
  off the running page (`getComputedStyle(:root)`), and the halo's computed
  `background-image` is a conic gradient in `rgb(47,138,116)`, `rgb(91,42,111)` and
  `rgb(127,209,185)` (primal, abyssal, primal glow). Both the CG preview and the sheet reach
  them because `AuraHalo` imports `sheet.css`; the tokens are not left to a stylesheet linked
  only from another page.
- **R3. Screen 4 Atone card layout.** Split: the rite's controls (source chip, amount,
  component pills, rate line, cap) are today's drift-correction rite and are required to
  run it; the demo omitted them for space. That part is justified. Order, cramp and button
  style are F2.

## Visual checklist

`MATCH` = compared by eye, demo and app, same viewport and theme, and the same. `DIFF` =
differs (finding noted). `N/A` = demo annotation, not UI.

### Screen 1: Character creation, Gift stage (demo `demo-frame-01.png`, `demo-screen1.png`; app `app-screen1-10of10-1280.png`, `app-screen1-resonance-step.png`, `app-screen1-9of10-1280.png`)

| Demo element | Result |
|---|---|
| Player-screen frame bar | N/A (demo chrome) |
| "IV - Resonance" step label | DIFF, ruled acceptable (R1): app shows "Step 4 of 5" in the funnel entry |
| "Your Resonance" heading | MATCH in words; it is the funnel entry name, not an h3 (R1) |
| Intro paragraph 1 ("Resonance is what powers your magic ...") | MATCH, word for word |
| Intro paragraph 2 ("Most people are moved by more than one thing ...") | MATCH |
| Budget line "10 of 10 placed" | MATCH (`aria-live` line; reads "9 of 10 placed" mid-spread) |
| Fury row: name, PRIMAL tag, - button, six pips, + button | MATCH (buttons are grey outlines, not primary-coloured outlines; cosmetic) |
| Wonder row: one pip | MATCH |
| Domination row: ABYSSAL, three pips | MATCH |
| Mercy row: CELESTIAL, only a + button | MATCH (+ is greyed at a full budget, a state the demo does not show; correct behaviour) |
| Row description and codex line | MATCH (rows show descriptions; demo says it left them out for space and "as today") |
| Halo, primal/abyssal with glow edges | MATCH (same proportions, same colours, same ring thickness) |
| "Your aura" label above the sentence | DIFF (F5) |
| Sentence "Mostly primal, a third abyssal." | MATCH in words; upright, not italic (F5) |

Tested interactions: from 9 of 10 placed (Fury 6, Wonder 1, Domination 2) pressed "More
Domination"; the draft PATCH carried the new weights, the line read "10 of 10 placed", the
aura sentence moved from "a fifth abyssal" to "a third abyssal", the + buttons locked, and
the step closed itself as done (`app-screen1-complete-step-closed-1280.png`); reopened by
pressing the step name. No page errors.

### Screen 2: Pulling threads (demo `demo-frame-02.png`, `demo-frame-03.png`, `demo-screen2.png`; app `app-screen2-dialog-*.png`, `app-screen2-inspect-*.png`, `app-screen2-picker.png`)

| Demo element | Result |
|---|---|
| Title "Cast - Pull threads" | DIFF in wording only: "Pull Threads" (existing dialog title) |
| Tier 1 / 2 / 3, tier 2 selected | MATCH in behaviour; labels read "Tier 1", "Tier 2" |
| Gift thread card with makeup "Level 3 - mostly Fury, some Domination" | DIFF for the dialog (S1: no Gift thread offered); MATCH in the picker (`app-screen2-picker.png`); a Facet thread with the same two resonances shows the makeup line in the dialog |
| "Pay with" label and three payers, starting on the leading one | MATCH (Fury selected first) |
| Payer row: radio, name, "3 Fury - you have 22" | MATCH, cost line word for word |
| Fury perks: Bonus to this cast +4; Intensity +2 with its snippet | MATCH in content (F6: not shaded bars) |
| Domination perks: Cowed, Bonus +2 with snippet | MATCH in content; "Grants Cowed 2" where the demo says "Grants Cowed against your target 2" (placeholder copy, noted) |
| Wonder: "No perks on this thread", no Inspect link | MATCH |
| "Inspect perks" link on Fury and Domination only | MATCH |
| Rival thread: "Pays with Domination", "3 Domination", "+3" | MATCH (fixed payer, no choice; the demo's "against him" is placeholder copy) |
| Preview line "3 Fury, 3 Domination - 4 anima" | DIFF in form: "Resonance cost: 3 Domination, 3 Fury   Anima cost: 4" (existing preview panel; amounts agree) |
| Cancel / Pull | MATCH in layout; the confirm button reads "Select Pull" (existing label) |
| Inspect panel title "Domination through Pyromancy" | MATCH ("through Cinders" for the fixture's thread) |
| Inspect rows: Strength, From, Thread level used, Lasts | DIFF: "Amount" where the demo says "Strength" for a capability, and no "Lasts" row |
| Inspect "Thread level used: 2 (thread is 3; Domination is its second resonance)" | DIFF in wording: "(thread is 3; Domination is not its leading resonance)"; same facts |
| Inspect "From: Domination pull perk for Gift threads, tier 2" | MATCH (reads "Facet threads" for the fixture's thread kind) |
| (not in demo) "Worked out: 2 x 1" row | Extra row the demo does not have |

Tested interactions: ticked two threads; the mixed thread expanded to the Pay with list and
the one-resonance thread to "Pays with Domination" with no choice; chose Domination; the
dialog's next preview request carried `"payers":{"3":13}` (the request is recorded in the
run log), and the cost line moved from "3 Domination, 3 Fury" to "6 Domination" (both threads now pay in Domination, `app-screen2-dialog-domination-pays.png`); opened Inspect perks on
Domination. Picker: tier 2 on the Gift thread shows the same Pay with list. No page errors.

### Screen 3: Character sheet, aura (demo `demo-frame-04..07.png`, `demo-screen3.png`; app `app-screen3-*.png`, `app-screen3-*-page-1280.png`, `app-dark-screen3-unsettled.png`, `demo-dark-frame-unsettled.png`)

| Demo element | Settled | Unsettled | Faded | Sineater |
|---|---|---|---|---|
| Halo, approved colours, glow edges | MATCH | MATCH | MATCH | MATCH (gold, violet, murk in the demo's order) |
| Dashed "who you are" line | DIFF (S2, coloured arcs) | DIFF (S2) | DIFF (S2) | DIFF (S2) |
| Words | MATCH "Mostly primal, a third abyssal." | MATCH, the ruled Unsettled line | MATCH "Nearly all primal, a trace of abyssal." (at 94/6; the demo's picture shows 82/18, which its own words would call "a fifth", an inconsistency in the demo, not the build) | **DIFF (F1)** |
| "Unsettled" status pill | n/a | MATCH | n/a | n/a |
| "Settle your aura" button | n/a | MATCH, rust on the sheet | n/a | n/a |
| Restless halo | n/a | MATCH (animated; none under reduced motion) | n/a | n/a |
| Key "your own / from the Mire" | n/a | n/a | n/a | MATCH |
| Sentence typeface | upright serif, larger than the demo's italic (minor) | same | same | same |

Dark theme (unsettled): halo, pill and amber button MATCH the demo's dark frame; the pill
and button read as in the demo. Tested interactions: opened the sheet's Magic section for
four auras; the Unsettled aura's button opens the dialog.

### Screen 4: Settle your aura (demo `demo-frame-08.png`, `demo-screen4.png`; app `app-screen4-scene-atone-and-accept-1280.png`, `-390.png`, `app-screen4-sheet-accept-only.png`, `app-screen4-sheet-after-accept.png`)

| Demo element | Result |
|---|---|
| Dialog heading, the Unsettled sentence | MATCH |
| Atone card heading "Atone" | MATCH |
| "Perform the rite of atonement. The Domination you gained turns to Fury." | DIFF (F2): second sentence moved below the halo |
| Mini halo and "Mostly primal, a third abyssal." in the Atone card | MATCH (sentence upright, not italic) |
| "Begin the rite" outline button, left | DIFF (F2) |
| Rite controls (not in the demo) | Present: cap remaining, source chip, amount, component pills, rate line (R3, justified) |
| Accept card heading "Accept the changes to your Aura" | MATCH |
| "You become more abyssal." | MATCH |
| Mini halo with the accepted aura and its sentence | MATCH ("Mostly primal, half abyssal." where the demo says "much of it abyssal"; the words come from the shared thresholds) |
| "Accept" solid button, left | MATCH in position and weight; colour DIFF (F4) |
| "Not now", bottom right | MATCH in position; colour DIFF (F4) |
| Outside a scene: Accept and Not now only | MATCH in content (the Atone card is absent); layout DIFF (F3) |

Tested interactions: from the sheet pressed "Settle your aura": only the Accept exit
shows; pressed Accept: one POST to `/api/magic/character-auras/42/accept/` and the result
line "You settle into who you have become." showed. The fixture does not change the aura
after accept, so the redraw to a settled halo is **not** evidenced here. In the scene
harness both exits show side by side at 1280 and stacked at 390.

### Screen 5: What creation and play write (data, checked against the code)

| Demo row | Check | Result |
|---|---|---|
| Creation: one `CharacterResonance` per picked resonance | `test_no_balance_granted_by_seed`: 3 rows for 3 picks, balances 0 | MATCH. It also writes a `CHARACTER_CREATION` ledger row per pick (lifetime 60/10/30), which the demo does not list. |
| Creation: `CharacterAuraShare` per affinity, with a settled share equal to the weights | `test_settled_equals_starting_aura`: Primal 70/70, Abyssal 30/30 | MATCH |
| Creation: Gift thread level 0, "starts with nothing put into it" | `test_gift_thread_rows_at_zero_heaviest_leads`: the thread holds a `ThreadResonance` row per pick at amount 0, heaviest leading | MATCH with a note: the build keeps a zero-amount row per pick rather than no rows, which the spec's "a thread always has a row" invariant requires; level and development are 0. |
| Imbuing, Pull, Sineating, Atone, Accept rows | Not re-run here; covered by the backend tests in the diff | Not reviewed for this report |

## Mandatory criteria

| Criterion | Verdict |
|---|---|
| Exact reviewed commit named | PASS |
| Approved design reachable and read in full | PASS |
| Rendered the built surfaces (not source reading) | PASS (fixture data; see boundary table) |
| Screenshots committed beside this report | PASS (37 PNGs) |
| Rules reach the page (finding 1): approved aura colours and halo/ring/dialog CSS | PASS. Tokens resolved on the running pages and the halo gradient computed; `AuraHalo` imports `sheet.css`. Run on the vite dev server, not the production bundle (see below). |
| Host CSS contract (finding 2): surface uses the page's own tokens | PASS for CG (`cg.css` `.interview .resonance-*`), PASS for the sheet; FAIL for the Settle dialog's action colours (F4) |
| Layout the demo shows (finding 3) | FAIL (F2, F3, F6; S1, S2, S4 for the human) |
| Approved copy dropped (finding 4) | PASS with notes: intro, "Pay with", cost lines, "No perks on this thread", Unsettled line, Atone/Accept headings all present. Differences are placeholder-flagged wording (S1-adjacent): "against your target", "Strength", "Lasts", "second resonance", "Pull". |
| Demo affordance silently unbuilt (finding 5) | FAIL for S1 (Gift thread in the dialog), unwritten in the spec; the demo's "Lasts" row on a perk is also unbuilt and unrecorded |
| Divergence the build got right (finding 6) | Rule R1 (funnel step label), R3 (rite controls) accepted |
| Screen 1 verdict | **Matches with noted gaps** (F5) |
| Screen 2 verdict | **Matches with noted gaps** (F6, S1) |
| Screen 3 verdict | **Diverges** on the Sineater sentence (F1); other states match with noted gaps (S2) |
| Screen 4 verdict | **Matches with noted gaps** (F2, F3, F4) |
| Screen 5 verdict | **Matches** |

## Not exercised (BLOCKED, never inferred as pass)

- **BLOCKED: live backend.** No Evennia server was started; no UI shot used a real API
  response. The wire shapes come from the generated types and the repo's fixtures, so a
  serializer that disagrees with its own schema would not show here.
- **BLOCKED: the live scene and game pages.** The pull dialog (combat) and the Settle dialog
  with an open Atone offer (scene page via `DriftConversionOfferGate`) were mounted in a
  harness, not reached through play. The auto-open strip ("Settle your aura" call-out)
  was not drawn.
- **BLOCKED: production bundle.** The vite dev server was used; the component CSS imports
  are standard and resolved, but a built-bundle check was not run.
- **BLOCKED: post-Accept redraw** (fixture does not change the aura).
- Telnet `aura`, `aura atone`, `aura accept` are not UI and were not compared.
- Fonts: Cinzel and EB Garamond could not load; letterforms differ from a real session on
  both the demo and the app, so type sizes were compared, not faces.

## Proposed mechanical companions

- A test that renders `AuraHalo` for a Sineater aura (Celestial 56, Abyssal 44, Mire "a
  third") and asserts the sentence's leading share word equals `shareInWords` of the
  halo's own part, i.e. the sentence and the gradient read the same whole (guards F1).
- A test that renders `SettleAuraDialog` with `offer={null}` and an unsettled aura and
  asserts the Accept card spans the dialog's width (a single child must not sit in a
  two-column grid) (guards F3).
- A style test that, for every `--aura-*` token and every `aura-halo*` / `resonance-*` class
  the three surfaces emit, asserts a rule exists in the CSS reached from the rendered
  page's imports (the shape of `BuilderStylingTest`).
