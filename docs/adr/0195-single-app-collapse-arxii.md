# ADR-0195: All first-party apps collapse into one Django app, `arxii`

**Status:** Accepted · **Date:** 2026-08-04 · **Issue:** #2906

Every first-party app collapses into **one** Django app: the `world` package **is** the
app, registered under the label `arxii`. The 66 previously-separate `world.*` apps stop
being installed apps in their own right (their sub-package directories do not move); the
27 models that lived in `actions`, `flows`, `behaviors`, `evennia_extensions`, and
`web.admin` fold in too, each via an explicit `Meta.app_label = "arxii"`. 1088 migrations
across those apps become a single `src/world/migrations/0001_initial.py` (1026
`CreateModel` operations), with no migration history predating it.

**Why.** The cost this repo actually paid was never the file count or the app count in
the abstract - it was the **cross-app dependency graph** `makemigrations` had to resolve
on every run. Each FK that crossed an app boundary was an edge in that graph, and
Django's migration writer serializes it by walking dependencies to a fixed point: circular
references between apps force migrations to interleave (a stub field added in one app,
completed in another, once the referenced app's own table exists), and the whole graph's
project-state has to be rebuilt from scratch on every `makemigrations` invocation as the
app count and edge count grew. With one app there is no cross-app graph left to resolve -
every model emits in its final form in one pass, with no interleaving and no repeated
project-state rebuild. The single-leaf migration guard from ADR-0021 (one
`max_migration.txt` sentinel per app) also collapses from 66 independent sentinels a merge
queue could race on to one, which is strictly easier to reason about, not harder.

**Rejected: periodic squash/regeneration.** Squashing each app's migration history
back down to one file per app (rerun every few months) was rejected as **transitory, not
structural**: it resets the graph's *size* without removing the graph itself. The moment a
new cross-app FK lands - and cross-app FKs are exactly what a 66-app domain split
encourages, since a new feature routinely needs to relate to three or four existing
domains - the graph re-tangles, and the cost curve resumes climbing until the next squash.
A single app has no cross-app graph to re-tangle: there is nothing left for a future
feature to re-entangle, because there is no longer an app boundary for an FK to cross.

**Consequences.**

- **Dev databases cannot be migrated across this change.** All 1026 tables changed name
  (every `<oldapp>_<model>` table becomes `arxii_<model>`), so there is no migration path
  from a pre-collapse schema to the post-collapse one - only rebuild-and-reseed. This is a
  deliberate, ratified exception to CLAUDE.md's "preserve the dev database" rule, made
  possible only because ADR-0013 (no data migrations pre-production) already established
  that no dev database holds meaningful rows worth a migration path: deleting the
  migration history was free specifically because there was nothing to lose crossing it.
- **`app_label` no longer carries authoring-domain meaning.** Before this change, an
  app label doubled as the model's authoring domain: it grouped the Django admin index,
  named the lore repo's `fixtures/<domain>/` directory, and keyed the admin pin/exclude
  rows. With one label (`arxii`) shared by nearly every model, that signal moved to
  `core.app_domains.domain_of()`, which derives the same domain string from the model's
  *module path* instead (`world.magic.models` -> `"magic"`; `web.admin.models` ->
  `"web_admin"`) and now backs all three of those surfaces.
- **Model names must stay globally unique.** Fixtures, the admin pin/exclude toggles, and
  content export all resolve a stored `"<label>.<model>"` reference to a live model class
  via `core.app_domains.resolve_model_by_name`, which - because the label half of that
  reference is frequently stale post-collapse - resolves primarily by **name**. A name
  collision across domains is therefore a real ambiguity, not a cosmetic one:
  `resolve_model_by_name` raises `LookupError` naming every candidate rather than
  guessing, so a second model sharing a name breaks fixture loading loudly instead of
  loading the wrong row.

Narrows ADR-0013 (schema-only migrations pre-production is *why* deleting the pre-collapse
migration history cost nothing) and relates to ADR-0021 (the merge queue's single-leaf
migration guard, now guarding one sentinel instead of 66).
