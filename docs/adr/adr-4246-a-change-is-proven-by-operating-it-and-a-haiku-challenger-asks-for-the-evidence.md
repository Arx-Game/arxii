# ADR-4246: A change is proven by operating it, and a Haiku challenger asks for the evidence

**Status:** Accepted (2026-10-11, TehomCD)
**Issue:** #4246 (children #4247, #4248)
**Related:** ADR-0021 (main uses a merge queue), ADR-0237 (authored content is durable),
ADR-0276 (migration chain regeneration)

## Context

Agents write most of this repo's tests, after they write the code, so the code's
output tends to become the expected value. Research on LLM-written regression tests
(arXiv 2610.11835) found that 8-17% of them asserted the faulty behavior and that the
projects' own suites caught few of those; a second study (arXiv 2602.07900) found the
tests agents write while working are mostly print probes. Here, three migrations passed
CI and failed on the production deploy because CI migrates an empty database
(`0220_upbringings`, the `0149` constraint, the `0170` re-level); agents claimed
production-copy tests they had not run; #3660 shipped past nineteen green tests. Specs
named "unit tests" as their testing plan, and nothing checked that.

## Decision

**Unit tests alone are not proof that a change works.** Before a PR, the agent operates
the change through the interface a person or caller uses, against isolated data, and
reports in plain words what it did, expected, saw, and where the evidence is
(`tools/skills/real-testing/`, adapted from an MIT skill). Expected results come from the
spec, never from the code's output. Specs carry a Verification section in that shape.
The agent judges whether the machine can carry a pass; if not, it records
`BLOCKED: resources` instead of trying, and `BLOCKED` is never a pass. There is no
memory budget to measure.

**A cheap reviewer challenges claims, and it is advisory.**
`evidence-challenge-reviewer` runs on Haiku 5.5 from `evidence-challenge.yml` on PR open
and on each member reply that starts with `<!-- evidence-answer -->`, up to three
rounds. It rejects justification-shaped objects: test counts, restated claims, "should",
hedges, jargon, no concrete output. The coding agent must answer each open challenge
with evidence; after round 3 it enqueues and lists what is open. The reviewer posts
plain PR comments only. It is never a required check, and a maintainer approval always
overrides it.

## Rejected alternatives

- **A blocking reviewer through review threads.** The ruleset already requires resolved
  review threads, so posting challenges as threads would block the merge queue for free.
  Rejected: a maintainer approval would not clear an open thread, and the maintainer must
  always be able to merge by approving. It also let the coding agent's token resolve its
  own challenges.
- **A required status check.** Same objection, plus a check missing on `merge_group`
  hangs the queue.
- **Measuring memory per machine before allowing a browser pass.** Rejected as
  needless precision; the agent's judgment plus an honest `BLOCKED` is enough, and the
  evidence can come from CI (#4247) or a larger machine.
- **Deleting agent-written tests now.** Rejected until there is evidence of which tests
  guard nothing (#4248).

## Consequences

Each PR spends a few Haiku runs from the subscription token's quota. Haiku can check
that evidence is consistent (the PR head commit, timestamps, matching error text) but
cannot prove it is real; evidence produced by CI can, which is why #4247 matters. The
`issue_comment` trigger runs the default-branch workflow, so a change to the answer
loop is only exercised after it merges.

## Amendment (2026-10-16, #4390): one helper for production-dump checks

The standing preference is that every migration or data check is proven against the
newest production dump. Eight PRs each hand-wrote the fetch, restore, migrate and
cleanup, and the evidence challenger had to ask each time how the dump was fetched.
`just prod-migration-check` (`tools/prod_migration_check.sh`) is now the one sanctioned
path: read-only `dev_reader` key, a fresh `scratch_pmc_` database that the script
refuses to replace with any other name, forward / back / forward, row counts, cleanup
on every exit path, under the shared heavy-command lock. The alternative rejected was
documenting the recipe in the skills only, which is what produced the eight variants;
`just pull-prod` stays the tool for refreshing `arxiidev`, and is not used for checks.
