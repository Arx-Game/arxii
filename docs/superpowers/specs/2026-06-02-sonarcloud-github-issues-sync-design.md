# SonarCloud → GitHub Issues Sync

**Date:** 2026-06-02
**Status:** Approved

## Purpose

Automatically surface SonarCloud findings as GitHub issues so they can be triaged and fixed incrementally, without requiring anyone to work from the SonarCloud UI. Also provides a bulk triage script to mark known false positives in SonarCloud via API so they vanish from the dashboard.

## Components

### `tools/sonarcloud_sync.py`

Queries the SonarCloud REST API for open issues on `Arx-Game_arxii` and creates corresponding GitHub issues. Idempotent — safe to re-run at any time.

**Priority tiers** (all tiers are still deduplicated; the distinction is batch limiting):
- **Security** (`VULNERABILITY`, `SECURITY_HOTSPOT`) — not batch-limited; all qualifying new findings created each run
- **Blockers** — not batch-limited; all qualifying new findings created each run
- **Highs** — batch-limited; default 50 new issues per run, configurable via `--high-limit` (0 = unlimited)

**Skip filters** — issues whose file path matches any of these are never created:
- `*/tests/*`
- `*tests.py`
- `*/test_*.py`
- `*/migrations/*`
- `src/cli/arx.py`

**Deduplication** — before creating an issue the script fetches all GitHub issues (open and closed) carrying the `sonarcloud` label and extracts embedded SonarCloud keys (`<!-- sc: <key> -->`). Any issue whose key already exists in that set is skipped. Closed issues with a `wont-fix` label are permanently excluded — they will never be recreated.

**GitHub issue format:**
- Title: `[sonarcloud:<severity>] <rule>: <truncated message> — <file>:<line>`
- Body: rule, severity, file+line, full message, link to SonarCloud finding, hidden `<!-- sc: <key> -->` marker
- Labels: `sonarcloud` on all; additionally `security` on security findings

**Authentication:** Read calls to the SonarCloud public API require no auth. GitHub writes use `GH_TOKEN` (injected by Actions as `secrets.GITHUB_TOKEN`).

---

### `tools/sonarcloud_triage.py`

Bulk-marks SonarCloud issues as `falsepositive` or `wontfix` via the SonarCloud write API (`/api/issues/do_transition`). Uses `SONAR_TOKEN` for authentication.

**Triage rules** are passed as CLI flags:
- `--rule python:S2068` — match by rule key
- `--path "*/tests/*"` — match by file path glob (repeatable)
- `--transition falsepositive` (default) or `--transition wontfix`
- `--dry-run` — print what would be marked without making API calls

The intended use is one-off bulk cleanup: e.g. mark all S2068 (hard-coded password) issues in test files as false positives so they disappear from the SonarCloud dashboard and never enter the sync feed.

---

### `.github/workflows/sonarcloud-issues.yml`

Two jobs in one workflow:

**`sync` job**
- Triggers: `schedule` (weekly, Monday 09:00 UTC) + `workflow_dispatch`
- `workflow_dispatch` input: `high_limit` (default `"50"`, `"0"` for unlimited)
- Steps: checkout → setup Python → run `sonarcloud_sync.py --high-limit <input>`
- Permissions: `issues: write`
- Secrets: `GITHUB_TOKEN` (automatic)

**`triage` job**
- Triggers: `workflow_dispatch` only
- Inputs: `rule` (rule key to target), `path_pattern` (file glob), `transition` (`falsepositive` / `wontfix`), `dry_run` (boolean, default true)
- Steps: checkout → setup Python → run `sonarcloud_triage.py` with the inputs
- Permissions: none beyond default (all writes go to SonarCloud, not GitHub)
- Secrets: `SONAR_TOKEN`

---

## Labels Required

Create these in the repo before first run (the workflow will not create them):
- `sonarcloud` — applied to all synced issues
- `wont-fix` — applied by humans to closed issues that should never be recreated
- `security` — applied to security-type findings

## Constants

Both scripts share a small `tools/sonarcloud_constants.py` with:
- `SONAR_ORG = "arx-game"`
- `SONAR_PROJECT = "Arx-Game_arxii"`
- `GH_REPO = "Arx-Game/arxii"`
- `SKIP_PATTERNS` list

## Error Handling

- SonarCloud API: retry once on 429/5xx; abort with non-zero exit on persistent failure
- GitHub API: if label creation fails (label missing), print a clear message naming the missing label and exit non-zero — do not silently skip issue creation
- Triage script: `--dry-run` defaults to `true` in the workflow input so a human must explicitly flip it to make real API calls

## What Is Not In Scope

- Coverage reports (not needed for static analysis findings)
- Medium / Low / Info severity findings (not created as issues; can be added later by adjusting the tier logic)
- Auto-closing GitHub issues when SonarCloud marks a finding resolved (a separate future concern)
