#!/usr/bin/env bash
set -eu
root=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/devcontainer" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$TEST_ARGS"
echo 'fake-secret-stdout'
echo 'fake-secret-stderr' >&2
exit "${TEST_EXIT:-0}"
EOF
chmod +x "$tmp/devcontainer"
export PATH="$tmp:$PATH" TEST_ARGS="$tmp/args" TMPDIR="$tmp"
bash "$root/safe-up.sh" --build-no-cache --remove-existing-container > "$tmp/out" 2>&1
grep -qx -- '--build-no-cache' "$tmp/args"
grep -qx -- '--remove-existing-container' "$tmp/args"
if grep -q 'fake-secret' "$tmp/out"; then echo 'secret leaked on success' >&2; exit 1; fi
if compgen -G "$tmp/arxii-devcontainer.*" >/dev/null; then echo 'success log retained' >&2; exit 1; fi
export TEST_EXIT=42
status=0
bash "$root/safe-up.sh" > "$tmp/out" 2>&1 || status=$?
[ "$status" -eq 42 ]
if grep -q 'fake-secret' "$tmp/out"; then echo 'secret leaked on failure' >&2; exit 1; fi
grep -q 'startup failed (exit 42)' "$tmp/out"
log=$(find "$tmp" -maxdepth 1 -name 'arxii-devcontainer.*' -type f)
[ -n "$log" ]
[ "$(stat -c %a "$log")" = 600 ]
grep -q 'fake-secret-stdout' "$log"
grep -q 'fake-secret-stderr' "$log"
echo 'safe-up tests passed'
