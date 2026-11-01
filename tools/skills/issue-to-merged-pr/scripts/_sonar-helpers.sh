# shellcheck shell=bash
# Shared by enqueue-pr.sh and watch-merge.sh: whether SonarCloud holds an open issue
# on a PR's new code (#4850). SonarCloud's quality gate can pass with issues open,
# and its findings fail no check, so #4841 and #4845 reached the merge queue
# carrying one each. The rule is that every one is fixed before merge; only an issue
# the maintainer has marked Accepted or False positive in SonarCloud stops counting.
#
# Reads SonarCloud's public API (the project is public: no token, nothing sent).
# SONAR_PR_JSON_FILE and SONAR_ISSUES_JSON_FILE substitute the two responses
# (tests, no network). SONAR_PROJECT_KEY overrides the project (default Arx-Game_arxii).

SONAR_API="https://sonarcloud.io/api"

_sonar_fetch() {  # _sonar_fetch <override-file> <url>
  if [[ -n "$1" ]]; then
    cat "$1"
  else
    curl -fsS --max-time 20 "$2"
  fi
}

# sonar_gate <pr-number> <head-sha>
# Prints one of, on the first line:
#   CLEAN               SonarCloud analyzed <head-sha> and has no open issue on it
#   PENDING <sha|none>  SonarCloud's newest analysis of the PR is not <head-sha> yet
#   OPEN <n>            <n> open issues, then one "  rule path:line message" line each
#   UNREADABLE          SonarCloud did not answer
sonar_gate() {
  local pr="$1" head="$2" project="${SONAR_PROJECT_KEY:-Arx-Game_arxii}"
  local pulls issues analyzed count
  pulls=$(_sonar_fetch "${SONAR_PR_JSON_FILE:-}" \
    "$SONAR_API/project_pull_requests/list?project=$project") || { echo UNREADABLE; return; }
  analyzed=$(jq -r --arg pr "$pr" \
    '[.pullRequests[]? | select(.key == $pr) | .commit.sha][0] // "none"' <<<"$pulls" \
    2>/dev/null) || { echo UNREADABLE; return; }
  if [[ "$analyzed" != "$head" ]]; then
    echo "PENDING $analyzed"
    return
  fi
  issues=$(_sonar_fetch "${SONAR_ISSUES_JSON_FILE:-}" \
    "$SONAR_API/issues/search?componentKeys=$project&pullRequest=$pr&issueStatuses=OPEN,CONFIRMED&sinceLeakPeriod=true&ps=100") \
    || { echo UNREADABLE; return; }
  count=$(jq -r '.issues | length' <<<"$issues" 2>/dev/null) || { echo UNREADABLE; return; }
  if [[ "$count" == "0" ]]; then
    echo CLEAN
    return
  fi
  echo "OPEN $count"
  jq -r --arg project "$project" '.issues[]
    | "  \(.rule) \(.component | ltrimstr($project + ":")):\(.line // "?") \(.message)"' \
    <<<"$issues"
}
