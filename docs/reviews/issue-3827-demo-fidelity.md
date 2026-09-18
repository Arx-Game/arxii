# Review evidence: issue #3827

- Reviewed revision: `df4ce60b3621a8a96e3413a4581658bdb4f796ee`
- Reviewer: demo-fidelity-reviewer (delegated pre-PR review), with implementer verification
- Reviewer verdict: PASS
- Application/build identity: Arx II backend at `df4ce60b3621a8a96e3413a4581658bdb4f796ee`; frontend bundle unchanged by this revision
- Environment: `/workspaces/arxii/.claude/worktrees/feature-3827-block-mute-does-not-gate-tagging-a-block`; SQLite fast test tier; repository frontend test/typecheck review
- Viewports/themes: Approved reference captured at 1280px wide in the default dark scene theme; no new rendered surface in this backend-only change
- Approved design: [issue #3827 approved demo](https://github.com/Arx-Game/arxii/issues/3827#issuecomment-5722596019)
- Visual review: Not applicable to the changed surface: this revision changes target validation and persistence only, keeps the existing frontend request/error contract, and adds no frontend markup, CSS, or client moderation state.
- Visual verdict: NOT_APPLICABLE
- Screenshots: ![Approved issue #3827 demo](../.github/issue-evidence/3827/20260917T232719Z-issue-3827-demo.png)
- Comparison notes: The approved image is retained as the immutable issue reference. The branch has no frontend diff, so its existing composer and neutral error path remain unchanged. The server now returns the approved neutral detail and draft-preservation hint before target rows are written.
- Tested interactions: Exact-face Block; account-level Block; unrelated alternate identity; pending-removal Block; persona-scoped IC Mute; account-level IC Mute snapshot; OOC-only Mute; one-way Mute; multi-target atomic refusal; persistent whisper; ephemeral interaction; REST target submission path; existing frontend scene/error tests and typecheck review.
- Fixture/live boundary: The approved screenshot is a fixture/reference artifact published from immutable repository content. Backend behavior was exercised with Django service/action tests; no live production data or moderation state was used.
- Overall outcome: PASS

## requirement ledger

|id|status|evidence|authorizeddecision|
|---|---|---|---|
|target-gate|PASS|`social_control_excluded_target_ids` batches active Block and IC Mute scope before target writes; 22 reachability tests pass|Approved issue #3827 spec|
|neutral-refusal|PASS|Generic `UnreachableError` detail and `Your draft is kept.` hint disclose no moderation relationship|Approved issue #3827 spec and ADR-0204 addendum|
|atomicity|PASS|Multi-target and persistent/ephemeral tests verify no interaction or target bridge is written on refusal|Approved issue #3827 spec|
|delivery|PASS|ADR-0204 remains flag-only for IC delivery; system-authored outcome writers remain exempt|ADR-0204 addendum #3827|
|frontend-contract|PASS|No frontend source changed; existing typed error and draft-preservation contract remains intact|Approved issue #3827 spec|

## Visual checklist

|element|expected|result|evidence|
|---|---|---|---|
|scene-composer|Approved scene composer remains the reference surface; no frontend surface changed|MATCH|Approved demo image and zero frontend diff at `df4ce60b3621a8a96e3413a4581658bdb4f796ee`|
|neutral-refusal|Refusal remains neutral and preserves the draft without moderation state|MATCH|Server detail/hint assertions and approved demo reference|
|target-marking|Affected persona is not written as an interaction target|MATCH|22 Django target/reachability tests and target-row no-write assertions|

## Unresolved findings

- None
