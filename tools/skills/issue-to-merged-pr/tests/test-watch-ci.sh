#!/usr/bin/env bash
set -euo pipefail
script="$(cd "$(dirname "$0")/.." && pwd)/scripts/watch-ci.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/gh" <<'GH'
#!/usr/bin/env bash
cat "$ROLLUP"
GH
chmod +x "$tmp/gh"
export PATH="$tmp:$PATH"
export ROLLUP="$tmp/rollup.json"

printf '%s\n' '[{"name":"CodeQL","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"SonarCloud","status":"COMPLETED","conclusion":"SUCCESS"}]' >"$ROLLUP"
output=$(timeout 1 "$script" 123 2>&1 || true)
if grep -q '^OK$' <<<"$output"; then
  echo 'partial rollup was accepted' >&2
  exit 1
fi
echo 'PASS: current script did not report OK for CodeQL+SonarCloud; initial state was pending.'

printf '%s\n' '[{"name":"backend","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"CodeQL","status":"COMPLETED","conclusion":"SUCCESS"}]' >"$ROLLUP"
output=$("$script" 123)
[[ "$output" == "OK" ]]
echo 'PASS: backend+CodeQL successful rollup returned OK (exit 0).'
# Prove the pre-fix script accepts the same partial rollup (the original bug).
old_script="$tmp/watch-ci-old.sh"
git show HEAD^:tools/skills/issue-to-merged-pr/scripts/watch-ci.sh >"$old_script"
chmod +x "$old_script"
output=$("$old_script" 123)
[[ "$output" == "OK" ]]

# Exercise the hard-cap path quickly while still asserting timeout + exit 6.
printf '%s\n' '[{"name":"CodeQL","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"SonarCloud","status":"COMPLETED","conclusion":"SUCCESS"}]' >"$ROLLUP"
short_script="$tmp/watch-ci-short.sh"
sed "s/HARD_CAP=\$((25 \* 60))/HARD_CAP=1/" "$script" >"$short_script"
chmod +x "$short_script"
set +e
output=$("$short_script" 123 2>&1)
code=$?
set -e
[[ "$code" -eq 6 ]]
grep -q '^TIMEOUT after 1s with checks still pending$' <<<"$output"
echo 'PASS: missing backend hit shortened hard cap (exit 6): TIMEOUT after 1s with checks still pending'
