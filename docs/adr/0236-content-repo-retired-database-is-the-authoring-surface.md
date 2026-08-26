# ADR-0236: The content repo is retired; the database is the authoring surface, and a content load is never run again

**Status:** Accepted (Tehom, 2026-08-19 in-session; recorded here 2026-08-26).
**Supersedes the authoring-direction property of
[ADR-0142](0142-content-vs-config-boundary-in-the-dev-seed.md)** - content no
longer flows repo to database. The rest of ADR-0142 (which models are content
versus config, and that arxii seeders never author catalog content) stands, as
does [ADR-0168](0168-content-models-registration-is-the-seed-boundary.md)'s
`CONTENT_MODELS` boundary.

The whole arx2-lore corpus has been loaded into the database, and the markdown
plus fixture round trip that built it is over. **Authoring and editing happen in
the database from now on** - Django admin and the Authoring Workbench
(`web/admin/authoring`) - never through content-repo branches and PRs. The
database is the single source of truth for content, which is what makes
[ADR-0235](0235-alpha-is-durable-the-production-database-is-the-master-copy.md)'s
durability tier real rather than aspirational: there is no git copy to fall back
on, so **database backups are load-bearing** and the offsite replication in
`infra/` is the corpus's only redundancy.

**A content load is never run again.** That means `tools/build_content_fixtures.py
--load`, the admin's "Load private content repo" action
(`web/admin/game_setup_views.py`), and the content phase of the Big Button
(`world.seeds.database.seed_dev_database` calling `load_world_content`). All three
remain wired and are deliberately left in place for the clone-bootstrap and E2E
paths that still need to populate an empty database, but pointing any of them at a
populated production database overwrites authored work: ADR-0201's freeze guard
only protects rows whose `written_by` is set, so every uncredited authored row -
which is most of what routine editing produces - is silently replaced by the
stale repo version. The export direction (`content_export`, content sessions) is
unaffected and may still snapshot database to repo; that is archival, not
authoring.

Downstream: content issues no longer go to the content repo, and the
`authoring-lore-content` skill's worktree/PR/load lifecycle is obsolete - its
`deslop` craft rules still apply in full to any prose written into the database.

**Rejected:** *Keeping the repo as a two-way sync* - ADR-0201 already rejected the
per-field dirty-marker bookkeeping that would make a merge safe, so a live
round trip could only ever guess which side moved; one authoritative side is
the cheap correct shape. *Deleting the load machinery outright* - a fresh clone
and the E2E suites still need to fill an empty database, and removing the code
would take that with it; the guard has to be "never point it at a populated
database," which is a rule, not a deletion. *Leaving this ruling unrecorded* -
it had lived only in agent memory since 2026-08-19 while ADR-0142 still told
every reader the Big Button loads the real corpus from the repo, which is exactly
the belief that makes an agent treat a production database as reconstructible.

> Status: accepted · Source: Tehom in-session 2026-08-19 · Supersedes ADR-0142's
> authoring direction · Related: ADR-0235 (alpha durability), ADR-0201 (credited
> rows frozen against loads), ADR-0168 (the seed boundary), ADR-0140 (the content
> pipeline)
