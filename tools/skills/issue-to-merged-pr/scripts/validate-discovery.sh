#!/usr/bin/env bash
# Validate the auditable discovery state before a workflow phase transition.
# Usage: validate-discovery.sh <issue-number> [--body-file PATH] [--labels CSV] [--allow-approved-legacy]
set -euo pipefail

usage() {
  echo "Usage: $0 <issue-number> [--body-file PATH] [--labels CSV]" >&2
  exit 2
}

issue=""
body_file=""
labels=""
allow_legacy=0
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LEGACY_ALLOWLIST="$SCRIPT_DIR/../references/legacy-approved-issues.txt"
while (($#)); do
  case "$1" in
    --body-file)
      (($# >= 2)) || usage
      body_file="$2"
      shift 2
      ;;
    --labels)
      (($# >= 2)) || usage
      labels="$2"
      shift 2
      ;;
    --allow-approved-legacy)
      allow_legacy=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    -*)
      usage
      ;;
    *)
      [[ -z "$issue" ]] || usage
      issue="$1"
      shift
      ;;
  esac
done

[[ -n "$issue" ]] || usage

if [[ -n "$body_file" ]]; then
  [[ -f "$body_file" ]] || { echo "discovery: body file not found: $body_file" >&2; exit 1; }
  [[ -n "$labels" ]] || { echo "discovery: --labels is required with --body-file for phase validation" >&2; exit 1; }
  body=$(cat "$body_file")
elif [[ -z "$labels" ]]; then
  payload=$(gh issue view "$issue" --json body,labels)
  body=$(jq -r '.body // ""' <<<"$payload")
  labels=$(jq -r '[.labels[].name] | join(",")' <<<"$payload")
else
  body=$(gh issue view "$issue" --json body --jq '.body // ""')
fi

has_label() {
  local wanted=",$1,"
  [[ ",$labels," == *"$wanted"* ]]
}

is_allowlisted_legacy_issue() {
  [[ -f "$LEGACY_ALLOWLIST" ]] && grep -Eq "^${issue}[[:space:]]*\|" "$LEGACY_ALLOWLIST"
}

# The actual marker must be before spec:start. Examples inside the spec do not
# count, because spec rewrites must not be able to change workflow state.
prefix=$(awk '/<!-- spec:start -->/{exit} {print}' <<<"$body")
markers=$(grep -Eo '<!-- discovery:lane=(lightweight|standard|heavyweight);state=(complete|awaiting-stakeholder) -->' <<<"$prefix" || true)
marker_count=$(grep -c . <<<"$markers" || true)
if [[ "$marker_count" -ne 1 ]]; then
  if [[ "$allow_legacy" == "1" && "$marker_count" == "0" ]] && has_label status:implementing && has_label spec:approved; then
    if is_allowlisted_legacy_issue; then
      printf 'discovery: legacy-approved issue=%s (marker migration pending)\n' "$issue"
      exit 0
    fi
    echo "discovery: issue $issue is not in the temporary legacy compatibility allowlist" >&2
    exit 1
  fi
  echo "discovery: expected exactly one state marker before spec:start" >&2
  exit 1
fi
marker="$markers"

if [[ "$marker" =~ lane=([^;]+)\;state=([^[:space:]]+) ]]; then
  lane="${BASH_REMATCH[1]}"
  state="${BASH_REMATCH[2]}"
else
  echo "discovery: invalid state marker" >&2
  exit 1
fi

assessment=$(sed -n '/^## Discovery assessment[[:space:]]*$/,$p' <<<"$prefix")
if [[ -z "$assessment" ]]; then
  echo "discovery: missing '## Discovery assessment' section before spec:start" >&2
  exit 1
fi

require_field() {
  local field="$1" line value
  line=$(grep -Eim1 "^[[:space:]*-]*[[:space:]]*${field}[[:space:]]*:" <<<"$assessment" || true)
  if [[ -z "$line" ]]; then
    echo "discovery: missing required field: $field" >&2
    exit 1
  fi
  value="${line#*:}"
  value=$(sed -E 's/^[[:space:]]+|[[:space:]]+$//g' <<<"$value")
  if [[ -z "$value" || "$value" == '<'*'>' || "$value" == "TBD" || "$value" == "TODO" ]]; then
    echo "discovery: field is empty or a placeholder: $field" >&2
    exit 1
  fi
}

required_fields=("Outcome" "Success signal" "Stakeholder provenance" "Impact" "Lane rationale")
for field in "${required_fields[@]}"; do
  require_field "$field"
done

if has_label status:implementing && ! has_label spec:approved; then
  if [[ "$lane" != lightweight || "$state" != complete ]]; then
    echo "discovery: status:implementing requires a complete lightweight marker or spec:approved" >&2
    exit 1
  fi
fi

printf 'discovery: valid lane=%s state=%s issue=%s\n' "$lane" "$state" "$issue"
