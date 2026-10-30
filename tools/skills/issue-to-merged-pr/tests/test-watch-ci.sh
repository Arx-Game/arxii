#!/usr/bin/env bash
# Stubs `gh` with a fixed statusCheckRollup and checks watch-ci.sh's verdict (#4643).
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

# A copy with a one-second hard cap, so a held-pending rollup times out quickly.
short_script="$tmp/watch-ci-short.sh"
sed "s/HARD_CAP=\$((25 \* 60))/HARD_CAP=1/" "$script" >"$short_script"
chmod +x "$short_script"

expect_held_pending() {
  local label="$1" output code
  set +e
  output=$("$short_script" 123 2>&1)
  code=$?
  set -e
  [[ "$code" -eq 6 ]] || { echo "FAIL: $label exited $code: $output"; exit 1; }
  grep -q '^TIMEOUT after 1s with checks still pending$' <<<"$output"
  echo "PASS: $label held pending through timeout (exit 6)."
}

ok='"status":"COMPLETED","conclusion":"SUCCESS"'

echo "[{\"name\":\"CodeQL\",$ok},{\"name\":\"SonarCloud\",$ok}]" >"$ROLLUP"
expect_held_pending "CodeQL+SonarCloud only"

echo "[{\"name\":\"backend\",$ok},{\"name\":\"CodeQL\",$ok}]" >"$ROLLUP"
expect_held_pending "backend without frontend"

echo "[{\"name\":\"backend\",$ok},{\"name\":\"frontend\",$ok},{\"name\":\"CodeQL\",$ok}]" >"$ROLLUP"
output=$("$script" 123)
[[ "$output" == "OK" ]]
echo 'PASS: backend+frontend+CodeQL successful rollup returned OK (exit 0).'

echo "[{\"name\":\"backend\",\"status\":\"COMPLETED\",\"conclusion\":\"FAILURE\"},{\"name\":\"frontend\",$ok}]" >"$ROLLUP"
set +e
output=$("$script" 123)
code=$?
set -e
[[ "$code" -eq 5 && "$output" == "FAIL backend" ]]
echo 'PASS: a failed backend check reported FAIL backend (exit 5).'
