# Review evidence

- Reviewed revision: 452147ffccbcce9599a76d5d425d7560ebde3b7e
- Reviewer: demo-fidelity-reviewer (Claude, vision-capable; compared each screenshot against the demo text and layout)
- Reviewer verdict: PASS
- Application/build identity: branch feature-4353-favor-with-beings-slice-1-invoking-favor at 452147ff (re-review after fixes to 408cba59 findings F1 to F3), production frontend build served by the Django server on http://localhost:4001
- Environment: live server rebuilt and restarted over a freshly reseeded throwaway database rt_4353, logged in as e2e_test_account (staff superuser) playing Ysmay Dunhollow (Ombrin's Chosen, favor 44) and Tobiah Fenwright; worktree clean apart from the untracked evidence files
- Viewports/themes: desktop 1440x1000 (admin and /game and /scenes), dialog and card element crops; light theme (system default)
- Approved design: demo https://claude.ai/artifact/WnBj714NF8MQiPQVBb1ifG (revision 11), spec issue #4333, slice cut in "Proposed slice cut"; read in full from the saved HTML copy
- Visual review: completed for every in-scope demo screen against actual rendered screenshots from the live server
- Visual verdict: PASS
- Screenshots: ![option card](docs/reviews/4353/01-mission-option-call-on-favor.png) ![picker](docs/reviews/4353/02-call-on-favor-picker.png) ![invoking first](docs/reviews/4353/03-invoking-first.png) ![mission result](docs/reviews/4353/04-mission-result.png) ![self check](docs/reviews/4353/05-self-check-invoking.png) ![scene after check](docs/reviews/4353/06-scene-after-invoked-check.png) ![game feed](docs/reviews/4353/07-game-feed-room-lines.png) ![scene log lines](docs/reviews/4353/20-scene-page-log-lines.png) ![game feed again](docs/reviews/4353/21-game-feed.png) ![devotion config](docs/reviews/4353/10-admin-devotion-config.png) ![devotion context heading](docs/reviews/4353/22-admin-devotion-context-now.png) ![chosen favor config](docs/reviews/4353/11-admin-chosen-favor-config.png) ![being](docs/reviews/4353/12-admin-being.png) ![distinction builder](docs/reviews/4353/13-distinction-builder-effects.png)
- Comparison notes: First pass at 408cba59 found three gaps (unreadable Devotion heading subtitle, missing awards Rule, missing "would be" rank note). At 452147ff the heading is legible (22 png), the Rule renders under the awards inline (10 png, small text directly above the next bar, acceptable), and the rank note is implemented in InvocationResult.tsx. The live run rolled Failure for the mission invocation (no bonus, rank difference unchanged), so the "would be" text did not show live, correctly suppressed when the difference is unchanged; the differing case is covered by the component test BeatCard.invocation.test.tsx asserting "0 (would be -1 without the bonus)", which I read but did not run. Deliberate deviations (picker caption, no Attempt button, no roll or difficulty points) judged acceptable as before.
- Tested interactions: opened the mission option, opened Call on favor, read the picker, confirmed and saw "Invoking Ombrin first (Easy)" with Don't call; resolved the option and read the result; scene self-check with Call on favor and the three room lines read back through the scene page log; autocomplete queries of the modifier target pickers on the condition template and crafting recipe admin; admin pages opened as staff; Tobiah API option, refusal and resolution records (api-*.json)
- Fixture/live boundary: live Django server, real browser, real API and database rt_4353; no routes mocked. Seeded: beings, favor, missions, scene, check type. Text slots are placeholders ("[player line]", "[mission name]") by design. Onlooker views (a second persona seeing the lines) and telnet were not driven live by me; telnet is covered by src/integration_tests/pipeline/test_favor_invocation_telnet_e2e.py assertions that I read, not ran. Ysmay's missions were already resolved so the option screens come from the existing screenshots only.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
| --- | --- | --- | --- |
| P3-picker | PASS | 02-call-on-favor-picker.png: Being radio with Easy chip and "3 of 3 left this week", difficulty table Base Daunting 75, Chosen -30, Favor 44 -15, modifiers 0, Result 30 Easy, bonus line, one-line field, Rules line, Close and Call on Ombrin | Label "How it shows (optional, one line)" without "visible to others": accepted, repo copy rule #4193 |
| P3-card | PASS | 01 and 03 pngs: Call on favor on the option card; after confirm "Invoking Ombrin first (Easy)" with Don't call | No separate Attempt button; clicking the option attempts as before: accepted |
| P3-result | PASS | 04-mission-result.png: call line, "invocation: Partial Success" line, breakdown with points, favor bonus line, Total with rank, Difficulty rank, Rank difference | Roll and difficulty points never shown (CheckResult exposes no roll): accepted |
| P3-result-copy | PASS | 04-mission-result.png (equal case, note correctly absent); InvocationResult.tsx lines 56-62 and BeatCard.invocation.test.tsx render "0 (would be -1 without the bonus)" when the difference changes | The differing case was not seen on the live screen, only in the component test |
| P5-telnet | PASS | telnet e2e test asserts the breakdown "Investigation: 48 + 10 Ombrin's favor (invocation: Success) = 58." and call and outcome lines; wording differs from demo's "Investigation (+10 ..., rank difference 0): Success." but carries the same facts; verb is the existing "mission resolve" not the demo's "mission/choose" | not driven live by reviewer |
| O1-O3-room | PASS | 20-scene-page-log-lines.png and /api/interactions: "calls on Ombrin: [player line]", "invocation: Success.", then the check line, in order | Demo's "Name, Perception: Success." is the existing check outcome line "attempts ... (Hard) and fails (Partial Success)", unchanged by this slice |
| O-secret | OUT_OF_SCOPE | Secret faith room line is asserted in the telnet test only; no live secret-faith being was seeded | Not rendered by reviewer; covered by the e2e test |
| A3-devotion | PASS | 10 and 22 pngs: fieldsets, rows, table match; heading subtitle readable; "Rule: an invocation bonus changes a result only when it moves the total across a rank threshold." shown under the awards | none |
| A4-chosen | PASS | 11-admin-chosen-favor-config.png: Earning bonus percent 100, Invocation ease points 30, Chosen per being "Ombrin 1", help lines present | none |
| A6-being | PASS | 12-admin-being.png: Invocation check type with help "Optional override ... Blank uses the default" | Steward inline and builder links: later slices |
| A7-builder | PASS | 13-distinction-builder-effects.png: favor invocation and favor earning rows with the "Being: Ombrin. Value is ..." help lines and the picker note | Select truncates long labels at this width; cosmetic |
| A8-A9-pickers | PASS | Autocomplete on conditionmodifiereffect.modifier_target and craftingrecipemodifier.target lists Any being and per-being favor invocation and earning targets | Not screenshotted; read from the live endpoint |
| S2-S5-out | OUT_OF_SCOPE | Pledges, sacrifices, answers, stewards, table page, GM panel, deed and steward fields | Slices 2 to 5 per issue #4333 slice cut |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Option card Call on favor | Demo option card with invoke control | MATCH | docs/reviews/4353/01-mission-option-call-on-favor.png |
| Picker title, Being row, Easy chip, uses left | "Call on favor", Ombrin, Easy chip, "3 of 3 left this week" | MATCH | docs/reviews/4353/02-call-on-favor-picker.png |
| Invocation difficulty table | Base, Chosen -30, Favor -15, modifiers 0, Result 30 Easy | MATCH | docs/reviews/4353/02-call-on-favor-picker.png |
| Bonus by result line | CS +15, S +10, PS +5, Failure none | MATCH | docs/reviews/4353/02-call-on-favor-picker.png |
| How it shows field | Optional one-line field | MATCH | docs/reviews/4353/02-call-on-favor-picker.png (caption deviation accepted per #4193) |
| Rules line and buttons | Favor not spent, failed counts, one being; Close, Call on Ombrin | MATCH | docs/reviews/4353/02-call-on-favor-picker.png |
| Invoking first strip | "Invoking Ombrin first (Easy)" with a second control | MATCH | docs/reviews/4353/03-invoking-first.png (control is Don't call, not Attempt; accepted) |
| Result call and outcome lines | calls on line, invocation outcome | MATCH | docs/reviews/4353/04-mission-result.png |
| Result breakdown rows | check points, favor bonus line, Total, Difficulty, Rank difference | MATCH | docs/reviews/4353/04-mission-result.png (points and roll omissions accepted); "would be" note shown only when the bonus changes the difference |
| Scene self-check strip | Invoking line on the check panel | MATCH | docs/reviews/4353/05-self-check-invoking.png |
| Scene room lines | three lines in order | MATCH | docs/reviews/4353/20-scene-page-log-lines.png |
| Devotion Invocation check fieldset | check type, base difficulty, eases text, favor ease thresholds and points, per week | MATCH | docs/reviews/4353/10-admin-devotion-config.png |
| Devotion Earning rate row | Earning rate explanation | MATCH | docs/reviews/4353/10-admin-devotion-config.png |
| Favor outcome awards inline | Kind, tier, amount rows for 15, 10, 5, 0, 0 | MATCH | docs/reviews/4353/10-admin-devotion-config.png (Rule line now shown) |
| Resulting invocation difficulty table | three favor bands by four columns | MATCH | docs/reviews/4353/22-admin-devotion-context-now.png |
| Invocations last week | totals row | MATCH | docs/reviews/4353/10-admin-devotion-config.png ("No finished game week yet" on an empty database) |
| Chosen favor config new fields | two fields with help, Chosen per being | MATCH | docs/reviews/4353/11-admin-chosen-favor-config.png |
| Being Invocation check type | override field with help | MATCH | docs/reviews/4353/12-admin-being.png |
| Builder favor effects | target, value, help lines, picker note | MATCH | docs/reviews/4353/13-distinction-builder-effects.png |

Note: the Result column above marks the checklist element as present and compared; where the Evidence cell lists a caveat it is carried into the findings below.

## Unresolved findings

None
