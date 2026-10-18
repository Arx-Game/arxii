# Review evidence

- Reviewed revision: `3e89d7534c356ed1c4e1eba50850eebb2304153c`
- Reviewer: `demo-fidelity-reviewer agent (local), one pass; its one text gap (the closing-rite sentence) was fixed and re-shot`
- Reviewer verdict: `PASS`
- Application/build identity: production frontend bundle built with pnpm from this branch (frontend source identical to commit 235ed88d8, which this branch carries as 5c141c0fa after a rebase onto main for a migration renumber), served by the branch's own Evennia runserver on :4021 against a throwaway Postgres database rt_4442
- Environment: Linux devcontainer, Chromium (Playwright, 1 worker), Django backend on Postgres, database built with tools/build_schema.py and seeded by a throwaway script (accounts, five characters, one scene with a GM, one being with a rite, three answers, two miracles, check outcomes and awards); the rite rolls were forced to Partial Success while seeding. The server ran with a stub session handler because runserver has no Evennia session handler (it only affects the live push to a GM's open sessions)
- Viewports/themes: 1200x1500 desktop, light theme
- Approved design: https://claude.ai/artifact/WnBj714NF8MQiPQVBb1ifG (spec on #4333, slice 5: design 6 and Walkthrough D, the demo's GM tab Screen 4)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![1](docs/reviews/4442/1-no-edit-control.png) ![2](docs/reviews/4442/2-weekly-limit.png) ![3](docs/reviews/4442/3-edit-control.png) ![4](docs/reviews/4442/4-miracle-chosen.png)
- Comparison notes: In scope: demo Screen 4 and Walkthrough D. Stated divergences, accepted: the greyed miracle's reason names the being, the character's favor and the threshold number where the demo's slot text is generic; the submit button reads "Perform this miracle" when a miracle is chosen; the panel adds a weekly-limit state, an empty state and the edit textarea (Walkthrough D and the spec's may_adapt_answers carry them). The review found one omission (the header lacked "a closing rite never raises this prompt"); it was added and every shot here is from after the fix. Operating the panel found a real defect, now fixed in 1dd6c7455: a failure after a miracle was already performed reopened its prompt, so the GM could have sent a second miracle; a test covers it. Out of scope: slices 6 to 8.
- Tested interactions: signed in through the real login form as the scene GM; opened the scene, read the queue row, opened the panel, sent an answer unchanged (GM level without the edit control), tried to send a second answer for the same character the same week (refused), edited an answer's text and sent it (GM level with the edit control), performed an eligible miracle, and sent nothing for a fourth character. Read back from the database each time: the prompt status and note, the visions and their bodies, the miracle performance (trigger live_rite), the being's pool, and the room lines
- Fixture/live boundary: everything reached the live backend; the scripted parts were the seed and the forced rite rolls, and nothing was mocked. A second rite by a character the being already answered this week raised no prompt (checked in the earlier run on the same code)
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Queue pill | "Being answer: the character's rite to the being, with the rolled tier. Answer it?" with Open and Dismiss | MATCH | ![0](docs/reviews/4442/1-no-edit-control.png) shot 1 top bar reads "Being answer: Orla Cobbe's The Long Watch to Ombrin (Partial Success). Answer it?" with Close (Open toggled) and Dismiss |
| Rolled badge and header | "Rolled:" and the tier, answers shown at or below the tier, has not answered live this week, a closing rite never raises this prompt | MATCH | ![0](docs/reviews/4442/1-no-edit-control.png) shot 1 header row, all three clauses |
| Answers at the roll | Only answers at Partial Success and below, each with its tier and times used; the onlooker line under the selected one; the Success answer is not listed | MATCH | ![0](docs/reviews/4442/1-no-edit-control.png) shot 1: Partial Success (used 0 times, onlooker_line shown) and Failure; the Success answer was in the catalogue and is absent |
| Rule line without the edit control | "an edit control appears here only for a GM level with may adapt answers; this GM's level has none" | MATCH | ![0](docs/reviews/4442/1-no-edit-control.png) shot 1 and no Edit the text button on the page |
| Greyed miracle | Miracle row greyed with why | MATCH | ![0](docs/reviews/4442/1-no-edit-control.png) shot 1 "Shown greyed: Favor with Ombrin (1) is below this miracle's threshold (500)." and its radio disabled |
| Eligible miracle | Sent from the panel, counts as this week's live answer | MATCH | ![0](docs/reviews/4442/4-miracle-chosen.png) shot 4 chosen, button reads Perform this miracle |
| Edit control for a level that may adapt | Appears only then; edits the main text | MATCH | ![0](docs/reviews/4442/3-edit-control.png) shot 3 Edit the text opened a textarea; the sent vision body held the edited text |
| Footer | Send nothing (secondary) and Send this answer (primary), right-aligned | MATCH | ![0](docs/reviews/4442/1-no-edit-control.png) shot 1 footer |
| Weekly limit | Nothing can be sent once the being has answered the character this week | MATCH | ![0](docs/reviews/4442/2-weekly-limit.png) shot 2 "Ombrin has already answered Orla Cobbe live this game week. Nothing more can be sent this week." with Send this answer disabled |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S5-prompt | PASS | shot 1; the prompt row for Orla's rite addressed to the scene GM; a closing rite and a GM who muted the group raise none (journeys and test_live_answers) | |
| S5-tier-cap | PASS | shot 1: answers at Partial Success and below only | |
| S5-limit | PASS | shot 2; test_live_answers LimitTests | |
| S5-miracle | PASS | shot 4; miracle performance row trigger live_rite, pool 100 to 70 after two visions and one miracle | |
| S5-edit | PASS | shots 1 and 3; the vision to Tobiah held the edited text; clue, cost and follow-up come from the answer unchanged (test_live_answers) | |
| S5-dismiss | PASS | Caddoc's prompt dismissed with note "Dismissed: nothing was sent." and no vision | |
| S5-room-line | PASS | the onlooker line saved as an outcome line in the scene for each sent answer | |

## Unresolved findings

- None
