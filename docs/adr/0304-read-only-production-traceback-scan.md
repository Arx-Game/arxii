# ADR-0304: Keep a bounded read-only traceback scan as the Sentry fallback

- **Status:** Accepted
- **Date:** 2026-09-18
- **Issue:** #3746

## Context

Sentry is currently the only path that puts production exceptions in front of
a human. Its free-tier quota can be exhausted by one repeating error, at which
point new production errors are dropped. The game still writes `server.log`
and rotated copies under `/var/log/arxii`, and the gated `arxops` account can
read those files without access to application secrets or write privileges.

The first fallback should not add another daemon, database, alerting vendor, or
production write path. It should let an operator or agent answer the narrow
question "what tracebacks happened recently?" while preserving the existing
SSH gate and least-privilege account.

## Decision

Keep the log files as the fallback source and provide
`infra/scripts/scan_prod_logs.py`, exposed as `just scan-prod-logs`.

The scanner:

- defaults to the `arxii-prod` SSH alias and the last two days of `server.log*`;
- uses only fixed, read-only `find` and `tail` SSH commands;
- validates the host target and every returned filename before reading it;
- bounds files, bytes, traceback blocks, and traceback lines;
- groups Python traceback headers into separate blocks;
- applies heuristic redaction and terminal-control escaping before output; and
- supports text for a human and bounded JSON for an agent.

The result is explicitly bounded and may be incomplete because it reads tails;
absence of a traceback is not a health check. The scanner does not run arbitrary
commands, use `sudo`, inspect the database,
change service state, copy logs to a remote location, or claim that a bounded scan proves the service is healthy. It remains subject to the explicit
operator-controlled SSH gate documented in `ops-access.md`.

## Operational flow

1. Confirm the incident and open the normal ops gate for this task.
2. Run `just scan-prod-logs`. For custom bounds, run
   `python3 infra/scripts/scan_prod_logs.py --days 2 --max-matches 20` directly.
3. If an agent is consuming the result, add `--json` to the direct command and keep the output in the
   private incident session.
4. Correlate the traceback with deploy, journal, and request evidence. Do not
   put production traceback text in a public issue or PR.
5. Close the gate when the read is complete.

## Alternatives considered

- **Turn on Prometheus now:** useful for health and saturation signals, but it
  does not provide exception frames and is a separate deployment decision.
- **Ship logs to a new collector:** may improve retention and alerting, but it
  adds cost and another production service before the budget decision in #3746.
- **Give an agent a general SSH shell:** rejected. The scanner keeps the
  existing read-only account boundary and makes the remote action auditable.

## Consequences

This restores a practical error-visibility floor without deciding whether to
pay for Sentry, self-host an error collector, or deploy a metrics stack. The
result is bounded and safe for agentic inspection, but it is not durable log
shipping: it cannot recover lines already pruned by the 30-day retention rule,
and it cannot detect failures that never reached `server.log`.
