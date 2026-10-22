# Outbound TLS trust after the eMudhra incident (#4506)

The compromised intermediate keys can authenticate forged servers to clients
that still trust their chains. This concerns outbound package downloads and
API calls as well as production traffic. A local devcontainer can download and
execute code and hold service credentials; its location does not remove this
risk. No compromise of Arx infrastructure has been established.

## Managed mitigation

- Ubuntu 24.04: require `ca-certificates >= 20260816ubuntu0.24.04.1`
  ([USN-8944-1](https://ubuntu.com/security/notices/USN-8944-1)). The Docker
  build checks this before bootstrap downloads; Ansible upgrades old hosts
  before downloading uv or other tools. Newer vendor packages remain allowed.
- Developer tooling: mise selects Node 24.22.1. CI selects Node 22.23.4.
  The image first installs mise 2026.10.17 with the official checksum-verifying
  installer, explicitly bypassing the installer's default release-age delay.
  That [mise release](https://github.com/jdx/mise/releases/tag/v2026.10.17)
  removes the compromised CA trust from its own downloader before tool installs.
  The devcontainer pins native **pnpm 12.15.0**, preserving pnpm 12's workspace
  `allowBuilds` policy instead of downgrading its install-script protections.
  pnpm 12 is Rust, including when installed through its npm wrapper; updating
  Node or choosing the npm package does not patch that separate client.
  The [12.15.0 release](https://github.com/pnpm/pnpm/releases/tag/v12.15.0)
  has `rustls-webpki` 0.103.16 and its network crate's fallback
  `webpki-root-certs` 1.0.10 in the [tagged lockfile](https://github.com/pnpm/pnpm/blob/v12.15.0/Cargo.lock).
  Production requires NodeSource Node >=22.23.4 and refreshes apt metadata.
  It also checks the build user's effective executable and rejects a different
  major or an older runtime, including unsupported higher majors and PATH overrides.
  These releases include native compromised-public-key rejection and updated
  roots: [Node 24](https://github.com/nodejs/node/releases/tag/v24.22.1),
  [Node 22](https://github.com/nodejs/node/releases/tag/v22.23.4).
- The certifi and uv changes in #4505 remain necessary for their independent
  trust stores. Updating the OS does not update every embedded CA bundle.

Prefer supported updates over a permanent Node preload or local root blacklist.
[Node's native SPKI block](https://github.com/nodejs/node/pull/66871) handles
alternate certificates with the same compromised key. `NODE_EXTRA_CA_CERTS`
adds trust; it cannot remove an unsafe root. Disabling TLS verification is not
a mitigation.

## Apply to an existing devcontainer

1. Stop credential-bearing agents and downloads before the update. Save work;
   rebuilding/recreating interrupts sessions. Preserve the existing named volumes.
2. From the host's main checkout with this change integrated, rebuild the app
   image without old apt layers and recreate it using the normal devcontainer
   flow (`just dc-build` rebuilds and recreates the container, including its
   setup hooks). If building manually, use `--pull --no-cache` and the
   same compose files and build context as the normal flow. Do not delete volumes.
3. In the new container, run `mise install` / activate the project environment.
   Confirm `node --version` is 24.22.1 or a later patched Node 24 release and
   `dpkg-query -W ca-certificates` meets the minimum above. Global npm tools
   are installed under the newly selected Node during the image build.
   Also run `git worktree list` and audit every worktree where agents or package
   tools run: its own `mise.toml` survives in the named volume. Integrate the
   Node and pnpm security pins into each active branch, preserving its work, then check
   `mise current node`, `command -v node` and `node --version` there. A check in main alone is
   insufficient. All automatic tool installation (`mise exec`, `mise run` and
   the command-not-found hook) is disabled in the image so an old
   missing pin cannot silently fetch a vulnerable runtime. The shim refuses
   system fallback, but `mise exec` and `mise run` can still use a same-named
   executable on PATH. Verify custom and inherited PATHs in each launch context;
   explicit `mise install` can still install an old pin, so audit it first.
   Check `mise which pnpm` and `pnpm --version` too: the selected native client
   must be 12.15.0 or a separately reviewed patched version. An npm shebang can
   hide a native child process; a patched parent Node is insufficient evidence.
   Compose repeats the three mise guards explicitly, so retained `dev.env`
   entries cannot override the image defaults. Confirm their effective values
   in the recreated container; custom compose overrides still need review.
4. Restart agent processes, shells and other long-running TLS clients; an old
   process does not become patched because a new binary exists on disk.
5. Run the diagnostic below from an environment where its hosts are reachable.
   The runtime firewall may block the public probes; this is inconclusive.

For an already provisioned production host, apply the base role and app_deploy
through the normal deployment workflow. Check package versions and diagnostic
results on the actual host. Restart TLS clients holding old SSL contexts,
including both Evennia Server and Portal when refreshing their Python bundles.
A Server reload alone does not refresh the Portal. Merge status is not rollout
status. Ansible's minimum Node requirement should fail if NodeSource has not
yet published a suitable candidate, rather than silently keep a vulnerable one.
After repairing Caddy's binary/configuration and flushing its handlers, the
Caddy role compares the system CA bundle's SHA-256 with the last bundle
applied to an already-running Caddy on every converge. A missing or different
fingerprint triggers a restart, then records the fingerprint only on success.
This also catches prior unattended or out-of-band CA updates at the next converge.
Caddy's Go root pool is cached for the process lifetime, so reloading its config
is insufficient. The reconciliation itself never starts Caddy; the role's normal
`state: started` does, and that process is then reconciled in the same run. Verify that the
actual production Caddy process has restarted and its ACME/Cloudflare DNS calls
work; this has not been exercised on production by the disposable rehearsals.
Ansible check mode probes the current version without changing it; when apt
plans an upgrade, it defers the post-upgrade assertion until a real run.

## Verify actual clients

Run on Linux with the same Node executable, curl backend and trust environment
used by the tools being assessed:

```sh
node --test scripts/check-tls-trust.test.mjs
node scripts/check-tls-trust.mjs
```

The diagnostic makes credential-free direct connections to twelve public TLS
test hosts from the [incident disclosure](https://emudhra.we-have-a-problem.com/),
covering DV/OV/EV, G3B/G3C and their AAA cross-signs. It also requires normal
HTTPS to npm, GitHub and PyPI to succeed. For each negative Node probe, it pins
the ordered leaf/intermediate fingerprints in `scripts/tls-trust-fixtures.json`
to the disclosure's archive (SHA-256 recorded in the manifest). It reads peer
identity and authorization failure from the same TLS socket. A changed, partial
or unrelated chain is inconclusive even when it produces a certificate error.

The negative Node sockets use `rejectUnauthorized: false` solely to finish the
TLS handshake and inspect `authorized` / `authorizationError` plus the peer
chain before destroying the socket. Certificate verification still runs. No
HTTP, credentials or other application bytes are sent on those sockets.
Normal controls use strict authorization. curl's personal config and proxy
settings are bypassed. Its negative results are labeled unbound observations:
they come from a different socket and cannot prove which chain it received.

Exit 0 requires a supported Node 22/24 runtime at its security floor, all twelve
pinned handshakes rejected specifically with `CERT_REVOKED`, and successful
normal HTTPS controls. It establishes Node behavior only; curl negative
observations cannot enable success. Exit 1 flags a trusted negative endpoint
for investigation (Node identity is pinned; curl identity is unbound). Exit 2
means an inconclusive Node result or failed positive control. DNS failures,
blocked egress, timeouts, expiry, hostname mismatch and fixture rotation cannot
prove Node protection. Public test services can change; retain timestamped
output and review fixture updates rather than automatically accepting new pins.
No exit code establishes historical safety or covers every tool's trust store.
Root/issuer rejection alone is inconclusive for Node: it does not establish
that the runtime contains the native compromised-key block.

To independently reproduce the fingerprint manifest (requires `unzip`), download
the disclosure's archive in a patched environment, then run:

```sh
node scripts/verify-tls-trust-fixtures.mjs /path/to/chains.zip
```

It requires the recorded archive hash and verifies every ordered DER fingerprint
without extracting archive paths to disk. A changed archive fails until reviewed.

For restricted egress, use the disclosure's offline `chains.zip` in an isolated
test environment, recording its hash. Verify the leaf with the intermediates
as `-untrusted`, the actual CA bundle, `-purpose sslserver` and the expected
hostname; disable unintended default CA paths/stores. Offline OpenSSL checks
do not exercise Node's native SPKI callback. Do not weaken production firewall
rules merely to reach public probes.

Rehearse the minimum package tasks twice (second run should not change the
packages), reinstall/upgrade ca-certificates, and rebuild cleanly. Repeat both
negative and positive checks after each step. Inspect custom anchors and
`SSL_CERT_FILE`, `SSL_CERT_DIR`, `NODE_OPTIONS`, `NODE_EXTRA_CA_CERTS` and
application-specific `ca` configuration without logging credentials. Vendor
root removal may break legitimate services sharing the removed roots; have
those services move to supported chains instead of restoring unsafe trust.

## Remaining independent clients

The pinned AWS CLI 2.36.24 has a vulnerable private CA bundle: offline checks
accepted six AAA chains, and an unsigned real CLI request reached an incident
endpoint. The base role now replaces its public command symlink with a wrapper
that passes `--ca-bundle /etc/ssl/certs/ca-certificates.crt` to the real CLI.
Backup, replication, archive sync, rehearsal, restore and devcontainer `uvx` fallback calls
also select that bundle explicitly. [AWS documents this option](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html).
The wrapper must be reapplied after an out-of-band AWS installer update. Direct
calls to the underlying versioned executable bypass it. Verify the system CA
package on every calling host; selecting an old system bundle is insufficient.
Test without sending storage credentials to incident probes. Also inventory standalone agent binaries and
the runtimes embedded in GitHub JavaScript actions; setup-node only selects
the Node used by subsequent shell steps.

In each real agent launch context (zellij, `dc-shell`, VS Code terminal), record
`command -v claude`, `readlink -f "$(command -v claude)"`, its file type and
version, plus the effective Node executable/version. In the rebuilt image,
the npm-installed Claude command resolves to `@anthropic-ai/claude-code/bin/claude.exe`,
an independent native binary; Node's probe does not establish its TLS safety.
The initial 2.1.306 startup was a compatibility check only. Subsequent tests of
2.1.306 and the final image's 2.1.307 native API path, with empty configuration
and a fake nonsecret key, rejected all twelve incident endpoints with
`CERT_REJECTED`; the normal
Anthropic API completed TLS and returned the expected HTTP 401. Polytoken 0.9.2
daemon-provider requests similarly rejected all twelve with `UnknownIssuer`
and reached the normal API. These are client observations, not same-socket
pinned-chain proofs. They cover the tested provider paths and clean config;
standalone auth, updater, web and persisted custom trust settings need their
own rollout checks. [Polytoken documents its trust settings](https://docs.polytoken.dev/reference/configuration/).
Audit persisted agent installs/configured paths that could shadow tested binaries.

### Prime Agent: verified stable artifact, activation pending

The existing container was inventoried as Prime stable 0.10.0. Do not run that
artifact: its bundled Rust TLS dependencies predate the incident fixes. The
[upstream security change](https://github.com/PrimeIntellect-ai/prime-agent/commit/1a486b6c11b06517062283b6aafd196cc80fce16)
requires `rustls-webpki >=0.103.16` and `webpki-roots >=1.0.10`; adding
`NODE_EXTRA_CA_CERTS` cannot remove unsafe bundled roots. Rebuilding this image
does not install Prime, and retaining its credentials is not an instruction to
reinstall the vulnerable stable release.

Stable **0.10.1** is now the reviewed candidate. The official [release](https://github.com/PrimeIntellect-ai/prime-agent/releases/tag/v0.10.1)
is tag commit `8aac8692456c00c01d4e53e60e6d3347a3506559`; GitHub's compare API
confirms the upstream fix commit is an ancestor. The [fix](https://github.com/PrimeIntellect-ai/prime-agent/commit/1a486b6c11b06517062283b6aafd196cc80fce16)
was merged to `main` before the release. Its source lockfile has
`rustls-webpki 0.103.16` and `webpki-roots 1.0.10`, with vulnerable
`webpki-roots 0.26.x` absent. The release's `reqwest` configuration still enables
WebPKI roots, but it resolves to the patched 1.0.10 package.

- [Linux x64 archive](https://github.com/PrimeIntellect-ai/prime-agent/releases/download/v0.10.1/prime-agent-0.10.1-linux-x64.tar.gz)
  SHA-256: `21ec219183f4134dd23dce9572102e69456066fe374846525561c776d4d1945c`.
- Executable SHA-256: `1fbb506f54a8e9af1f0d123e521d13a765bce34883707c69656f06d5951b314c`.
- Source archive SHA-256: `27350c8318c4715482b72d15188e0dc23c9a023ba57dc58db454a88a4ed83053`.

The release archive and source archive hashes were verified in a disposable
container; the extracted executable reports `0.10.1`, and its hash matches the
official release manifest. Use the launcher only after runtime validation:
`PRIME_AGENT_BIN=/absolute/path/to/verified/prime-agent bash scripts/run-prime-agent.sh`.
It refuses every hash except the reviewed Linux x64 executable, then also
requires `PRIME_AGENT_TLS_VALIDATED=1`. Leave that variable unset until the
candidate proves incident-chain rejection and normal HTTPS behavior. The
launcher does not install/update Prime or intercept direct `prime-agent` calls.
Stop old processes and verify the effective executable before activation.

A credential-free request against an incident probe returned only a generic
`Connection error`, which is inconclusive. A separate dummy-key request to the
normal OpenAI endpoint completed TLS but received an HTTP 400 response, not the
expected authentication control. These probes do not establish successful
incident rejection or a valid normal API control. Keep Prime activation pending;
do not resume the installed old process.

Also inventory Git's libcurl backend, the actual mise version in old launch contexts, the pinned Playwright
browser/NSS stores, the Docker daemon/sidecar image pulls and hosted-runner OS
trust. Test production's actual HTTPS destinations (backup storage, Sentry,
Resend, Cloudflare, NodeSource and PostgreSQL package hosts) as post-rollout
compatibility controls, using the actual client without sending credentials
to incident probe hosts. npm/GitHub/PyPI controls do not cover those services.

VS Code's server and extension host have a separate Node executable, commonly
`~/.vscode-server/bin/<commit>/node` or under `~/.vscode-server/cli/servers/`.
Inventory it before attaching, including credential-bearing extensions; mise
does not replace it. The existing container contained Node 24.21.0 at one such
path, below this issue's security floor; no process using it was observed in
the targeted process check. Update the host VS Code installation/server to a
release with patched Node, then run this diagnostic with the actual server
Node executable before enabling extensions. Do not overwrite that binary by
hand or infer its protection from a terminal's `node --version`. If the vendor
uses a different release line or a backport, require vendor security evidence
and client-specific checks rather than bypassing the diagnostic's version gate.

Controller-side AWS scripts are supported here on the listed Ubuntu releases;
their preflight checks the vendor CA package floor, not merely file existence.
On macOS/other hosts use the updated Ubuntu devcontainer, rather than silently
selecting a different or stale bundle. The standalone restore script targets
the provisioned Ubuntu 24.04 host and checks that package floor itself.

Keep #4506 open until running environments, independent clients and process
restarts have evidence recorded. Repository changes alone do not demonstrate
that a host rejects compromised certificate chains.

## Implementation rehearsal (21 October 2026)

- Existing devcontainer: Ubuntu CA package `20260601~24.04.1`, Node `24.4.1`.
  Public incident probes were blocked by egress rules, so those results were
  inconclusive. Normal npm/GitHub/PyPI connections succeeded.
- The exact old Node binary, copied into a disposable container without
  credentials or the runtime firewall, accepted all twelve incident chains.
  This confirms susceptible validation, not a historical attack on Arx.
- Isolated Node 24.22.1 and Node 22.23.4 both rejected all twelve chains with
  `CERT_REVOKED`; normal HTTPS controls succeeded. Updated curl rejected all
  twelve at issuer validation and passed the same controls.
- On disposable Ubuntu 24.04, the actual CA and NodeSource tasks selected
  `20260816ubuntu0.24.04.1` and `22.23.4-1nodesource1`. A second Ansible run
  reported `changed=0`. After reinstalling ca-certificates, both Node versions
  and curl still rejected every incident chain and passed the controls.

- The initial modified Dockerfile built successfully as the local image
  `arxii-4506-devcontainer`. In a fresh instance of that image, Node 24.22.1
  and curl passed its initial negative and positive probes; the initial three diagnostic
  classification tests passed and Claude Code 2.1.306 started successfully.
- Changed Ansible roles passed ansible-lint. With a clean frozen pnpm 9
  install, frontend typecheck and build initially passed under Node 24.22.1. The build
  emitted CSS/chunk warnings and skipped Python collectstatic because uv was
  absent from that isolated frontend test image.
- The optional broad infrastructure baseline scan was stopped during a slow
  whole-repository Git grep over the Windows bind mount; it did not finish.

These tests did not replace the running devcontainer, update production,
restart active agents, or establish protection for standalone AWS/agent
bundles and GitHub action runtimes. The new image is available locally for
rollout after integrating the matching source configuration.

## Adversarial review corrections

Three independent Luna reviewers and a Claude Opus reviewer checked trust
assumptions, diagnostic behavior and rollout. Negative Node checks
now bind rejection to pinned incident certificates on the same socket, and
production checks the effective runtime rather than trusting an apt lower bound
alone. The diagnostic requires native revocation, covers its exit-code matrix,
and rejects unsupported runtime versions. Persisted worktree pins and native
agent runtime inventory are explicit activation gates; implicit missing-tool
installation is disabled. curl negatives are observations, not incident-proof results.
Opus also identified the standalone pnpm runtime and the security regression
from downgrading its major. The final image uses patched native pnpm 12.15.0;
its Rust verifier and fallback bundle were reviewed separately. The runtime assertion preserves Ansible dry
runs and defers claims about an upgrade that check mode has not performed.
The final bootstrap audit also found mise's default age delay selecting
2026.10.15; the image now explicitly installs the fixed 2026.10.17 release
before it fetches the remaining tools.
The updated regression tests reject unrelated, reordered, partial and rotated
fixtures, as well as network failures and unrelated certificate errors.

## Latest post-review verification

The rebuilt image contains mise 2026.10.17 and the required Ubuntu CA package.
All seven diagnostic regression tests passed. Node 24.22.1 rejected all twelve
same-socket pinned incident chains with CERT_REVOKED; all six Node/curl normal
HTTPS controls passed. curl negative results remain unbound observations.
The archive verifier independently reproduced all twelve pinned chains.

Native pnpm 12.15.0 rejected all twelve incident registry requests with
`CertDistrusted` and successfully queried the normal npm registry. It is a
separate Rust client, not JavaScript executing under the project's Node.
With an old worktree pin, mise exec, mise run and the Node shim failed in the
clean image without downloading Node
24.4.1. Compose explicitly overrides all three automatic-install settings to
false, including when a synthetic env file sets them true.

Frontend typecheck and build passed under both Node 22.23.4 and 24.22.1.
A fresh pnpm 12.15.0 image also completed a noninteractive frozen install,
typecheck and frontend build against a copied 334 MB retained pnpm 12 dependency
volume with the corrected `storeDir` setting. The original volume was mounted
read-only. The fresh container downloaded the package store again; this proves
noninteractive recovery with retained dependencies, not cache reuse. This
frontend-only rehearsal used the supported CI postbuild branch
that skips Django collectstatic; it did not run the complete database/setup hook.
The Ansible rehearsal verified convergence, rejected unsupported or shadowed
runtimes, and preserved check mode for both converged and planned-change cases.
It was also repeated successfully on ansible-core 2.18.19, matching the
controller's pinned 2.18 release line, including both Node TLS checks after a
CA package reinstall. The final Caddy fingerprint tasks were exercised with real
Ansible file modules and a simulated systemctl in a disposable container: initial
restart, unchanged convergence, out-of-band CA changes, failed restart retry,
check mode, and absent/stopped services passed. Installed CA floor acceptance,
rejection and planned-upgrade check mode also passed on ansible-core 2.18.19.
This is not an actual
running production Caddy restart, which remains pending.
Changed roles passed ansible-lint (14 files, no failures or warnings); the final
four base/Caddy task/handler files also passed after the reconciliation change. This was
a disposable fresh-install rehearsal, not a live upgrade from an older installed
NodeSource package. Production upgrade and compatibility evidence remain rollout
requirements. No running devcontainer or production service was replaced.
