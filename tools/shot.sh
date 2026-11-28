#!/usr/bin/env bash
# shot.sh [--as ACCOUNT] [--anon] [--viewport WxH] [--db NAME] [--spec FILE] [PATH...]
#   (just shot, #5310)
#
# Screenshots of THIS worktree's code running for real: its own server, its own
# database, its own build. Then `just shot-post <pr> <png>...` puts them on the PR.
#
#   just shot /characters/1/sheet /roster          # PNG of each path, signed in
#   just shot --anon /                             # signed out
#   just shot --spec e2e/evidence/foo-5310.spec.ts # a spec that clicks through steps
#
# What keeps it from hurting other sessions in the same container:
#   - it runs only in a worktree: the main checkout's src/.env points at the shared
#     dev database, whose content must not end up in a public screenshot;
#   - it refuses with BLOCKED: resources under 8 GiB total or 3 GiB available;
#   - it waits for the container-wide heavy-work lock ($ARX_HEAVY_LOCK, the one
#     prod_migration_check.sh takes), so only one session builds and runs a browser
#     at a time, with a 20 minute ceiling once it holds the lock;
#   - its server binds its own port block, 4100-4106 (ARX_PORT_BASE in settings.py),
#     never the 4000-4006 that `just start` and the owner's browser use, so it
#     neither waits on another checkout's server nor stops one: `arx stop` finds the
#     server through the AMP port, and ours is 4106. The lock means only one shot
#     server exists at a time; it still checks its ports are free first;
#   - it stops only the server it started, and keeps its database for next time
#     (drop it with `dropdb -h db -U arxii <name>` when the branch is done).
#
# The coordinator or PR shepherd runs this, never an implementer subagent: a build
# or a lock wait outlasts the two minutes after which a subagent's call goes to the
# background and the subagent stops without reporting (#3652).
#
# Exits: 0 shots taken; 1 usage or a failed step; 2 a page answered 4xx/5xx;
#        3 BLOCKED (resources, lock, or ports), with the reason on stderr.
set -euo pipefail

LOCK_FILE="${ARX_HEAVY_LOCK:-/tmp/claude-1000/arx-heavy.lock}"
LOCK_WAIT_SECONDS="${ARX_SHOT_LOCK_WAIT:-1800}"
MAX_SECONDS="${ARX_SHOT_MAX_SECONDS:-1200}"
readonly MIN_TOTAL_KIB=$((8 * 1024 * 1024))
readonly MIN_AVAILABLE_KIB=$((3 * 1024 * 1024))
readonly PORT_BASE="${ARX_SHOT_PORT_BASE:-4100}"
readonly SERVER_PORTS="$PORT_BASE $((PORT_BASE + 1)) $((PORT_BASE + 2)) $((PORT_BASE + 5)) $((PORT_BASE + 6))"
readonly BASE_URL="http://localhost:$((PORT_BASE + 1))"

log() { printf '[shot] %s\n' "$*" >&2; }
blocked() { printf 'BLOCKED: %s\n' "$*" >&2; exit 3; }
fail() { printf '[shot] FAILED: %s\n' "$*" >&2; exit 1; }

top="$(git rev-parse --show-toplevel)"
cd "$top"

# Checks that need no lock come first, so a refusal is immediate.
if [[ "$(git rev-parse --git-dir)" == "$(git rev-parse --git-common-dir)" || -f src/.env ]]; then
  fail "run this from a worktree under .claude/worktrees/, not the main checkout: its src/.env uses the shared dev database"
fi
total_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
(( total_kib >= MIN_TOTAL_KIB )) || blocked "resources (this machine has under 8 GiB; use the CI real-test run)"
(( available_kib >= MIN_AVAILABLE_KIB )) || blocked "resources (under 3 GiB available right now; try again later)"

if [[ -z "${SHOT_LOCKED:-}" ]]; then
  mkdir -p "$(dirname "$LOCK_FILE")"
  log "waiting for the heavy-work lock ($LOCK_FILE, up to ${LOCK_WAIT_SECONDS}s)"
  set +e
  env SHOT_LOCKED=1 flock -w "$LOCK_WAIT_SECONDS" -E 75 "$LOCK_FILE" \
    timeout "$MAX_SECONDS" bash "$top/tools/shot.sh" "$@"
  status=$?
  set -e
  (( status == 75 )) && blocked "another session held the heavy-work lock for ${LOCK_WAIT_SECONDS}s"
  (( status == 124 )) && fail "took longer than ${MAX_SECONDS}s"
  exit "$status"
fi

account="e2e_test_account"
viewport="1440x900"
db=""
spec=""
paths=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --as) account="$2"; shift 2 ;;
    --anon) account=""; shift ;;
    --viewport) viewport="$2"; shift 2 ;;
    --db) db="$2"; shift 2 ;;
    --spec) spec="$2"; shift 2 ;;
    -*) fail "unknown option $1" ;;
    *) paths+=("$1"); shift ;;
  esac
done
[[ ${#paths[@]} -gt 0 || -n "$spec" ]] || fail "give one or more URL paths, or --spec FILE"

for port in $SERVER_PORTS; do
  if ss -ltnH "sport = :$port" | grep -q .; then
    blocked "port $port is held by another process; find it with: ss -ltnp 'sport = :$port'"
  fi
done

if [[ -z "$db" ]]; then
  issue="$(git rev-parse --abbrev-ref HEAD | grep -oE -- '-[0-9]+-' | head -n 1 | tr -d -)"
  db="rt_${issue:-shot}"
fi
[[ "$db" =~ ^[a-z0-9_]+$ && "$db" != arxii* ]] || fail "database name $db is not a throwaway rt_ name"
export DATABASE_URL="postgres://arxii:arxii@db:5432/$db"
# The shared Postgres has a small /dev/shm; parallel query during a schema build
# once ran it out and put every session's database into crash recovery (#4669).
export PGOPTIONS='-c max_parallel_workers_per_gather=0'
export ARX_PORT_BASE="$PORT_BASE"
export DJANGO_PORT="$((PORT_BASE + 1))"

if ! PGPASSWORD=arxii psql -h db -U arxii -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1; then
  log "creating database $db"
  PGPASSWORD=arxii createdb -h db -U arxii "$db"
  uv run python tools/build_schema.py
  EVENNIA_SUPERUSER_USERNAME=rt_admin EVENNIA_SUPERUSER_EMAIL=rt_admin@example.com \
    EVENNIA_SUPERUSER_PASSWORD="rt-admin-$db" uv run arx manage shell -c "
from world.seeds.test_account import seed_test_account
print(seed_test_account(username='e2e_test_account', email='e2e_test@example.com', password='TestPass123!'))
"
fi

# Rebuild only when the frontend changed since the last build from this worktree.
stamp_file="src/web/static/dist/.shot-build-stamp"
fingerprint="$(
  {
    echo "ws-port $((PORT_BASE + 2))"
    git rev-parse HEAD:frontend
    git diff HEAD -- frontend ':!frontend/test-results' ':!frontend/e2e'
    git ls-files --others --exclude-standard -- frontend/src | xargs -r sha1sum
  } | sha1sum | cut -d' ' -f1
)"
# A `just fe-build` since the last shot leaves a newer index.html built for 4002.
index_file="src/web/static/dist/index.html"
if [[ ! -f "$stamp_file" || "$(cat "$stamp_file")" != "$fingerprint" \
  || "$index_file" -nt "$stamp_file" ]]; then
  [[ -d frontend/node_modules ]] || pnpm --dir frontend install --frozen-lockfile --prefer-offline
  log "building the frontend (it changed since the last shot)"
  # The page reaches the game socket on this port; postbuild also runs collectstatic.
  VITE_WS_PORT="$((PORT_BASE + 2))" pnpm --dir frontend build >&2
  echo "$fingerprint" > "$stamp_file"
else
  log "frontend unchanged since the last build; reusing it"
fi

# The browser build this worktree's Playwright expects; a no-op once it is there.
# The devcontainer firewall can refuse the download; shot.mjs then falls back to the
# newest Chromium already in the shared cache.
# A spec run has no fallback of its own, so it is handed the cached build by name.
browser_fallback=""
if ! pnpm --dir frontend exec playwright install chromium >&2; then
  log "could not download Playwright's Chromium; using the newest one already cached"
  browser_fallback="$(node frontend/scripts/cached-chromium.mjs)"
fi

started=0
# shellcheck disable=SC2317  # called by the trap below
cleanup() {
  if (( started )); then
    log "stopping the server this run started"
    uv run arx stop >&2 || true
  fi
}
trap cleanup EXIT INT TERM

log "starting this worktree's server on database $db"
started=1
uv run arx start >&2
for _ in $(seq 1 90); do
  curl -fsS -o /dev/null "$BASE_URL/api/registration/status/" && break
  sleep 2
done
curl -fsS -o /dev/null "$BASE_URL/api/registration/status/" || fail "the server did not answer on $BASE_URL"

out="$top/frontend/test-results/shots/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$out"
status=0
if [[ ${#paths[@]} -gt 0 ]]; then
  login_args=()
  [[ -n "$account" ]] && login_args=(--account "$account")
  node frontend/scripts/shot.mjs --base "$BASE_URL" --out "$out" --viewport "$viewport" \
    "${login_args[@]}" "${paths[@]}" || status=$?
fi
if [[ -n "$spec" ]]; then
  # CI=1 makes the backend config keep a screenshot of every test.
  (cd frontend && CI=1 E2E_BASE_URL="$BASE_URL" E2E_CHROMIUM_EXECUTABLE="$browser_fallback" \
    npx playwright test --config e2e.backend.config.ts "$spec" \
    --workers=1 --output "$out/spec") >&2 || status=$?
  find "$out/spec" -name '*.png' >&2 || true
fi
if (( status == 0 )); then
  log "screenshots are in $out"
  log "post them with: just shot-post <pr-or-issue> $out/*.png"
else
  log "FAILED with exit $status; whatever was saved is in $out"
fi
exit "$status"
