# Narrative-play delivery incident analysis

**Incident:** #3731/#3735
**Reviewed revisions:** approved design `c183f42773d8a4c78b077f0cc5a11f2acd2ff62f`; implementation head `4a094f2448a0d23c4f1d23bb48ddfe9d13e6660e`
**Date:** 2026-09-09

## What the record proves

PR #3735 merged on 2026-09-09 with one empty-body approval. Its validation list named backend tests, frontend tests, typecheck, and build. It did not include the A01-A22 requirement ledger, a browser journey, a live backend boundary, viewport/theme details, screenshots, the 500/2,000-pose workload, or unresolved findings. The implementation issue #3731 then auto-closed while its visible acceptance criteria remained unchecked and stale implementation/approval labels remained attached. The timeline contains review-request and merge-queue events but no visual-review event.

The internal executor record is recoverable in the agent environment at `/home/vscode/.prime/agent/sessions/01a08395-9d93-73b0-9839-492dc3b0fdde.jsonl`. It shows a child named `spec-reviewer` was asked for source/spec inspection, not an exact approved-demo render or browser comparison. That child reported P0/P1 findings about history/reference, reply wiring, read state, acknowledgement lifecycle, chronology/windowing, accessibility, and layout. The parent later described the main blockers as addressed, but no structured finding disposition or re-review was published.

## What remains unknowable

The external reviewer assignment, tool calls, running-app URL/build identity, rendered screenshots, and final verdict are not present in the recovered GitHub or executor records. We therefore do not claim whether an external reviewer inspected the wrong build, never opened the app, misunderstood the assignment, or reported findings that were overridden. The evidence supports a dropped finding channel and an absent acceptance gate, not individual blame.

## Causal chain

1. The approved design had mandatory user and visual requirements, but no machine-readable evidence ledger was carried into the PR.
2. The executor's reviewer assignment was a source/spec review, while the repository's demo-fidelity policy was advisory and was not dispatched.
3. Existing tests proved component/API/build properties and accepted mocks, but did not prove the ordinary entry journey, real wire boundary, or rendered visual fidelity.
4. `open-pr.sh` and `enqueue-pr.sh` had no evidence precondition, and the PR template only recorded generic validation commands.
5. `Closes #3731` caused auto-close despite unchecked acceptance criteria; post-merge cleanup checked only whether linked issues closed.
6. An empty-body approval was enough for GitHub's one-approval rule, and stale approvals were not dismissed on new pushes.

## Repaired controls

This incident is repaired by a committed review-evidence contract, exact-HEAD validator, mandatory pre-PR validation, a durable evidence link in the PR body, a CI validator for pull requests, explicit `Refs` versus `Closes` semantics, and reviewer instructions requiring screenshots, user journeys, provenance, and per-criterion dispositions. A scoped repair defaults to `Refs`; only an explicitly complete report may request closure.

## Regression target

The archived #3735 PR body is a negative fixture: its generic validation list has no evidence report, no exact revision, no screenshot or journey provenance, and no criterion ledger. The validator must reject that shape before a PR can be opened or queued.
