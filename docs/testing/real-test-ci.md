# The real-test CI job

`.github/workflows/real-test.yml` operates the real program in CI (#4247, part of
#4246, ADR-4246 and ADR-4247). It is separate from `ci.yml` and is **advisory**: it
is not a required check and is not in any aggregator, so it cannot block the merge
queue.

## What one run does

1. Starts Postgres as a service and builds a throwaway database with
   `tools/build_schema.py` (the same path the backend shards use), then seeds the
   account `e2e_test_account` with the same function `arx manage seed_test_account`
   calls, run through `arx manage shell` because that is the launcher path that
   initialises Evennia first. It also opens registration (it is invite-only by
   default, `RegistrationConfig`) and sets no Facebook credentials, so the login page
   has one "Log in" button.
2. Builds the frontend bundle once (`pnpm build`) and collects static files.
3. Starts the server with `arx start` and waits until `/api/status/` answers on :4001.
4. Seeds the rows a spec needs beyond the account, after the server is up, through
   `arx manage shell` and a function in `src/integration_tests/live_seeds.py`
   (test-factory rows; the database lives for one run). Today those are
   `seed_motif_facet_spec` (a character the account plays holding one resonance, three
   facets, and the account's creation draft at the Gift stage),
   `seed_gift_substance_spec`, `seed_thrown_strike_spec` and `seed_channels_spec` (a
   character played by its own account, `e2e_channels_reader`, in an organization with
   its channel, and two other players' lines in Public, one of them from a player that
   account blocks). The channels spec signs in as its own account because its play-page
   test enters the world, which would change the character `e2e_test_account` acts as
   in the specs that follow.
   The missives spec (#3289) uses its own `e2e_missives_account` and
   `seed_missive_spec`, which prepares a waiting letter, coin and an item and writes
   its identifiers to `/tmp/missive-seed.json`.
   The family seats spec (#5130) uses its own `e2e_family_seats_account` and
   `seed_family_seats_spec`: that account's creation draft at Lineage, a house with a
   title holder and two open seats, and a house with none; its identifiers go to
   `/tmp/family-seats-seed.json`.
   The life-points spec (#5141) uses its own `e2e_life_points_account` and
   `seed_life_points_spec`: that account's creation draft at Lineage and two life
   beats offered to that draft's beginning alone, a childhood one with a card that costs
   CG points and a card the world pays for, and a youth one with one card (#5160, so the
   life has two stages); its identifiers go to `/tmp/life-points-seed.json`.
5. Runs the Playwright specs that need a live server, with one worker, using
   `frontend/e2e.backend.config.ts`: `e2e/account-settings.spec.ts`,
   `e2e/user-journey.spec.ts`, `e2e/motif-facets.spec.ts` (the Spellbook Facets
   panel and the creation facet field, #5021), `e2e/gift-substance.spec.ts` (#5018),
   `e2e/thrown-and-enchanted-strike.spec.ts` (#5026), `e2e/channels.spec.ts`
   (#3299), `e2e/missives.spec.ts` (#3289), `e2e/one-scale.spec.ts` (#5091), and `e2e/family-seats.spec.ts` (the seat picker
   in character creation, #5130), and `e2e/home-while-connected.spec.ts` (the site name
   opening the home page from inside the world, #5137; it reuses the channels spec's
   account and runs after it), and `e2e/life-points.spec.ts` (the "CG points" line of
   the right-hand panel moves with a card click and is what the server then holds, #5141,
   read from the panel every stage shows since #5148; then
   "Restart: Clear All Choices" asks first, leaves the server's life alone on Cancel and
   empties it on confirm, #5146; and the life opens with both stages and both sections
   open and no text box, and the Background written on Final Touches is sent on leaving
   the stage, held by the server, quoted on Review and shown again after a reload,
   #5160 and #5178).
   Every other spec mocks the API and runs against `vite preview` under
   `frontend/playwright.config.ts`. A new spec that talks
   to :4001 must be added to the spec list in the workflow, and its rows to
   `live_seeds.py` and the seed step.
6. Always uploads one artifact, `real-test-<run id>-<attempt>`: a screenshot and a
   trace for every test (`frontend/test-results`), the HTML report
   (`frontend/playwright-report`) and the server logs (`src/server/logs`). The final
   step prints the run URL and the artifact URL in the log and the job summary.
7. Stops the server (also when a spec failed).

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

## Known limits

- The throwaway database has no game clock row, so `/api/clock/` answers 503 in the
  server log. No spec asserts on it.
- The password-change spec changes the seeded account's password and restores it at
  the end. A run that dies between the two changes leaves a throwaway database in an
  odd state; in CI that is irrelevant, locally re-seed or restore it in the admin.
