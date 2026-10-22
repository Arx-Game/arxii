#!/usr/bin/env bash
# Guarded launcher for the reviewed Linux x64 Prime security build.
# Does not install or update anything; keep credentials in the normal store.
set -euo pipefail

binary="${PRIME_AGENT_BIN:-$(command -v prime-agent || true)}"
if [[ -z "${binary}" || ! -f "${binary}" ]]; then
  echo 'Prime is unavailable. See docs/operations/tls-trust.md before installing it.' >&2
  exit 2
fi
binary="$(readlink -f -- "${binary}")"
expected=1fbb506f54a8e9af1f0d123e521d13a765bce34883707c69656f06d5951b314c
actual="$(sha256sum -- "${binary}" | cut -d' ' -f1)"
if [[ "${actual}" != "${expected}" ]]; then
  echo 'Refusing unverified Prime binary; only the reviewed v0.10.1 Linux x64 hash is accepted. See docs/operations/tls-trust.md.' >&2
  exit 2
fi
if [[ "${PRIME_AGENT_TLS_VALIDATED:-}" != "1" ]]; then
  echo 'Prime v0.10.1 artifact identity is verified, but runtime TLS validation is pending; refusing to start.' >&2
  exit 2
fi
exec "${binary}" "$@"
