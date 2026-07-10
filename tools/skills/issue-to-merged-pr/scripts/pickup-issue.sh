#!/usr/bin/env bash
# pickup-issue.sh <issue-number>
#
# 1. Precheck: superpowers plugin must be installed.
# 2. Fetch the issue via `gh issue view`.
# 3. Infer the issue type from labels (feature|fix|chore|refactor|test|docs|perf).
# 4. Ensure lane labels exist; claim the issue (assign self + status:spec-draft).
# 5. Build slug from the title (lowercase, alphanumerics + hyphens, max 40 chars).
# 6. Create branch <type>-<N>-<slug> from origin/main.
# 7. Emit JSON {type, slug, branch, parent_issue_url} on stdout.
#
# Exits:
#   0  success
#   1  usage / generic error
#   2  superpowers plugin missing
#   3  issue closed or assigned to a different user
set -euo pipefail

usage() {
  echo "Usage: $0 <issue-number>" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage
ISSUE="$1"
[[ "$ISSUE" =~ ^[0-9]+$ ]] || usage

# 1. Skill-availability precheck (harness-aware).
# The brainstorming + writing-plans skills must be reachable. They can come from
# EITHER source, so pass if either is present:
#   (a) the `superpowers` Claude Code plugin (Claude Code harness), OR
#   (b) the harness-agnostic ported skills under tools/skills/ (Polytoken),
#       which the sync script mirrors into .polytoken/skills/.
# This keeps the script usable under both harnesses without a flag.
SKILLS_AVAILABLE=0
if command -v claude >/dev/null 2>&1 \
  && claude plugin list 2>/dev/null | grep -q "superpowers@claude-plugins-official"; then
  SKILLS_AVAILABLE=1
fi
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ "$SKILLS_AVAILABLE" -eq 0 ]] \
  && [[ -f "$REPO_ROOT/tools/skills/brainstorming/SKILL.md" ]] \
  && [[ -f "$REPO_ROOT/tools/skills/writing-plans/SKILL.md" ]] \
  && [[ -f "$REPO_ROOT/tools/skills/using-git-worktrees/SKILL.md" ]]; then
  SKILLS_AVAILABLE=1
fi
if [[ "$SKILLS_AVAILABLE" -eq 0 ]]; then
  echo "ERROR: neither the superpowers plugin nor the ported skills are available." >&2
  echo "Install one of:" >&2
  echo "  [Claude Code] claude plugin marketplace add anthropics/claude-plugins-official" >&2
  echo "                claude plugin install superpowers@claude-plugins-official" >&2
  echo "  [Polytoken]   just sync-polytoken-skills   (mirrors tools/skills/ -> .polytoken/skills/)" >&2
  exit 2
fi

# 2. Fetch the issue
ISSUE_JSON=$(gh issue view "$ISSUE" --json number,title,labels,state,assignees,url)

STATE=$(jq -r '.state' <<<"$ISSUE_JSON")
if [[ "$STATE" != "OPEN" ]]; then
  echo "ERROR: issue #$ISSUE is $STATE, not OPEN." >&2
  exit 3
fi

CURRENT_USER=$(gh api user --jq '.login')
ASSIGNEES=$(jq -r '.assignees[].login' <<<"$ISSUE_JSON")
if [[ -n "$ASSIGNEES" ]] && ! grep -qx "$CURRENT_USER" <<<"$ASSIGNEES"; then
  echo "ERROR: issue #$ISSUE is assigned to: $ASSIGNEES (you are $CURRENT_USER)." >&2
  exit 3
fi

# 3. Infer type from labels
LABELS=$(jq -r '.labels[].name' <<<"$ISSUE_JSON")
TYPE=""
for candidate in feature fix chore refactor test tests docs perf performance tech-debt tooling; do
  if grep -qx "$candidate" <<<"$LABELS"; then
    TYPE="$candidate"
    break
  fi
done
# Normalize label aliases to canonical branch-prefix types.
if [[ "$TYPE" == "performance" ]]; then
  TYPE="perf"
fi
if [[ "$TYPE" == "tests" ]]; then
  TYPE="test"
fi
if [[ "$TYPE" == "tech-debt" || "$TYPE" == "tooling" ]]; then
  TYPE="chore"
fi
if [[ -z "$TYPE" ]]; then
  echo "WARN: issue #$ISSUE has no recognized type label; defaulting branch prefix to 'feature'." >&2
  echo "Labels found: $LABELS" >&2
  TYPE="feature"
fi

# 4. Ensure lane labels exist (idempotent) and claim the issue.
for spec in \
  "status:spec-draft|BFD4F2|Agent drafting the spec into the issue body" \
  "status:spec-review|FBCA04|Spec on the issue; awaiting org-member approval" \
  "status:implementing|1D76DB|Spec approved; implementation in progress" \
  "spec:approved|0E8A16|Org member approved the spec — clear to implement (members only)"; do
  name="${spec%%|*}"; rest="${spec#*|}"; color="${rest%%|*}"; desc="${rest##*|}"
  gh label create "$name" --color "$color" --description "$desc" --force >/dev/null 2>&1 || true
done
# Claim: assign self and move to the spec-draft lane. Strip any OTHER status:*
# lane first so the lane is idempotent — a re-pickup or a manually-labeled issue
# can already carry status:spec-review / status:implementing / status:in-progress,
# and stacking lanes confuses the project board (#2060).
gh issue edit "$ISSUE" --add-assignee "$CURRENT_USER" >/dev/null
for stale in status:spec-review status:implementing status:in-progress; do
  gh issue edit "$ISSUE" --remove-label "$stale" >/dev/null 2>&1 || true
done
gh issue edit "$ISSUE" --add-label "status:spec-draft" >/dev/null

# 5. Build slug
TITLE=$(jq -r '.title' <<<"$ISSUE_JSON")
SLUG=$(echo "$TITLE" \
  | tr '[:upper:]' '[:lower:]' \
  | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//' \
  | cut -c1-40 \
  | sed 's/-$//')
BRANCH="${TYPE}-${ISSUE}-${SLUG}"

# 6. Create branch from origin/main. Use `git branch` (not `git checkout -b`) so
# the main checkout stays on `main`: the branch is meant to be checked out into
# a worktree on the .claude/worktrees named volume by the using-git-worktrees
# skill, not worked on in place on the slow 9p bind mount.
git fetch origin main --quiet
# Idempotent: reuse the branch if a prior start-work.sh run already created it
# (re-invocation), instead of failing. Safe — the branch is still based on
# origin/main only when first created.
#
# `git branch <name> origin/main` prints "branch '<name>' set up to track
# 'origin/main'." to STDOUT — which would pollute this script's JSON contract and
# crash the caller's jq ("Invalid numeric literal at line 1, column 7"). Route
# that human notice to stderr so stdout stays JSON-only (#2060 root cause).
git show-ref --verify --quiet "refs/heads/$BRANCH" || git branch "$BRANCH" origin/main >&2

# 7. Emit JSON (includes model recommendation from complexity:* label)
URL=$(jq -r '.url' <<<"$ISSUE_JSON")
COMPLEXITY=$(jq -r '.labels[] | select(.name | startswith("complexity:")) | .name' <<<"$ISSUE_JSON" | head -1)
# Model selection is harness-dependent. Claude Code uses claude-* models; this
# repo's Polytoken config uses umans-* models. The model name for each
# complexity tier is overridable via env var so neither harness is hardcoded:
#   ISSUE_MODEL_HIGH / ISSUE_MODEL_MEDIUM / ISSUE_MODEL_LOW
# Defaults are the Claude Code tiers (backwards-compatible with the prior
# behavior). Set the env vars (e.g. in .devcontainer/dev.env) to retarget.
case "$COMPLEXITY" in
  "complexity:high")   MODEL="${ISSUE_MODEL_HIGH:-claude-opus-4-8}" ;;
  "complexity:medium") MODEL="${ISSUE_MODEL_MEDIUM:-claude-sonnet-4-6}" ;;
  "complexity:low")    MODEL="${ISSUE_MODEL_LOW:-claude-sonnet-4-6}" ;;
  *)                   MODEL="" ;;
esac
# Compact (single-line) JSON: the contract is one stdout line, so a caller can
# safely take the last line and validate it (#2060 belt-and-suspenders).
jq -nc \
  --arg type "$TYPE" \
  --arg slug "$SLUG" \
  --arg branch "$BRANCH" \
  --arg url "$URL" \
  --arg model "$MODEL" \
  --arg complexity "$COMPLEXITY" \
  '{type: $type, slug: $slug, branch: $branch, parent_issue_url: $url, model: $model, complexity: $complexity}'
