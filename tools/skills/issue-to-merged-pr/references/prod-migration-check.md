# Proving a migration against production: `just prod-migration-check`

Use this for any PR that adds or edits a migration, or whose claim depends on
rows that exist in production. Do not write a one-off script: eight PRs did
(#4355, #4366, #4367, #4381, #4383, #4384, #4387, the #4389 audit) and each
carried a slightly different way of fetching, restoring and cleaning up.

```bash
just prod-migration-check                                  # forward, back to main's tip, forward
just prod-migration-check 0230 --tables creaturetemplate   # step back further, count a table
just prod-migration-check --keep                           # leave the scratch DB (prints dropdb)
```

What it does: newest dump from the backups bucket with the read-only
`dev_reader` key, restored into a fresh `scratch_pmc_<timestamp>_<pid>`
database; migrate to the branch head, back, and forward again; row counts before
and after; pending migrations; cleanup on every exit path. It refuses `arxiidev`
and every database named in `src/.env`, and runs under the shared
`arx-heavy.lock`. It takes about six minutes.

Put its report (dump name, head SHA, the Applying/Unapplying lines, counts,
`RESULT: PASS`) in the PR's Verification section or the evidence answer. It does
not replace the `migration-reviewer`. For a check on old-shape rows seeded at an
intermediate migration, run with `--keep`, seed, and drop the database when done.
