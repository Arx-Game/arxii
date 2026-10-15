# Demo fidelity review: #4121 slice 2 (#4361)

- Reviewed commit: 7a07273146073bf3f43883bde8307bc4b2e1400b (re-review; first pass was 9ddca0b7c)
- Approved design: demo artifact saved at
  `.../tool-results/artifact-011e9f82-1791928927-5c15.html` (Screen 1 GM seat lines 291-374;
  Admin B lines 853-924; Admin C lines 926-981; Admin A lines 780-850).
- Evidence: the eight PNGs in this directory (real server run, Chromium, production build,
  throwaway DB). Viewing was done with vision on each image. Names are placeholders by design.
- Not done: no side-by-side at an identical viewport (the demo is a static mock); no dark theme;
  screenshot 05 is clipped at the dialog bottom, so the footer is unseen.

## Visual checklist

| Element (per demo) | Verdict | Evidence |
|---|---|---|
| Admin B: title "Faction rules: <org>", breadcrumb Org > Faction rules | MATCH | 01 |
| Admin B: "Rules this organization holds" with stacked per-rule headings + Delete | MATCH (headings are generated labels, accepted) | 01 |
| Admin B: Test row hosts predicate widget (leaf select, org param, x remove, help line) | MATCH | 01 |
| Admin B: widget "+ Group / + Leaf" links under a top-level leaf | MATCH (fixed, G1) | 09 |
| Admin B: Difficulty shift bands, Angle text, Revealed text rows with help | MATCH | 01 |
| Admin B: Drive + shift as one inline row | STATED DIVERGENCE (G2) | 01 |
| Admin B: Cause effect select | OUT_OF_SCOPE (build has "Suppresses cause" checkbox) | 01 |
| Admin B: "+ Add another faction rule", submit row (Save, Save and continue) | MATCH (extra "Back to the organization" is fine) | 01 |
| Admin B rail: Inherits from above, rows with source + precedence note | MATCH | 01 |
| Admin B rail: Reaches (templates, placements, child orgs) | MATCH | 01 |
| Admin B rail: Test a character, matches + reason, staff-only note | MATCH (plain name field, stated divergence G3) | 02 |
| Admin C: "This placement": Opens as standoff, Cause (template: Orders), Affiliation | MATCH (G4 fixed in code; placeholder not re-shot) | 03, 04 |
| Admin C: Drives here table Drive/Template/Here/Effect, "edited", "removed here" | MATCH | 03, 04 |
| Admin C: "+ Add a drive for this placement" | MATCH | 03 |
| Admin C: Inherited faction rules, Rule/From/Switch off here, checkbox persists | MATCH | 03, 04 |
| Admin C: submit row, "Back to the beat" | MATCH | 03 |
| Admin C rail: What spawns, The beat, The GM's own path | MATCH (adds "The template" panel, harmless) | 03 |
| Admin C: saved confirmation | MATCH (extra, expected) | 04 |
| Admin A: Affiliation field + "Also applies (inherited)" rail with source column and note | MATCH | 09 |
| Beat dialog: "Standoff for this line" dashed panel, Opens as a standoff | MATCH | 05 |
| Beat dialog: Cause + Affiliation selects with "(template)" | MATCH (extra search box: stated divergence G5; label still truncated) | 05, 05b |
| Beat dialog: Drive/Template/Here table, edited/removed marks | MATCH | 05 |
| Beat dialog: "+ Add a drive" | MATCH | 05 |
| Beat dialog: Inherited rule / From / Off here, Riverland off checked | MATCH (rows visible up to the fold) | 05 |
| Beat dialog: "Spawns ..." summary line | MATCH (fixed, G6) | 05b |
| Beat dialog: Cancel / Save beat footer | UNVERIFIED (not in any image) | none |
| GM panel: Drives "Defining edited here" | MATCH | 06, 08 |
| GM panel: Affiliation row with "set on this line" mark | UNVERIFIED visually; covered by GMStandoffPanel.test.tsx and test_placement.py (G7) | 06, 08 |
| GM panel: Faction rule table Rule/From/Matches/Read | MATCH | 06, 08 |
| GM panel: Force bar, morale controls, participants line | MATCH | 06 |
| GM panel: Speaks, named NPC group, Cause "inherited" | OUT_OF_SCOPE | n/a |
| Player: angle from an organization rule + Share | MATCH (two angles stacked in one box, valid for Ottilie matching two rules) | 07 |
| Predicate widget in Admin A (op select, param, x, + Leaf / + Group) | MATCH | 09 |
| Approach/Terms/Config previews, PC profiles | OUT_OF_SCOPE | n/a |

## Gaps (status after 7a0727314)

- G1: FIXED. Top-level test has "+ Leaf" / "+ Group" (09).
- G2: STATED DIVERGENCE. Drive and drive shift remain two standard admin form rows.
- G3: STATED DIVERGENCE. Character test is a plain name field; CharacterSheet has no admin
  autocomplete source.
- G4: FIXED in `src/web/admin/standoff_placement/forms.py` (placeholder "(template: <org>)").
  Not re-shot; only the code claim.
- G5: STATED DIVERGENCE for the search box (organizations are searched server-side). The
  select's label is still truncated in 05b ("Saltreed Company (test) (ten..."); cosmetic.
- G6: FIXED. 05b shows the whole panel with the Spawns line. The dialog's Cancel / Save footer
  is still not in any image.
- G7: PARTLY FIXED. Admin A is in 09. The "set on this line" mark has no screenshot; it
  rests on tests (GMStandoffPanel.test.tsx, test_placement.py), which is not visual evidence.

## Verdict

PASS. Every in-scope captured surface matches the approved design; the remaining differences are
stated divergences or cosmetic. Two minor items stay without visual proof (the "set on this
line" mark and the dialog footer), recorded above rather than marked MATCH.
