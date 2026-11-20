# Security alert triage

Dependabot makes the first attempt at every security fix. This runbook covers the part
that does not rely on it: a deterministic check, run on a maintainer's own machine, that
finds every Dependabot security alert (including the backlog), keeps one generic public
tracking issue per alert, tells the maintainers privately, starts a local agent on the
alert, and escalates before a 48 hour target is missed. The target is a goal, never a
reason to dismiss an alert (#4896, ADR-4896).

Routine version updates are a separate concern: grouped weekly in
`.github/dependabot.yml` (#4901), independent of security updates.

## What the pieces are

| Piece | Where it lives | Role |
| --- | --- | --- |
| `tools/security_monitor.py` | this repository | The check: reads alerts, keeps tracking issues, decides, notifies, dispatches. Never calls a language model. |
| `tools/security_alert_agent_brief.md` | this repository | What the dispatched agent is told. It receives an alert number, never alert text. |
| State directory | maintainer's machine, outside the checkout | Alert number, state, timestamps, escalation stage, worker lease and exception record. No advisory text, no credentials. |
| Notification command, dispatch command | maintainer's machine | Private delivery of the report and the start of the local agent. Configured by environment variable; nothing about them is in the repository. |
| OS scheduler entry | maintainer's machine | Runs `check` every 4 hours. |

## What one check does

1. Takes an exclusive lock in the state directory (an expiring lease, so a crashed run
   is recoverable) and exits quietly if another check holds it.
2. Reads **every page** of open alerts, then does a fresh single read of each tracked
   alert that is no longer in that list. Any API failure stops the run: an error is never
   treated as an empty list.
3. Lists every tracking issue (label `security-alert`, open and closed) and reads its
   marker `<!-- security-alert-tracking:alert=N -->`, so mappings survive lost state and
   concurrent runs cannot create a duplicate.
4. Decides per alert (a pure function, tested with fixed clocks):
   - a new alert: create the tracking issue, tell the maintainers, dispatch the agent;
   - a reopened alert: reopen its issue, restart escalation against the **original** age;
   - a changed alert (its `updated_at` moved): tell the maintainers, dispatch the agent;
   - escalation at 24 hours and at 48 hours from original detection, then at most once
     per 24 hours while unresolved. An alert first seen past a threshold fires the
     corresponding escalation at once, once;
   - a retry dispatch at most once per 24 hours while no agent run holds the lease;
   - a **fixed** alert (fresh read says `fixed`): close its issue. A dismissed alert is not
     fixed: its issue stays open and escalation continues. A merged PR with the alert
     still open changes nothing.
5. Applies the public writes (idempotent), then sends the private notification, then
   dispatches (at most `--max-dispatch`, default 3, per run; the rest wait for the next
   run), then writes state. If the notification fails, state is not written, so the next
   run repeats the same escalation and nothing is lost.

A run with no new, changed, retryable or due work prints "No change", sends nothing and
starts no agent.

## What is public and what is not

The public tracking issue is titled `Security alert follow-up (alert N)` and its body is
the marker, a link to the alert page (which only maintainers can open) and one sentence.
It never carries a package, severity, version, advisory, exploit or mitigation detail.
The GitHub calls filter each alert to `number, state, created_at, updated_at` inside
`gh --jq`, so the rest never enters the process. A generic issue and its timing still show
that some alert exists. Anything the agent learns stays in its private run; its PR text
must be generic too, although a dependency diff can name the package (the agent brief
tells it to re-read the diff for anything else).

## Exceptions

A maintainer can record that an alert is accepted for now:
`uv run python tools/security_monitor.py exception <alert> --by <name>`. This closes the
tracking issue and stops dispatch and escalation, **keeps the record and the alert's
original age**, and restates the unresolved alert in the private report every 7 days. If
the alert later reads `fixed`, or reopens after being fixed, the exception is dropped.
`exception <alert> --clear` reverses it and sends the agent back to the alert.

## Commands

```text
uv run python tools/security_monitor.py check [--dry-run] [--max-dispatch N]
uv run python tools/security_monitor.py status
uv run python tools/security_monitor.py ack <alert> --outcome fix-proposed|containment|blocked|no-action
uv run python tools/security_monitor.py exception <alert> [--by NAME] [--clear]
```

`check --dry-run` reads alerts, tracking issues and state, prints the proposed work for
each alert (numbers, ages and fixed words only) and changes nothing: no issue, no state,
no notification, no agent. It needs no notification or dispatch command.

Configuration is by environment: `ARX_SECURITY_MONITOR_DIR` (or `--state-dir`; refused if
inside the checkout), `ARX_SECURITY_NOTIFY_CMD` (receives `{"events": [...]}` as JSON on
stdin; each event has a kind, an alert number, a protected link, an age in hours and a fixed
detail word) and `ARX_SECURITY_DISPATCH_CMD` (run detached with the alert number and the
reason as its last two arguments; the environment also carries `ARX_SECURITY_ALERT`,
`ARX_SECURITY_REASON` and `ARX_SECURITY_BRIEF`, the brief's path). A real run without both
commands fails instead of pretending.

Exit codes: 0 ok, 1 some alert could not be processed, 2 the run failed (alert API, `gh`,
notification, configuration), 3 `status` found no recent successful check.

## How you know it ran, and how you know it did not

- Every successful run records `last_success_at`. `status` prints it and exits 3 when it is
  older than 9 hours (two intervals plus one hour), or when no check ever succeeded. Run
  it by hand, or from a second scheduler entry that reports a non-zero exit.
- The first successful run after a gap longer than that sends a `missed_runs` event, so a
  machine that was off still reports on return, together with any escalation that came due
  meanwhile. An offline machine cannot warn about itself; nothing in this repository can
  notice it from outside, and there is no independent watchdog.
- A failed run (API, container, authorization, notification) prints the cause, exits 2 and
  sends a `failure` event, repeated at most once per 24 hours while it keeps failing. It
  never closes an issue or reports all-clear.
- A dispatched agent records its end with `ack`, which frees its lease and stores the
  outcome. A lease that is never freed expires after 6 hours, and a retry follows.
- There is no in-repository fast trigger: GitHub Actions has no workflow event for
  Dependabot alerts, so detection waits for the next scheduled check (up to 4 hours). Run
  `check` by hand for an immediate pass.

## What the maintainer does by hand to activate it

None of this is done by the repository. The scheduler, the commands and the credentials
live on the maintainer's machine.

1. Create the issue label `security-alert` in the repository (one time).
2. In the authenticated development container, run
   `uv run python tools/security_monitor.py --state-dir <a directory outside the checkout> check --dry-run`.
   Confirm it lists the alerts. A 403 means the container's token lacks the Dependabot
   alerts read permission listed in `docs/devcontainer-setup.md`.
3. Make the state directory persistent and visible inside the container, and set
   `ARX_SECURITY_MONITOR_DIR` to it.
4. Write the notification command (reads the JSON on stdin and delivers it to a channel only
   maintainers see) and set `ARX_SECURITY_NOTIFY_CMD`. Test it by piping a sample event in.
5. Write the dispatch command (starts a local agent run with `ARX_SECURITY_BRIEF` as its
   instructions and the alert number as its input, using the container's `gh` login) and
   set `ARX_SECURITY_DISPATCH_CMD`. Confirm the agent can read an alert, open a PR and run
   `ack`.
6. Run one real check by hand with `--max-dispatch 1`. Confirm the notification arrived,
   the tracking issue text is generic, and the agent's run started. Then confirm no alert
   detail appears in the public issue, any workflow log, artifact, job summary or the PR
   it opens (a dependency diff may name the package; review that deliberately).
7. Register the operating-system scheduler to run `check` every 4 hours, with the option
   that runs a missed start as soon as the machine is back. After the first scheduled run,
   run `status` and confirm exit 0.
8. Confirm in the repository security settings that Dependabot alerts and Dependabot
   security updates are on (this change does not touch settings).

## Verification record

Acceptance of the automation itself requires a real authorized alert read, a generic
tracking item, a real local agent run, a private notification and a tested escalation, none
of which a unit test proves. The unit tests (`tools/tests/test_security_monitor.py`) cover
the decisions and the privacy rule with sentinel text; the activation steps above are the
end-to-end check.
