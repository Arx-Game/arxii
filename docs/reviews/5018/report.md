# Review evidence

- Reviewed revision: 8ea9ef0b99cb5ce942f14ee0401177ec597a0427
- Reviewer: demo-fidelity-reviewer (vision-capable; third pass after fixes 28b9aa7f9, ea245f1c7 and 8ea9ef0b9; compared each committed screenshot against the demo file and the built source)
- Reviewer verdict: PASS
- Application/build identity: branch feature-5018-a-technique-can-need-the-right-surroundi at 8ea9ef0b99cb5ce942f14ee0401177ec597a0427; production frontend bundle rebuilt from this branch for screenshots 01, 02, 03, 06, 07, 10, 11, 13 (04, 05, 08, 09 come from the earlier build at 9a1ca1050; the surfaces they show did not change in the fix commits); own Evennia server on port 4001; throwaway Postgres database rt_5018
- Environment: local devcontainer, headless Chromium against the live Evennia server above; no /api route mocked; seeded live data (a Gloamcraft gift with a shadow substance, character Vesper Shade, scene Shadows in the Hall, a fight with a Bandit Captain)
- Viewports/themes: 1280px wide (01, 02, 03), 1400px (04, 05, 06, 07, 10, 11, 13), 1500px (08, 09); light theme only. Dark theme not exercised.
- Approved design: issue 5018 body, demo link https://claude.ai/artifact/XqMtkydSzGzGt4F8MP7kh2 (Gift Substance Demo, nine numbered screens), read from the saved copy at /tmp/claude-1000/-workspaces-arxii/fc44b5ef-7a3b-4009-b7da-06a109d94293/scratchpad/demo/index.html. The demo states every name, number and line of text is an example, so shape, placement, system-line wording and controls were compared, not invented example names or numbers.
- Visual review: completed for screens 1 to 6 and the admin half of screen 8; the place-cheaper and place-dearer wording, screen 7 and the roll-breakdown line of screen 8 were checked in source or REST output only (no screenshot exists) and are not marked MATCH
- Visual verdict: PASS
- Screenshots: ![cast card with free call-up and balance line](docs/reviews/5018/01-cast-card-free-call-up.png) ![GM present here](docs/reviews/5018/02-gm-present-here.png) ![called up free](docs/reviews/5018/03-called-up-free.png) ![result ledger](docs/reviews/5018/04-result-ledger.png) ![room line](docs/reviews/5018/05-room-line.png) ![gift admin substance inline](docs/reviews/5018/06-admin-gift-substance.png) ![restriction admin surroundings](docs/reviews/5018/07-admin-restriction-surroundings.png) ![fight call-up](docs/reviews/5018/08-fight-call-up.png) ![fight call-up spent](docs/reviews/5018/09-fight-call-up-spent.png) ![blinding room, no resonance, card](docs/reviews/5018/10-blinding-no-resonance-card.png) ![blinding room, no resonance, result](docs/reviews/5018/10-blinding-no-resonance-result.png) ![blinding room in a fight, cast card](docs/reviews/5018/11-blinding-fight-card.png) ![resonance environment settings, Gift substance group](docs/reviews/5018/13-admin-substance-settings.png)
- Comparison notes: The four defects from the first pass are fixed and now render as the demo draws them. F1: the Your gift row shows "Anima: 30 · after: 30 · Gloaming resonance after: unchanged" under the button (01), and "Anima: 30 · after: 22 · Gloaming resonance after: 7" for a paid call-up (11). F2: a cast that could not call up reads "0 anima spent · no resonance left to call up shadow" with Environment, Surroundings: shadow -10 in the ledger (10 result), and the card reads "Too little resonance to call up shadow" and "Too bright here -10 power" (10 card). F3: the call-up line is the left label with the cost in a right-hand column: "Calls up shadow | free, your control covers it" (01) and "Calls up shadow against the light | 8 anima, 3 Gloaming resonance" with Cost: 12 anima and "Shadow here after the call-up +5 power" (11), which matches demo screen 2's blinding card. F4: Gift admin labels are Name in lines, Room reading, More substance when the reading (falls), Full measure, Opposed by, When it arrives, the room sees (06); Restriction labels are Room reading, At least, At most (07). Everything else matched on the first pass still matches (GM Stage panel, Narrator line, fight button beside Dig deep with its once-a-round line, telnet). F5 is also fixed: the Resonance environment settings admin has a Gift substance group with the six demo labels, Power at a full measure, Counts as present at (% of a measure), Anima per measure called up, Resonance per measure called up, Largest place discount or surcharge (%), and Unmet surroundings penalty (% of a typical roll) (13). No divergence remains. Example-value differences (Gloaming instead of abyssal, Dig deep 3 fatigue instead of 2, Veil of Dusk instead of Shadow technique, totals) are not defects.
- Tested interactions: opened the scene action panel and read the Cast section, the Your gift row and its balance line; pressed Call up shadow (toast "You call up shadow. Cost: free." then the row reads "shadow is already here"); cast a technique and read the spend line and Power ledger; cast in a blinding room with no resonance left and read the card and the result; as GM opened Stage, chose Present here, picked shadow, pressed Mark present (toast "Shadow is now present here for this scene."), saw it listed under Marked in this scene with Remove; read the scene log for the unattributed Narrator line; opened the Gift admin change form, the Restriction add form and the Resonance environment settings change form; in a fight read Call up shadow beside Dig deep, then a blinding-room card with the call-up line, pressed Call up shadow and saw it spent for the round; telnet stage present shadow and callup.
- Fixture/live boundary: everything is live on the branch's own server and database; nothing mocked at the API. Seed rows (gift, substance, character, scene, fight) come from src/integration_tests/live_seeds.py. Not live-exercised: the place-cheaper and place-dearer variants (no place resonance authored in the test database; wording read from _call_up_text in src/world/magic/services/substance.py), screen 7 weather and wall readings (backend only, no new UI), the roll-breakdown line of screen 8, dark theme.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S1-gift-admin-substance-inline | PASS | 06-admin-gift-substance.png shows the Substance inline with the demo's six labels and help lines. | none needed |
| S2-cast-card-lines | PASS | 01-cast-card-free-call-up.png and 11-blinding-fight-card.png show Cost, the call-up line with right-hand cost, against-the-light wording and the power line. Place variants verified in source only (U1). | none needed |
| S3-result-spend-and-ledger | PASS | 04-result-ledger.png and 10-blinding-no-resonance-result.png show the spend line, the no-resonance-left clause and the Environment, Surroundings: shadow ledger line. | none needed |
| S4-room-line-unattributed | PASS | 05-room-line.png shows the italic Narrator line naming no one. | none needed |
| S5-call-up-no-technique-social | PASS | 01 and 03 show the Your gift row, button, cost line and the Anima and resonance balance line. | none needed |
| S5-call-up-no-technique-fight | PASS | 08, 09 and 11 show Call up shadow beside Dig deep with Once a round. Not your action for the round., spent after pressing, and the balance line. | none needed |
| S5-telnet | PASS | stage and callup transcripts in Tested interactions match the demo transcripts. | none needed |
| S6-gm-present-here | PASS | 02-gm-present-here.png shows Stage tab, Mode Present here, Substance shadow, Mark present, Marked in this scene with Remove. | none needed |
| S7-weather-walls | PASS | Backend only per the demo (existing inlines); no UI to compare; behaviour covered by the journey tests. | none needed |
| S8-restriction-surroundings | PASS | 07-admin-restriction-surroundings.png shows the Surroundings (DESIGN only) fieldset with Room reading, At least, At most and the own-gift help line. Roll-breakdown line verified in source only (U1). | none needed |
| S-authoring-settings-admin | PASS | 13-admin-substance-settings.png shows the Gift substance group on the Resonance environment settings admin with the demo's six labels and help lines. | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Screen 1 Substance inline on the Gift form | A Substance section on Change gift | MATCH | 06-admin-gift-substance.png |
| Screen 1 field labels | Name in lines; Room reading; More substance when the reading; Full measure; Opposed by; When it arrives, the room sees | MATCH | 06-admin-gift-substance.png |
| Screen 1 help lines | Approved help text under each field | MATCH | 06-admin-gift-substance.png (Full measure help carries one extra closing sentence, accepted) |
| Screen 2 cost line | Cost: N anima | MATCH | 01-cast-card-free-call-up.png and 11-blinding-fight-card.png (Cost: 12 anima) |
| Screen 2 free call-up line | Calls up shadow, value free: your control covers it, right-aligned | MATCH | 01-cast-card-free-call-up.png |
| Screen 2 blinding call-up line | Calls up shadow against the light, 8 anima, 3 resonance, right-aligned | MATCH | 11-blinding-fight-card.png |
| Screen 2 power line after call-up | Shadow here after the call-up, +5 power | MATCH | 01-cast-card-free-call-up.png and 11-blinding-fight-card.png |
| Screen 2 no-resonance lines | Too little resonance to call up shadow; Too bright here -10 power | MATCH | 10-blinding-no-resonance-card.png (demo wording "of her resonance" is persona phrasing) |
| Screen 3 spend line | N anima spent (X to call up shadow) · Y resonance spent | MATCH | 04-result-ledger.png shows the spend line; the call-up clause is conditional and rendered by CastSpendLine.tsx |
| Screen 3 no resonance left clause | 0 or 4 anima spent · no resonance left to call up shadow | MATCH | 10-blinding-no-resonance-result.png |
| Screen 3 Power ledger Environment line | Environment, Surroundings: shadow, amount, Total power | MATCH | 04-result-ledger.png and 10-blinding-no-resonance-result.png |
| Screen 4 Narrator line | Italic Narrator line, names no one | MATCH | 05-room-line.png |
| Screen 5 Your gift row | Heading Your gift, Call up shadow button, cost line | MATCH | 01-cast-card-free-call-up.png and 03-called-up-free.png |
| Screen 5 balance readout | Anima: N · after: M · resonance after: value under the button | MATCH | 01-cast-card-free-call-up.png (unchanged) and 11-blinding-fight-card.png (after: 22, resonance after: 7) |
| Screen 5 fight button and hint | Call up shadow with cost beside Dig deep; Once a round. Not your action for the round. | MATCH | 08-fight-call-up.png and 09-fight-call-up-spent.png |
| Screen 5 telnet | callup lists gift; callup shadow replies You call up shadow. Cost: free. | MATCH | src/commands/gift_substance.py output and the toast in 03-called-up-free.png |
| Screen 6 Stage mode, substance, Mark present | Present here mode, Substance picker, Mark present | MATCH | 02-gm-present-here.png |
| Screen 6 marked list | Marked in this scene with shadow and Remove | MATCH | 02-gm-present-here.png |
| Screen 6 telnet | stage present shadow replies Shadow is now present here for this scene. | MATCH | toast text in 02-gm-present-here.png |
| Screen 8 Surroundings fieldset | Fieldset with Room reading, At least, At most and own-gift help | MATCH | 07-admin-restriction-surroundings.png |
| Authoring page: resonance environment settings labels | Gift substance group with Power at a full measure, Counts as present at, Anima per measure called up, Resonance per measure called up, Largest place discount or surcharge, Unmet surroundings penalty | MATCH | 13-admin-substance-settings.png |

## Unresolved findings

None

## Reviewer notes

Not findings: F1 to F5 from the earlier passes were fixed and re-checked at this revision. Not screenshotted and verified in source or REST output only: the place-cheaper and place-dearer wording (_call_up_text in src/world/magic/services/substance.py matches the demo), the roll-breakdown line of screen 8 (src/world/magic/services/surroundings.py), and screen 7's weather, wall and window readings (backend only, no UI). They are listed as not visually compared, not as divergences. Proposed mechanical test: an admin test that loads the ResonanceEnvironmentConfig change form and asserts the six substance fields sit under a Gift substance fieldset with the demo labels, beside the frontend component tests that pin the balance line and the no-resonance-left clause.
