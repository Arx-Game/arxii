#!/usr/bin/env bash
# Validate the auditable discovery state before a workflow phase transition.
# Usage: validate-discovery.sh <issue-number> [--body-file PATH] [--labels CSV]
#        [--parent-labels CSV --parent-state open|closed] [--allow-approved-legacy]
# --parent-labels/--parent-state inject the parent issue's state (tests; no network).
set -euo pipefail

usage() {
  echo "Usage: $0 <issue-number> [--body-file PATH] [--labels CSV] [--parent-labels CSV --parent-state open|closed]" >&2
  exit 2
}

issue=""
body_file=""
labels=""
allow_legacy=0
parent_labels=""
parent_state=""
parent_injected=0
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
    --parent-labels)
      (($# >= 2)) || usage
      parent_labels="$2"
      parent_injected=1
      shift 2
      ;;
    --parent-state)
      (($# >= 2)) || usage
      parent_state="$2"
      parent_injected=1
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

# A slice of an approved spec declares its parent with one `Slice N of #M` line
# before spec:start (trailing prose on that line is fine). More than one such line is ambiguous, so it fails closed.
parent_lines=$(grep -E '^[[:space:]]*Slice [0-9]+ of #[0-9]+([^0-9].*)?$' <<<"$prefix" || true)
parent_count=$(grep -c . <<<"$parent_lines" || true)
if [[ "$parent_count" -gt 1 ]]; then
  echo "discovery: more than one 'Slice N of #M' parent line before spec:start" >&2
  exit 1
fi

if has_label status:implementing && ! has_label spec:approved; then
  if [[ "$lane" == lightweight && "$state" == complete ]]; then
    :
  elif [[ "$parent_count" -eq 1 ]]; then
    parent=$(grep -Eo '#[0-9]+' <<<"$parent_lines" | head -n1)
    parent="${parent#\#}"
    if [[ "$parent" == "$issue" ]]; then
      echo "discovery: issue $issue names itself as its parent" >&2
      exit 1
    fi
    if [[ "$state" != complete ]]; then
      echo "discovery: a slice needs state=complete in its marker before implementing" >&2
      exit 1
    fi
    if [[ "$parent_injected" == "0" ]]; then
      if ! parent_payload=$(gh api "repos/{owner}/{repo}/issues/$parent" 2>/dev/null); then
        echo "discovery: could not fetch parent issue #$parent" >&2
        exit 1
      fi
      parent_state=$(jq -r '.state // ""' <<<"$parent_payload" 2>/dev/null) || parent_state=""
      parent_labels=$(jq -r '[.labels[].name] | join(",")' <<<"$parent_payload" 2>/dev/null) || parent_labels=""
    fi
    if [[ "$parent_state" != open ]]; then
      echo "discovery: parent issue #$parent is not open (state: ${parent_state:-unknown})" >&2
      exit 1
    fi
    if [[ ",$parent_labels," != *",spec:approved,"* ]]; then
      echo "discovery: parent issue #$parent does not carry spec:approved" >&2
      exit 1
    fi
    printf 'discovery: valid lane=%s state=%s issue=%s parent=#%s\n' "$lane" "$state" "$issue" "$parent"
    exit 0
  else
    echo "discovery: status:implementing requires a complete lightweight marker, spec:approved, or an approved parent ('Slice N of #M')" >&2
    exit 1
  fi
fi

printf 'discovery: valid lane=%s state=%s issue=%s\n' "$lane" "$state" "$issue"
