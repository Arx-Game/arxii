# Migration nuke-and-rebuild playbook

**Goal:** collapse the project's migration chain (currently 101 migrations across ~30 apps) into a single `0001_initial.py` per app, plus the small set of essential data migrations (materialized views, partitions, reference seeds, defensive dedupes). Net: ~100 → ~52 migrations (45 initials × 1 each + 7 preserved data migrations; could climb to ~55-60 if a few apps split into `0001_initial` + `0002_initial` from circular FKs). Inner-loop and CI gain back the migration-replay time as net wall-clock.

**When to execute:** during a quiet moment when **no other branches are in flight**. Right after all 4 missions follow-up PRs (#605-#608) merge and CI is green on main is exactly such a moment.

**Background:** the project previously nuked 260 → 84 on 2026-05-24 (per `feedback_reset_regenerate_squash_unsafe`). This is a follow-up nuke to bring it down further. The procedure is the same; this doc is the playbook.

---

## Pre-flight

```bash
# Verify clean state — no in-flight branches with model changes
git -C /workspaces/arxii checkout main
git -C /workspaces/arxii pull origin main
git -C /workspaces/arxii branch -a | grep -v origin/main | grep -v "^[* ]\+main$"
# Output should be EMPTY (no other branches) or stragglers we're sure don't touch models.

# Verify no uncommitted model changes
git -C /workspaces/arxii status --short
# Working tree should be clean (justfile mod is OK; nothing else).

# Snapshot baseline regression time + count for before/after comparison
just test-fast world.missions 2>&1 | grep "Ran "
# Note the time; we'll compare against post-nuke later.
```

---

## Inventory: what's about to be nuked

Run these to confirm the current state matches expectations:

```bash
# Total migrations
find /workspaces/arxii/src -path '*/migrations/0*.py' -type f | wc -l
# Should be ~101 (as of 2026-05-29). If wildly different, recon before proceeding.

# Per-app count
find /workspaces/arxii/src -path '*/migrations/0*.py' -type f \
  | sed -E 's|^.*/src/([^/]+(/[^/]+)?)/migrations/.*|\1|' \
  | sort | uniq -c | sort -rn

# Data migrations (the ones requiring careful preservation)
grep -rln "RunPython\|RunSQL" /workspaces/arxii/src/*/migrations /workspaces/arxii/src/*/*/migrations
```

**Expected data-migration inventory** (verified by reading each file body 2026-05-29):

| App | File | Type | Disposition | Notes |
|---|---|---|---|---|
| areas | `0002_create_areaclosure_view.py` | Materialized view via RunSQL | **PRESERVE** as new 0002 | Reads `areas/sql/areaclosure.sql`. Self-contained. Dep: `areas/0001_initial`. |
| codex | `0003_create_subjectbreadcrumb_view.py` | Materialized view via RunSQL | **PRESERVE** as new 0002 | Reads `codex/sql/subjectbreadcrumb.sql`. Was `0003` because codex had `0002_initial` (split init). After nuke: dep on `codex/0001_initial`. |
| combat | `0005_interaction_fk_composites.py` | Composite FK constraint via RunSQL | **PRESERVE** as new 0002 | **Cross-app dep.** Reads `combat/sql/interaction_fk_composites_*.sql`. Adds FK from combat tables to **partitioned** `scenes_interaction`. After nuke: deps `[("combat", "0001_initial"), ("scenes", "0002_partition_interaction")]` — partition MUST exist first. |
| magic | `0003_accept_soul_tether_placeholder_grants.py` | Defensive idempotent grant | **PRESERVE** as new 0002 | NOT a one-time backfill — grants `accept_soul_tether` ritual to every Path so `reconcile_ritual_knowledge()` works for new characters. Idempotent (`get_or_create`); silently skips when ritual doesn't yet exist. Safe on fresh DBs. |
| missions | `0006_missiongiver_name_unique.py` | Dedupe RunPython + `AlterField unique=True` | **FOLD INTO 0001** | The `unique=True` is already declared on the model (`name = models.CharField(max_length=200, unique=True)`). New `0001_initial` picks it up directly. The dedupe RunPython is defensive against existing duplicates — fresh DB has none. Skip. |
| missions | `0008_predicate_giver_name_to_id.py` (after PR #606 merges) | One-time JSON rewrite | **SKIP** | Walks existing `availability_rule` / `visibility_rule` / `requirements_override` JSONFields. On a fresh DB, all three fields default to `{}` — nothing to rewrite. |
| progression | `0003_social_engagement_kudos_category.py` | Reference seed via RunPython | **PRESERVE** as new 0002 | `update_or_create` for the `social_engagement` KudosSourceCategory row. The seed is required: `SceneActionRequest` accept flow looks it up at runtime. After nuke: dep `progression/0001_initial`. |
| scenes | `0003_partition_interaction.py` | Range-partitions `scenes_interaction` table | **PRESERVE** as new 0002 | Reads `scenes/sql/partition_interaction_*.sql`. Was `0003` (scenes had `0002_initial` from split init). After nuke: dep `scenes/0001_initial`. **Critical: combat FK composite migration depends on this.** |
| societies | `0002_create_legend_views.py` | 3 materialized views via RunSQL | **PRESERVE** as new 0002 | Reads `societies/sql/{character,guise,covenant}_legend_summary.sql`. The `managed=False` summary models (CharacterLegendSummary, PersonaLegendSummary, CovenantLegendSummary) end up in the new `0001_initial` as Django stubs — `makemigrations` picks them up but they don't generate DDL because `managed=False`. The view-creation SQL here is what actually populates them. |
| vitals | `0003_migrate_status_to_life_state.py` | One-time data backfill | **SKIP** | Reads legacy `status` column, writes `life_state`. The `status` column is removed by the next migration. On a fresh DB, the new `0001_initial` creates `life_state` directly with no `status` column to migrate from. Already applied on every existing dev DB. |

**Updated tally:**
- **PRESERVE as new 0002**: 7 migrations (areas, codex, combat, magic, progression, scenes, societies)
- **SKIP**: 3 migrations (missions 0006 dedupe, missions 0008 JSON rewrite, vitals 0003 backfill)
- **FOLD into new 0001**: 1 constraint (missions giver-name unique, already on the model)
- **Net result**: 27 nuked apps × 1 new initial + 18 untouched apps (already at 0001 only) + 7 preserved data migrations = **~52 total migrations** (was 100)

**Heads-up: `_initial.py` splits are the norm, not the exception.** The previous 2026-05-24 nuke produced multi-`_initial` chains for 24 of the 27 apps in this scope (`actions` and `checks` ended up with 4 each, several others with 3). This is `makemigrations` resolving circular FKs by writing the model first, then back-filling the FK in a separate `_initial`. The split count drives the actual final-migration numbering, which drives the preserved files' dependencies — see Step 5.5.

**External assets to NOT delete during cleanup**:
- `src/world/areas/sql/areaclosure.sql`
- `src/world/codex/sql/subjectbreadcrumb.sql`
- `src/world/combat/sql/interaction_fk_composites_{forward,reverse}.sql`
- `src/world/scenes/sql/partition_interaction_{forward,reverse}.sql`
- `src/world/societies/sql/{character,guise,covenant}_legend_summary.sql`

All live in `<app>/sql/` which is OUTSIDE migrations/, so the cleanup `find -path '*/migrations/0*.py' -delete` won't touch them. But sanity-check this after the cleanup step.

**Managed=False models confirmed**:
- `areas/models.py`: AreaClosure
- `codex/models.py`: SubjectBreadcrumb
- `societies/models.py`: CharacterLegendSummary, PersonaLegendSummary, CovenantLegendSummary

The new `0001_initial` per app should declare these as model stubs (no DDL). `makemigrations` does this automatically when it sees `class Meta: managed = False`.

**Tricky-pattern audit** (all clean):
- No `SeparateDatabaseAndState` migrations
- No `state_operations` / `database_operations` split migrations
- No swappable models
- **No `RenameField` operations anywhere** — across all 100 migrations. Means: every current column name matches what the new initial will declare. Fake-initial won't hit name-mismatch errors.
- **No `RenameModel` operations anywhere** — same point for class/table names.
- **No `AlterModelTable` / `AlterModelManagers`** — table names stay where they are.
- `Meta.db_table` overrides on 3 models (`AreaClosure`, `SubjectBreadcrumb`, `*LegendSummary`) — these match the materialized-view names. `makemigrations` preserves Meta.db_table in the new initial, so the table-name → model mapping survives the nuke.
- The lone `app_label` reference in `web/admin/models.py` is a `CharField` field name, not a Meta override. False alarm — no app uses an `app_label` override.

---

## Branch + execute

```bash
git -C /workspaces/arxii checkout -b chore/migration-rebuild-2026-05-29
```

### Step 1: Save the essential data migrations to a temp location

```bash
mkdir -p /tmp/migration-rebuild-keep
cp src/world/areas/migrations/0002_create_areaclosure_view.py /tmp/migration-rebuild-keep/areas_create_view.py
cp src/world/codex/migrations/0003_create_subjectbreadcrumb_view.py /tmp/migration-rebuild-keep/codex_create_view.py
cp src/world/combat/migrations/0005_interaction_fk_composites.py /tmp/migration-rebuild-keep/combat_fk_composites.py
cp src/world/magic/migrations/0003_accept_soul_tether_placeholder_grants.py /tmp/migration-rebuild-keep/magic_soul_tether_grants.py
cp src/world/progression/migrations/0003_social_engagement_kudos_category.py /tmp/migration-rebuild-keep/progression_seed.py
cp src/world/scenes/migrations/0003_partition_interaction.py /tmp/migration-rebuild-keep/scenes_partition.py
cp src/world/societies/migrations/0002_create_legend_views.py /tmp/migration-rebuild-keep/societies_create_views.py
ls /tmp/migration-rebuild-keep/
# Should list 7 files.
```

### Step 2: Clear migration-tracking rows in dev DB

The Evennia setup wizard hangs `arx manage migrate` (per memory `feedback_collectstatic_after_pnpm_build`'s sibling — same wizard hang we hit during the missions work). Use direct Django for the migration tracking ops:

**Scope: only nuke apps with 2+ migrations.** Single-migration apps are already at the target state — nuking them produces an identical file. Wastes time, adds noise to the diff. Skip them.

The 27 apps to nuke (every app from `find` that has 2+ migrations):

```python
apps_to_nuke = [
    "missions",        # 7 migrations
    "scenes",          # 6
    "combat",          # 6
    "vitals",          # 4
    "magic",           # 4
    "conditions",      # 4
    "checks",          # 4
    "actions",         # 4
    "progression",     # 3
    "codex",           # 3
    "character_sheets",# 3
    "character_creation", # 3
    "achievements",    # 3
    "societies",       # 2
    "relationships",   # 2
    "player_submissions", # 2
    "narrative",       # 2
    "mechanics",       # 2
    "locations",       # 2
    "journals",        # 2
    "items",           # 2
    "goals",           # 2
    "gm",              # 2
    "events",          # 2
    "distinctions",    # 2
    "covenants",       # 2
    "areas",           # 2
]
```

The 18 apps NOT touched (already at one `0001_initial.py` each): `traits, tarot, stories, species, skills, roster, realms, instances, game_clock, forms, fatigue, consent, classes, action_points, web_admin, flows, evennia_extensions, behaviors`.

```bash
cd /workspaces/arxii/src && uv run python <<'EOF'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.conf.settings')
django.setup()
from django.db import connection
apps_to_nuke = [
    "missions", "scenes", "combat", "vitals", "magic", "conditions", "checks",
    "actions", "progression", "codex", "character_sheets", "character_creation",
    "achievements", "societies", "relationships", "player_submissions",
    "narrative", "mechanics", "locations", "journals", "items", "goals", "gm",
    "events", "distinctions", "covenants", "areas",
]
with connection.cursor() as c:
    for app in apps_to_nuke:
        c.execute("DELETE FROM django_migrations WHERE app = %s", [app])
        print(f"cleared django_migrations for {app}")
EOF
```

Verify nothing else broke: a SELECT should now show only Django/Evennia core apps:

```bash
cd /workspaces/arxii/src && uv run python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.conf.settings')
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute('SELECT app, COUNT(*) FROM django_migrations GROUP BY app ORDER BY app')
    for row in c.fetchall(): print(row)
"
```

Expected output: only Django/Evennia core apps remain (auth, contenttypes, sessions, accounts, comms, help, objects, scripts, server, sites, socialaccount, typeclasses, web_admin). All our apps should be missing.

### Step 3: Delete migration files

**Only delete migration files for the 27 apps in `apps_to_nuke`.** Single-migration apps keep their existing `0001_initial.py` intact.

```bash
# Build the list of dirs to clean. world/* apps + actions (top-level).
NUKE_DIRS=(
    src/world/missions src/world/scenes src/world/combat src/world/vitals
    src/world/magic src/world/conditions src/world/checks src/actions
    src/world/progression src/world/codex src/world/character_sheets
    src/world/character_creation src/world/achievements src/world/societies
    src/world/relationships src/world/player_submissions src/world/narrative
    src/world/mechanics src/world/locations src/world/journals src/world/items
    src/world/goals src/world/gm src/world/events src/world/distinctions
    src/world/covenants src/world/areas
)
for d in "${NUKE_DIRS[@]}"; do
    if [ -d "$d/migrations" ]; then
        find "$d/migrations" -maxdepth 1 -type f -name '0*.py' -delete
        rm -rf "$d/migrations/__pycache__"
    fi
done

# Verify: only __init__.py should remain under nuked apps' migrations/
for d in "${NUKE_DIRS[@]}"; do
    files=$(ls "$d/migrations/" 2>/dev/null | grep -v __pycache__ | grep -v '^__init__' || true)
    if [ -n "$files" ]; then
        echo "ERROR: $d/migrations/ still has files beyond __init__.py:"
        echo "$files"
    fi
done

# Sanity-check SQL assets survive (they live under <app>/sql/, NOT migrations/)
ls src/world/areas/sql/ src/world/codex/sql/ src/world/combat/sql/ \
   src/world/scenes/sql/ src/world/societies/sql/
```

All 7 SQL files should still be present after the cleanup.

### Step 4: Regenerate initial migrations

The custom `core_management.makemigrations` (per CLAUDE.md) prevents phantom Evennia library migrations. Use it via `arx manage`:

```bash
# Generate one fresh 0001_initial.py per app. The custom command handles
# the cross-app FK dependency ordering automatically.
uv run arx manage makemigrations
```

If `makemigrations` hits the wizard hang (per the same Evennia setup quirk that bit us in this session), fall back to direct Django:

```bash
cd /workspaces/arxii/src && uv run python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.conf.settings')
django.setup()
from django.core.management import call_command
call_command('makemigrations', interactive=False, verbosity=1)
"
```

Verify each app got one `0001_initial.py`:

```bash
find /workspaces/arxii/src -path '*/migrations/0001_initial.py' -type f | wc -l
# Should match the number of apps nuked (~30)
```

### Step 5: Re-add the preserved data migrations

For each preserved file, copy it back to its app's migrations directory. The CURRENT filenames in main already reflect the post-2026-05-24-nuke world (most apps split into multiple `_initial` files, so most preserved files are numbered 0002 or 0003). Keep the existing filenames as a starting point, then verify via Step 5.5.

| Source (in `/tmp/migration-rebuild-keep/`) | Destination (CURRENT filename in main) | CURRENT `dependencies` (in source) |
|---|---|---|
| `areas_create_view.py` | `src/world/areas/migrations/0002_create_areaclosure_view.py` | `[("areas", "0001_initial")]` (areas has only 1 `_initial`) |
| `codex_create_view.py` | `src/world/codex/migrations/0003_create_subjectbreadcrumb_view.py` | `[("codex", "0002_initial")]` (codex splits to 0001+0002) |
| `combat_fk_composites.py` | `src/world/combat/migrations/0005_interaction_fk_composites.py` | `[("combat", "0004_clashconfig_…"), ("scenes", "0003_partition_interaction")]` — ⚠️ intra-app dep on a non-initial file that the nuke DELETES |
| `magic_soul_tether_grants.py` | `src/world/magic/migrations/0003_accept_soul_tether_placeholder_grants.py` | `[("magic", "0002_initial")]` (magic splits to 0001+0002) |
| `progression_seed.py` | `src/world/progression/migrations/0003_social_engagement_kudos_category.py` | `[("progression", "0002_initial")]` (progression splits to 0001+0002) |
| `scenes_partition.py` | `src/world/scenes/migrations/0003_partition_interaction.py` | `[("scenes", "0002_initial")]` (scenes splits to 0001+0002) |
| `societies_create_views.py` | `src/world/societies/migrations/0002_create_legend_views.py` | `[("societies", "0001_initial")]` (societies has only 1 `_initial`) |

**Required dep edits regardless of split-count drift:**

- **combat: the intra-app dep MUST change.** Current dep is on `0004_clashconfig_clash_min_intensity_and_more` — that's a regular AlterField migration, not an `_initial`. The nuke deletes it. New dep target: combat's LAST `_initial` post-makemigrations (currently 3 splits → `("combat", "0003_initial")`). Rename file accordingly: if combat ends with 3 initials, the preserved file should be numbered `0004_interaction_fk_composites.py`.
- **magic: add a cross-app dep to `("classes", "0001_initial")`.** The current file has only an intra-app dep. The RunPython body iterates `apps.get_model("classes", "Path").objects.all()`. Without classes' table present, the iteration is a silent no-op — works in practice (production is correct) but the explicit dep is cleaner. Optional but recommended.

**Known under-declared deps (pre-existing; out of scope for this nuke):**

- **societies/0002's SQL reads `scenes_persona` and `covenants_covenant`** but only declares intra-app deps. Works today because societies migrates last by happenstance of the dep graph. If you want to fix this, add `("scenes", "<last initial>")` and `("covenants", "<last initial>")` deps while you're in the file — but don't let scope-creep block the nuke.

### Step 5.7: Reconcile UNTOUCHED apps' deps against the new nuked-app initials

The 18 untouched apps weren't deleted, so their migration files stay on disk verbatim. But several of them have cross-app dependencies that target **specific numbered `_initial` files** in nuked apps — not just `0001_initial`. Examples from the current chain (`stories/0001_initial.py`):

```python
dependencies = [
    ("achievements", "0003_initial"),  # depends on achievements having 3 splits
    ("actions", "0004_initial"),       # depends on actions having 4 splits
    ("character_sheets", "0003_initial"),
    ("codex", "0002_initial"),
    ("conditions", "0002_initial"),
    ("covenants", "0002_initial"),
    # ...
]
```

These deps target the LAST `_initial` of each nuked app **at the time the previous nuke was performed**. If the new `makemigrations` produces a SMALLER split count for any of those nuked apps (e.g., achievements drops from 3 splits to 2 because a circular FK got resolved upstream), the dep `("achievements", "0003_initial")` references a file that no longer exists, and `migrate` fails with:

```
NodeNotFoundError: Migration stories.0001_initial dependencies reference nonexistent parent node ('achievements', '0003_initial').
```

**Run this scan post-Step-4:**

```bash
# Build the apps_to_nuke set as a bash array for grep
NUKE_APPS_RE='missions|scenes|combat|vitals|magic|conditions|checks|actions|progression|codex|character_sheets|character_creation|achievements|societies|relationships|player_submissions|narrative|mechanics|locations|journals|items|goals|gm|events|distinctions|covenants|areas'

# Grep untouched-app migrations for deps on numbered _initial files of nuked apps
for app in traits tarot stories species skills roster realms instances game_clock forms fatigue consent classes action_points flows behaviors evennia_extensions; do
    for d in /workspaces/arxii/src/world/$app/migrations /workspaces/arxii/src/$app/migrations; do
        [ -d "$d" ] || continue
        for f in "$d"/0*.py; do
            [ -f "$f" ] || continue
            # Find deps like ("achievements", "0003_initial") or ("scenes", "0002_initial")
            matches=$(grep -E "\(\"($NUKE_APPS_RE)\", \"00[0-9]+_initial\"\)" "$f" | grep -vE "0001_initial")
            if [ -n "$matches" ]; then
                echo "=== $f ==="
                echo "$matches"
            fi
        done
    done
done
# Also check the preserved migrations themselves for the same pattern
for f in /workspaces/arxii/src/web/admin/migrations/0*.py; do
    [ -f "$f" ] && grep -HE "\(\"($NUKE_APPS_RE)\", \"00[0-9]+_initial\"\)" "$f" | grep -vE "0001_initial"
done
```

For each line of output: confirm the referenced `_initial` file actually exists after Step 4's `makemigrations`. If it doesn't, edit the untouched migration to point at the new LAST `_initial` of that nuked app (whichever number that is).

**Don't try to re-run `makemigrations` to fix this — it won't help.** `makemigrations` regenerates migrations for apps whose model state has changed; untouched apps' model state hasn't changed, so their 0001_initial stays put with its stale dep. The fix is a manual edit to the dep tuple.

### Step 5.6: Update the seed-data hook allowlist if file numbers changed

`tools/check_migration_seed_data.py` has an `ALLOWED_MIGRATIONS` set that path-pins the two seed migrations by exact filename:

```python
ALLOWED_MIGRATIONS: set[str] = {
    "world/progression/migrations/0003_social_engagement_kudos_category.py",
    "world/magic/migrations/0003_accept_soul_tether_placeholder_grants.py",
}
```

If Step 5.5 caused either file to be renumbered (e.g., progression now has 3 `_initial` splits so the seed lands at 0004 instead of 0003), **edit `tools/check_migration_seed_data.py`** to match the new paths. Pre-commit will block the commit otherwise — the `check-migration-seed-data` hook reads this allowlist literally and rejects any RunPython-with-data-insertion outside it.

Verify with a dry run before the big add:

```bash
uv run python tools/check_migration_seed_data.py
# Exit code 0 + no output = allowlist matches reality.
# Any output = update the allowlist to match the actual filenames.
```

### Step 5.5: Reconcile preserved migrations against the actual initial filenames

**Don't skip this even if Step 4 looked clean.** The previous nuke (2026-05-24) saw `makemigrations` split most apps into multiple `_initial` files due to circular FKs — `actions` and `checks` ended up with 4 each, `combat`/`character_sheets`/`achievements`/etc. with 3 each. This pattern almost certainly recurs because the same model relationships exist. But the split COUNT can drift between runs if any FK shape has changed since the last nuke.

```bash
# List the actual generated initials per nuked app
for app_dir in "${NUKE_DIRS[@]}"; do
    app=$(basename "$app_dir")
    initials=$(ls "$app_dir/migrations/" 2>/dev/null | grep -E '^0[0-9]+_initial\.py$' | sort | tr '\n' ' ')
    echo "$app: $initials"
done
```

Compare against the expected pattern (today's state, for reference):
- `checks: 4 initials`, `actions: 4`
- `achievements/character_creation/character_sheets/combat/conditions: 3 each`
- `codex/covenants/distinctions/events/gm/goals/items/journals/locations/magic/mechanics/missions/narrative/player_submissions/progression/relationships/scenes: 2 each`
- `areas/societies/vitals: 1 each`

For each preserved migration:
1. Confirm the intra-app dep target file exists. If the LAST `_initial` for the app changed number (e.g., scenes went from 0002 to 0003 splits), update the dep and rename the preserved file.
2. Confirm cross-app dep targets exist. The combat → scenes cross-app dep is the canonical one: combat's preserved file points at `("scenes", "0003_partition_interaction")` — if scenes split count drifted, the partition migration's number drifts and combat's dep must follow.

Concrete edits checklist:

```
□ areas/0002_create_areaclosure_view.py — verify dep on areas/0001_initial
□ codex/0003_create_subjectbreadcrumb_view.py — verify dep on codex/<last initial>
□ combat/<N>_interaction_fk_composites.py — update intra-app dep from 0004_clashconfig_… to combat/<last initial>; verify cross-app dep on scenes/<N>_partition_interaction
□ magic/0003_accept_soul_tether_placeholder_grants.py — verify dep on magic/<last initial>; consider adding ("classes", "0001_initial")
□ progression/0003_social_engagement_kudos_category.py — verify dep on progression/<last initial>
□ scenes/<N>_partition_interaction.py — verify dep on scenes/<last initial>
□ societies/0002_create_legend_views.py — verify dep on societies/0001_initial
```

### Step 5.5: Reconcile preserved migrations against the actual initial filenames

**Don't skip this even if Step 4 looked clean.** `makemigrations` may have split one or more apps into `0001_initial.py` + `0002_initial.py` due to circular FKs (codex hit this previously). If that happens, the dep table in Step 5 is partially wrong and a preserved migration would target the wrong predecessor.

```bash
# List the actual generated initials per nuked app
for app_dir in "${NUKE_DIRS[@]}"; do
    app=$(basename "$app_dir")
    initials=$(ls "$app_dir/migrations/" 2>/dev/null | grep -E '^0[0-9]+_initial\.py$' | sort)
    echo "$app: $initials"
done
```

For each app that shows BOTH `0001_initial.py` and `0002_initial.py`:
1. Rename the preserved migration you copied in Step 5 from `0002_…` → `0003_…`
2. Update its `dependencies` to point to the LAST initial: `("<app>", "0002_initial")`
3. If any OTHER preserved migration cross-references the renamed one (combat → scenes is the canonical case), update that dep too

Concretely: if scenes generates `0001_initial.py` + `0002_initial.py`, then:
- `scenes_partition.py` → `0003_partition_interaction.py` with deps `[("scenes", "0002_initial")]`
- `combat_fk_composites.py` deps update to `[("combat", "0001_initial"), ("scenes", "0003_partition_interaction")]` (and its own filename adjusts if combat also split)

### Step 6: Apply the new chain to the dev DB

The dev DB already has the full schema from the old chain. We don't want to re-run any SQL — none of the preserved RunSQL files are idempotent (`CREATE MATERIALIZED VIEW areas_areaclosure AS …`, `ALTER TABLE scenes_interaction RENAME TO scenes_interaction_old`, etc. all fail on second run). Use `--fake` (not `--fake-initial`) to record EVERY pending migration as applied without running it:

```bash
# Use direct Django to dodge the Evennia wizard hang
cd /workspaces/arxii/src && uv run python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.conf.settings')
django.setup()
from django.core.management import call_command
call_command('migrate', fake=True, interactive=False, verbosity=1)
"
```

**Why `--fake` and not `--fake-initial`:**
- `--fake-initial` only auto-fakes migrations whose `initial = True` AND whose CreateModel-target tables already exist. It does NOT fake RunSQL/RunPython migrations.
- The preserved 0002 migrations are RunSQL/RunPython that depend on 0001. Under `--fake-initial`, Django would fake 0001 (good) then try to actually RUN 0002 (bad — the materialized view / partition / seed already exists, so SQL errors).
- `--fake` records ALL pending migrations as applied without running anything. Safe because we KNOW the schema matches (the old chain produced it).

A quick sanity-check the dev DB schema still matches the new initials (it should, since the only thing that changed was the migration files):

```bash
cd /workspaces/arxii/src && uv run python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.conf.settings')
django.setup()
from django.core.management import call_command
# --check exits non-zero if any model differs from its migrations
call_command('makemigrations', check=True, dry_run=True, verbosity=1)
"
# Expected: no output and exit 0. Any output means a model differs from the new
# initial — STOP and investigate.
```

If `--check` reports diffs, a model change snuck in OR makemigrations diverged from what's actually in the DB. STOP and investigate before pushing.

### Step 7: Full regression on a completely fresh DB

This is the gate. The whole point of the nuke is that CI / fresh-DB runs are faster, so verify against a fresh DB:

```bash
just regression 2>&1 | tail -15
```

Expect ~5-10 min faster than the pre-nuke baseline (the migration-replay phase shrinks proportionally to the migration count reduction).

If any tests fail, **STOP and investigate**. Don't proceed to push.

### Step 7.5: Pre-commit dry run

Before staging anything, run pre-commit against the working-tree changes to surface any hook complaints early. The mass diff (~70 file deletions, ~27 new initials, 7 preserved files re-added) touches `check-migration-seed-data` (covered in Step 5.6), `check-migrations` (verifies model state matches generated migrations — should pass cleanly), and `ruff`/`ruff-format` on the auto-generated initials (should pass cleanly).

```bash
pre-commit run --files \
    $(find src -path '*/migrations/0*.py' -type f) \
    tools/check_migration_seed_data.py
```

Fix any hook complaints before proceeding to Step 8. `check-type-annotations` does NOT fire on migration files (`"migrations"` is in its skip list), so preserved RunPython functions without annotations are safe.

### Step 8: Commit, push, PR

```bash
git -C /workspaces/arxii add -A
git -C /workspaces/arxii commit -m "$(cat <<'EOF'
chore(migrations): nuke and rebuild — 100 → ~52

Collapses the migration chain from ~100 across 30+ apps down to one
0001_initial.py per nuked app plus 7 preserved data migrations
(materialized views, partitions, reference seeds, defensive grants).
Net: ~48% fewer migrations to replay per fresh-DB run; CI and local
regression both benefit.

Preserved as new 0002 per affected app:
- areas: create_areaclosure_view (materialized view)
- codex: create_subjectbreadcrumb_view (materialized view)
- combat: interaction_fk_composites (composite FK constraints; cross-app
  dep on scenes' partition migration)
- magic: accept_soul_tether_placeholder_grants (defensive idempotent
  grant — keeps reconcile_ritual_knowledge() working for new chars;
  cross-app dep on classes/0001_initial since it iterates Paths)
- progression: social_engagement_kudos_category (reference seed used at
  runtime by SceneActionRequest accept flow)
- scenes: partition_interaction (range partition setup for the
  Interaction table)
- societies: create_legend_views (3 materialized views)

Skipped:
- missions 0006 dedupe RunPython (defensive against existing duplicates;
  fresh DB has none. The unique constraint itself lives on the model
  and is picked up by the new initial.)
- missions 0008 predicate_giver_name_to_id (one-time JSON rewrite;
  fresh DB's JSONFields are all {})
- vitals 0003 migrate_status_to_life_state (one-time data backfill;
  fresh DB's life_state column is created directly by the new initial,
  with no legacy status column to migrate from)

Procedure followed docs/superpowers/plans/2026-05-29-migration-rebuild-plan.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git -C /workspaces/arxii push -u origin chore/migration-rebuild-2026-05-29
gh pr create --repo Arx-Game/arxii --title "chore(migrations): nuke and rebuild — 100 → ~52" --body "$(cat <<'EOF'
## Summary

Collapses the migration chain from ~100 across 30+ apps down to one \`0001_initial.py\` per nuked app plus 7 preserved data migrations. Net ~48% fewer migrations to replay per fresh-DB run; CI and local regression both shorten.

## What's preserved as new 0002 per app

- \`areas\`: materialized-view creation
- \`codex\`: materialized-view creation
- \`combat\`: FK composite indexes
- \`progression\`: reference seed
- \`scenes\`: partition setup
- \`societies\`: materialized-view creation

## What's skipped

- One-time data backfills (\`magic\` soul tether grants, \`vitals\` life state migration, \`missions\` predicate JSON rewrite) — these were no-ops on fresh DBs once the new initial defines the canonical schema.

## What's folded into 0001

- \`missions\`: \`MissionGiver.name unique=True\` is now in the initial model rather than added via a later AlterField. The defensive dedupe RunPython from #594 is unnecessary on a fresh DB (no duplicates to dedupe).

## Post-merge: other contributors

This collapses your local migration state too. After pulling main:

1. \`git checkout main && git pull\`
2. Clear \`django_migrations\` rows for the 27 affected apps in your dev DB (one-liner in the playbook under Step 2)
3. \`arx manage migrate --fake\` to re-record EVERY new migration as applied (do NOT use \`--fake-initial\` — the preserved RunSQL data migrations are NOT initial, and the SQL is not idempotent, so they'd error on second run)
4. Drop your test database before the next run (or run \`echo "yes" | arx test\` once, which rebuilds it) — the old test DB has stale migration tracking
5. Your dev data is preserved through all of this — only migration tracking changes.

CI just sees fewer migrations to replay; no special handling needed (it always builds the test DB from scratch).

## Test plan

- [ ] \`just regression\` passes (full suite on fresh DB)
- [ ] Wall-clock noticeably shorter than baseline (~5-10 min reduction expected)
- [ ] All preserved data migrations actually apply on a fresh DB
EOF
)"
```

---

## Rollback

If something goes wrong post-execution:

```bash
git -C /workspaces/arxii reset --hard origin/main
```

If you've already merged and need to undo on others' dev DBs: the safest path is `arx manage migrate <app> zero --fake` then re-apply, but realistically a clean clone is faster. The nuke doesn't touch dev data, only the migration tracking table.

## Things that could go wrong (anticipated)

| Symptom | Likely cause | Fix |
|---|---|---|
| `makemigrations` emits phantom migrations for Evennia core apps | Custom `core_management.makemigrations` isn't being used (some shim bypassed it) | Use `uv run arx manage makemigrations` explicitly — the wrapper applies the custom command. If wizard hangs, fall back to `python -c "...call_command('makemigrations', interactive=False)"` |
| `migrate` says "no migrations to apply" but the DB schema is missing tables | The fake-initial path didn't run because the schema diverged from `0001_initial` | Check if a model change snuck in. Worst case: nuke dev DB and re-apply from scratch |
| `makemigrations` splits an app into `0001_initial.py` + `0002_initial.py` | Circular FK between two nuked apps — Django breaks the cycle by declaring the model with no FK first, then adding FK in 0002 | This is fine and expected for some apps (codex already had this shape). It's still ~half the migration count of the old chain |
| `interaction_fk_composites` migration fails: indexed columns don't exist | The new combat `0001_initial` is missing fields the preserved migration referenced | The preserved file's dependencies need to also include the apps whose tables the indexes touch — see the dep table in Step 5 |
| `accept_soul_tether_placeholder_grants` migration: `Path matching query does not exist` | The `classes/0001_initial` hasn't run yet | The preserved file's dependencies must include `("classes", "0001_initial")` — see Step 5 dep table |
| Materialized view migration fails on SQLite: `CREATE MATERIALIZED VIEW` is PG-only | Running on the SQLite test tier | The materialized-view-creating apps (areas/codex/societies) should be in the PG-only set (CLAUDE.md "Running Tests" section). The SQLite tier already skips them via `@tag("postgres")` decorators or carve-outs. The PG parity tier is the real gate. |
| A test imports from `<app>.migrations.<old_file>` directly | Rare but happens — sometimes tests reach into migration internals | grep for `from .*\.migrations\.` and `import.*\.migrations\.`; fix the imports OR inline the function being borrowed |
| Pre-commit's `check-migration-seed-data` hook fires on a preserved migration | The hook reads a path-pinned `ALLOWED_MIGRATIONS` set; if the preserved seed file got renumbered (e.g., progression's split count drift moves `0003_social_engagement_kudos_category.py` to `0004_…`), the hook no longer recognizes it | Update `tools/check_migration_seed_data.py`'s `ALLOWED_MIGRATIONS` set to match the new filenames. Step 5.6 covers this — run the hook explicitly before the big `git add`. |
| Other contributor (TehomCD) tries to pull main and migrate, hits "table already exists" | His dev DB has the old migration chain applied; new chain's 0001 thinks it needs to create tables that exist | He follows the post-merge instructions: clear `django_migrations` for the 27 nuked apps + `migrate --fake` (NOT `--fake-initial` — see Step 6 for why). Documented in the PR description. |
| Step 6 fails with `psycopg.errors.DuplicateObject: relation "areas_areaclosure" already exists` | The `migrate` call ran without `fake=True`, so Django tried to RE-EXECUTE the preserved RunSQL migrations against a dev DB that already has those objects | Re-read Step 6 — `call_command('migrate', fake=True, …)` is mandatory. None of the preserved SQL files are idempotent. |
| Preserved migration deps target an `_initial` filename that doesn't exist post-makemigrations | App's split count drifted from the previous nuke (e.g., scenes used to split into 2, now 3) | Step 5.5's inspection loop catches this. The preserved files' filenames AND deps all need to advance to match the new last `_initial`. Don't forget cross-app refs (combat → scenes). |
| `migrate` fails on `combat/<N>_interaction_fk_composites`: `Migration … depends on non-existent migration combat.0004_clashconfig_clash_min_intensity_and_more` | The intra-app dep is a non-initial file that the nuke deleted; the preserved file was never re-pointed | Required edit in Step 5: change combat's preserved-file intra-app dep from `0004_clashconfig_…` to combat's last `_initial`. Listed explicitly in Step 5's "Required dep edits" callout. |
| `societies/<N>_create_legend_views` tries to read `scenes_persona` or `covenants_covenant` but the table doesn't exist yet | Pre-existing under-declared deps; works on the current main only because the dep graph happens to schedule societies last | Optional: add `("scenes", "<last initial>")` and `("covenants", "<last initial>")` to societies' preserved file. Not strictly required for the nuke to succeed (production has been running this way), but cleaner. |
| `NodeNotFoundError: Migration stories.0001_initial dependencies reference nonexistent parent node ('achievements', '0003_initial')` | An untouched app deps on a specific numbered `_initial` of a nuked app, and that nuked app's split count decreased post-makemigrations so the referenced file no longer exists | Step 5.7 catches this. Edit the untouched migration's dep tuple to point at the nuked app's NEW last `_initial`. Don't try to re-run `makemigrations` — untouched apps' model state didn't change, so it won't regenerate them. |

## Estimated time

- Pre-flight + inventory: 5 min
- Steps 1-5 (the actual nuke): 15-20 min
- Step 6 (migrate apply): 1-2 min
- Step 7 (regression verification): wall-clock of the new regression run (target: ~15-20 min, down from ~26)
- Steps 8 (commit, push, PR): 5 min
- **Total: ~45-60 min of active work**, plus the regression wall-clock.

## After it lands

- Future regression / CI is faster, permanently.
- New contributors get a clean migration chain — easier to onboard.
- Roughly every 6-12 months as the chain re-grows past 100, repeat. Add to a "tooling-debt watchlist" in CLAUDE.md or similar.
