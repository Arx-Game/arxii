# ADR-0207: The beta-reset wipe is guarded by a hardcoded constant AND a one-way DB latch

Context: #3055 PR 2 needed the guarded management command that actually performs the
alpha→beta pristine-world wipe (ADR-0206 supplies the provenance data it filters on). A
destructive, whole-database command that must be reachable exactly once, ever, and never
again after early access ships, rules out the usual gates: a Django `Command.handle()`
guarded only by a settings flag or env var can be re-armed by anyone who can edit
`.env`/`settings.py` and redeploy, with no code review forcing a second pair of eyes on
the re-arm. The accepted design stacks two independent guards that must both pass:
`BETA_RESET_ENABLED`, a hardcoded Python literal in `world/beta_reset/services.py`
(flipping it to `False` at cutover is itself a reviewed PR, and turning it back on
afterward requires another one, by construction — not an operational toggle); and
`ReleaseLatch`, a one-way database row (write-once, no "unmark" function exists) that
still blocks the command even against a stale deploy that never got the constant flip.
Either guard alone was rejected: a constant alone is bypassed by simply not redeploying
the flip; a DB latch alone is bypassed by anyone with DB write access clearing the row.
Together, defeating the guard needs both a code change under review AND a database write
against a row nothing is designed to delete — the friction is deliberate, not an oversight
to streamline later.

> Status: accepted · Source: #3055 PR 2 · Related: ADR-0206 (acquisition provenance, the
> data this wipe filters on)
