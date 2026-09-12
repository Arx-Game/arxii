# Review evidence: actions woven into prose (#3787)

- Reviewed revision: `ac34711a9158cc0b293c7c96a65f5fcec6249557`
- Reviewer: demo-fidelity-reviewer agent (vision-capable), plus per-task and whole-branch code reviewers
- Reviewer verdict: PASS
- Application/build identity: production build of the branch frontend (`pnpm build`) served via `pnpm preview`, Django backend from the same worktree
- Environment: devcontainer, Node 20, Python 3.13, headless Chromium via Playwright
- Viewports/themes: desktop viewport, light theme on both sides. Dark theme was NOT exercised; see Unresolved findings note below for why that is not an open finding.
- Approved design: the demo published for this issue, compared from its byte-for-byte published source at `.superpowers/sdd/3787-plan/approved-demo.html` (artifact URL requires an authenticated session, so the local source was used)
- Visual review: both sides rendered and screenshotted, then compared screen by screen with a vision-capable model. Screens 1, 2 and 3 of the approved demo were enumerated element by element.
- Visual verdict: PASS
- Screenshots: both sides of all three screens, committed under `docs/reviews/3787-shots/` and removed before merge. ![Built Screen 1](docs/reviews/3787-shots/build-screen1-fullpage.png) ![Demo Screen 1](docs/reviews/3787-shots/demo-screen1.png)
- Comparison notes: Screen 1 matches, including the fix that the involved row now renders exactly once inside the amber mark rather than duplicating the plain bubble. Screen 2 matches, parent chip quoting the excerpt with reveal-in-place and never a persona name. Screen 3 matches, with the reader refusal box now carrying the same alarm rail the composer's already had. One divergence is RULED and stands as built: an involved row keeps its mark when the reply is unreachable, where the demo drew that row bare; the demo's Screen 3 existed to show the refusal and never composed the two treatments.
- Tested interactions: clicked "Answer this" and confirmed the composer receives the event excerpt rather than the Narrator's name; clicked the parent chip and confirmed reveal-in-place; forced a genuine WS/REST-driven venue change that flipped an in-flight reply target from reachable to refused, then confirmed the refusal renders pre-emptively, the draft survives, Send is disabled, and a forced click dispatches no action frame.
- Fixture/live boundary: the frontend ran against the real production bundle with WebSocket and REST responses supplied by the repository's own `frontend/e2e/support/gameHarness.ts` fixture harness. No production or staging data was used. Backend behaviour was exercised separately by the Django test suites named in the ledger.
- Overall outcome: PASS

## Visual checklist

Demo on the left of each pair, built surface on the right. Every element enumerated, then marked.

### Screen 1 - in the fight

![Demo Screen 1](docs/reviews/3787-shots/demo-screen1.png)
![Built Screen 1](docs/reviews/3787-shots/build-screen1-fullpage.png)

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| ordinary pose bubbles around the event | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| room's third-person outcome line | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| "This happened to you" flag on the involved row | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| tinted panel with left rail on the involved row | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| "Answer this" control on the involved row only | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| quiet Reply link on non-involved rows | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| involved row's content rendered once | exactly one rendering of the line | MATCH | the demo shows the line twice only to contrast two viewers; the build renders it once, pinned by test |

![Answer this, clicked](docs/reviews/3787-shots/build-screen1-answerclick.png)

### Screen 2 - answering it

![Demo Screen 2](docs/reviews/3787-shots/demo-screen2.png)
![Built Screen 2](docs/reviews/3787-shots/build-screen2-collapsed.png)

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| parent chip above the author line | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| chip word "Answering" | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| parent excerpt in quotation marks | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| chip left rail | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| no persona name for the parent | no parent persona name | MATCH | rendered and compared side by side in the screenshots above |
| reveal parent in place on click | described in the demo | MATCH | rendered and compared side by side in the screenshots above |

![Parent revealed in place](docs/reviews/3787-shots/build-screen2-revealed.png)

### Screen 3 - out of reach

![Demo Screen 3](docs/reviews/3787-shots/demo-screen3.png)
![Built Screen 3 reader](docs/reviews/3787-shots/build-screen3-reader.png)

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| disabled Reply control, struck through | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| reader refusal box with alarm left rail | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| refusal bold first sentence | present in the demo | MATCH | rendered and compared side by side in the screenshots above |
| quieter second line naming the venue and keeping the draft | present in the demo | MATCH | rendered and compared side by side in the screenshots above |

![Composer before the venue change](docs/reviews/3787-shots/reverify-screen3-composer-before.png)
![Composer after the venue change](docs/reviews/3787-shots/reverify-screen3-composer-after.png)

### Divergences from the approved design

Both are recorded in the requirement ledger with a decision; neither is a silent difference.

1. The composer's pre-emptive check for a free-text at-mention tag (Screen 3's second panel) is NOT built. The client holds no per-place occupancy data, so a pre-check needs a new endpoint. The refusal still happens server-side with the venue hint and the draft preserved. Ruled out of scope and disclosed for a human ruling.
2. An involved row keeps its mark when the reply is unreachable; the demo drew that row as a bare italic line. Ruled: stands as built. Screen 3 existed to show the refusal and never composed the two treatments, and the event still happened to you even where you cannot answer it from.

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| screen1.involvement-mark | PASS | Amber "This happened to you" mark with "Answer this" on the involved row only; others keep the quiet Reply link. Rendered and compared. | n/a |
| screen1.single-render | PASS | Involved row renders content once; test asserts a single occurrence and fails if the duplicate is restored. | n/a |
| screen2.parent-chip | PASS | Chip reads "Answering" plus the quoted excerpt, reveal-in-place clicked and confirmed. | n/a |
| screen2.no-actor-leak | PASS | Chip renders parent content only; test asserts the parent persona name is absent. | n/a |
| screen3.preemptive-refusal | PASS | Refusal renders before the click after a live venue change; draft preserved, submit blocked, no action frame dispatched. | n/a |
| screen3.refusal-consistency | PASS | Reader refusal box carries the same destructive left rail as the composer's. | n/a |
| screen3.tag-precheck | OUT_OF_SCOPE | Composer has no per-place occupancy data client-side; a pre-check needs a new endpoint. | Ruled out of scope by the controller and disclosed in the PR body for a human ruling. |
| privacy.concealment | PASS | Concealed tiers write zero target rows, pinned by test; the involvement mark cannot fire without target rows. | n/a |
| privacy.parent-visibility | PASS | get_reply_to gates on the parent's own visible_to, batched once per page; a viewer who cannot read the parent gets null. | n/a |
| backend.reachability | PASS | Refusals raised at the shared service seam; refused writes persist nothing, asserted by row counts. | n/a |
| backend.suites | PASS | scenes, combat, cast and actions suites green at this revision; see the branch's task reports. | n/a |
| telnet.parity | PASS | Involvement mark and both refusals reach telnet with the venue hint; web sessions excluded from the plain-text mark. | n/a |

## Unresolved findings

None
