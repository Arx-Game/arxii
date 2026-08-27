# ADR-0238: The database is the authoring surface; the content repo is never loaded into a populated database again

**Status:** Accepted (Tehom, 2026-08-19 in-session; scope clarified 2026-08-26).
**Supersedes the authoring-direction property of
[ADR-0142](0142-content-vs-config-boundary-in-the-dev-seed.md)** - content no
longer flows repo to database. The rest of ADR-0142 (which models are content
versus config, and that arxii seeders never author catalog content) stands, as
does [ADR-0168](0168-content-models-registration-is-the-seed-boundary.md)'s
`CONTENT_MODELS` boundary.

The whole arx2-lore corpus has been loaded into the database, and the markdown
plus fixture round trip that built it is over. **Authoring and editing happen in
the database** - Django admin and the Authoring Workbench (`web/admin/authoring`) -
not through content-repo branches and PRs. The database is the single source of
truth for content, which is what makes
[ADR-0237](0237-alpha-is-durable-the-production-database-is-the-master-copy.md)'s
durability tier real rather than aspirational: there is no git copy to fall back
on, so **database backups are load-bearing** and the offsite replication in
`infra/` is the corpus's only redundancy.

**What "retired" does and does not mean.** The content repo is **not deleted, and
may still be written to** - as a drafting space, as an archive, or as the
destination of a database-to-repo export (`content_export`, content sessions),
which is unaffected by this ADR. Exactly one thing ended: **the repo is no longer a
source the database is populated from.** It is downstream now, never upstream.

Concretely, that bans running `tools/build_content_fixtures.py --load`, the admin's
"Load private content repo" action (`web/admin/game_setup_views.py`), or the content
phase of the Big Button (`world.seeds.database.seed_dev_database` calling
`load_world_content`) **against a populated database**. All three remain wired and
are deliberately kept for the clone-bootstrap and E2E paths that still need to fill
an *empty* database. Pointed at a populated one they overwrite authored work:
ADR-0201's freeze guard only protects rows whose `written_by` is set, so every
uncredited authored row - which is most of what routine editing produces - is
silently replaced by the stale repo version.

Downstream: content issues no longer go to the content repo, and the
`authoring-lore-content` skill's worktree/PR/load lifecycle is obsolete - its
`deslop` craft rules still apply in full to any prose written into the database.

**Rejected:** *Keeping the repo as a two-way sync* - ADR-0201 already rejected the
per-field dirty-marker bookkeeping that would make a merge safe, so a live round
trip could only ever guess which side moved; one authoritative side is the cheap
correct shape. *Deleting the repo or the load machinery* - the repo still has value
as a drafting and archival surface, and a fresh clone plus the E2E suites still need
to fill an empty database; the guard has to be "never point a load at a populated
database," which is a rule, not a deletion. *Leaving this ruling unrecorded* - it
had lived only in agent memory since 2026-08-19 while ADR-0142 still told every
reader the Big Button loads the real corpus from the repo, which is exactly the
belief that makes an agent treat a production database as reconstructible.

> Status: accepted · Source: Tehom in-session 2026-08-19, scope clarified 2026-08-26 ·
> Supersedes ADR-0142's authoring direction · Related: ADR-0237 (alpha durability),
> ADR-0201 (credited rows frozen against loads), ADR-0168 (the seed boundary),
> ADR-0140 (the content pipeline)
