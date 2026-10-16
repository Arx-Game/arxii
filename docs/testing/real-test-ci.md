# The real-test CI job

`.github/workflows/real-test.yml` operates the real program in CI (#4247, part of
#4246, ADR-4246 and ADR-4247). It is separate from `ci.yml` and is **advisory**: it
is not a required check and is not in any aggregator, so it cannot block the merge
queue.

## What one run does

1. Starts Postgres as a service and builds a throwaway database with
   `tools/build_schema.py` (the same path the backend shards use), then
   `arx manage seed_test_account` (user `e2e_test_account`).
2. Builds the frontend bundle once (`pnpm build`) and collects static files.
3. Starts the server with `arx start` and waits until `/api/status/` answers on :4001.
4. Runs the Playwright specs that need a live server, with one worker, using
   `frontend/e2e.backend.config.ts`: `e2e/account-settings.spec.ts` and
   `e2e/user-journey.spec.ts`. Every other spec mocks the API and runs against
   `vite preview` under `frontend/playwright.config.ts`. A new spec that talks to
   :4001 must be added to the spec list in the workflow.
5. Always uploads one artifact, `real-test-<run id>-<attempt>`: a screenshot and a
   trace for every test (`frontend/test-results`), the HTML report
   (`frontend/playwright-report`) and the server logs (`src/server/logs`). The final
   step prints the run URL and the artifact URL in the log and the job summary.
6. Stops the server (also when a spec failed).

## Triggers and limits (overridable)

- Runs on pull requests that touch `frontend/**`, `src/web/**`,
  `src/world/**/views.py` or `src/world/**/serializers.py`; on any PR that carries
  the `real-test` label (adding the label starts a run); and on
  `workflow_dispatch`. Not on `merge_group` or `push` to main.
- One job, one Playwright worker, `timeout-minutes: 25`, and a `concurrency` group
  per PR with `cancel-in-progress`, so a new push replaces the run in flight and the
  job respects the org concurrent-job cap noted in `ci.yml`.
- Any of these is a decision the maintainer can change by editing the workflow.

## Using a run as evidence

A green or red run of this job is acceptable evidence for a behavior it covers
(login, registration, account settings, and whatever a new live-server spec
asserts), because the agent that wrote the change did not produce it. To cite it
in a PR comment or in an `<!-- evidence-answer -->`:

- Link the run URL and the artifact URL (both are in the job summary).
- Name the commit the run built (`GITHUB_SHA` is printed; on a PR it is the merge
  commit, so also give the PR head SHA).
- Say which spec and which step covers the claim and what the screenshot or trace
  shows. A green run only proves what its specs assert; a change in a surface no
  spec visits is still unproven, and the answer should say `BLOCKED` for that part.
- To close a claim the existing specs do not cover, add a spec under
  `frontend/e2e/` that asserts the new behavior and add it to the workflow's spec
  list, or run `workflow_dispatch` against the branch.
