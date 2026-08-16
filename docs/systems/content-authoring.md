# Content Authoring Workflow (operator guide)

How staff load the game's authored content into a database, find what still
needs writing, edit and credit it, and save it back to the private content
repo. This is the operator walkthrough; the implementation detail lives in
`src/web/admin/CLAUDE.md` and the per-part specs on issues #3017-#3020.

The mental model: **the database is your working copy, the content repo is
the durable source of truth, and credit stamps are the lock between them.**

## One-time setup

The private lore repo is a two-game monorepo: one repo, two top-level game
directories. The Arx II corpus lives in the `arx2/` subdirectory
(`arx2/fixtures/`, `arx2/content/`, plus the domain directories such as
`arx2/items/`, `arx2/skills/`). `CONTENT_REPO_PATH` must point at `arx2/`,
not at the repo checkout root — the checkout root has no `fixtures/` or
domain directories of its own, so every content lookup at that level
silently finds nothing.

1. Clone the private content repo somewhere on the machine.
2. In `src/.env`, set `CONTENT_REPO_PATH` to the `arx2/` subdirectory of
   that checkout (not the checkout root). Every surface below resolves the
   path through the same helper
   (`core_management.content_repo.resolve_content_root()`); if it is unset,
   loading/export surfaces hide themselves and show a setup hint instead of
   erroring. A path with neither known domain directories nor a `fixtures/`
   directory (for example, the checkout root by mistake) now raises a clear
   error naming the path instead of silently loading zero rows.
3. If this machine will open session pull requests (see below), make a
   GitHub token available: `GITHUB_ISSUE_TOKEN` in settings, or the
   `GH_TOKEN` env var. Local commits work without it; only the open-PR
   action needs it. The target repo is parsed from the checkout's own
   `origin` remote, so the content repo is never named in this codebase.
4. Optional, for reference search: place the Arx I dump as a sibling
   `arx1/` directory next to the content root.

First time in the Authoring Workbench, it will ask you to link your account
to a contributor identity (pick an existing unlinked one or type a name).
Credit stamps come from that link.

## Prod

The checkout is provisioned **on demand, not automatically on every
deploy**. `standup.yml`'s `content_repo` role is dormant by default (it
carries `site.yml`'s special `never` tag); to actually clone/refresh the
private lore repo onto the box, trigger `standup.yml` (Actions → "Stand up
infra" → Run workflow) with the **"Also refresh the private lore-repo
checkout"** `workflow_dispatch` input checked — this appends
`--tags all,content_repo` to the converge, running the ordinary deploy as
usual plus this role. `CONTENT_REPO_PATH` is always set for the app process
(a fixed path, pointing at the `arx2/` subdirectory of the checkout, not the
checkout root — see `infra/ansible/roles/content_repo/defaults/main.yml`);
the checkout itself only exists after the on-demand refresh has been run at
least once. Expect to use this once during alpha bootstrap and
maybe again after a full alpha rebuild — not as part of routine ongoing
operation. See `infra/README.md`'s "Content-repo checkout credential"
section for the one-time credential setup.

**Loading content into the database stays a manual step** (unchanged from
local dev): Admin → Game Setup → **Load private content repo**, same
credited-row-freeze protections apply. Nothing loads automatically on
deploy — see #2236 Phase 4 for why (protects in-progress prod-admin edits
from being silently clobbered by an unattended load).

Uncommitted export output sitting in the prod checkout (from prod-admin
content authoring) blocks the next content-repo refresh until it's
committed or cleaned up — the `content_repo` role's clone/pull task refuses
to run over local modifications, and its failure message names this as the
first likely cause.

## Loading content into a database

Admin header, then **Game Setup**, then **Load private content repo**. The
load is an upsert by natural key: existing rows update, missing rows are
created, and rows the corpus does not know are left alone.

One deliberate exception (#3017): a **credited row is frozen against
loads**. If a row has `written_by` set and any of its values differ from
what the corpus says, the load leaves the whole row untouched and it
appears on the **Load conflicts** page instead. Resolving a conflict is
one row at a time: read the field-by-field diff, then type the row's own
natural key back to confirm replacing the database version with the corpus
version. There is no bulk resolve on purpose; clearing a human's credited
edit is always a deliberate, single-row act.

## Finding what needs writing

Two doors into the same backlog:

- **The Authoring Workbench** (header link, superuser) is the writer's
  door: one worst-first queue across every credited model - placeholder
  text first, then unwritten, then unreviewed - with per-domain stats and
  domain/status/text filters. You never need to know which model a piece
  of prose lives in.
- **The stock changelists** (#3020) are the browser's door: every
  registered credited model's changelist carries a **credit status**
  column and filter (`?credit=unwritten|written|reviewed`). When you are
  already in a model doing mechanical work, flip the filter to "Unwritten"
  and the prose debt is right there. The status cell links into the
  workbench editor for that row, and every change form has an **Open in
  Authoring Workbench** button. Credit fields are editable on every
  credited admin; a system check (`web_admin.E001`) fails any admin whose
  explicit fieldsets would hide them.

## Editing, crediting, reviewing

The workbench editor shows only the row's prose fields as textareas;
mechanical fields cannot be submitted through it at all. Actions:

- **Save** writes the prose.
- **Save and credit me** additionally stamps `written_by`/`written_on`
  from your linked contributor. From that moment the row is frozen against
  loads (above) until the corpus catches up.
- **Mark reviewed** stamps `reviewed_by`/`reviewed_on` and never touches
  prose or authorship; writing and reviewing are separate acts.

There is no stored status enum anywhere: unwritten / written / reviewed is
always derived from those two links, so it can never drift.

For mechanical edits, use the ordinary change form; the deep links run in
both directions.

## Saving back to the content repo

From a change form's **Export to content repo** button (or the workbench's
export handoff after crediting): the row's corpus form is written into the
content checkout, you review the resulting diff, and confirming commits it
onto the shared session branch (`content-export-session`). A row whose
natural key is not in the corpus yet additionally requires the explicit
new-row checkbox (the row-scoped form of the addition gate, ADR-0191).
Only one row export can be pending confirmation at a time; git state, not
a table, is the bookkeeping.

Rows accumulate as small commits across a writing session. When you are
done, the **Content session** page shows the branch's commits and its full
diff against main, and one click pushes and opens (or reuses) the pull
request for the whole batch. Merge that PR in the content repo and the
loop closes: the corpus now matches the database, so the freeze on those
rows dissolves naturally - the next load finds no difference.

A few builder-domain models (ItemTemplate, NPCRole, BuildingKind,
DecorationKind) carry credit but are database-only; the editor says so in
place of the export handoff, and that is expected.

## Bulk export and push

Game Setup also carries the corpus-wide **Export to content repo** and
**Push content to lore repo** buttons (all flat fixtures plus grid
bundles, then commit and push, with the same addition gate as a checkbox).
That is the maintainer bulk path; the expected day-to-day rhythm is the
row-level one: load once, write all session, export as you credit, one PR
per session.

## Reference search while writing

The workbench's reference panel searches the content database's prose by
default. Two file corpora are opt-in per search: the staff docs inside the
content repo (`design/`, `world_bibles/`) and the Arx I dump (`arx1/`
sibling directory). Missing roots are silently omitted, so database search
works with no content repo configured at all.

## Where the deeper detail lives

- `src/web/admin/CLAUDE.md` - the full admin-surface reference (load
  conflicts, row export, session branch, workbench, stock-admin
  complement).
- ADR-0191 (export addition gate), ADR-0201 (credited-row load freeze),
  ADR-0142 (content vs config in the dev seed).
- Issues #3017-#3020 - the approved specs for each part of this program.
