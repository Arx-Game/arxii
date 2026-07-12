#!/usr/bin/env bash
#
# acceptance.sh — STATIC CONTRACT CHECKS for the IaC ("the tests"; tofu/
# ansible can't run locally on Windows, CI is the dynamic gate). Greps the
# repo for the plan's safety invariants AND (see the #2236 section below)
# cross-file contracts that a single-file grep can't see. Exit 1 on ANY
# violation. Account-independent: no creds, no cloud, no apply.
#
# HONEST SCOPE (per the #2236 audit): a PASS here means the checked
# invariants hold in the source text right now — it is NOT a deploy-
# readiness proof. It cannot catch a real `tofu apply`/`ansible-playbook`
# failure, a bad credential, or a runtime-only bug. See the ACCOUNT-TIME
# checklist printed at the end for what still needs real infrastructure.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "${ROOT}"
fails=0
ok()   { printf '  PASS  %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; fails=$((fails+1)); }
chk()  { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi }
chkno(){ if eval "$2" >/dev/null 2>&1; then bad "$1"; else ok "$1"; fi }
# Strip comment lines (#...) so checks assert real CODE, not the prose/docs
# that *describe* the safe behaviour (a test matched by its own explanation
# is a broken test).
nc(){ sed -E '/^[[:space:]]*#/d; s/[[:space:]]+#.*$//' "$1"; }
# line_no <pattern> <file>: 1-based line number of the first match, or ""
# if not found. Used by assert_before() below (previously two hand-rolled
# grep+cut+head pipelines per ordering check).
line_no(){ grep -nE "$1" "$2" | head -1 | cut -d: -f1; }
# assert_before <name> <pattern_a> <pattern_b> <file>: pattern_a's first
# match must exist AND appear at an earlier line than pattern_b's first
# match, in the same file.
assert_before(){
  local name="$1" pat_a="$2" pat_b="$3" file="$4" la lb
  la="$(line_no "${pat_a}" "${file}")"
  lb="$(line_no "${pat_b}" "${file}")"
  chk "${name}" "[[ -n '${la}' && -n '${lb}' && '${la}' -lt '${lb}' ]]"
}

echo "== non-destruction =="
chkno "the button (standup.sh) never runs tofu destroy" \
  "nc infra/scripts/standup.sh | grep -E 'tofu .*destroy'"
chkno "the CI button (standup.yml) never runs tofu destroy" \
  "nc .github/workflows/standup.yml | grep -iw destroy"
for r in 'terraform/bootstrap/main.tf' 'terraform/modules/compute/main.tf' \
         'terraform/modules/object_storage/main.tf' \
         'terraform/modules/r2_offsite/main.tf' \
         'terraform/modules/cloudflare_dns/main.tf'; do
  chk "prevent_destroy present in ${r}" \
    "grep -q 'prevent_destroy = true' infra/${r}"
done

echo "== state bucket: object lock OFF =="
chkno "bootstrap state bucket has NO active object_lock" \
  "grep -nE '^[^#]*object_lock' infra/terraform/bootstrap/main.tf"

echo "== firewall =="
chk   "linode_firewall default-deny inbound"  "grep -q 'inbound_policy  = \"DROP\"' infra/terraform/modules/linode_firewall/main.tf"
chkno "no plaintext-telnet (4000) rule, edge" "grep -n '\"4000\"' infra/terraform/modules/linode_firewall/main.tf"
chk   "host nftables policy drop"             "grep -q 'policy drop' infra/ansible/roles/host_firewall/templates/nftables.conf.j2"

echo "== postgres / app hardening =="
chk   "postgres binds localhost only" "grep -q \"listen_addresses = 'localhost'\" infra/ansible/roles/postgres/templates/10-arxii.conf.j2"
chkno "pg_hba has no 'trust'"         "nc infra/ansible/roles/postgres/templates/pg_hba.conf.j2 | grep -w trust"
chk   "app runs as non-root user"     "grep -q 'User={{ app_user }}' infra/ansible/roles/app_deploy/templates/arxii.service.j2"
chk   "django: DEBUG = False"         "grep -q 'DEBUG = False' infra/ansible/roles/django_hardening/templates/secret_settings.py.j2"
chk   "django: TELNET_ENABLED False"  "grep -q 'TELNET_ENABLED = False' infra/ansible/roles/django_hardening/templates/secret_settings.py.j2"

echo "== first-run setup =="
chk   "base role installs uv (pinned + sha-verified)" \
  "grep -q 'sha256:{{ base_uv_sha256 }}' infra/ansible/roles/base/tasks/main.yml"
chk   "base role pins uv version + sha256"           \
  "grep -qE '^base_uv_version: ' infra/ansible/roles/base/defaults/main.yml && grep -qE '^base_uv_sha256: ' infra/ansible/roles/base/defaults/main.yml"
chk   "app_deploy runs uv sync --frozen --no-dev"    \
  "grep -q 'sync --frozen --no-dev' infra/ansible/roles/app_deploy/tasks/main.yml"
chk   "app_deploy runs evennia migrate --noinput"    \
  "grep -q 'evennia migrate --noinput' infra/ansible/roles/app_deploy/tasks/main.yml"
chk   "app_deploy runs evennia collectstatic --noinput" \
  "grep -q 'evennia collectstatic --noinput' infra/ansible/roles/app_deploy/tasks/main.yml"
chk   "app_deploy guards superuser create with an exists-check (idempotent)" \
  "grep -q 'is_superuser=True' infra/ansible/roles/app_deploy/tasks/main.yml && grep -q \"'YES' not in\" infra/ansible/roles/app_deploy/tasks/main.yml"
chk   "secrets_vault maps ARXII_DJANGO_SUPERUSER_PASSWORD -> DJANGO_SUPERUSER_PASSWORD" \
  "grep -q 'ARXII_DJANGO_SUPERUSER_PASSWORD: DJANGO_SUPERUSER_PASSWORD' infra/ansible/roles/secrets_vault/defaults/main.yml"
chkno "no plaintext superuser password committed anywhere"               \
  "git grep -nE '^[^#]*DJANGO_SUPERUSER_PASSWORD\\s*[=:]\\s*\"[^{$]' -- ':!infra/scripts/acceptance.sh' ':!infra/ansible/group_vars/secrets.env.example'"
chk   "systemd unit uses uv run (not a bare evennia binary)" \
  "grep -q '{{ base_uv_bin }} run evennia start' infra/ansible/roles/app_deploy/templates/arxii.service.j2"
chk   "app_pidfile points at the Evennia gamedir (src/server/server.pid)" \
  "grep -q 'app_pidfile: /opt/arxii/current/src/server/server.pid' infra/ansible/roles/app_deploy/defaults/main.yml"

echo "== secrets posture (public repo) =="
chkno "no tracked *.tfstate"          "git ls-files | grep -E '\\.tfstate'"
chkno "no tracked .env"               "git ls-files | grep -E '(^|/)\\.env$'"
chkno "no ansible-vault ciphertext committed" "git grep -lE '^\\\$ANSIBLE_VAULT;1' -- ."
chkno "no --vault-password-file in real config" "grep -rn --include='*.sh' --include='*.cfg' --include='*.yml' -- 'vault[_-]password[_-]file' infra/ .github/ | grep -v 'infra/scripts/acceptance.sh' | grep -vE '#'"
chk   "secrets_vault uses lookup('env')"      "grep -q \"lookup('env'\" infra/ansible/roles/secrets_vault/tasks/main.yml"
chk   "forbidden-env guard uses REAL token names (not a dead ARXII_ guard)" \
  "grep -A4 secrets_forbidden_env infra/ansible/roles/secrets_vault/defaults/main.yml | grep -q '^[[:space:]]*- LINODE_TOKEN$'"
chkno "standup.sh never passes secrets via --extra-vars" "nc infra/scripts/standup.sh | grep -- '--extra-vars'"
chk   "gitleaks secret-scan job exists"       "grep -q 'gitleaks' .github/workflows/validate.yml"

echo "== email / MTA =="
chk   "django_hardening asserts NO on-box MTA" "grep -q 'forbidden MTA' infra/ansible/roles/django_hardening/tasks/main.yml"
chkno "no role installs postfix/sendmail/exim" "grep -rn 'name: \\(postfix\\|sendmail\\|exim\\)' infra/ansible/roles/*/tasks/"

echo "== CI button shape =="
chk   "standup.yml is workflow_dispatch"      "grep -q 'workflow_dispatch' .github/workflows/standup.yml"
chk   "standup.yml uses the gated prod env"   "grep -q 'environment: prod' .github/workflows/standup.yml"
chk   "standup.yml invokes the shared script" "grep -q 'infra/scripts/standup.sh' .github/workflows/standup.yml"

echo "== #2236 cross-file CONTRACT checks (regression guards) =="
# These exist because the #2236 audit found the 23 single-file grep checks
# above would have caught NONE of the real blockers — every one of them was
# a mismatch BETWEEN two files (a preflight list vs. a secrets map, a task
# order, a paired plugin+directive) that a same-file grep can't see. Each
# check below asserts one such cross-file invariant.

# (a) Every secrets_vault secrets_map key must have a standup.sh preflight
# guard, with two documented exemptions: the ARXII_BACKUP_WRITER_* pair is
# produced by tofu post-apply and handed to ansible in-memory (never
# operator-supplied, so it can't be a preflight requirement); and
# ARXII_DJANGO_SUPERUSER_USERNAME/EMAIL are non-secret with sensible
# defaults (live in Variables, not Secrets — see secrets.env.example) and
# so are never added to secrets_map at all. A secret added to the map
# without also adding it to REQUIRED_ARXII (or documenting a real
# exemption here) would silently ship with no preflight guard.
secrets_map_missing=""
# shellcheck disable=SC2013  # tokens are single-word ARXII_* names, word-split is fine
for k in $(sed -n '/^secrets_map:/,/^[^ ]/p' \
             infra/ansible/roles/secrets_vault/defaults/main.yml \
             | grep -oE 'ARXII_[A-Z0-9_]+'); do
  case "${k}" in
    ARXII_BACKUP_WRITER_ACCESS_KEY|ARXII_BACKUP_WRITER_SECRET_KEY) continue ;;
  esac
  grep -q "${k}" infra/scripts/standup.sh || secrets_map_missing="${secrets_map_missing} ${k}"
done
chk "every secrets_vault secrets_map key (less the tofu-post-apply BACKUP_WRITER pair) has a standup.sh preflight guard" \
  "[[ -z '${secrets_map_missing}' ]]"

# (b) standup.sh must unset the provisioning tokens BEFORE invoking
# ansible-playbook (order-sensitive — defense-in-depth so LINODE_TOKEN /
# CLOUDFLARE_API_TOKEN can never reach the box even by accident).
assert_before "standup.sh unsets LINODE_TOKEN/CLOUDFLARE_API_TOKEN before invoking ansible-playbook" \
  '^[[:space:]]*unset LINODE_TOKEN CLOUDFLARE_API_TOKEN' '^[[:space:]]*ansible-playbook -i' \
  infra/scripts/standup.sh

# (c) The caddy DNS-01 plugin install and the Caddyfile directive that
# needs it are paired — if either half disappears the other is stale.
chk   "caddy role installs the caddy-dns/cloudflare plugin (add-package)" \
  "grep -q 'caddy add-package github.com/caddy-dns/cloudflare' infra/ansible/roles/caddy/tasks/main.yml"
chk   "Caddyfile.j2 still uses DNS-01 via cloudflare (paired with add-package above)" \
  "grep -q 'acme_dns cloudflare' infra/ansible/roles/caddy/templates/Caddyfile.j2"

# (d) nftables must never `flush ruleset` (wipes fail2ban's own table too);
# it must flush only OUR table. nc() strips comments first so the check
# asserts real code, not the explanatory comment that mentions the banned
# phrase.
chkno "nftables.conf.j2 has no 'flush ruleset'" \
  "nc infra/ansible/roles/host_firewall/templates/nftables.conf.j2 | grep -w ruleset"
chk   "nftables.conf.j2 flushes only OUR table (flush table inet ...)" \
  "nc infra/ansible/roles/host_firewall/templates/nftables.conf.j2 | grep -qE 'flush table inet\\b'"

# (e) SSH identity: base creates a login-capable admin (arxadmin) via
# authorized_key, and ssh_hardening's allowlist names that same user — not
# the nologin service account.
chk   "base role creates the arxadmin login user" \
  "grep -q 'name: arxadmin' infra/ansible/roles/base/tasks/main.yml"
chk   "base role authorizes SSH keys for arxadmin (authorized_key task)" \
  "grep -q 'ansible.posix.authorized_key' infra/ansible/roles/base/tasks/main.yml && grep -q 'user: arxadmin' infra/ansible/roles/base/tasks/main.yml"
chk   "ssh_hardening's ssh_allow_users references arxadmin (not the nologin service user)" \
  "grep -A1 '^ssh_allow_users:' infra/ansible/roles/ssh_hardening/defaults/main.yml | grep -q arxadmin"

# (f) The first-run superuser PASSWORD (unlike username/email) is a real
# secret with no safe default — it must be preflight-required.
chk   "ARXII_DJANGO_SUPERUSER_PASSWORD is a standup.sh preflight-required secret" \
  "sed -n '/REQUIRED_ARXII=(/,/)/p' infra/scripts/standup.sh | grep -q ARXII_DJANGO_SUPERUSER_PASSWORD"

# (g) app_deploy must flip `current` AFTER uv sync/migrate/collectstatic —
# never before, or a mid-deploy failure leaves `current` pointing at a
# half-prepared release.
assert_before "app_deploy flips the current symlink AFTER uv sync/migrate/collectstatic" \
  'name: Build the project venv from uv.lock' 'name: Atomically point' \
  infra/ansible/roles/app_deploy/tasks/main.yml

# (h) Backups: PGPASSWORD must be exported (pg_hba requires scram, not
# trust, even on 127.0.0.1) and both the backup + offsite units must carry
# OnFailure= alerting (a failed backup that fails silently is worse than no
# backup — you find out at restore time).
chk   "arxii-backup.sh.j2 exports PGPASSWORD" \
  "grep -q 'export PGPASSWORD=' infra/ansible/roles/backups/templates/arxii-backup.sh.j2"
chk   "arxii-backup.service carries OnFailure= alerting" \
  "grep -q 'OnFailure=arxii-alert-failure@%n.service' infra/ansible/roles/backups/tasks/main.yml"
chk   "arxii-offsite.service carries OnFailure= alerting" \
  "grep -q 'OnFailure=arxii-alert-failure@%n.service' infra/ansible/roles/offsite_replication/tasks/main.yml"

# (i) restore.sh supports a real drop/recreate restore with a remote
# target; restore-rehearsal.sh must run it ON the ephemeral stage box over
# SSH, never against the operator's own local machine (the original bug
# this rework fixed).
chk   "restore.sh supports RESTORE_TARGET_HOST and drops/recreates the DB before restoring" \
  "grep -q 'RESTORE_TARGET_HOST' infra/scripts/restore.sh && grep -q 'dropdb' infra/scripts/restore.sh"
chk   "restore-rehearsal.sh runs restore.sh remotely on the stage box via ssh (ssh_stage marker), not locally" \
  "grep -qE 'ssh_stage \"set -a;.*bash /root/restore\.sh' infra/scripts/restore-rehearsal.sh"
chkno "restore-rehearsal.sh never reintroduces the split 'ssh_stage bash -c' argv shape (ssh flattens multi-arg remote commands with un-requoted spaces, so sourcing rehearsal.env under set -a in the outer shell never reaches restore.sh as a child process — see the fix comment above the ssh_stage call)" \
  "grep -q 'ssh_stage bash -c' infra/scripts/restore-rehearsal.sh"
# Every mention of restore-rehearsal.sh's OWN local copy of restore.sh
# (SCRIPT_DIR}/restore.sh) must be the scp_stage line that ships it to the
# stage box — never a bare local bash-exec of that same path. Direct
# disallowed-shape check: any line mentioning the path that is NOT also a
# scp_stage line is the bug (previously a count-comparison between two
# separate greps, which passes vacuously if BOTH counts are zero).
chkno "restore-rehearsal.sh's only local reference to restore.sh is the scp_stage copy (never exec'd against the invoking machine)" \
  "grep -n 'SCRIPT_DIR}/restore.sh' infra/scripts/restore-rehearsal.sh | grep -v scp_stage"

# (j) standup.sh generates the group_vars the fail-closed asserts below
# depend on; host_firewall and django_hardening both refuse to converge on
# an empty (ungenerated) config rather than silently opening/allowing
# everything.
chk   "standup.sh generates group_vars/arxii_prod.yml from tofu output" \
  "grep -q 'Generating inventory + group_vars from tofu output' infra/scripts/standup.sh"
chk   "host_firewall fails closed on empty allow-lists" \
  "grep -q 'Fail-closed' infra/ansible/roles/host_firewall/tasks/main.yml && grep -q 'length > 0' infra/ansible/roles/host_firewall/tasks/main.yml"
chk   "django_hardening fails closed on empty ALLOWED_HOSTS" \
  "grep -q 'dh_allowed_hosts | length > 0' infra/ansible/roles/django_hardening/tasks/main.yml"

# (k) #2236 F1 regression guard: settings.py's guarded prod-overlay import
# and secrets_vault's EnvironmentFile rendering of the env vars settings.py
# actually reads must both be present. This exact mismatch (an overlay
# nothing ever imported; an EnvironmentFile providing names settings.py
# never read — DJANGO_SECRET_KEY/CLOUDINARY_URL vs. the SECRET_KEY/
# CLOUDINARY_CLOUD_NAME+API_KEY+API_SECRET settings.py's env() calls
# actually use) was the #2236 review's headline finding.
chk   "settings.py guards the prod secret_settings overlay import" \
  "grep -q 'from server.conf.secret_settings import' src/server/conf/settings.py"
chk   "secrets_vault's EnvironmentFile renders SECRET_KEY and DATABASE_URL (settings.py's actual env-read contract)" \
  "grep -q 'ARXII_DJANGO_SECRET_KEY: SECRET_KEY' infra/ansible/roles/secrets_vault/defaults/main.yml && grep -q '^DATABASE_URL=' infra/ansible/roles/secrets_vault/templates/arxii.env.j2"

echo
if [[ "${fails}" -gt 0 ]]; then
  echo "ACCEPTANCE: ${fails} FAILED"; exit 1
fi
echo "ACCEPTANCE: all static contract checks PASS (single-file greps + #2236"
echo "cross-file checks) — this is NOT a deploy-readiness proof; see the"
echo "ACCOUNT-TIME checklist below for what still needs real credentials."
cat <<'EOF'

ACCOUNT-TIME checklist (run once real creds exist — cannot be static):
  [ ] 2nd `tofu apply` => no changes; `tofu plan` => 0 destroy/replace
  [ ] 2nd `ansible-playbook` => changed=0 (idempotent)
  [ ] external port scan: only SSH/80/443/TLS-telnet; NO plaintext telnet
  [ ] restore-rehearsal.sh passes from BOTH linode + r2 copies
  [ ] CI validate.yml (tofu/ansible-lint/caddy/gitleaks) green
EOF
