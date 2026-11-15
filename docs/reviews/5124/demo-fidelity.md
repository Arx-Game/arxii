# Review evidence: demo fidelity for #5124 (kindled resonances), round 3

- Reviewed revision: 4e6f2fc71049fa1ed96180d11d89f1e54b6afbab
- Reviewer: demo-fidelity-reviewer agent (Claude Sonnet 5.5, vision-capable); every screenshot was read at the same viewport and theme as the demo render before a row was marked MATCH
- Reviewer verdict: PASS
- Application/build identity: the real Evennia and Django server on :4001 (web) and :4002 (websocket), frontend bundle built at 4e6f2fc71 (fix commits 0268762aa, fd8c6a491, 4e6f2fc71 on top of b2a8244a6); `/api/user/` answers 200
- Environment: branch feature-5124-what-stirs-a-resonance-the-situations-th, throwaway Postgres database rt_5124 built from the models, Chromium (cached headless shell 1208) driven by Playwright, player accounts e2e_test_account (Mira Vale, Brannoc Hale) and kindled_second_player (Tomas Reeve), staff account demo_fidelity_staff for the admin pages
- Viewports/themes: 1600 px wide for the game pages and sheet, 1400 px wide for the admin pages, theme "system" which rendered light; the demo was rendered at 1600 px, light, and the demo's paper palette is a placeholder skin so colours are not compared
- Approved design: demo https://claude.ai/artifact/9GAFpngyx6KMFSbjhkZDZs, read in full from the exact local copy /tmp/claude-1000/-workspaces-arxii/f9b72c8d-5420-462d-b7e2-0639e5112f77/scratchpad/demo-5124.html and rendered to docs/reviews/5124/demo/demo-light-section1.png through demo-light-section8.png (section N is Screen N); the spec is the issue body of #5124
- Visual review: Completed by comparing the rendered application and the rendered demo side by side for Screens 1 to 6 and 8; Screen 7 is an annotation table in the demo and Screen 9 is a table of rows, neither is player-facing, so neither has a screenshot
- Visual verdict: PASS
- Screenshots: ![Panel in the scene sidebar](docs/reviews/5124/fresh/r2-01-scene-sidebar-panel.png) ![Panel and Dig deep in the combat rail](docs/reviews/5124/fresh/r2-01-combat-panel.png) ![Dig deep](docs/reviews/5124/fresh/r2-01-dig-deep.png) ![Give in picker](docs/reviews/5124/fresh/r2-02-give-in.png) ![Rally control](docs/reviews/5124/fresh/r2-03-rally-control.png) ![Mission options with feeds lines](docs/reviews/5124/fresh/r3-04-three-options.png) ![Grant line after acting](docs/reviews/5124/fresh/r2-04-mission-option-taken.png) ![Second player sees nothing](docs/reviews/5124/fresh/r2-04-tomas-view.png) ![Reflecting on row live after earning](docs/reviews/5124/fresh/r3-a-row-live-after-earning.png) ![Row after reload](docs/reviews/5124/fresh/r2-05-reflecting-row-after-reload.png) ![Reflection card in the feed](docs/reviews/5124/fresh/r2-05-reflection-feed-card.png) ![Journal dialog with the row](docs/reviews/5124/fresh/r2-05-journal-dialog-disown-ready.png) ![Journal posted](docs/reviews/5124/fresh/r2-05-journal-dialog-posted.png) ![Aura card](docs/reviews/5124/fresh/r3-06-aura-card-element.png) ![Rite dialog](docs/reviews/5124/fresh/r3-06-rite-dialog-embrace-and-disown.png) ![Admin resonance](docs/reviews/5124/fresh/r2-08-admin-resonance.png) ![Admin affinity](docs/reviews/5124/fresh/r2-08-admin-affinity.png) ![Admin mission template](docs/reviews/5124/fresh/r2-08-admin-mission.png) ![Admin kindling config](docs/reviews/5124/fresh/r3-b-kindling-config.png) ![Pull dialog at tier 2 with the Intensity row](docs/reviews/5124/fresh/r4-02-pull-dialog-intensity.png) ![Rite Roll line with the worn focus clause](docs/reviews/5124/fresh/r4-06-rite-dialog-roll-line-worn-focus.png)
- Comparison notes: Round 1 (e887ddcad) found nine mismatch groups; round 2 (b2a8244a6) fixed them and left three minor ones, A, B and C; this round re-checked A, B and C on fresh renders and all three are fixed. A: the Reflecting on row now lists a deed the moment its "You earned" line arrives (4 Fury and 4 Dawnlight from taking "Strike the chains loose") without a reload. B: the Kindling config page is 1400 px wide at a 1400 px viewport with no raw row captions. C: a deed with no recorded label reads "Your Domination from this mission is about people held for what they are grows, up to 5." in the rite dialog; the line above it, the reflection's title, still opens with a capital and ends with a full stop for such an old deed, which is a standalone line and grammatical, and only grants made before the fix lack a label. The fixer chose "Remind them of" for Rally because the combat payload carries no ally pronouns and adding them would leak a mask; the choice is acceptable. The two details that could not be rendered in round 3 were rendered after the coordinator restarted the server at this revision: at tier 2 the kindled Fury payer shows "Bonus to this cast +6" and "Intensity +4" while the unkindled Wonder payer shows only "+3" (the intensity perk is authored at tier 2 because a tier's perks add up across tiers and one tier holds one effect per key), and with a worn touchstone the rite's Roll line reads "Roll: Composure, +2 from your worn focus. A full success carries out every reflection in full; a lesser one carries each out part of the way. The offering is spent whatever the roll.", word for word as the demo. Pre-existing UI the branch did not touch is listed under its own heading.
- Tested interactions: scene sidebar panel with a second player present; Dig deep pick; combat Cinder Lash with target and the give-in picker; Rally ally pick and resonance pick; mission option taken through the real UI (Failure result, 4 Fury and 4 Dawnlight earned) and the second player's page checked for leaks; pose reflecting on a deed with Embrace and the feed card; journal dialog with a reflection posted (HTTP 201 with X-Character-ID); pull dialog opened at tier 2 with Fury and Wonder payers; sheet aura card and rite dialog opened with each offering picked in turn (the rite was not performed); admin resonance, affinity, mission template and Kindling config pages with the page scroll width measured
- Fixture/live boundary: all screens are the live application on real API data, nothing mocked; the authored world comes from seed_kindled_resonances_spec plus shell edits in rt_5124 (strength tiers, situations, themes, awards, a Dawnlight situation and a "Strike the chains loose" option with an Oppression theme added this round, a fresh mission run for Mira, an intensity perk for Fury at tier 2 with its pull cost, and a worn Iron Signet and Dawn-gold Ring tied to Domination and Dawnlight); the deeds in the A and rite screenshots were earned in play, not seeded; one deed from before the label fix is kept deliberately to check C
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Screen 1 panel label and rows | "Your resonances", one row per resonance with name and affinity | MATCH | docs/reviews/5124/fresh/r2-01-scene-sidebar-panel.png |
| Screen 1 kindled tag | orange pill with a dot: "Kindled, blazing", "Kindled, faint" | MATCH | docs/reviews/5124/fresh/r2-01-scene-sidebar-panel.png |
| Screen 1 reason lines | "Tomas Reeve is here"; the theme's player text | MATCH | docs/reviews/5124/fresh/r2-01-scene-sidebar-panel.png |
| Screen 1 row order | kindled rows first and strongest first, unkindled dimmed last | MATCH | docs/reviews/5124/fresh/r2-01-scene-sidebar-panel.png |
| Screen 1 combat rail panel | same panel beside Dig deep | MATCH | docs/reviews/5124/fresh/r2-01-combat-panel.png |
| Screen 1 Dig deep | label "Dig deep", resonance picks, kindled note, Dig deep button | MATCH | docs/reviews/5124/fresh/r2-01-dig-deep.png |
| Screen 2 give-in label and picker | "Give in to your Fury" with the kindled resonance picker | MATCH | docs/reviews/5124/fresh/r2-02-give-in.png |
| Screen 2 steps | Hold steady, Let it in, Give in, deeper steps withheld by strength | MATCH | docs/reviews/5124/fresh/r2-02-give-in.png |
| Screen 2 depth line | how far the strength goes plus the weakest strength's limit | MATCH | docs/reviews/5124/fresh/r2-02-give-in.png |
| Screen 2 preview line | give up control, gain up to intensity, control roll eased by the strength | MATCH | docs/reviews/5124/fresh/r2-02-give-in.png |
| Screen 3 Rally heading and pick | "Rally" heading with the ally, "Remind them of", the ally's resonance names | MATCH | docs/reviews/5124/fresh/r2-03-rally-control.png |
| Screen 3 Rally note and button | unkindled note, "Declare Rally" | MATCH | docs/reviews/5124/fresh/r2-03-rally-control.png |
| Screen 4 option feeds lines | "Your resonance is kindled" plus reason on the options carrying a theme only; "Strike the chains loose" and "Bar the overseers' door" both present | MATCH | docs/reviews/5124/fresh/r3-04-three-options.png |
| Screen 4 grant line | "You earned N" for the actor only | MATCH | docs/reviews/5124/fresh/r2-04-mission-option-taken.png |
| Screen 4 second player | sees nothing of the grant | MATCH | docs/reviews/5124/fresh/r2-04-tomas-view.png |
| Screen 5 Reflecting on row | label, optional, deed pills in the act's own words, unsettling resonance pill, Embrace and Disown | MATCH | docs/reviews/5124/fresh/r3-a-row-live-after-earning.png |
| Screen 5 row after reload | deed named "Bar the overseers' door" with its amount | MATCH | docs/reviews/5124/fresh/r2-05-reflecting-row-after-reload.png |
| Screen 5 feed card | recorded line and the Settle your aura button in the feed | MATCH | docs/reviews/5124/fresh/r2-05-reflection-feed-card.png |
| Screen 5 journal editor | same Reflecting on row with the replace notice | MATCH | docs/reviews/5124/fresh/r2-05-journal-dialog-disown-ready.png |
| Screen 5 journal post | entry posted with its reflection and the recorded confirmation | MATCH | docs/reviews/5124/fresh/r2-05-journal-dialog-posted.png |
| Screen 6 aura card | Your reflections list, one Settle your aura button, Not yet reflected on list | MATCH | docs/reviews/5124/fresh/r3-06-aura-card-element.png |
| Screen 6 chance to atone line | "A chance to atone is open: up to N toward Dawnlight." | MATCH | docs/reviews/5124/fresh/r3-06-aura-card-element.png |
| Screen 6 rite dialog cards | title, italic excerpt with where it was written, effect line per reflection | MATCH | docs/reviews/5124/fresh/r3-06-rite-dialog-embrace-and-disown.png |
| Screen 6 Disown line | "Domination turns toward Dawnlight, up to N" with a chance open | MATCH | docs/reviews/5124/fresh/r3-06-rite-dialog-embrace-and-disown.png |
| Screen 6 offering block | each carried offering with how it counts | MATCH | docs/reviews/5124/fresh/r3-06-rite-dialog-embrace-and-disown.png |
| Screen 2 pull dialog perk rows | a kindled payer shows Bonus to this cast and Intensity rows; an unkindled payer shows only its bonus | MATCH | docs/reviews/5124/fresh/r4-02-pull-dialog-intensity.png |
| Screen 6 Roll line | Roll: Composure, +2 from your worn focus, then the full success sentence and the offering is spent sentence | MATCH | docs/reviews/5124/fresh/r4-06-rite-dialog-roll-line-worn-focus.png |
| Screen 8 resonance page | Feeling with the demo's help, What kindles it with four columns | MATCH | docs/reviews/5124/fresh/r2-08-admin-resonance.png |
| Screen 8 situation labels | the demo's phrasing for the new situations | MATCH | docs/reviews/5124/fresh/r2-08-admin-resonance.png |
| Screen 8 affinity page | What kindles every Celestial resonance, four columns | MATCH | docs/reviews/5124/fresh/r2-08-admin-affinity.png |
| Screen 8 mission template | Themes field with the demo's help | MATCH | docs/reviews/5124/fresh/r2-08-admin-mission.png |
| Screen 8 Kindling config | strength table, Harm property help, Rally table, Earned table, fits the page, no raw captions | MATCH | docs/reviews/5124/fresh/r3-b-kindling-config.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| screen-1-panel-and-dig-deep | PASS | docs/reviews/5124/fresh/r2-01-scene-sidebar-panel.png and r2-01-dig-deep.png compared with demo-light-section1.png | |
| screen-2-casting | PASS | docs/reviews/5124/fresh/r2-02-give-in.png compared with demo-light-section2.png | |
| screen-3-rally | PASS | docs/reviews/5124/fresh/r2-03-rally-control.png compared with demo-light-section3.png; "Remind them of" accepted | |
| screen-4-mission-feeds-and-grant | PASS | docs/reviews/5124/fresh/r3-04-three-options.png and r2-04-tomas-view.png compared with demo-light-section4.png | |
| screen-5-reflecting-on | PASS | docs/reviews/5124/fresh/r3-a-row-live-after-earning.png, r2-05-reflection-feed-card.png and r2-05-journal-dialog-posted.png compared with demo-light-section5.png | |
| screen-6-aura-and-rite | PASS | docs/reviews/5124/fresh/r3-06-aura-card-element.png and r3-06-rite-dialog-embrace-and-disown.png compared with demo-light-section6.png | |
| screen-7-situations | PASS | annotation table in the demo, not player-facing; the admin situation labels were checked under screen 8 | |
| screen-8-admin | PASS | docs/reviews/5124/fresh/r2-08-admin-resonance.png, r2-08-admin-affinity.png, r2-08-admin-mission.png and r3-b-kindling-config.png compared with demo-light-section8.png; scroll width equals viewport width (1400 of 1400) | |
| finding-a-row-refresh | PASS | docs/reviews/5124/fresh/r3-a-row-live-after-earning.png: the row lists both new deeds without a reload | |
| finding-b-kindling-config-fit | PASS | docs/reviews/5124/fresh/r3-b-kindling-config.png: scroll width 1400 of 1400, no raw captions | |
| finding-c-unlabelled-deed-sentence | PASS | docs/reviews/5124/fresh/r3-06-rite-dialog-embrace-and-disown.png: "Your Domination from this mission is about people held for what they are grows, up to 5." | |
| round-1-and-2-mismatches | PASS | all nine round 1 groups re-checked in round 2 on fresh renders (docs/reviews/5124/fresh/r2-*.png) and not regressed in this round's renders | |
| screen-2-intensity-row | PASS | docs/reviews/5124/fresh/r4-02-pull-dialog-intensity.png: tier 2, Fury Kindled strong shows Bonus to this cast +6 and Intensity +4, Wonder shows +3, as demo-light-section2.png | |
| screen-6-worn-focus-clause | PASS | docs/reviews/5124/fresh/r4-06-rite-dialog-roll-line-worn-focus.png: the Roll line reads Roll: Composure, +2 from your worn focus, as demo-light-section6.png | |
| pre-existing-mission-option-card | OUT_OF_SCOPE | the "Check:" prefix and separate "Choose" button the demo draws on mission options are in the existing option card, which this branch did not touch | coordinator ruling relayed in the round 2 re-run brief: out of scope because the branch did not touch it |
| pre-existing-pose-send-label | OUT_OF_SCOPE | the pose composer button reads "Send", the demo's "Pose"; the button is existing UI this branch did not touch | coordinator ruling relayed in the round 2 re-run brief: out of scope because the branch did not touch it |
| pre-existing-journal-buttons | OUT_OF_SCOPE | the journal editor buttons read "Discard" and "Post entry", the demo's "Save draft" and "Publish"; existing UI this branch did not touch | coordinator ruling relayed in the round 2 re-run brief: out of scope because the branch did not touch it |

## Pre-existing, out of scope

These differ from the demo but sit in UI this branch did not touch, so they are not findings against this PR.

- Mission option card: no "Check:" prefix before "Presence" and no separate "Choose" button (the option itself is the button, beside "Call on favor").
- Pose composer button reads "Send", the demo's "Pose".
- Journal editor buttons read "Discard" and "Post entry", the demo's "Save draft" and "Publish".

## Unresolved findings

None
