# Review evidence

- Reviewed revision: `2e5f74891e3ac05f887ba69b3cefd49dd79b1c2e`
- Reviewer: `demo-fidelity-reviewer (local agent), plus controller comparison of the final captures`
- Reviewer verdict: `PASS`
- Application/build identity: `Local server from this branch (just fe-build + just start) on a throwaway database rt_4665, dropped afterwards`
- Environment: `Linux devcontainer, Chromium via Playwright, Django/Evennia backend on :4001 against PostgreSQL`
- Viewports/themes: `Desktop width, light theme`
- Approved design: `https://claude.ai/artifact/1Qhk7T66r8aFYticDQCDuy (demo linked from #4659's spec)`
- Visual review: `Completed`
- Visual verdict: `PASS`
- Screenshots: ![Screen 1](docs/reviews/4665/screen1-tradition-gift.png) ![Resonance step](docs/reviews/4665/resonance-step.png) ![Screen 2 exact](docs/reviews/4665/screen2-training-exact.png) ![Screen 2 over](docs/reviews/4665/screen2-training-over.png) ![Skills stage](docs/reviews/4665/skills-stage-magic.png) ![Screen 3](docs/reviews/4665/screen3-course-offer.png) ![Screen 3 non-fit](docs/reviews/4665/screen3-course-offer-nonfit.png) ![Admin tradition](docs/reviews/4665/admin-tradition.png) ![Admin teaching config](docs/reviews/4665/admin-teaching-config.png) ![Admin affinity](docs/reviews/4665/admin-affinity.png) ![Admin schooling line](docs/reviews/4665/admin-schooling-line.png) ![Admin distinction effect](docs/reviews/4665/admin-distinction-effect.png) ![Admin NPC role](docs/reviews/4665/admin-npc-role.png)
- Comparison notes: `Screens 1-3 and the admin mocks compared element by element. Deliberate departures, each a recorded ruling: the training block is its own Gift-stage step after Resonance (its bonuses depend on the Gift and the resonance); the stance keeps today's price and techniques line; favored affinities use admin's two-column picker instead of checkboxes; Special techniques help keeps the exact #4555 rule. The demo's explanatory sentence under the chosen Gift ("Every Major Gift ... under any Tradition") is demo explainer text, not shipped copy.`
- Tested interactions: `Web CG: pick Tradition, stance, Studious, Gift Shadowcraft, the Abyssal resonance in the Resonance step; allocate Occult 30 + Ritualism 20 (Remaining 0, stage complete); swap to Pyromancy (pool 40, Over by 10, submit refused); underspend shows Remaining 10 flagged. Finalize: skills 30/20 in both stores, aura Abyssal 80 / Primal 20. Academy web dialog and telnet: fitting student sees both lines and rolls 4 easier; non-fitting student sees only the Tradition line and the base difficulty. Resubmit of an incomplete draft is refused (400).`
- Fixture/live boundary: `All data seeded into the throwaway database through the Django shell; every screen and request reached the live backend; nothing mocked.`
- Overall outcome: `PASS`

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Tradition card "Teaches well" line | Gifts: Shadowcraft · Affinity: Abyssal chips | MATCH | ![](docs/reviews/4665/screen1-tradition-gift.png) |
| Gift list under any Tradition | Pyromancy listed under Smiling Shadows | MATCH | ![](docs/reviews/4665/screen1-tradition-gift.png) |
| Favored Gift tag | separate "Teaches well" tag beside Major | MATCH | ![](docs/reviews/4665/screen1-tradition-gift.png) |
| Stance price column | Free · no training / Tradition Training 1 / 2 | MATCH | ![](docs/reviews/4665/screen1-tradition-gift.png) |
| Resonance step | lists real resonances with their affinity | MATCH | ![](docs/reviews/4665/resonance-step.png) |
| Training heading | What Smiling Shadows taught you | MATCH | ![](docs/reviews/4665/screen2-training-exact.png) |
| Breakdown lines | Tradition Training, rank 1 20 / Studious +10 / Fits: Shadowcraft +10 / Fits: Abyssal +10 / Magical training 50 | MATCH | ![](docs/reviews/4665/screen2-training-exact.png) |
| Ledger | Spend all of it · Remaining 0 | MATCH | ![](docs/reviews/4665/screen2-training-exact.png) |
| Magic skill rows | Occult 30, Ritualism 20, Theology 0 with − / + | MATCH | ![](docs/reviews/4665/screen2-training-exact.png) |
| Changed pick state | Shadowcraft line gone, 40, Over by 10, flagged | MATCH | ![](docs/reviews/4665/screen2-training-over.png) |
| Skills stage Magic group | read-only 30 / 20 / 0 | MATCH | ![](docs/reviews/4665/skills-stage-magic.png) |
| Course offer Tradition line | Taught in the manner of Smiling Shadows | MATCH | ![](docs/reviews/4665/screen3-course-offer.png) |
| Course offer fit line | Fits your Shadowcraft and Abyssal aura. Sessions are easier for you. | MATCH | ![](docs/reviews/4665/screen3-course-offer.png) |
| Non-fitting student | Tradition line only | MATCH | ![](docs/reviews/4665/screen3-course-offer-nonfit.png) |
| Admin: favored affinities | field with the demo's help text | MATCH | ![](docs/reviews/4665/admin-tradition.png) |
| Admin: favored gifts inline | Gift help "A Gift listed here is one this Tradition favors. Any Gift can still be picked under any Tradition." | MATCH | ![](docs/reviews/4665/admin-tradition.png) |
| Admin: teaching fit row | four fields, demo labels and help texts, single row | MATCH | ![](docs/reviews/4665/admin-teaching-config.png) |
| Admin: affinity aura type | aura type with help text | MATCH | ![](docs/reviews/4665/admin-affinity.png) |
| Admin: schooling line | floor field gone, training points shown | MATCH | ![](docs/reviews/4665/admin-schooling-line.png) |
| Admin: distinction effect | target magic_training_points, value per rank 20 | MATCH | ![](docs/reviews/4665/admin-distinction-effect.png) |
| Admin: NPC role | Teaches tradition with course-ease help | MATCH | ![](docs/reviews/4665/admin-npc-role.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | Training pool from distinctions, flat fit bonuses, must spend (screen2 captures, test_magic_training_pool) | |
| A02 | PASS | Finalize writes the allocation; starting aura follows the resonance (live finalize, test_services) | |
| A03 | PASS | Academy course ease and offer lines (screen3 captures, telnet transcript, test_skill_course_teaching_fit) | |
| A04 | PASS | Floors carried into training points then dropped (just prod-migration-check PASS) | |
| A05 | OUT_OF_SCOPE | Session result message carries the fit line (spec technical design) | Demo Screen 3 shows the session message as today; controller ruling recorded in the PR |

## Unresolved findings

- None
