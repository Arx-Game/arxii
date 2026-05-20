#!/usr/bin/env bash
#
# acceptance.sh — STATIC acceptance harness ("the tests" for the IaC; tofu/
# ansible can't run locally on Windows, CI is the dynamic gate). Asserts the
# plan's safety invariants by inspecting the repo. Exit 1 on ANY violation.
# Account-independent: no creds, no cloud, no apply.
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

echo
if [[ "${fails}" -gt 0 ]]; then
  echo "ACCEPTANCE: ${fails} FAILED"; exit 1
fi
echo "ACCEPTANCE: all static checks PASS"
cat <<'EOF'

ACCOUNT-TIME checklist (run once real creds exist — cannot be static):
  [ ] 2nd `tofu apply` => no changes; `tofu plan` => 0 destroy/replace
  [ ] 2nd `ansible-playbook` => changed=0 (idempotent)
  [ ] external port scan: only SSH/80/443/TLS-telnet; NO plaintext telnet
  [ ] restore-rehearsal.sh passes from BOTH linode + r2 copies
  [ ] CI validate.yml (tofu/ansible-lint/caddy/gitleaks) green
EOF
