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
export PATH="$tmp:$PATH" TEST_ARGS="$tmp/args"
bash "$root/safe-up.sh" --build-no-cache > "$tmp/out" 2>&1
grep -qx -- '--build-no-cache' "$tmp/args"
! grep -q 'fake-secret' "$tmp/out"
export TEST_EXIT=42
status=0
bash "$root/safe-up.sh" > "$tmp/out" 2>&1 || status=$?
[ "$status" -eq 42 ]
! grep -q 'fake-secret' "$tmp/out"
grep -q 'startup failed (exit 42)' "$tmp/out"
echo 'safe-up tests passed'
