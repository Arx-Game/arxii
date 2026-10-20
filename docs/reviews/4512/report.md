# Review evidence

- Reviewed revision: `9be2f4836f711611b90436fb811d1ec2a4aeba46`
- Reviewer: `demo-fidelity-reviewer agent (local), two passes; the first returned FAIL with five divergences, four were fixed and re-shot, the second pass returned PASS`
- Reviewer verdict: `PASS`
- Application/build identity: this branch's own code (commit before the rebase onto main, no code change since): the Django dev server on :4101 and the Vite dev server on :3101 proxying to it, against a scratch Postgres database arxiidev_4512 built with tools/build_schema.py
- Environment: Linux devcontainer, Chromium (Playwright), Postgres. The scratch database was seeded by a throwaway script (two played characters, Corwen's shop with a Lab station, a Kestrel facet offer at 40 coppers, a tie between them, a coat, a cloak, a jerkin and an heirloom saddle). No other session's server or database was touched.
- Viewports/themes: 1000 px wide desktop (1300 for the Django admin), light theme
- Approved design: local copy of the demo for spec #4462 (`demo.html`, tabs Player "Commission Crafting (6b)", Artist "Craft: riding coat / riding boots" and "What the artist sees on their work", Onlooker "Examining the coat", Admin forms "Item instance")
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![1](docs/reviews/4512/1-commission-form.png) ![2](docs/reviews/4512/2-craft-worked-from.png) ![3](docs/reviews/4512/3-item-admin.png) ![4](docs/reviews/4512/4-examine.png)
- Comparison notes: In scope: the commission form, the crafting form's Made for and Worked from, examine, the item admin's Dedication, Lineage and rail, and the five Devotion config numbers. First pass found: the facet-work credit not shown in the evidence (re-shot from a succeeded commission on a Fine-quality coat), the made-from cap missing from the worked-from box (now "4 points; 3 recorded on the new piece (the cap)"), staff help text naming an issue and a function (cleaned), the lineage column header (now "Points at consumption"), the offer reading "facet attach" (now "facet work"), the five new Devotion fields sharing the Sacrifices fieldset (now "Made and shown"). Accepted divergences: the offer is a dialog subtitle rather than a table row and names the artist by persona; "for Linnet" where the demo says "for you"; a Facet picker the demo does not draw (the offer names the kind, the buyer picks the facet); Cancel before Commission (the shared dialog footer); the locked-dedication state shows the dedicatee's name with the exact demo note instead of disabled radios; no Silhouette or Recipe materials rows (the crafting dialog is the existing one). The toast "The attempt fails - Unknown." seen in a failed live roll is the scratch database having no check outcome names, not a code path. Out of scope: worn pieces and invocation, GM detail, keepsakes, trophies, requested items, resonance fed.
- Tested interactions: signed in as Linnet (session cookie for the account, the account's selected character set), opened the market page, pressed Commission on Corwen's offer, chose an item, a facet, wrote a name and description, chose a persona for Dedicate to, read the examine preview, and submitted (a failed roll still wrote the words and charged the fee; a later succeeded roll attached the Kestrel facet and listed Corwen's facet work); opened the wardrobe's Craft dialog, chose Riding Boots and the saddle as Worked from and read its meaning points and cap; read the web item panel for the commissioned coat; opened the item admin as staff
- Fixture/live boundary: everything reached the live backend; the scripted parts were the seed and, for the succeeded commission, a forced roll outcome. Nothing was mocked in the browser.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Commission title and offer line | "Commission from Corwen's shop"; offer, fee, charged whatever the roll | MATCH (offer in the subtitle, accepted) | ![1](docs/reviews/4512/1-commission-form.png) |
| Your item with chips | the item, "made by Corwen for ...", "no name or description yet" | MATCH | ![1](docs/reviews/4512/1-commission-form.png) |
| Name and Description | optional fields, the "only where the item has none" note word for word | MATCH | ![1](docs/reviews/4512/1-commission-form.png) |
| Dedicate to | radios no one and another character, persona chooser | MATCH | ![1](docs/reviews/4512/1-commission-form.png) |
| Examine will read | "Made by X for Y. Designed by Z. Facet work by W." | MATCH | ![1](docs/reviews/4512/1-commission-form.png) |
| Craft: Made for, Worked from | both fields, the used-up label, the warning and note | MATCH | ![2](docs/reviews/4512/2-craft-worked-from.png) |
| Worked from meaning | the source's signals and the points that count, capped | MATCH | ![2](docs/reviews/4512/2-craft-worked-from.png) |
| Examine credits | name, description, "Of fine quality. Made by Corwen for Linnet. Designed by Linnet. Facet work by Corwen." | MATCH | ![4](docs/reviews/4512/4-examine.png) |
| Item admin Design, Provenance, Holding, Dedication | four fieldsets, read-only, designer help | MATCH | ![3](docs/reviews/4512/3-item-admin.png) |
| Item admin Lineage inline | Source item, Source name, Points at consumption | MATCH | ![3](docs/reviews/4512/3-item-admin.png) |
| Item admin rail | "Meaning for the current holder", the signals, the points, "computed from the records" | MATCH | ![3](docs/reviews/4512/3-item-admin.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| commission-text | PASS | shot 1 and 4; test_commission_loop (written text credits the commissioner, a fee alone does not, someone else's words are refused before the fee is paid) and the journey in test_commissioning_a_piece_journeys | |
| dedication | PASS | shot 1; one dedication, permanent, never to oneself (test_commission_loop, the journey's refusals told in words) | |
| made-from | PASS | shot 2; a real making worked from an heirloom saddle used the saddle up and wrote a lineage row of 4 points (live run and the Bracken journey) | |
| shown | PASS | a real showing, four engagements and the weekly settlement added 2 shown points (live run) | |
| examine-credits | PASS | shot 4 and the journeys' look output; a piece given up keeps "Gone: Given up to Highwind" | |
| admin | PASS | shot 3; test_admin (the rail and its rules reach the page, no issue number in this slice's help) | |

## Unresolved findings

- None
