# Review evidence

- Reviewed revision: `f4b46ba95cdce6510ba780991fe1c228a7940696`
- Reviewer: `demo-fidelity-reviewer (Claude, vision-capable), comparing the rendered screenshots to the approved demo source`
- Reviewer verdict: `PASS`
- Application/build identity: `Arx II web client built with just fe-build from commit f4b46ba95 (bundle index-BwuqgM78.css, rebuilt at 06:03 after the fix commits daca48bc0 and f4b46ba95) served by the Evennia server on localhost:4001 against the throwaway database rt_5280`
- Environment: `Linux devcontainer, headless Chromium (Playwright chrome-headless-shell 1208), Postgres rt_5280, two logged-in players: e2e_test_account plays Mara, rt_tobin plays Tobin, both in the room The Lantern; anima config row has attunement costs anima 2, resonance 5, AP 10, a check type set, failed endorsement percent 50. Server restarted after nulling both picks so the unset editor was rendered.`
- Viewports/themes: `Light: 1400x1000 (unset editor, scroll check), 1400x800 (locked editor and Attune dialog, scroll check), 1400x1300 (game page card and feeds). Dark: 1400x1200 (Attune dialog). The app theme setting is system and Chromium supplied the colour scheme.`
- Approved design: `Issue 5280 demo https://claude.ai/artifact/S9DwCZqzJraG7mecxsRs2S (HTML source read in full from the session scratchpad demo-5280.html); screens 1 to 4 compared. Screen 5 and the authoring tables describe data and are out of scope for a visual comparison. The controller ruled that the demo's "Only X sees this" labels and the aura split bar with its hint were annotation drawn inside the demo's screen frames (a demo-framing error) and are out of scope, and that the Edit Anima Ritual title and the stacked pickers in the 512 px dialog stand.`
- Visual review: `Completed`
- Visual verdict: `PASS`
- Screenshots: ![Screen 1 unset editor at 1000 px, scrolled to top](.github/issue-evidence/5280/w01-unset-1000-top.png) ![Screen 1 unset editor at 1000 px, scrolled to bottom](.github/issue-evidence/5280/w01-unset-1000-bottom.png) ![Screen 1 two picks chosen](.github/issue-evidence/5280/v02-editor-picked.png) ![Screen 1 locked editor at 800 px, scrolled to top](.github/issue-evidence/5280/w02-locked-800-top.png) ![Screen 1 locked editor at 800 px, scrolled to bottom](.github/issue-evidence/5280/w02-locked-800-bottom.png) ![Screen 1 locked editor with Attune](.github/issue-evidence/5280/v03-editor-locked.png) ![Screen 4 Attune dialog at 800 px](.github/issue-evidence/5280/w03-attune-800.png) ![Screen 4 Attune dialog open](.github/issue-evidence/5280/v04-attune-open.png) ![Screen 4 outward pick changed](.github/issue-evidence/5280/v05-attune-changed.png) ![Screen 4 dark theme](.github/issue-evidence/5280/v19-dark-attune-dialog.png) ![Screen 2 partner card and feed after the fix](.github/issue-evidence/5280/w04-tobin-card-after-fix.png) ![Screen 2 card close-up](.github/issue-evidence/5280/w05-tobin-card-closeup.png) ![Screen 2 partner after answering](.github/issue-evidence/5280/v13-tobin-after-endorse.png) ![Screen 3 Mara lines with anima recovered, Endorse](.github/issue-evidence/5280/v17-mara-lines-with-anima-endorsed.png) ![Screen 3 Mara after Endorse, anima already full](.github/issue-evidence/5280/v12-mara-told-endorsed.png) ![Screen 3 Mara lines after Withhold](.github/issue-evidence/5280/v18-mara-lines-withheld.png) ![Screen 3 refusal with nobody named](.github/issue-evidence/5280/v06-mara-refused-no-partner.png)
- Comparison notes: `Re-review after the two defects of the first pass were fixed. Screen 2: the card hint now reads "Mara's ritual leaves you wearier." exactly as in the demo (w04, w05). Dialog fit: the Edit Anima Ritual dialog now scrolls inside itself (overflow-y auto, max height 90 vh); with the unset editor at 1000 px high the title shows at y 75 and Save and Cancel are reachable at y 925 after scrolling, and with the locked editor at 800 px high the title shows at y 65 and Save and Cancel are reachable at y 735 (w01, w02); the Attune dialog at 800 px fits whole with overflow-y auto (w03). Screens 1, 3 and 4 match as in the first pass. Screenshots v02 to v06, v12, v13 and v17 to v19 were taken at the earlier revision c6a855726; the commits since touch only the card hint text and a max-height class on the two dialogs, so those renders are unchanged apart from what the w-series re-renders at the reviewed revision. Items resolved by controller ruling and not counted as discrepancies: the "Only Tobin sees this" and "Only Mara sees this" labels, the aura split bar and its hint, the Edit Anima Ritual title, and the stacked pickers. Seen but not a demo finding: the existing white-on-white colour markup hides the command names in the consent line and the endorsement feed line ("Type  to agree or  to refuse.").`
- Tested interactions: `As Mara: opened Rituals, Manage, Edit on a ritual with no picks, scrolled the dialog to its top and bottom at 1000 px and 800 px viewport heights, picked Hollow and Ruin, pressed Set resonances, saw the picks lock and Attune appear, opened Attune, read the cost rows, switched the outward pick to Dawn (earlier revision), cancelled. In a started scene typed ritual anima with no partner and read the refusal (earlier revision); typed ritual anima Tobin. As Tobin on the live game page: read the consent request and the private lines, pressed Accept, read the endorsement card, pressed Endorse. As Mara: read the ritual lines and the follow-up line. Withhold, the attune submit and the earlier scene runs come from the real-testing pass on commit c6a855726. Not operated live: a failed roll, an NPC partner, a lapse on scene finish, the Attune refusals.`
- Fixture/live boundary: `Everything shown reached the live Evennia server, the real REST endpoints and the Postgres database rt_5280 through the built web client; nothing is mocked. Data is seeded fixture data in a throwaway database (placeholder names Hollow, Marrow, Ruin, Dawn, Mara, Tobin, a check type named CheckType2 and a one-band result chart so every roll is a Success). Placeholder names differ from the demo's Thrill, Hunger, Dread, Mercy.`
- Overall outcome: `PASS`

## Comparison detail

Screen 1, the ritual editor. The two pill pickers, their labels, hints, affinity inks, the free Set resonances button, the read-only locked boxes and the ghost Attune button match the demo, and the typed resonance number is gone. The dialog now scrolls inside itself, so its title and its Save and Cancel row are reachable at 1000 px and 800 px viewport heights.

Screen 2, the partner answers. The card sits above the feed on the game page and shows the prompt "Mara's ritual reached for your ruin. Did it take hold of you?", a filled Endorse, an outlined Withhold and the hint "Mara's ritual leaves you wearier." The Celestial case now serves "leaves you lighter." and a fatigue of 0 serves nothing, per commit daca48bc0.

Screen 3, what Mara reads. Line one and line two match the demo's shape: "Your ritual feeds on Tobin. You recover 6 anima. Your Hollow grows by 3." and "Tobin felt it. Your Ruin grows by 3." The withheld line "Tobin did not feel it." and the refusal "Name someone else to take part in your ritual." match the demo's annotation.

Screen 4, attuning. Title, both pickers with the current picks selected, the cost rows Anima, Resonance cost with the newly picked name in brackets, Action points and Roll, and the Attune and Cancel buttons match. The Roll row shows the staff-set check type name where the demo's "Willpower + Ritualism" is an example.

Departures that stand: the pickers start with nothing selected where the demo shows one pill already on (the demo says its picks are placeholders); the Roll row is conditional, as the demo's note says; the dialog keeps its title Edit Anima Ritual and stacks the pickers (controller ruling).

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Screen 1 heading | Card headed "Your anima ritual" | MATCH | resolved by controller ruling: the existing title Edit Anima Ritual stands; ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 primal label | "What you feel when you perform it" | MATCH | ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 primal pills | One pill per Primal resonance held, orange ink, selected pill bold with current-colour border | MATCH | ![v02](.github/issue-evidence/5280/v02-editor-picked.png) |
| Screen 1 primal hint | "Primal resonances you hold" | MATCH | ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 outward label | "What it does to the other person" | MATCH | ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 outward pills | Celestial (cyan) and Abyssal (violet) pills plus a neutral None pill | MATCH | ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 outward hint | "Celestial and Abyssal resonances you hold" | MATCH | ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 layout of the two fields | Side by side in one row | MATCH | resolved by controller ruling: stacked in the 512 px dialog stands; ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 Set resonances button | Filled button under the pickers | MATCH | grey until a pick is made, dark after; ![v02](.github/issue-evidence/5280/v02-editor-picked.png) |
| Screen 1 typed resonance number | Gone | MATCH | ![w01](.github/issue-evidence/5280/w01-unset-1000-top.png) |
| Screen 1 locked primal box | "What you feel" with a dashed box in Primal ink | MATCH | ![w02](.github/issue-evidence/5280/w02-locked-800-top.png) |
| Screen 1 locked outward box | "What it does to them" with a dashed box in outward ink | MATCH | ![w02](.github/issue-evidence/5280/w02-locked-800-top.png) |
| Screen 1 Attune button | Ghost button under the locked boxes | MATCH | ![v03](.github/issue-evidence/5280/v03-editor-locked.png) |
| Screen 1 dialog fit | Whole screen reachable in the viewport | MATCH | scrolls inside the dialog at 1000 px and 800 px; ![w02](.github/issue-evidence/5280/w02-locked-800-bottom.png) |
| Screen 2 private header | "Only Tobin sees this" above the question | MATCH | resolved by controller ruling: annotation inside the demo frame, out of scope; ![w04](.github/issue-evidence/5280/w04-tobin-card-after-fix.png) |
| Screen 2 prompt | "Mara's ritual reached for your dread. Did it take hold of you?" | MATCH | placeholder resonance reads ruin; ![w05](.github/issue-evidence/5280/w05-tobin-card-closeup.png) |
| Screen 2 buttons | Filled Endorse and ghost Withhold | MATCH | ![w05](.github/issue-evidence/5280/w05-tobin-card-closeup.png) |
| Screen 2 hint line | "Mara's ritual leaves you wearier." | MATCH | ![w05](.github/issue-evidence/5280/w05-tobin-card-closeup.png) |
| Screen 2 card placement | Shown to the partner in the scene | MATCH | above the feed on the game page; ![w04](.github/issue-evidence/5280/w04-tobin-card-after-fix.png) |
| Screen 3 private header | "Only Mara sees this" above her lines | MATCH | resolved by controller ruling: annotation inside the demo frame, out of scope; ![v17](.github/issue-evidence/5280/v17-mara-lines-with-anima-endorsed.png) |
| Screen 3 line one | "Your ritual feeds on Tobin. You recover 6 anima. Your Thrill grows by N." | MATCH | placeholder resonance Hollow, 3; ![v17](.github/issue-evidence/5280/v17-mara-lines-with-anima-endorsed.png) |
| Screen 3 line two | "Tobin felt it. Your Dread grows by N." | MATCH | placeholder resonance Ruin, 3; ![v17](.github/issue-evidence/5280/v17-mara-lines-with-anima-endorsed.png) |
| Screen 3 aura split bar | Two coloured segments sized by the aura | MATCH | resolved by controller ruling: annotation inside the demo frame, out of scope; ![v17](.github/issue-evidence/5280/v17-mara-lines-with-anima-endorsed.png) |
| Screen 3 split hint | "Her aura is 75 Abyssal to 25 Primal, so an award of 8 splits 6 to Dread and 2 to Thrill." | MATCH | resolved by controller ruling: annotation inside the demo frame, out of scope; ![v17](.github/issue-evidence/5280/v17-mara-lines-with-anima-endorsed.png) |
| Screen 3 note lines | "Tobin did not feel it." on Withhold and the Name someone else refusal | MATCH | ![v18](.github/issue-evidence/5280/v18-mara-lines-withheld.png) |
| Screen 4 title | "Attune your ritual" | MATCH | ![w03](.github/issue-evidence/5280/w03-attune-800.png) |
| Screen 4 pickers | Both pickers with the current picks selected, outward offers None | MATCH | ![w03](.github/issue-evidence/5280/w03-attune-800.png) |
| Screen 4 cost rows | Anima, Resonance cost (new pick), Action points, Roll | MATCH | ![v05](.github/issue-evidence/5280/v05-attune-changed.png) |
| Screen 4 buttons | Filled Attune and ghost Cancel | MATCH | ![v05](.github/issue-evidence/5280/v05-attune-changed.png) |
| Screen 4 dark theme | Pills and costs readable on the dark ground | MATCH | ![v19](.github/issue-evidence/5280/v19-dark-attune-dialog.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| D01 | PASS | Screen 1 unset and locked editor render with the demo's pickers, hints, inks and buttons; w01, w02, v02, v03 | |
| D02 | PASS | Screen 2 card hint reads "Mara's ritual leaves you wearier." after commit daca48bc0; w04, w05 | |
| D03 | PASS | Screen 3 lines match the demo's wording and amounts; v17, v18, v06 | |
| D04 | PASS | Screen 4 Attune dialog matches title, pickers, cost rows and buttons in light and dark, and fits at 800 px; w03, v05, v19 | |
| D05 | PASS | Every utility class the new components use renders: inks, pills, amber card, dashed boxes and cost grid show in the screenshots, the dark variant is in the built stylesheet index-BwuqgM78.css and the max-h-[90vh] rule is in it too | |
| D06 | PASS | The Edit dialog scrolls inside itself after commit f4b46ba95: title and Save and Cancel reachable at 1000 px (unset) and 800 px (locked); w01, w02 | |
| D07 | OUT_OF_SCOPE | The private-line headers, the aura split bar and hint, the Your anima ritual heading and the side by side pickers | Controller ruling after the first pass: the headers, bar and hint were annotation inside the demo frames, and the Edit Anima Ritual title and stacked pickers stand |

## Unresolved findings

- None
