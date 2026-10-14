# Review evidence

- Reviewed revision: `84fef9029a7f3fdd054a2b85a105b0582df67e30`
- Reviewer: `demo-fidelity-reviewer agent (local), two passes; report docs/reviews/4354/demo-fidelity.md`
- Reviewer verdict: `PASS`
- Application/build identity: production frontend bundle built with pnpm build from this branch, served by the branch's own Evennia server on :4001 against a throwaway Postgres database rt_4354
- Environment: Linux devcontainer, Chromium (Playwright 1 worker), Evennia/Django backend on Postgres, database built with tools/build_schema.py and seeded by a throwaway script
- Viewports/themes: 1500x1100 desktop, light theme
- Approved design: https://claude.ai/artifact/1926LF7noogf1hKijgL3v8 (spec on #4121, slice 1)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![player](docs/reviews/4354/01-player-deciding.png) ![onlooker](docs/reviews/4354/02-onlooker-summary.png) ![gm prompt and panel](docs/reviews/4354/03-gm-prompt-and-panel.png) ![gm after hold](docs/reviews/4354/04-gm-after-hold.png) ![gm shake confirm](docs/reviews/4354/05-gm-shake-confirm.png) ![gm after shake](docs/reviews/4354/06-gm-after-shake.png) ![player after](docs/reviews/4354/07-player-after-hold-and-shake.png) ![onlooker after](docs/reviews/4354/08-onlooker-after-shake.png) ![builder](docs/reviews/4354/09-admin-profile-builder.png) ![builder saved](docs/reviews/4354/10-admin-profile-builder-saved.png)
- Comparison notes: Screens 1 to 3 for the GM, player and onlooker seats and Admin A were compared with the demo. First pass found six gaps (missing "Something about one of you matters to them." line, no force line in the prompt, shake confirm copy, no last-decision line, builder submit row, observer Join); all but Join were fixed and re-shot. Join keeps the existing rule (only open encounters between rounds), recorded as a stated divergence. Grades read Impossible because the scratch database has no check rank rows; that is data, not layout. Items the slice cut leaves for later (named NPC group, language, affiliation, inherited rules, predicate widget) are absent by design.
- Tested interactions: signed in through the real login form as the player, the onlooker, the GM and a staff account; player card and onlooker summary while a proposal was pending; GM prompt row with Override disabled until a reason is typed; Hold for one action; GM morale Shake with a required reason; reload of player and onlooker after the GM acted; Standoff Profile Builder reached from the creature page, margin changed and saved, read back
- Fixture/live boundary: everything reached the live backend; the only scripted step was the seed, which created the accounts, characters, scene, encounter and authored rows and rolled one player press through the real standoff_press service with the check pinned to a critical failure so the proposal is repeatable
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| GM tab standoff panel | Group with chips, cause and whether it holds, drives read or unread, morale per member, force line and bar, faction rule table, Shake and Steady | MATCH | ![gm](docs/reviews/4354/03-gm-prompt-and-panel.png) |
| GM prompt | Standoff chip, group cause fires, cause and reason and force, Confirm they attack, Hold for one action, Override with reason, keep-acting hint | MATCH | ![gm](docs/reviews/4354/03-gm-prompt-and-panel.png) |
| Shake confirm | Shake group, reason field, Shake and Cancel, steady to faltering gloss | MATCH | ![shake](docs/reviews/4354/05-gm-shake-confirm.png) |
| Last decision line | Shows the held decision once no proposal is pending | MATCH | ![hold](docs/reviews/4354/04-gm-after-hold.png) |
| Player card | Angle box with Share, face-down tiles, emboldened deciding marker, matters-to-them line, approaches, terms, Fight | MATCH | ![player](docs/reviews/4354/01-player-deciding.png) |
| Onlooker summary | Observer pill, group count state table with chips, in-the-standoff line, no cause or drive | MATCH | ![onlooker](docs/reviews/4354/08-onlooker-after-shake.png) |
| Room line | Group falters line seen by player and onlooker | MATCH | ![player after](docs/reviews/4354/07-player-after-hold-and-shake.png) |
| Standoff Profile Builder | Creature module, drives table with meaning and hit by, faction rule blocks, Save, Save and continue editing, Back, rail with grade preview, cause check, placements | MATCH | ![builder](docs/reviews/4354/10-admin-profile-builder-saved.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S1-beat-opens-standoff | PASS | actions/tests/test_gm_story_run_beat.py a line that opens as a standoff holds round one | |
| S1-proposal-mode | PASS | 03 and 04 screenshots; world/standoffs/tests/test_proposals.py | |
| S1-gm-panel | PASS | 03 and 06 screenshots; test_gm_payloads GM sees the whole profile | |
| S1-morale-control | PASS | 05 and 06 screenshots; test_gm_morale | |
| S1-observer-summary | PASS | 02 and 08 screenshots | |
| S1-orders-cause | PASS | seeded botch became a proposal with the provocation reason (03) | |
| S1-profile-builder | PASS | 09 and 10 screenshots, saved margin read back | |
| S1-rename-and-glossary | PASS | migrations 0223 to 0225, AGENT_GLOSSARY entries | |
| S1-cause-glosses-authored | PASS | StandoffCauseGloss model and admin; test_view gloss tests | |
| S1-telnet | PASS | commands/tests/test_gm_standoff_commands.py | |
| S1-observer-join | OUT_OF_SCOPE | existing Join rule kept | Demo marks Join as existing behaviour; the observer keeps today's open-encounter Join rule, no new join path in this slice |

## Unresolved findings

- None
