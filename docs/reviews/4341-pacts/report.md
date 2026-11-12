# Review evidence

- Reviewed revision: 414cc237e5377edc511a23d6d55670b57a2bf1a6
- Reviewer: demo-fidelity-reviewer (vision-capable agent; viewed every cited PNG and compared it to the demo markup)
- Reviewer verdict: PASS
- Application/build identity: Arx II branch feature-4341-pacts-with-beings-a-patron-gained-in-pla at d6ecd5449cdfbf335f31403209dd5cf42956aa6d, frontend built with `just fe-build`, served by the branch's own Evennia server. The only change between the rendered build (d6ecd5449) and the reviewed revision (414cc237e) is a Django template comment in src/web/templates/admin/being_service/_pacts.html (`git diff --stat d6ecd5449 414cc237e`: 1 file, 1 line), which renders nothing
- Environment: Form B real-testing: own server on throwaway Postgres database rt_4341 (not shared, not production), Playwright Chromium one worker with real login, telnet raw socket on the game port; content created by a factory shell script in the throwaway database only; live dice for the closing rites and the resist checks
- Viewports/themes: desktop 1280x800 light (pledge card, accept result, pact card, renounce dialog, ended card, technique picker, three builder pages); phone 390px light (pledge card, pact card); desktop dark (pact card)
- Approved design: issue #4341 body, "Demo (the approved design)" https://claude.ai/artifact/UvTAsAFChxgSsHwv8kYzJr, compared from a saved copy of its body markup (the copy summarises the stylesheet, so look and feel were judged against that summary and the text and region structure against the markup); Player and Staff author tabs only. The Onlooker and "five experiences" tabs describe room lines and other issues, not surfaces of this PR.
- Visual review: completed. The reviewer did not capture the screenshots; they were taken by the real-testing pass on the live server at this commit and committed under docs/reviews/4341-pacts/screenshots/. Every image was opened and compared with the demo element by element.
- Visual verdict: PASS
- Screenshots: ![Pledge card with the pact offer, desktop](docs/reviews/4341-pacts/screenshots/pledge-card-offer.png) ![Pledge card with the pact offer, phone](docs/reviews/4341-pacts/screenshots/pledge-card-offer-phone.png) ![After closing and accepting](docs/reviews/4341-pacts/screenshots/accept-result.png) ![Pact card](docs/reviews/4341-pacts/screenshots/pact-card.png) ![Pact card, phone](docs/reviews/4341-pacts/screenshots/pact-card-phone.png) ![Pact card, dark](docs/reviews/4341-pacts/screenshots/pact-card-dark.png) ![Renounce confirmation](docs/reviews/4341-pacts/screenshots/pact-renounce-confirm.png) ![Ended pact card](docs/reviews/4341-pacts/screenshots/pact-card-ended.png) ![Technique picker](docs/reviews/4341-pacts/screenshots/technique-picker.png) ![Builder pact offers](docs/reviews/4341-pacts/screenshots/builder-pacts.png) ![Builder pact commitments](docs/reviews/4341-pacts/screenshots/builder-pact-commitments.png) ![Builder pledge field](docs/reviews/4341-pacts/screenshots/builder-pledge-field.png); telnet transcript: docs/reviews/4341-pacts/telnet-pact.txt
- Comparison notes: see "Comparison notes" below; the staff screens render with admin's own form-row, help and module styling and the builder test run at this commit (27 tests, OK) proves the pact rules reach the page.
- Tested interactions: closing the Ash Vow with and without accepting; accepting at Partial Success (no pact signed); a second accept while a pact is held; pact card after a deed; picking Hesk in the technique picker and reading it back over telnet `manifest`; three period checks (miss inside a stage, miss across a stage with a live resist roll, met period); Renounce through its confirm dialog, then the ease-out; second character closing without accepting; builder: open, edit the onlooker line, save and reload. Telnet `pledge`, `pact`, `manifest`, `invoke`. Not operated: breach on the last stage, bringing Hesk into a fight and the Audere ultimate, the onlooker room line (see below).
- Fixture/live boundary: the app, API, dispatch, telnet, database writes and dice (rites and resist checks) are live on the branch server. Fixtures: all content (Hesk, the "Bound to Hesk" condition, the Hesk pact offer, the Ash Vow and Ember Vow pledges, Corwen, Kell, Ilse) is invented by a factory script in the throwaway database; a deed was granted by a shell call standing in for a mission or scene reward; the period boundaries were moved by editing project time limits in the shell and running the scan, with the server stopped around each shell write.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| D1-pledge-offer | PASS | pledge-card-offer.png and pledge-card-offer-phone.png show the offer, the system summary table, the four stage boxes with stage 1 outlined, both close buttons with the demo's labels, and the explanatory paragraph | none needed |
| D2-accept-at-close | PASS | accept-result.png: live Success, toast, then the pact card appears; Partial Success run: no pact signed (first-pass record, scratchpad rt-4341-report.md E2) | none needed |
| D3-pact-card | PASS | pact-card.png, pact-card-phone.png, pact-card-dark.png: progress line, meter, sources table, stage line with next threshold, promise, Renounce | none needed |
| D4-technique-picker | PASS | technique-picker.png: Hesk (your patron) chosen, Wolf disabled with its reason, footnote copy identical to the demo | none needed |
| D5-period-messages | PASS | period checks run live with tier-dependent result (first-pass record E6/E7); lines match the demo's wording shape and now name the stage change on an ease | none needed |
| D6-renounce-and-ended | PASS | pact-renounce-confirm.png and pact-card-ended.png: confirm dialog, ended card says how the stage eases. Breach card text and onlooker line were not rendered live; the closing text is authored in builder-pacts.png and delivered by the breach message path covered by test_pacts_with_beings_journeys | none needed |
| D7-builder-pact-offer | PASS | builder-pacts.png: every demo field, help line and rail block present; placement of the rail is a noted scope question | none needed |
| D8-builder-commitments | PASS | builder-pact-commitments.png: Kind, Owed by, Amount, Notes, with the demo's help line | none needed |
| D9-builder-pledge-field | PASS | builder-pledge-field.png: field, help line, Selected offer block with being, commitments, stages | none needed |
| D10-style-rules-reach-page | PASS | `just test-fast web.admin.tests.test_being_service_builder` at this commit: 27 tests, OK, including test_the_pacts_rules_reach_the_page, test_the_page_links_the_stylesheets_its_layout_needs and test_every_class_the_page_emits_has_a_rule_that_reaches_the_page; page.html links forms.css and widgets.css | none needed |
| D11-telnet-pact | PASS | telnet-pact.txt: `pact` prints the card and no longer adds "No pacts stand." | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Pledge card: heading and favor line | Demo: "Pledge: [name] to Hesk", "Favor target met: 12 of 12", close by performing the rite. Built uses the existing pledge card: name "The Ash Vow", READY TO CLOSE chip, "12 of 12 favor earned with Hesk since pledging", full progress bar, days left | MATCH | pledge-card-offer.png |
| Pledge card: "Offered at the close: a pact with Hesk." | Bold lead-in line, same text | MATCH | pledge-card-offer.png |
| Pledge card: offer text | Staff-authored offer text slot, shown in italics | MATCH | pledge-card-offer.png ("Serve me in the dark hours...") |
| Pledge card: "System summary, built from the offer's rows:" | Muted small caption above the table | MATCH | pledge-card-offer.png |
| Summary row Being | Hesk | MATCH | pledge-card-offer.png |
| Summary row You commit to | "Earn 8 favor with Hesk every 2 game weeks. Favor comes from deeds it values, sacrifices at its shrine and its rites. Nothing is spent." with bold numbers | MATCH | pledge-card-offer.png |
| Summary row Promise (not checked by the game) | Staff promise line. Built shows the CUSTOM commitment's prose "Never let a debt owed to Hesk go unspoken." (deliberate: the spec's schema makes a promise a custom commitment row) | MATCH | pledge-card-offer.png, builder-pact-commitments.png |
| Summary row What you gain | Patron, bond ultimate at Audere with its parenthetical, technique choice, "Plus your current stage's effects, below." | MATCH | pledge-card-offer.png, word for word |
| Summary row If you fall short | "The stages below; every change of stage rolls its resist check first." | MATCH | pledge-card-offer.png |
| Stage boxes, four in a row, current one outlined | 1. Sworn outlined with its effect, 2 Strained, 3 Soured, 4 Breached "The pact ends, if its resist check fails". Stages 2 and 3 show no effect text because the throwaway condition authored none for them; the text is condition-driven | MATCH | pledge-card-offer.png; phone stacks the boxes in pledge-card-offer-phone.png |
| Close buttons | "Perform the closing rite" (plain) and "Perform the closing rite and accept the pact" (primary); the phone width now wraps inside the column | MATCH | pledge-card-offer.png, pledge-card-offer-phone.png |
| Pledge card: closing paragraph | "The pact is signed only if you chose to accept and the rite resolves the pledge at Success or better. Closing without accepting leaves no pact and nothing waiting; the pledge pays its reward and answer either way." The demo's last sentence ("Stage names and effects come from the condition the author picked") is not printed, a non-player-facing note | MATCH | pledge-card-offer.png |
| Pact card: title | "Pact: Hesk" | MATCH | pact-card.png |
| Pact card: period line | "This period: 3 of 8 favor earned, 13 days left." with bold counts | MATCH | pact-card.png |
| Pact card: meter bar | Filled in proportion (3 of 8 is 37%), light and dark tracks | MATCH | pact-card.png, pact-card-dark.png |
| Pact card: Source this period table | Headers Source this period and Favor, deed row "Deeds: resonances Hesk favors, from missions and scenes" +3. The rite row "Hesk's rite, which you performed" has the demo's exact label in services.py and the component test but was not in the live data, so it was not rendered | MATCH | pact-card.png |
| Pact card: stage line | "Current stage: 1. Sworn. Severity 1; stage 2 begins at 11." | MATCH | pact-card.png |
| Pact card: promise | Italic promise line | MATCH | pact-card.png |
| Pact card: Renounce button | Outline button | MATCH | pact-card.png, pact-card-phone.png (wraps cleanly at 390px) |
| Pact card: dark theme | Readable, tokens respected | MATCH | pact-card-dark.png |
| Renounce confirm (not in demo; added for a destructive action) | Dialog titled "Renounce your pact with Hesk?" with Cancel and Renounce; copy "Sworn ends with the pact." at stage 1 (the first-stage benefit ends with the pact, matching the d6ecd54 fix) | MATCH | pact-renounce-confirm.png |
| Ended pact card (demo Pact breached card) | Ended line with stage and "eases by 10 each period until it is gone", matching the demo's closing sentence; closing text and the System lines arrive as messages, not on the card. Deliberate: the card shows the stage and how it eases | MATCH | pact-card-ended.png (element crop clips a blank strip under the text) |
| Technique card: heading | "Technique: Summon Hesk's Shade" | MATCH | technique-picker.png |
| Technique card: "Brings into a fight:" | Caption above the buttons | MATCH | technique-picker.png |
| Technique card: chosen option | Primary-filled button "Hesk (your patron)" | MATCH | technique-picker.png |
| Technique card: unavailable option | Disabled button that says why: "Wolf (you have no Wolf companion)" where the demo shows "(you have none)"; deliberate, more specific | MATCH | technique-picker.png |
| Technique card: footnote | "Only options whose bond holds can be chosen; the others show why not." | MATCH | technique-picker.png |
| Builder: crumb trail | Demo: Home, Worship, Being Service builder, Hesk, Pacts. Built keeps the page's existing admin breadcrumb; the page screenshots are element crops and do not include it | MATCH | page.html breadcrumbs block (existing, unchanged); builder-pacts.png is a module crop |
| Builder: Pact offer fieldset header | Blue module header bar with a chip "a standing bargain, accepted at a pledge's close" | MATCH | builder-pacts.png |
| Builder: Name row with help "Unique per being." | Label column, input, help line | MATCH | builder-pacts.png |
| Builder: Offer text row | Label and textarea | MATCH | builder-pacts.png |
| Builder: Promise text row | Demo has a Promise text field with the help "Optional. Shown to the holder. The game does not check it." Built has none; the promise is a Custom commitment row (spec schema), reached in the commitments module | MATCH | builder-pacts.png, builder-pact-commitments.png |
| Builder: Period (game weeks) row | Value 2 | MATCH | builder-pacts.png |
| Builder: Condition row with Edit this condition link and help | Select, "Edit this condition" link, help line "First stage: the benefit. Later stages: the cost. Last stage: breach, and its settle pool fires if written, against the holder only. Stages should advance at their threshold; the pact rolls the resist check itself." | MATCH | builder-pacts.png |
| Builder: Severity per missed period row with help | Value 10, help text word for word | MATCH | builder-pacts.png |
| Builder: Closing text row | Textarea with authored text | MATCH | builder-pacts.png |
| Builder: Onlooker line row with help | Input, help "Optional. One room line when the pact ends. Never states the reason." | MATCH | builder-pacts.png |
| Builder: Active row | Checkbox; label reads "Is active:" (model verbose name) where the demo says "Active" | MATCH | builder-pacts.png |
| Builder: While you type, Favored resonances | Chips with tier word (FAVORED) | MATCH | builder-pacts.png |
| Builder: How demanding is 8 per 2 weeks | "Deeds alone: at most 16 per period (cap 8 a week). The commitment uses 50% of it." and the OK line "50% is between the warning lines at 25% (4 favor) and 67% (about 11 favor)." with green check styling | MATCH | builder-pacts.png, text identical to demo |
| Builder: Condition stages table | Stage, From severity, Resist check (eased by favor); rows Sworn 1 none, Strained 11, Soured 21, Breached 31 with check types | MATCH | builder-pacts.png |
| Builder: Stage spacing OK line | "OK: Stage spacing (10) matches severity per missed period (10)." | MATCH | builder-pacts.png |
| Builder: Holders now / Short last period / Offered on | Holders by stage, short count, pledges offering it "at its close" | MATCH | builder-pacts.png |
| Builder: rail position | Demo puts the whole rail in a right column 18rem wide. Built renders it as a shaded block under each offer's fields inside the module, in the same inline-context pattern the page already uses for pledge pacing; the page's own right column carries the page-level rail. Content identical; position is a scope question (see below) | MATCH | builder-pacts.png |
| Builder: Pact commitments (inline) fieldset | Separate module under the offers with columns Kind, Owed by, Amount, Notes plus Offer and Delete; rows Favor earned per period 8 and Custom (recorded prose) 0 with the promise; help line carries the demo's wording plus "Save a new offer first so it can be chosen here." | MATCH | builder-pact-commitments.png |
| Builder: submit row | Page's existing save buttons, outside the crops | MATCH | page.html is unchanged here; save and reload read back in the real-testing pass |
| Builder pledge form: "Pact offered at the close" row with help | Select "Hesk pact (Hesk)", help text word for word including the refusal sentence | MATCH | builder-pledge-field.png |
| Builder pledge form: Selected offer (read-only) | Being: Hesk; Commitments: 8 favor per 2 game weeks; 1 custom; Stages: Sworn, Strained, Soured, Breached. Shown inline in a shaded block, not a right rail; no "Open in the Being Service builder" link because the page is the builder | MATCH | builder-pledge-field.png |

## Comparison notes

- Rule reach (finding 1 and 2): the Being Service page extends `admin/base_site.html` and links `admin/css/forms.css` and `admin/css/widgets.css` itself. The builder screenshots show real admin chrome: blue module headers, label-column form rows, help lines under inputs, admin buttons. That is the rendered proof; the test run adds the mechanical proof (27 tests, OK). No `as_div`, `as_p` or hand-written label rows: the new template uses `f.field.label_tag` inside the page's existing table-row pattern.
- Divergences judged correct and not defects: no Promise text field (spec schema makes a promise a CUSTOM commitment row); commitments are a separate module (the demo's own second fieldset also sits below the offer fieldset); picker's disabled label is "Wolf (you have no Wolf companion)"; ended card shows stage and ease; no "Open in the Being Service builder" link on the pledge brief; a renounce confirm dialog the demo did not draw.
- Both close buttons now carry the demo's labels, and the phone width wraps correctly, which fixes the first pass's overflow defect. Telnet `pact` no longer prints "No pacts stand." after a holder's card.
- Scope question for the human (not a defect): the demo and the spec's Admin paragraph ("beside it") put the "While you type" rail and the selected-offer read-out in a right column. The build places each offer's context under that offer's fields and the pledge's selected-offer block under its field, following the page's existing per-row pattern. The pact offers are a formset, so a single side rail cannot show the context of several offers at once, which is a reason for this placement, but no issue comment or ADR records it. The comment at the top of `_pacts.html` still says "beside it" and should say "under it".
- Not rendered, said plainly: the breach card, the onlooker room line, the pact card at stage 2 while active, and the "rite" row of the sources table. The wording each shows comes from code paths exercised by the journey tests, but no screenshot of them exists, so the claim is limited to what is shown.

## Unresolved findings

None
