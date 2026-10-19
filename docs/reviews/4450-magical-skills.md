# Review evidence: #4450 magical skills, slice 1 (demo fidelity)

- Reviewed revision: 0ab13ade353b996eb289bf609c4c9d921ce7fc88
- Reviewer: demo-fidelity-reviewer agent (Claude Sonnet 5.5), reading the demo render and the built-surface screenshots with vision
- Reviewer verdict: PASS
- Application/build identity: Arx II, branch feature-4450-magical-skills-every-magical-check-uses at the revision above. Built surfaces were rendered by Chromium (Playwright) against a real Evennia server on localhost:4001 with a throwaway database named rt_4450 (Form B real-testing pass, `.superpowers/sdd/2026-10-18-magical-skills-slice-1/real-testing-browser-report.md`), frontend rebuilt with `just fe-build` from this commit. The demo was rendered from its exact published source file by the same Chromium.
- Environment: devcontainer, Linux, Chromium via Playwright 1.58.2; Django admin and React character creation served by the branch; demo opened from a file URL. Fast-tier checks run by the reviewer: 41 backend tests (`just test-fast world.magic.tests.test_magic_skills web.admin.tests.test_magic_skill_probes world.magic.tests.test_magic_activity_models world.checks.tests.test_extra_traits`, OK) and 2 frontend tests (vitest AnimaCheckStep.test.tsx, passed).
- Viewports/themes: 1280x900 light theme for every built screenshot and every demo render. Dark theme and narrow viewports were not reviewed.
- Approved design: Magical Skills Demo, published at https://claude.ai/artifact/9XwT6pHFzfvGZ2JVKUJqhA (issue #4450 spec, "the demo is the approved design"). The exact published source read in full is the local file `/tmp/claude-1000/-workspaces-arxii/136537e0-2101-4cd8-88a9-675f3975dfee/scratchpad/magic-skills-demo.html`. Rendered references are committed as demo-screen-1 to demo-screen-6 under docs/reviews/4450/. The spec ruling that renamed the condition flag to adds_loss_of_self_skills was applied to the demo before approval.
- Visual review: completed. Demo Screens 1 to 4 compared image to image with the built page; Screens 5 and 6 are not rendered surfaces and were compared against code and tests (said so in each row).
- Visual verdict: PASS
- Screenshots: Demo references ![Demo screen 1](docs/reviews/4450/demo-screen-1.png) ![Demo screen 2](docs/reviews/4450/demo-screen-2.png) ![Demo screen 3](docs/reviews/4450/demo-screen-3.png) ![Demo screen 4](docs/reviews/4450/demo-screen-4.png) ![Demo screen 5](docs/reviews/4450/demo-screen-5.png) ![Demo screen 6](docs/reviews/4450/demo-screen-6.png) built surfaces ![Magic activity skills changelist](docs/reviews/4450/admin-magic-activity-skills-changelist.png) ![Magic activity skill add form](docs/reviews/4450/admin-magic-activity-skill-add.png) ![Path technique skill](docs/reviews/4450/admin-path-technique-skill.png) ![Minor Gift technique skill saved](docs/reviews/4450/admin-gift-minor-technique-skill.png) ![Major Gift refused](docs/reviews/4450/admin-gift-major-refused.png) ![Technique skill override](docs/reviews/4450/admin-technique-skill-override.png) ![Condition category flag](docs/reviews/4450/admin-condition-category-flag.png) ![Required content probes](docs/reviews/4450/admin-required-content-magic-probes.png) ![CG Anima Check skills](docs/reviews/4450/cg-anima-check-skills.png)
- Comparison notes: see "Comparison notes by screen" below.
- Tested interactions: as staff through the real admin: opened the Magic Activity Skills changelist (4 rows, activity filter) and the add form; saved a Technique skill on a Minor Gift and read it back after "Save and continue editing"; saved the same on a Major Gift and got the refusal; opened the Path, Technique and Condition Category change forms; opened the Required content dashboard with Path One and Minor Gift One unmapped. As e2e_test_account opened `/characters/create` on the Anima Check step. Test-client pass (same revision): admin POSTs for activity rows, duplicate and negative-weight rejection, Path, Gift, Technique and category saves, dashboard before and after mapping, draft validation with a magic-category skill, REST scene casts with Path skill, standoff view, caster without a Path. The reviewer did not click a skill or submit in the CG step.
- Fixture/live boundary: live code and real server, real admin and real React app, real login through the React login page. Rows were staged in a throwaway database (Skills "Skill A/B/C" and magic-category "Magic Skill X/Y", "Path One", "Major Gift One", "Minor Gift One", "Category One", four MagicActivitySkill rows). The CG draft was created directly with the ORM (stage Gift) instead of playing stages 1 to 4, so the right rail reads "not yet chosen" for Gift. Demo skill names are labelled slots ("[skill A]"), the built pages show the staged names; that is not a divergence. The demo's production figures (16 skills, 306 techniques, 11 Minor Gifts) are example data and were not compared.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S1-changelist | PASS | admin-magic-activity-skills-changelist.png against demo-screen-1.png: Activity, Skill, Weight columns, inline weight, activity filter, Add and Save buttons | none needed |
| S1-weight-help | PASS | admin-magic-activity-skill-add.png shows the exact approved Weight help line | none needed |
| S2-path | PASS | admin-path-technique-skill.png: Technique skill dropdown with help, in a Casting section | none needed |
| S2-gift | PASS | admin-gift-minor-technique-skill.png saved and read back; admin-gift-major-refused.png shows the exact approved refusal | none needed |
| S2-technique | PASS | admin-technique-skill-override.png: blank-by-default dropdown with Path or Gift fallback help | none needed |
| S3-dashboard | PASS | admin-required-content-magic-probes.png: three new probe rows with counts, names and consequence | none needed |
| S4-cg | PASS | cg-anima-check-skills.png: skills offered are Skill A, B, C; magic-category Magic Skill X and Y absent while the page's own API response contained them; vitest does-not-offer-magic test passes | none needed |
| S5-behind-roll | PASS | code and tests: magic_skills.py technique_skill_term, checks extra_traits tests (41 backend tests OK); not a rendered surface | none needed |
| S6-rows-written | PASS | code: models, admin, migration 0253 and 0254, validator; not a rendered surface | none needed |
| S-delete | PASS | on_delete PROTECT on MagicActivitySkill.skill, SET_NULL on Path, Gift and Technique | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Screen 1 title and list | A changelist titled "Select magic activity skill to change" with one row per activity and skill | MATCH | admin-magic-activity-skills-changelist.png shows "Select Magic Activity Skill to change" and 4 rows, Ceremony twice, as the demo's Soulfray resilience appears twice |
| Screen 1 columns | Activity, Skill, Weight | MATCH | same screenshot: ACTIVITY, SKILL, WEIGHT headers (admin adds a row checkbox and sort arrows) |
| Screen 1 activity as a link | Activity text is a link to the row | MATCH | same screenshot: Ceremony, Dispelling, Invocation rendered as links |
| Screen 1 weight cell | Editable weight shown as 1.00, 0.50 | MATCH | same screenshot: inline inputs 1.00, 0.50, 1.00, 1.50 |
| Screen 1 one activity with several rows | An activity may repeat with different skills and weights | MATCH | Ceremony: Skill A 1.00 and Skill B 0.50, matching the demo's Soulfray resilience pair |
| Screen 1 activity filter | Filter by activity on the right | MATCH | same screenshot: "By activity" filter listing all activities |
| Screen 1 Add and Save buttons | An add button and a Save button | MATCH | same screenshot: ADD MAGIC ACTIVITY SKILL top right, Save under the table |
| Screen 1 Weight help text | "Weight multiplies the skill's value before it becomes points. 1.00 is the default." | MATCH | admin-magic-activity-skill-add.png help line under Weight, identical text |
| Screen 2 Path form | Technique skill dropdown, with help that it is added to Major Gift techniques unless the technique sets its own | MATCH | admin-path-technique-skill.png, Casting section: help says every cast of a Major Gift technique, a technique's own skill wins, a Minor Gift uses the Gift's skill, blank adds none |
| Screen 2 Gift form dropdown and help | Technique skill dropdown, "Minor Gifts only", added to this Gift's technique casts, Major Gift uses the Path | MATCH | admin-gift-minor-technique-skill.png: Skill A selected after save, success banner, help begins "Minor Gifts only" and carries the Major Gift sentence |
| Screen 2 Major Gift refusal | "A Major Gift's techniques take the caster's Path technique skill. Set it on the Path instead." | MATCH | admin-gift-major-refused.png: red error banner and the exact sentence above the outlined field (stock admin places it above the field, the demo mock below the help) |
| Screen 2 Technique override field | Optional dropdown shown as blank, "Leave blank to use the Path's skill (Major Gift) or the Gift's skill (Minor Gift)" | MATCH | admin-technique-skill-override.png: empty Skill dropdown with help "Blank = use the caster's Path technique skill (Major Gift) or the Gift's technique skill (Minor Gift)" (label reads "Skill", see Comparison notes) |
| Screen 2 other fields unchanged | Name, Stage, Style, Kind, Gift and existing fields stay as today | MATCH | admin-path-technique-skill.png, admin-gift-minor-technique-skill.png and admin-technique-skill-override.png show the existing fields around the one new field |
| Screen 3 magic activities probe | A row for activities with no skill, a count and the activity names | MATCH | admin-required-content-magic-probes.png: "Skills mapped to magical activities", "15 magical activit(ies) have no skill mapped: the roll adds none." and the 15 names |
| Screen 3 Paths probe | A row for Paths with no technique skill, a count, the Path names | MATCH | same screenshot: "Technique skill on each active Path", Path One, "1 active Path(s) have no technique skill: their casts add none." |
| Screen 3 Minor Gifts probe | A row for Minor Gifts with no technique skill, a count, names | MATCH | same screenshot: "Technique skill on each Minor Gift", Minor Gift One, "1 Minor Gift(s) have no technique skill: their casts add none." |
| Screen 3 line links to the fixing page | Each probe links to the admin page that fixes it | MATCH | same screenshot: each probe title is a link; declarations set admin_model MagicActivitySkill, Path and Gift |
| Screen 3 consequence copy | Until mapped, the roll runs without the added skill | MATCH | same screenshot: consequence column reads that the roll or cast adds no skill |
| Screen 3 dashboard frame | Existing Required content dashboard in its tuning tier | MATCH | probes are declared with DependencyTier.TUNING in required_content.py and appear in the existing dashboard table; the clipped screenshot shows only the new rows beside the existing ones |
| Screen 4 option chips | The pickable skills appear as choices | MATCH | cg-anima-check-skills.png: SKILL A, SKILL B, SKILL C buttons beside the stat buttons |
| Screen 4 magic skills not offered | Magic-category skills are not offered | MATCH | same screenshot: Magic Skill X and Y absent although the page's own request returned them |
| Screen 4 suggested marker | The suggested option is marked "(suggested)" | MATCH | same screenshot: "WILLPOWER (SUGGESTED)" on the stat row; the skill row uses the same label code (AnimaCheckStep.tsx line 113) and Path One has no suggestions, so a suggested skill was not rendered |
| Screen 5 technique skill term | Technique override, else Path (Major Gift) or Gift (Minor Gift), weight 1.00 | MATCH | not rendered (never shown to players); magic_skills.py _skill_for_path and TECHNIQUE_SKILL_WEIGHT, test_magic_skills passes |
| Screen 5 mapped activity terms and unchanged parts | Mapped skills add as terms; check type, aspect, level, modifiers unchanged | MATCH | not rendered; activity_skill_terms adds terms next to the unchanged check type; test_extra_traits passes |
| Screen 5 threads and development | Added skill develops from use and counts for thread pulls | MATCH | not rendered; skill_development._developing_traits and cast_involved_trait_ids in the diff |
| Screen 6 written rows | MagicActivitySkill, Path, Gift (Minor only), Technique skill fields and the category flag | MATCH | not rendered; models in the diff, migrations 0253 and 0254, Gift CheckConstraint and clean(), admin-condition-category-flag.png shows the new checkbox |
| Screen 6 category flag | A checkbox on the condition category | MATCH | admin-condition-category-flag.png: "Adds loss of self skills" checkbox with its help line |
| Screen 6 Anima Check validation | A new draft's Anima Check skill is validated against magic skills | MATCH | not rendered; validators.py excludes TraitCategory.MAGIC, the test-client pass got the validator error for a magic skill |

## Comparison notes by screen

Screen 1 (Staff map skills to magical activities): matches. The real changelist has the stock admin chrome (side nav, checkboxes, Action bar) the demo's mock leaves out. The demo's Weight help line lives on the add form in the build, which is where admin shows help text; the changelist has no help line.

Screen 2 (Staff set where a technique's skill comes from): matches with noted gaps.
- Technique field label: the demo draws "Skill (override)", the build's admin label is "Skill" (the model field name). The help line starts "Overrides the technique skill for this one technique". Cosmetic; optional fix is `verbose_name="Skill (override)"` on `Technique.skill` (src/world/magic/models/techniques.py).
- Help wording on Path, Gift and Technique is lengthened and tagged "(#4450)" compared with the demo's shorter lines; the meaning of every demo sentence is present.
- The Major Gift refusal sentence is identical to the demo's. The Path field sits in a new "Casting" fieldset rather than under Style; the demo drew one flat fieldset.

Screen 3 (Required content dashboard lists what is unmapped): matches with noted gaps. The real dashboard is its existing four-column table, not the demo's three orange cards, and the probe titles differ from the demo's ("Skills mapped to magical activities" against "Magic activities with no skill"; "Technique skill on each active Path" against "Paths with no technique skill"; "Technique skill on each Minor Gift" against "Minor Gifts with no technique skill"). The demo marks the dashboard as existing, so table versus cards is the host's own style. The build lists every name (no "and 8 more" truncation). The clipped screenshot does not show the page header; the dashboard frame is the existing page and is untouched by the diff.

Screen 4 (Anima Check skill no longer offers magic skills): matches. The demo's struck-through chips are an annotation of what is not offered, and the spec says they are not offered; the build removes them. The demo's heading "The skill your magic rolls" is mock copy; the real step uses its own Statistic and Skill fields and cg.css styling. A suggested skill was not rendered (see the checklist row). The staged draft is partial, so Gift steps read "No gifts are available".

Screen 5 (Behind the roll): not a rendered surface, compared against code and the 41 passing backend tests. Technique skill precedence, mapped activity terms, development and thread involvement all exist as the demo's table describes. One deliberate behaviour the demo does not draw: an override whose skill is inactive adds no term and does not fall back to the Path or Gift (documented in `_skill_for_path`, a stated ruling, not a defect).

Screen 6 (What is written): not a rendered surface, compared against the diff. Every row exists; Gift.technique_skill is Minor only through both a model clean() and a database CheckConstraint. Deleting a skill is blocked while a MagicActivitySkill row uses it (PROTECT) and blanks the Path, Gift and Technique fields (SET_NULL), as the demo's "Staff delete a skill" card says.

Unbuilt demo affordances: none. The demo's authoring-table row "Skills > Skills (today)" is unchanged by design.

Mechanical companion: a styling reachability test is not proposed. Every new page is the stock admin or the existing dashboard and CG step, so no new class hook or inline stylesheet was introduced; the screenshots show stock admin styling applied on all new fields.

Review-limit notes: dark theme and narrow viewports were not rendered. The Required content and Technique captures are clips of long pages.

## Unresolved findings

None
