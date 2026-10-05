# Review evidence

- Reviewed revision: 475a571a667401fb862caaae509dfd421696d8e7
- Reviewer: demo-fidelity-reviewer
- Reviewer verdict: PASS
- Application/build identity: real components from frontend/src (CombatantsList, PoseUnit, StandoffCard) served by Vite dev server 6.4.3 from the worktree; real Django admin HTML at the reviewed commit rendered through the test client with the repo's admin CSS (base, forms, arx_admin) loaded
- Environment: devcontainer, Playwright Chromium headless; SQLite test DB for admin; throwaway harness and test deleted afterwards
- Viewports/themes: React surfaces 480x700 light (standoff also dark); admin 1100x800 light; demo reference 1100 wide
- Approved design: https://claude.ai/artifact/WsPK3mSHVFjXEYT8YPgysZ (v2, local copy .superpowers/sdd/2026-10-05-spectacle-breaks-morale/approved-demo.html)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![demo screen 1](docs/reviews/4147/demo-screen1.png) ![demo screen 2](docs/reviews/4147/demo-screen2.png) ![demo screen 3](docs/reviews/4147/demo-screen3.png) ![player rows](docs/reviews/4147/app-player-light.png) ![GM rows](docs/reviews/4147/app-gm-light.png) ![scene feed](docs/reviews/4147/app-feed-light.png) ![standoff](docs/reviews/4147/app-standoff-light.png) ![standoff dark](docs/reviews/4147/app-standoff-dark.png) ![display picker open](docs/reviews/4147/app-standoff-display-open-light.png) ![technique select](docs/reviews/4147/app-standoff-display-select-light.png) ![terms](docs/reviews/4147/app-standoff-terms-light.png) ![spectacle config](docs/reviews/4147/app-admin-config.png) ![reaction line list](docs/reviews/4147/app-admin-lines.png) ![reaction line form](docs/reviews/4147/app-admin-line.png) ![audere](docs/reviews/4147/app-admin-audere.png) ![majora](docs/reviews/4147/app-admin-majora.png) ![approach](docs/reviews/4147/app-admin-approach.png) ![standoff config](docs/reviews/4147/app-admin-standoffcfg.png)
- Comparison notes: Combat chips, GM strip, feed lines, group Faltering chip, display picker, and all admin forms match in structure with admin CSS loaded (forms.css linked). Re-review at 475a571a6 after fixes D1 (terms_morale_ease line, StandoffCard) and D2 (escaped placeholder help). Terms and reaction-line screenshots were re-rendered at this commit and re-compared; the other screenshots were taken at 648be4784 and the diff since then touches none of those surfaces. The Faltering terms line is plain muted text in the build where the demo draws a pill; copy and position match. Admin mojibake in the first round was a harness artifact; the re-rendered form is clean.
- Tested interactions: opened the Display of power approach, opened the technique select, picked Kindled Brand, picked the Let us pass terms
- Fixture/live boundary: React props are fixture data (placeholder names); components, CSS and chip logic are live code. Admin pages are live admin code over factory rows. No network or live backend.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
| --- | --- | --- | --- |
| S1-chips | PASS | app-player-light.png, app-gm-light.png | none |
| S1-gm-strip | PASS | app-gm-light.png shows Morale N/70 for GM only | brief: GM strip stays |
| S2-feed | PASS | app-feed-light.png | none |
| S3-chip | PASS | app-standoff-light.png | none |
| S3-display | PASS | app-standoff-display-select-light.png | brief: inline select |
| S3-terms-morale | PASS | docs/reviews/4147/app-standoff-terms-light.png shows "Faltering: 1 more step easier" | none |
| S3-card-credit | OUT_OF_SCOPE | docs/reviews/4147/app-feed-light.png shows the credit line in the scene feed | Controller ruling 11: standoff lines post to the scene feed like every other standoff verb line; flagged on the PR for the owner |
| S4-admin-lines | PASS | docs/reviews/4147/app-admin-line.png shows the actor, group and display placeholders in the help line | none |
| S4-admin-rest | PASS | app-admin-config.png and others | none |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Opponent Faltering/Broken chips | amber and red chips beside name | MATCH | app-player-light.png vs demo-screen1.png |
| Player sees no morale number | no strip for players | MATCH | app-player-light.png |
| GM morale strip | Morale N/max state | MATCH | app-gm-light.png |
| Scene credit and flavour lines | italic muted OUTCOME lines | MATCH | app-feed-light.png vs demo-screen1.png |
| Group Faltering chip | chip under group name | MATCH | app-standoff-light.png vs demo-screen3.png |
| Display of power press with technique select | picker with technique options | MATCH | app-standoff-display-select-light.png |
| Terms morale ease line | "Faltering: 1 more step easier" under Name your terms | MATCH | docs/reviews/4147/app-standoff-terms-light.png vs demo-screen3.png |
| Standoff credit line | credit line in the scene feed per Controller ruling 11 | MATCH | docs/reviews/4147/app-feed-light.png |
| Spectacle config three fieldsets | three fieldsets with help lines | MATCH | app-admin-config.png |
| Reaction line list and form | columns and fields with help | MATCH | app-admin-lines.png, app-admin-line.png |
| Reaction line placeholder help | placeholders listed in help text | MATCH | docs/reviews/4147/app-admin-line.png |
| check_level_bonus on both thresholds | field with help | MATCH | app-admin-audere.png, app-admin-majora.png |
| casts_technique and terms_ease_* | checkbox and two fields | MATCH | app-admin-approach.png, app-admin-standoffcfg.png |

## Unresolved findings

None
