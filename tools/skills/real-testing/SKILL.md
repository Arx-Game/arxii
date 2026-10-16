---
name: real-testing
compatibility: polytoken
license: MIT
description: Use after implementing a feature, fix or migration and before saying it works or opening a PR. Prove the change by operating the real program (web client, REST/WebSocket, admin page, a migration against a production copy) and reporting what was seen, in plain words. Also use when writing a spec's Verification section, and when answering an evidence-challenge comment on a PR. Unit tests alone are not proof.
---

# Real Testing

Build it. Run it. Operate the changed feature. Explore how it fails. Keep what
you discover. Report what you saw, in plain words.

Adapted from
[Corvidae-Coding-Projects/real-testing](https://github.com/Corvidae-Coding-Projects/real-testing)
(MIT; see `LICENSE` in this directory) for Arx II (#4246, ADR-4246).

## Why

Agents write tests after the code, and the code's output becomes the expected
value. Research on LLM-written regression tests (arXiv 2610.11835) found that
8-17% of them asserted the faulty behavior. Here, three migrations passed CI
and failed on the production deploy, because CI migrates an empty database;
#3660 shipped a broken admin page past nineteen green tests.

So: compilation, a server that starts, an HTTP 200, a success message and a
green suite are steps on the way. They are not the finish. A change is done
when you have operated it and seen the promised result.

## 0. Check the machine first

Before you start a server, a browser or a build, check that this machine can
carry it, and that you would not be taking something from another session.
You already know the machine profile from the CLAUDE.md machine test ("Tool &
Subagent Sequencing"); under 8 GiB is the small laptop. The devcontainer is
shared: other sessions may have a server running (`ss -ltn` shows :4001 and
:4002), tests running, or their own worktrees open.

You do not need to measure memory or make a budget. Use judgment:

- If the machine looks able to carry the pass, do it.
- If it does not (small machine, a suite or build already running, other
  agents busy), **do not try the heavy pass.** Record it as
  `BLOCKED: resources` with the reason, and do the largest smaller form that
  fits (section 2):
  - your own server with real requests and no browser;
  - or, smallest, Form A: the test client against factory rows, in the test
    runner's own database.
- Never run a frontend build, a typecheck or a test suite while the server and
  a browser are up on the small machine.

`BLOCKED` is an honest result. It is never a pass. The evidence must then come
from somewhere else: a CI run, a run on a larger machine, or the maintainer.

## 1. Write down the expected behavior first

- From the issue, the spec's Verification section, the demo, an ADR or a
  documented contract, list each behavior the change promises and the
  interface a person or caller uses to reach it.
- For each one, write the action or input and the result you expect to see,
  **before** you run anything.
- **Never take the expected result from the code's own output.** If the code
  printed it, that does not make it correct.
- If two sources disagree (a doc says one thing, a spec or ADR another), do
  not pick one quietly. Name both in the report. When the issue or a newer
  ADR settles it, fix the stale doc in the same PR; when nothing does, ask
  the maintainer.
- Include the ordinary case and the one failure or edge case that matters
  most for this change (a bad input, a permission refusal, an empty state).
  Add more only for different ways it can fail. No case-count quota.
- Choose inputs that would expose a mistake: distinct values where order,
  identity or routing matters; not symmetric examples that hide a swap.

## 2. Choose the form, then start it

There are two forms. Check which one you can use, by process, not only by
port: `arx start` kills every process whose command line names `evennia`,
`twistd`, `server.py` or `portal.py`, on any port.

Run these as two separate commands (a compound command is refused):

```bash
pgrep -af '[e]vennia|[t]wistd|[s]erver\.py|[p]ortal\.py' | grep -v defunct
```

```bash
ss -ltn | grep -E ':(4001|4002) '
```

The brackets stop the pattern from matching the shell that runs it, and
`grep -v defunct` drops dead processes, which are many. Any line from either
command means Form A. Only when both print nothing may you use Form B.

**Never touch production, and never overwrite the shared `arxiidev`.** Every
session in the devcontainer uses it. `just pull-prod yes` restores over it (it
always targets the database in `src/.env`), so run it only with the
maintainer's go-ahead. `arx` and `evennia` run through `uv run`; they are not
on the PATH.

### Form A: the test client (always possible)

Use it when :4001 or :4002 is already in use, on the small machine, or on the
solo laptop. Something listening there is almost always another session's
server, running another worktree's code, not yours. **Do not run
`just start`, and never `uv run arx stop --hard`**: `arx start` and
`arx stop --hard` kill every Evennia process in the container. Do not operate
your change through that server either; it does not have your code.

Write a short test that drives the real URL, view, serializer and service
stack with Django's test client (`self.client`) against rows made by
factories, the way a request would, and reads the saved state back. Do not
mock the parts a request goes through. For an endpoint that acts as a
character (`X-Character-ID`), make the account the character's player with a
real roster tenure, as `src/world/journals/tests/test_offscreen_gate_web.py`
does, and pass `headers={"X-Character-ID": ...}`. Run it with
`just test-fast <dotted.path>`; the test runner makes its own isolated
database. Keep the test only if it found a failure (section 6); otherwise
paste its output into the report before you delete it.

Record the browser or server part as `BLOCKED: shared server` (or
`BLOCKED: resources`) and say in the report that this was the smaller form.
It cannot show that a page renders or that the WebSocket path works.

### Form B: your own server (when the ports are free and the machine has room)

Only from a worktree. A worktree has no `src/.env`, so settings read
`DATABASE_URL` from the environment; in the main checkout `src/.env` wins and
the server would use `arxiidev`.

1. Make your own throwaway database. Pick a name nobody else uses, for example
   `rt_<issue number>`:

   ```bash
   PGPASSWORD=arxii createdb -h db -U arxii rt_4246
   DATABASE_URL=postgres://arxii:arxii@db:5432/rt_4246 uv run python tools/build_schema.py
   DATABASE_URL=postgres://arxii:arxii@db:5432/rt_4246 uv run arx manage seed_test_account
   ```

   The seed makes `e2e_test_account` / `TestPass123!`. The container already
   sets `DATABASE_URL` to `arxiidev`, and each of your tool calls starts a
   fresh shell, so put `DATABASE_URL=...` in front of **every** command that
   must use your database, including `just start`. An `export` does not carry
   over to the next call.

   Do not use `just build-test-schema` here: it reads `src/.env` and rebuilds
   the shared `test_arxiidev` that other sessions' parity tests use.
2. For a UI check, build the frontend first, while nothing else is running:
   `pnpm --dir frontend install`, then `just fe-build` (it also collects
   static files). Chromium for Playwright: `just fe-e2e-install`, once per
   container.
3. Start: `DATABASE_URL=postgres://arxii:arxii@db:5432/rt_4246 just start`.
   Web is on
   :4001, the websocket on :4002. Watch the startup output and the server log
   for errors: a process that started is not a process that is ready.
4. Drive the UI with Playwright against your server, one worker:
   `just fe-e2e <spec> --workers=1` (`frontend/e2e.backend.config.ts` targets
   :4001). Write a spec for your scenario in `frontend/e2e/` if none exists;
   keep it only if it found a failure (section 6).
5. After a fix: `just stop`, rebuild if the frontend changed, and start
   again as in step 3. A stale bundle or an old server process is not evidence. Never
   build while the server and a browser are both up on a small machine.
6. When you finish: `just stop` (never `uv run arx stop --hard`), then drop only the database
   you created: `PGPASSWORD=arxii dropdb -h db -U arxii rt_4246`.

If a dependency you need is missing, say which behaviors that blocks, test the
rest, and never replace the missing part with a mock and call it verified.

### Form C: the CI run (`real-test.yml`, #4247)

When Form B is `BLOCKED: resources` (or you want a second pair of hands), the
`real-test` workflow operates the real program on a CI runner: throwaway Postgres,
built bundle, `arx start`, the live-server Playwright specs (one worker). It runs
on PRs touching `frontend/`, `src/web/`, or a `views.py`/`serializers.py`, when the
PR has the `real-test` label, and on `workflow_dispatch`
(`gh workflow run real-test.yml --ref <branch>`). It is advisory. Its run is
acceptable evidence: cite the run URL and the artifact URL (both are in the job
summary), the PR head commit it built, the spec that covers the claim, and what the
screenshot or trace shows. It only proves what its specs assert; for a surface no
spec visits, add a spec to `frontend/e2e/` and to the workflow's spec list, or
record `BLOCKED` for that part. See `docs/testing/real-test-ci.md`.

## 3. Operate the change through its real interface

| Change | What to do |
|---|---|
| Web client page or control | Open the running app (Playwright against the server, one worker), do what a player does, check what the page shows and what was saved. A direct API call can add to this; it cannot prove the UI works. |
| REST endpoint | Send real requests to the running server; check the response and the saved state it should change. |
| Game action over WebSocket | Do the action in the web client with Playwright (Form B, step 4); that is the real path the action takes. There is no standalone WebSocket driver in the repo: if you cannot run the browser, record the WebSocket part as `BLOCKED` and prove the action's service and state change with Form A. |
| Staff admin page | Load the page in the running server as a staff account; submit the form; read the row back. |
| Migration on tables with data | Copy `arxiidev` into a scratch database and migrate that (`reviewing-migrations` section 6, with a name of your own in place of `arx_migcheck` so two sessions do not collide); never migrate `arxiidev` itself. Say how old its production copy is: `pull-prod` drops and recreates the database, so its creation time is the pull time (`select (pg_stat_file('base/'||oid||'/PG_VERSION')).modification from pg_database where datname='arxiidev';`). If it is stale or was never pulled, ask the maintainer before a fresh `just pull-prod yes` (it overwrites the shared `arxiidev`), or record `BLOCKED: no current production copy`. Check the affected rows before and after. For a fix, show the old migration failing and the new one passing. |
| Service function with no outside interface | Call it the way its real caller does, with real related rows, and read back the state. |

- In Form A, the REST, admin and service rows go through the test client
  instead of a running server; the web-client and WebSocket rows are
  `BLOCKED` and say so.
- For anything that saves, read it back the normal way (reload the page,
  fetch it again) and check the content, not only that a row exists.
- Check the failure behavior the contract promises: the refusal, the error
  message, and that nothing changed when it should not.
- Read the server log for errors on the path you exercised, even when the
  page says it worked.
- Record where each piece of evidence came from: the commit, the command, the
  account, the database.

## 4. Look for failures beyond the happy path

Pick the ways this change could fail (values, sizes, order, identities,
permissions, empty collections, repeat or retry, reload). Try a bounded set of
varied inputs or action sequences through the same real interface. Decide the
expected result for each from the contract, not from the code. Record what
you tried and how many. If something fails, reduce it to the smallest case
that still fails.

## 5. Fix and repeat

Mark each scenario `PASS`, `FAIL` or `BLOCKED: <reason>` (for example
`BLOCKED: resources`, `BLOCKED: shared server`). On a failure, fix the cause,
restart, and run the scenario again with the checks next to it. Never loosen
an expectation just to get a pass. If an expectation was wrong, say why, with
the source that says so.

## 6. Keep what you discovered

Save each real failure you found as a small test that replays it: a
factory-based test next to the code, or a spec in `frontend/e2e/` for a UI
path. It must fail on the old behavior and pass on the fixed one. Do not add
tests only to record what you built.

## 7. Report in plain words

Write the report so that a person who does not know the code can follow it.
For each scenario: **what you did, what you expected, what you saw, and where
the evidence is** (command output, a screenshot of the running app, a CI run).
An example of the shape:

> I applied the migration to a production copy taken 2026-10-10. The 15 rows
> in Beginnings kept their family names; before and after counts match.
> Output: <link>.

Not acceptable as evidence (a reviewer will challenge these):

- test names or counts ("added 14 tests", "all tests pass", "CI is green");
- the claim said again ("verified that it works correctly");
- what should happen in place of what was seen;
- hedges ("appears to", "should work");
- jargon where a plain statement would do;
- a screenshot of a mockup in place of the running app.

Put the report in the PR body's `## Verification` section. Stop only the
processes you started, and remove throwaway data you created.

## When to use TDD instead, and when both

`superpowers:test-driven-development` stays the tool for pure logic: parsing,
math, a classifier, a service function with no outside interface. Write the
test first, from the spec.

This skill is required for anything a player, a staff member or a caller
operates, and for every migration that touches tables with data. Tests may
support the claim. They never replace operating it.

## Answering an evidence challenge

`.github/workflows/evidence-challenge.yml` runs `evidence-challenge-reviewer`
on each PR. It posts a comment that starts with `<!-- evidence-challenge`
and lists claims as `PROVEN`, `OPEN` or `BLOCKED`. For each `OPEN` item, do
the check above and answer in one PR comment that starts with
`<!-- evidence-answer -->`, in the format of section 7. If you cannot run it,
say `BLOCKED` and why. Do not argue without evidence.
