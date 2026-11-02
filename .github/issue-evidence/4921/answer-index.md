# Answer index for the PR #4927 evidence items 3, 5, 6 and 11

Head sha for every item: f2d2c3f7108faf27f9782e3ef8d0b1713f03e049 (each JSON carries it as `reviewed_commit`).
Recorded in a throwaway detached worktree at that sha (since removed), against the new private Postgres test database `test_arxii_ev4921d` (did not exist before; no existing database touched or dropped), through the DRF test client, the Django admin test client, model `full_clean()` and the telnet command handler (integration_tests harness). No live server.

## Item 3. A draft PATCH with a style the selected Tradition does not teach

- Head sha: f2d2c3f7108faf27f9782e3ef8d0b1713f03e049
- Did: in a draft whose Tradition is Masque (teaches The Daring Dance and The Iron Mask), PATCHed `selected_combat_style_id` with The Hollow Crown, a style taught only by another Tradition (Hollow Court). Once with The Daring Dance already chosen, once with no style chosen.
- Expected: refused with a 400 and an error text; the stored choice unchanged.
- Saw: status code 400 both times, body `{"selected_combat_style_id": ["Your tradition does not teach this style."]}`. With The Daring Dance chosen it stayed chosen; with none chosen the stored id stayed null.
- Files: item3-patch-untaught-style.json

## Item 5. An allocation to another style's skill

- Head sha: f2d2c3f7108faf27f9782e3ef8d0b1713f03e049
- Did: chose The Daring Dance, then PATCHed `draft_data.magic_skills` with 20 points on The Iron Mask's skill (another style's) and 10 on Occult, read the draft back, then tried to finalize with the allocation held (staff add-to-roster, the player submit route, and the finalize service call). Then corrected the allocation to the chosen style's own skill and finalized, as the contrast.
- Expected: the write is kept and flagged, not refused at write time; the Gift stage carries the stage error; finalize is refused while it is held.
- Saw, stated plainly: the write is kept and flagged, not refused at write time. The PATCH returned 200 with `magic_skills` holding the Iron Mask skill (id 27) at 20 and Occult (id 25) at 10, and the same stage error in its own response. The stored `draft_data.magic_skills` read straight from the database is `{"25": 10, "27": 20}`, so the other style's skill is stored. The stage errors on the draft (stage 6, Gift) read exactly `Magic skills only`. Finalize while it is held is refused, with no character created (character sheets 0 before and after, the draft still exists): staff add-to-roster returned 400 with the body `{"detail": "Character creation failed."}` (the view's own generic text; it does not carry the stage error), the player submit route returned 400 `{"detail": "Draft is not complete enough to submit."}`, and the finalize service raised DraftIncompleteError `Cannot finalize: incomplete stages: Gift`. So the stage error text `Magic skills only` is visible on the draft's stage errors, and the finalize responses name the Gift stage (service) or are generic (HTTP). After correcting the allocation to The Daring Dance's own skill the stage errors were empty and add-to-roster returned 200.
- Files: item5-other-styles-skill-allocation.json

## Item 6. The pickers and CombatStyle refuse the wrong skill

- Head sha: f2d2c3f7108faf27f9782e3ef8d0b1713f03e049
- Did: (a) as staff, opened the Path change page and POSTed `technique_skill` set to The Daring Dance's skill (a combat style's own); (b) called `full_clean()` on an unsaved row of each of the four picker models (MagicActivitySkill, Path, Gift, Technique) with that skill; (c) tried to make Veilwork, a skill the Path of Veils already adds, the skill of a new style, by `full_clean()` and by a real admin add POST on the combat style page.
- Expected: the picker refuses a style's skill; each model refuses it with the reason; the style refuses a skill a Path already adds.
- Saw: (a) status 200 (the page re-rendered, nothing saved), form error on `technique_skill`: `Select a valid choice. That choice is not one of the available choices.` The Path's `technique_skill` stayed null. This is Django's own message from the picker's limited queryset; a non-Magic skill (Persuasion) posted to the same page gets the identical text, and an ordinary Magic skill (Thaumaturgy) saved with 302. (b) each of the four models returned, on its skill field: `Choose a skill in the Magic category that is not a combat style's skill. A magical roll adds only skills made for magic, so it never counts a skill a character picks elsewhere.` (Path and Technique also list unrelated required-field errors because the rows were left blank.) (c) `full_clean()` gave `A Path, Gift, technique or magical activity already adds this skill. Give the style a skill of its own.`; the admin add POST returned 200 with the same text on `skill` and the style was not saved; a style given a skill of its own passed `full_clean()` with no errors.
- Files: item6-admin-post-path-picker.json, item6-full-clean-four-pickers.json, item6-combat-style-clean-refuses-a-path-skill.json

## Item 11. A sub-role vow

- Head sha: f2d2c3f7108faf27f9782e3ef8d0b1713f03e049
- Did: asked the Sphinx about the sub-role Swift Quicksilver (parent role Quicksilver) as two characters, over REST (`/api/covenants/roles/sphinx/?role=<id>`) and the telnet verb `sphinx Swift Quicksilver`. Ysmay's style, The Daring Dance, lists the anchor vow Quicksilver (and not Swift Quicksilver itself); Brom's style, The Iron Mask, lists only Bulwark.
- Expected: the sub-role counts by its anchor, so Ysmay's style suits it and Brom's does not.
- Saw: Ysmay: REST tier `takes`, `style: {"style_name": "The Daring Dance", "suits": true}`; telnet `The vow will take.` then `Your style suits it.` Brom: REST tier `takes`, `style: {"style_name": "The Iron Mask", "suits": false}`; telnet `The vow will take.` then `Your style does not suit it: no style benefits while it is active.` The verdict tier is unchanged in both (the vow warns and never blocks).
- Files: item11-sub-role-sphinx.json
