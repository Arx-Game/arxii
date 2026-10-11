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
  `BLOCKED: resources` with the reason (for example, the `MemTotal` line), and
  do the largest smaller form that fits:
  - API-only: a running server, real requests, saved state read back. No
    browser, no build at the same time.
  - The built frontend served by the server, one Playwright worker, nothing
    else running.
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
- Include the ordinary case and the one failure or edge case that matters
  most for this change (a bad input, a permission refusal, an empty state).
  Add more only for different ways it can fail. No case-count quota.
- Choose inputs that would expose a mistake: distinct values where order,
  identity or routing matters; not symmetric examples that hide a swap.

## 2. Build and start the current program

- **First check if a server is already running:** `ss -ltn | grep -E ':(4001|4002) '`.
  - **Something is listening:** it is almost always another session's server,
    started from another worktree, running that worktree's code, not yours.
    **Do not run `just start`, `just stop` or `uv run arx start`.** `arx start`
    kills every Evennia process in the container before it starts, so it
    would take that session's server down. Do not operate your change through
    that server either: it does not have your code. Record
    `BLOCKED: shared server` and use the smaller form: drive the real URL,
    view and serializer stack with Django's test client against real rows
    made by factories, and read back the saved state. Say in the report that
    this was the smaller form.
  - **Nothing is listening and the machine has room:** start your own from
    your worktree against your throwaway database:
    `DATABASE_URL=postgres://arxii:arxii@db:5432/<your_db> just start` (web on
    :4001, websocket on :4002), and stop it with `just stop` when you finish.
    This works because a worktree has no `src/.env`, so settings read
    `DATABASE_URL` from the environment. The main checkout has a `src/.env`,
    and `arx` loads it over the environment, so there the server always uses
    `arxiidev`: do not run this from the main checkout. On the solo laptop,
    where the branch is checked out in the main checkout, a server you start
    writes to `arxiidev`; use the smaller form above, or say in the report
    exactly which rows the check created there. `arx` and `evennia`
    run through `uv run`; they are not on the PATH. Use the built frontend
    bundle served by the server; run `pnpm dev` (Vite on :3000) only when the
    machine has room.
- Make sure what you exercise contains your change: rebuild and restart after
  a fix. A stale bundle or an old server process is not evidence.
- **Isolated data.** Use a throwaway database, for example one built by
  `just build-test-schema` plus `just seed-test-account`
  (`ALLOW_INTEGRATION_TESTS=true`), or the scratch database of
  `reviewing-migrations` section 6. Do not run the test suite against the same
  database while you use it.
- **Never touch production, and never overwrite the shared `arxiidev`.**
  Every session in the devcontainer uses it. `just pull-prod yes` restores
  over it (it always targets the database in `src/.env`), so run it only with
  the maintainer's go-ahead.
- Watch startup for errors. A process that started is not a process that is
  ready.
- If a dependency you need is missing, say which behaviors that blocks, test
  the rest, and never replace the missing part with a mock and call it
  verified.

## 3. Operate the change through its real interface

| Change | What to do |
|---|---|
| Web client page or control | Open the running app (Playwright against the server, one worker), do what a player does, check what the page shows and what was saved. A direct API call can add to this; it cannot prove the UI works. |
| REST endpoint | Send real requests to the running server; check the response and the saved state it should change. |
| Game action over WebSocket | Send the action the web client sends; check the response and the resulting state. |
| Staff admin page | Load the page in the running server as a staff account; submit the form; read the row back. |
| Migration on tables with data | Copy `arxiidev` into a scratch database and migrate that (`reviewing-migrations` section 6); never migrate `arxiidev` itself. Say how old its production copy is: `pull-prod` drops and recreates the database, so its creation time is the pull time (`select (pg_stat_file('base/'||oid||'/PG_VERSION')).modification from pg_database where datname='arxiidev';`). If it is stale or was never pulled, ask the maintainer before a fresh `just pull-prod yes` (it overwrites the shared `arxiidev`), or record `BLOCKED: no current production copy`. Check the affected rows before and after. For a fix, show the old migration failing and the new one passing. |
| Service function with no outside interface | Call it the way its real caller does, with real related rows, and read back the state. |

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

Mark each scenario `PASS`, `FAIL` or `BLOCKED`. On a failure, fix the cause,
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
