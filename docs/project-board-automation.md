# Project board automation

The org Project (**#1 "Arx II"**) mirrors our real issue lifecycle automatically.
Nobody hand-moves cards: GitHub events plus our existing `status:*` / `spec:*`
labels drive the board.

## The lifecycle

The board has two single-select fields:

**Status** — the lifecycle column (event-driven):

| Status | When |
|---|---|
| **Backlog** | Open, unassigned — not started. (Native auto-add lands new issues here.) |
| **In progress** | Someone is assigned. Stays here through spec + implementation until terminal. |
| **Done** | Issue closed as *completed*. |
| **Cancelled** | Issue closed as *not planned*. |

**Stage** — a swimlane field refining *In progress* (label-driven):

| Stage | Driven by label |
|---|---|
| **Spec design** | `status:spec-draft` |
| **Spec review** | `status:spec-review` |
| **Implementation** | `status:implementing` or `spec:approved` |
| **In review** | a linked PR is open (set by the PR event, not a label) |

`status:in-progress` is the "claimed" marker (added on assignment); it is
distinct from `status:implementing` (the implementation stage). Both are kept.

## Automation map

Driven by `.github/workflows/project-sync.yml` → `tools/project_board_sync.py`:

| Trigger | Effect |
|---|---|
| issue opened | ensured on board, Status = Backlog (belt-and-suspenders behind native auto-add) |
| issue **assigned** | Status = In progress; add `status:in-progress` |
| issue **unassigned** (→ 0 assignees) | Status = Backlog; remove `status:in-progress` |
| label `status:spec-draft` | Stage = Spec design |
| label `status:spec-review` | Stage = Spec review |
| label `status:implementing` / `spec:approved` | Stage = Implementation |
| linked PR **opened** (`Closes #N`) | issue Stage = In review |
| linked PR **closed** unmerged | issue Stage reverts to its label-derived stage |
| issue **closed** (completed) | Status = Done |
| issue **closed** (not planned) | Status = Cancelled |

Stage is recomputed from the full label set on every issue event (self-healing),
**except** it never downgrades an "In review" stage — only the PR closing does.

Writes are idempotent (a field/label changes only when it differs), so the
PAT-triggered re-runs our own writes cause are harmless no-ops that terminate.

## One-time setup (manual — only a maintainer can do these)

1. **`PROJECT_PAT` Actions secret.** The default `GITHUB_TOKEN` can't write
   org-level Projects v2, so the workflow needs a PAT.
   *Arx-Game/arxii → Settings → Secrets and variables → Actions → New repository
   secret*, name `PROJECT_PAT`. The PAT needs:
   - fine-grained: **Org → Projects: Read and write**, **Repo → Issues: Read and
     write** (Metadata: Read is automatic); or
   - classic: scopes `repo` + `project`.

   Until this exists the workflow runs but exits 0 (green, no-op).

2. **Add the `Cancelled` Status option** in the Project UI (*Project → ⋯ →
   Settings → Status field → + Add option → `Cancelled`*). This must be done in
   the UI: the GraphQL API regenerates **all** option IDs when options change,
   which would clear Status on every in-flight card. Until `Cancelled` exists,
   closing an issue as *not planned* logs a warning and leaves Status unchanged
   (no data loss).

3. **Native auto-add** (already on) keeps adding new issues to Backlog. Leave the
   native "*Item closed → Done*" workflow **off** — close handling lives in the
   Action so it can distinguish Done from Cancelled.

4. **Swimlanes:** in the board view, set *Group by → Stage* to see Spec
   review / Implementation / In review as horizontal lanes within In progress.

## Backfill the existing backlog

To reconcile issues that predate the automation (everything currently stuck in
Backlog), run the idempotent sweep once locally:

```bash
GH_TOKEN=<maintainer-pat> tools/backfill_project_board.sh
```

It adds every open issue to the board and sets Status (from assignment) + Stage
(from labels). Safe to re-run.

## Testing locally

The script reads the same env an Actions runner provides. Simulate an event with
a small JSON file:

```bash
cat > /tmp/evt.json <<'JSON'
{ "action": "assigned",
  "issue": { "number": 690, "node_id": "<issue node id>", "state": "open",
             "assignees": [{"login": "you"}], "labels": [] } }
JSON

GITHUB_REPOSITORY=Arx-Game/arxii GITHUB_EVENT_NAME=issues \
  GITHUB_EVENT_PATH=/tmp/evt.json GH_TOKEN=<pat> \
  python3 tools/project_board_sync.py
```

Get an issue's `node_id` with:
`gh api graphql -f query='{repository(owner:"Arx-Game",name:"arxii"){issue(number:690){id}}}'`

## Troubleshooting

- **Everything stays in Backlog** → `PROJECT_PAT` is missing or lacks Projects
  R/W. Check the workflow run log for the "skipping board sync" line.
- **`Cancelled` cards land in Done / nowhere** → add the `Cancelled` option (setup
  step 2).
- **A card's Stage looks stale** → re-run the backfill, or re-apply the label.
- **Workflow red X** → the PAT is set but a GraphQL call failed (often a scope
  gap). The failing call + response body is in the run log.
