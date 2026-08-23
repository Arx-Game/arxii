#!/usr/bin/env bash
# ops-key-install.sh — install (or remove) the gated prod-ops SSH key.
#
# Runs at every container start via postStartCommand, AFTER the firewall
# (both read the same /run/arxii-ops-key mount, so the two gates can never
# disagree within one start). The bind mount can't be used directly as an
# IdentityFile: a Windows-drive source arrives world-readable and ssh
# refuses such a private key, so we copy it into ~/.ssh with 0600 perms.
# When the mount is the empty no-ops-key default, any previously installed
# copy is REMOVED — a container restarted without the env var sheds the
# key instead of keeping a stale one. See docs/operations/ops-access.md.
set -euo pipefail

src=/run/arxii-ops-key/arxii_ops
dst="${HOME}/.ssh/arxii_ops"

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

if [ -s "${src}" ]; then
  install -m 0600 "${src}" "${dst}"
  if [ -s "${src}.pub" ]; then
    install -m 0644 "${src}.pub" "${dst}.pub"
  fi
  # Convenience host alias so `ssh arxii-prod` just works. accept-new (not
  # blind trust, not interactive prompt): first contact pins the host key,
  # later mismatches still fail hard. arxops is the least-privilege server
  # user provisioned by infra/ansible/roles/ops_access.
  if ! grep -qs '^Host arxii-prod$' "${HOME}/.ssh/config"; then
    {
      echo 'Host arxii-prod'
      echo '  HostName 23.92.20.94'
      echo '  User arxops'
      echo '  IdentityFile ~/.ssh/arxii_ops'
      echo '  IdentitiesOnly yes'
      echo '  StrictHostKeyChecking accept-new'
    } >> "${HOME}/.ssh/config"
    chmod 600 "${HOME}/.ssh/config"
  fi
  echo "Ops key installed at ${dst} (ssh arxii-prod)"
else
  rm -f "${dst}" "${dst}.pub"
  echo "No ops key mounted; ${dst} absent"
fi
