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

printf '%s\n' '[{"name":"backend","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"CodeQL","status":"COMPLETED","conclusion":"SUCCESS"}]' >"$ROLLUP"
output=$("$script" 123)
[[ "$output" == "OK" ]]
