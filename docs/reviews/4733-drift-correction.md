# Review evidence

- Reviewed revision: 1f8acbaa21d7800a7b5ad19dba2ac1fbfeb18560
- Reviewer: demo-fidelity-reviewer (Claude agent), second pass on the final UI after the first pass failed the dialog against Screen 5
- Reviewer verdict: PASS
- Application/build identity: Arx II branch feature-4733-drift-correction-the-conversion-offer-an at HEAD 1f8acbaa2, frontend built with `just fe-build` at that HEAD, own server on :4001 (web) and :4002 (telnet), throwaway database rt_4733 (dropped after the run)
- Environment: devcontainer, real Chromium (Playwright) against the built frontend and the running Evennia server, real telnet socket for the telnet commands, empty database seeded by script, no production data
- Viewports/themes: 1280x900 desktop, light and dark (Playwright colorScheme)
- Approved design: Screen 5 "Scene end, the conversion offer and the rite" of the "Cutting Loose" demo, https://claude.ai/artifact/1qQFaPkXf9UAPmfwmmRsLP (read by the controller and saved as live-4733/demo-screen5.md in the session scratchpad)
- Visual review: completed. The reviewer opened each screenshot below with an image-capable reader and compared it with the Screen 5 description element by element, same theme. The staff-admin probe screenshot is a 1280x18546 full-page capture that is unreadable at review size, so it is not cited; that state is evidenced by the live-run report text instead.
- Visual verdict: PASS
- Screenshots: ![light dialog three pills](docs/reviews/4733-drift-correction/01-light-dialog-three-pills.png) ![dark dialog three pills](docs/reviews/4733-drift-correction/01-dark-dialog-three-pills.png) ![light strip](docs/reviews/4733-drift-correction/01-light-strip-b.png) ![dark strip](docs/reviews/4733-drift-correction/01-dark-strip-b.png) ![light result](docs/reviews/4733-drift-correction/03-light-result.png) ![light exhausted](docs/reviews/4733-drift-correction/04-light-exhausted-close.png) ![dark exhausted](docs/reviews/4733-drift-correction/04-dark-exhausted-close.png) ![light not set up](docs/reviews/4733-drift-correction/05-light-not-set-up.png) ![dark not set up](docs/reviews/4733-drift-correction/05-dark-not-set-up.png) ![light refusal](docs/reviews/4733-drift-correction/06-light-refusal.png) ![dark refusal](docs/reviews/4733-drift-correction/06-dark-refusal.png) ![light after scene finish](docs/reviews/4733-drift-correction/07-light-after-finish.png)
- Comparison notes: The four first-pass failures are fixed at this HEAD. (1) The system line is present above the pills. (2) One box carries the small-caps label "Conversion offer · this scene". (3) Decline and Perform the rite sit in one right-aligned row inside that box. (4) The selected offering pill is filled in the primary colour (black in light, white in dark), not amber, and the other pills are outlined, as drawn. Rulings honoured and listed as noted differences, not defects: (a) the system line reads "You hold Ruin that does not fit you. Convert it to Dawnlight." instead of the demo's "You gained Ruin from a deed ..." because the approved spec defines drift as held off-aura resonance; (b) the rate line reads "Redemption: 8 Ruin becomes about 4 Dawnlight" and appends "; a focus adds N" only when focus is above 0 (the spec says a focus adds to the check, the demo drew it adding to the output); the focus clause is pinned in frontend/src/magic/components/DriftConversionOfferDialog.tsx line 149 and its unit test, but no live screenshot shows it because no focus-bearing pill was selected in the run; (c) additions beyond the drawing: the call-out strip, the source chip and Amount input, the Cap remaining figure, the result line, the red error line, the not-set-up state and the exhausted state with a Close button; (d) the dialog is a modal over the game page, not a standalone panel. Further notes: the chosen source chip "Ruin · 60 held · Redemption · up to 5" is drawn in the outline style while only the offering pill has a selected fill. This is an addition not drawn on Screen 5, there is only one source so nothing needs distinguishing, and it reads as a label next to the Amount input; it is a minor design note, not a defect. With 12 thread items the pill row wraps to seven rows; that is the data, and the design's row is three pills. The strip is legible in both themes: dark brown bold text on cream in light, gold on dark brown in dark.
- Tested interactions: strip appears on the first qualifying deed and opens the dialog; three offering routes shown (material, facet, keepsake); picked a thread and performed the rite through the browser (8 Ruin became 4 Dawnlight, cap 10 to 2, source chip 60 to 52 held); converted the remaining cap to reach the exhausted state with only a result line and Close, and it stayed so after a poll; a second deed in dark gave 10 Ruin became 5 Dawnlight; refusal path (the thread spent over telnet, then Perform pressed) showed only "You are not carrying everything you offered." with nothing more spent, in both themes; not-set-up state before the rite was authored, with Perform disabled; telnet `drift`, `drift convert Ruin=Dawnlight 2` and the scene-finish notice; strip gone 0.2 s after `scene finish`. Read-back by hand: Ruin 60-8-2-10-2-2 = 36 and Dawnlight 72 both matched.
- Fixture/live boundary: script-authored (setup3.py): the rite, the drift configuration (saved through the Django admin form), the shares, accounts, characters, items (threads, Sigil Cloak, Carved Ring) and the scene. Live: the deeds via staff `moment tag`, the real roll (five Critical Successes), the browser dialog in real Chromium, the telnet commands over a real socket, and the scene finish. Nothing was stubbed in the browser.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Box label | Small-caps "Conversion offer · this scene" at the top of one box | MATCH | 01-light-dialog-three-pills.png and 01-dark-dialog-three-pills.png show the small-caps label as the box title in both themes |
| Single box | One box holding the line, pills, rate note and buttons | MATCH | Same two images: one modal card holds everything, with a close X as the only extra |
| System line | One line of system text naming the resonance and the target | MATCH | With ruling (a): reads "You hold Ruin that does not fit you. Convert it to Dawnlight." in both themes; wording differs from the demo by an approved ruling |
| Pill row | Pills for a material, a facet item and a keepsake | MATCH | Pills "Dawn-gold Thread · material", "Sigil Cloak · facet", "Carved Ring · keepsake" in both dialog images |
| Selected pill | First pill filled in the primary colour, others outlined | MATCH | Selected thread is black with white text in light and white with black text in dark; others outlined; not amber |
| Rate note | A line stating the conversion rate with the focus clause | MATCH | With ruling (b): "Redemption: 8 Ruin becomes about 4 Dawnlight" in both themes; focus clause only when focus above 0, not drawn live (see notes) |
| Button row | Decline and Perform the rite right-aligned in one row inside the box | MATCH | Both buttons on one row at the lower right inside the card in both themes; Perform is the primary fill, Decline plain |
| Strip call-out (addition) | A strip that announces the offer, legible in both themes | MATCH | 01-light-strip-b.png dark brown on cream, 01-dark-strip-b.png gold on dark brown |
| Source chip and Amount (addition) | Source chip and numeric Amount above the pills | MATCH | With noted gap: chip "Ruin · 60 held · Redemption · up to 5" and Amount 8 in both dialog images; chip drawn outlined, not filled (note) |
| Cap remaining (addition) | Figure in the top right of the box | MATCH | "Cap remaining 10" in both dialog images; "Cap remaining 2" in 03-light-result.png |
| Result line (addition) | Outcome tier first, then the conversion | MATCH | 03-light-result.png "Critical Success: 8 Ruin became 4 Dawnlight." above the line, with cap and held figures updated |
| Exhausted state (addition) | Label, result line and a Close button only | MATCH | 04-light-exhausted-close.png and 04-dark-exhausted-close.png |
| Error line (addition) | Red box with plain sentence, no field prefix | MATCH | 06-light-refusal.png and 06-dark-refusal.png "You are not carrying everything you offered." in a red box above the button row |
| Not-set-up state (addition) | Plain sentence where the pills go, Perform disabled | MATCH | 05-light-not-set-up.png and 05-dark-not-set-up.png "The rite of correction is not set up yet; tell staff." with greyed Perform |
| Offer lapses at scene end | Strip and offer gone once the scene finishes | MATCH | 07-light-after-finish.png shows "The scene has ended" and no strip |
| Light and dark themes | Same layout, readable text in both | MATCH | Every cited image exists in both themes except the result and after-finish images, which are light only; the layout is identical where both exist |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
| --- | --- | --- | --- |
| D1-box-label-and-single-box | PASS | 01-light-dialog-three-pills.png and 01-dark-dialog-three-pills.png compared with Screen 5 | none needed |
| D2-system-line | PASS | Present in every dialog image; wording ruling (a) honoured | none needed |
| D3-pills-and-selected-fill | PASS | Three pill kinds shown; selected fill in the primary colour in both themes | none needed |
| D4-rate-line | PASS | "Redemption: N Ruin becomes about M Dawnlight" in both themes; focus clause per ruling (b), unit-tested | none needed |
| D5-button-row | PASS | Decline and Perform the rite in one right-aligned row inside the box | none needed |
| D6-additions-beyond-drawing | PASS | Strip, source chip, Amount, cap, result, error, not-set-up and exhausted states all rendered and listed in the notes | none needed |
| D7-live-behaviour | PASS | Rite performed in the browser, refusal and exhausted states, telnet and scene finish, numbers verified by hand | none needed |

## Unresolved findings

None
