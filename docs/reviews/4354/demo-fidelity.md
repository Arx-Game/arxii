# Demo fidelity review: #4354 Standoffs slice 1 (GM runs a standoff)

- Reviewed commit: 507d62a46e61e178dc908968147d3db94ebfd4bb (branch feature-4354-standoffs-gm-runs-a-standoff)
- Approved design: https://claude.ai/artifact/1926LF7noogf1hKijgL3v8 (read in full from the saved copy; screens 1-3 x three seats, Admin A)
- Build identity/environment: real dev server, scratch database (Orders group "Gate Sellswords", GM Hale, players Tamsin and Bram, onlooker Oriel). Viewport about 1500px wide, light theme.
- Fixture vs live: the server and UI are live. Names, placeholder texts, "Impossible" grades (no check-rank/result-chart rows) and the -50 margin default are seeded or missing data, not layout.
- Method: vision comparison of screenshots against the demo's rendered text and structure. Rendered admin page shows forms.css loaded (form rows, help text, submit-row all styled; `page.html` line 13 links `admin/css/forms.css`). I did not run the DOM-level CSS reach check beyond that.
- Out of slice (not counted): named NPC groups, Speaks/language, affiliation and per-placement edits, inherited rules, predicate builder, Admin B-E.

Screenshots (all in this directory): 01-player-deciding, 02-onlooker-summary, 03-gm-prompt-and-panel, 04-gm-after-hold, 05-gm-shake-confirm, 06-gm-after-shake, 07-player-after-hold-and-shake, 08-onlooker-after-shake, 09-admin-profile-builder, 10-admin-profile-builder-saved (.png).

## Interactions tested
GM sees the Standoff prompt and panel (03); Hold for one action (04); Shake with a required reason, confirm and result (05, 06); player and onlooker views before and after (01, 02, 07, 08); builder load and save (09, 10).

## Visual checklist

Screen 1/2 GM tab (03, 04, 06) vs demo GM screens
- GM tab present beside Your Turn / Map: MATCH
- "Standoff" section above GM Controls: MATCH
- Group name, x count, state chips (proposed, emboldened): MATCH
- Cause row "Orders" plus "holds: will not attack first": MATCH
- Drives row, read marks (drive names, strength, "unread"): MATCH
- Morale row, per member with state: MATCH
- Force line "party N, them N. Party outweighs them." plus bar: MATCH (bar is an addition)
- Faction rule table (rule / matches / read): MATCH (columns Faction rule, Matches, Read; "From" column excluded)
- Cause-fires reason line inside the panel: MATCH (extra, in-panel copy)
- Shake / Steady control, "one morale step, reason required": MATCH
- Shake confirm box with reason field and Cancel (05): MATCH (copy differs: "Shake them" vs demo "Shake", no "steady to faltering" gloss; see D3)
- Participants line "In the standoff: ...": MATCH
- Faltering chip after shake (06): MATCH
- "settled: Paid off" / "Toll recorded" / "Prompt 214 held" line: NOT BUILT (terms/settle is not in the GM prompt slice; see D4)
- Per-group Maud Carrow card: out of slice

GM prompt (03) vs "GM prompt · just now"
- Purple prompt row, kind chip "Standoff", title "<group>: cause fires": MATCH
- "Cause: Orders. Reason: ... (counts as a provocation)." line: MATCH (full stop doubled in 03, fixed in 507d62a46; not re-shot)
- Confirm: they attack / Hold for one action / Override buttons: MATCH
- Reason (required to override) field: MATCH
- "Players can keep acting while you decide..." help line: MATCH
- Force numbers and emboldened bands in the prompt body: DIFFERS (demo prompt body ends "Force: party 41, them 30, emboldened 1 band."; build shows force only in the panel; see D2)
- Prompt placement: demo shows it as a "GM Prompts" strip; build puts it above the composer under the scene log: MATCH in kind

Player card (01, 07) vs Player: Wrenna
- "Standoff at <place>" heading: MATCH
- Your angle here box, angle text, "How, you don't know yet. A read could tell you.", Share with the party: MATCH
- Group tile with name, x count, "emboldened, deciding" marker without saying what was proposed: MATCH
- Face-down "?" tiles, one per member: MATCH
- Look for dropdown: DIFFERS in default label ("Anything" vs demo "Why would they fight?"; the build does offer the cause option at StandoffCard.tsx:340): acceptable
- Read them / Bribe / Threaten rows with check and grade, "no known lever": MATCH
- "Name your terms. Each successful press makes this easier." plus Let us pass: MATCH
- "Faltering: 1 more step easier" line (07): MATCH
- Fight, "starts round one": MATCH
- "Something about one of you matters to them." line under tiles: MISSING on the web card (string exists only in `src/world/standoffs/services/describe.py:18`; see D1)
- Orders cause tile and gloss: not exercised in screenshots (needs the read); not verified

Onlooker (02, 08) vs Onlooker: Brother Anselm
- "Standoff" header with Observer pill: MATCH
- "Standoff at <place>" summary table Group / Count / State: MATCH
- State chips (emboldened, Faltering): MATCH
- "In the standoff: ..." line: MATCH
- Join button: MISSING (demo shows Join under the table; see D5)
- No cause/drive/angle shown to onlooker: MATCH

Admin A, Standoff Profile Builder (09, 10) vs demo
- Admin chrome, breadcrumb Home > Creature templates > Gate Sellswords > Standoff profile: MATCH
- Form left, context panel right layout: MATCH
- "The creature" module with Mook chip and "used in N placements": MATCH
- Cause select plus help copy: MATCH
- Cause margin percent plus help copy: MATCH
- Drives table (Property, Strength, What it means, Hit by, Delete?) and "+ Add another drive": MATCH
- Faction rules section, rule textarea with help, difficulty shift, angle and revealed text, "+ Add another faction rule": MATCH (JSON textarea is in slice; extra Deed archetype / Drive / Drive shift / Suppresses cause rows are additions)
- Submit row: DIFFERS ("Save" and "Save and go back to the creature"; demo has Save, Save and continue editing, and a Back link; see D6)
- Right rail panels: Grade preview (Try), Cause check, Placements: MATCH (demo's "Also applies (inherited)" excluded)
- Saved message after save (10): MATCH
- forms.css reaches the page (styled form rows, help, submit-row visible): MATCH

## Criteria verdicts
- Rule reaches the page (forms.css, GM/player/onlooker CSS): PASS
- Host CSS contract (admin form-row/module markup; app uses repo tokens): PASS
- Layout regions present in demo order: PASS with gaps (D1, D5)
- Approved copy retained: PASS with gaps (D1, D2, D3, D4)
- Silent unbuilt affordances: FAIL until D1, D5, D6 are either built or written down in the issue scope
- Divergences with a stated reason: none found beyond the slice cut

## Per-screen verdicts
- Screen 1 GM / player / onlooker: matches with noted gaps (D1, D5)
- Screen 2 prompt and views: matches with noted gaps (D2)
- Screen 3 GM morale control: matches with noted gaps (D3, D4)
- Admin A: matches with noted gaps (D6)

## Unresolved findings
- D1 (defect or scope question): player web card omits "Something about one of you matters to them." The demo shows it under the face-down tiles whenever a faction rule matches the viewer; telnet has it (describe.py:18), the web card (StandoffCard.tsx) does not.
- D2 (minor defect): GM prompt body lacks the "Force: party N, them N, emboldened N band" tail the demo puts in the prompt.
- D3 (minor): shake confirm copy: demo has a "Shake" button and gloss "moves her one state: steady to faltering"; build has "Shake them" and no from/to gloss.
- D4 (scope question): the "Prompt 214: held for one action by you; the cause did not fire again" line is not shown after a hold (04). Settled/terms rendering on the GM panel is not built; confirm the issue scopes it out.
- D5 (scope question): observer summary has no Join button (demo, marked "exists" there). Confirm the issue scopes it out, or add it.
- D6 (defect): Builder submit row lacks "Save and continue editing" and a "Back to the creature" link in the shape the demo draws; build has "Save" and "Save and go back to the creature" only.
- Not verifiable here: Orders cause tile and gloss for a player who has read it; grades (scratch data).

Mechanical companion proposal: a test like `BuilderStylingTest` for the profile builder page that renders the page, resolves linked stylesheets and asserts a rule exists for `.form-row`, `.submit-row`, `.module h2` in forms.css and for the rail classes in `_css.html`.

## Verdict on 507d62a46: FAIL (superseded by the re-review below)

---

# Re-review at 019b5cf1286722f2407eb8d4f11b081817f0d240

Reviewed revision: 019b5cf1286722f2407eb8d4f11b081817f0d240 (fixes in cf96d4455; migration renumbering after). The ten screenshots in this directory were re-shot from a fresh build of that HEAD on a fresh seeded server (same viewport and theme as above). I re-read 01, 03, 05 and 10 against the demo.

| Finding | Result | Evidence |
|---|---|---|
| D1 hidden-rule line | FIXED | 01: "Something about one of you matters to them." sits under the face-down tiles, as in the demo |
| D2 force tail in prompt | FIXED | 03: prompt ends "Force: party 2, them 2, emboldened 1 band." |
| D3 shake confirm copy | FIXED | 05: "Shake Gate Sellswords", reason field, Shake / Cancel, gloss "moves them one state: steady to faltering" |
| D4 hold feedback | FIXED within scope | 05: "Last decision: Held for one action." The demo's "Prompt 214 ... toll recorded" and Paid-off settle text belong to terms/settle rendering, which is outside the GM-prompt slice. Accepted as a scope cut. |
| D5 observer Join | STATED DIVERGENCE | Join keeps the panel's existing rule (open-type encounters between rounds), no new path. The observer summary shows no Join in the screenshots. Accepted because the author stated it; the human may still want it. |
| D6 submit row | FIXED | 10: Save, Save and continue editing, Back to the creature |

Other checklist rows from the first review are unchanged: MATCH. Still not verifiable in screenshots: the Orders cause tile and gloss after a read, and real grades (scratch data).

## Remaining unresolved findings
None that are defects. Two accepted scope cuts (D4 settle/terms text, D5 Join) are for the human to confirm.

## Verdict at 019b5cf1286722f2407eb8d4f11b081817f0d240: PASS
