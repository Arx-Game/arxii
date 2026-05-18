# Sandboxed devcontainer setup

This guide explains how to run Claude Code with `--dangerously-skip-permissions` safely
on a Windows host using the project's Docker devcontainer.

## Why this exists

`--dangerously-skip-permissions` lets Claude Code execute shell commands without
approval prompts. That is powerful and needs a real boundary around it.

**Plain WSL2 is NOT a security boundary.** A WSL2 shell shares the Windows filesystem
(your `C:\` is mounted at `/mnt/c`) and the Windows network stack. Anything running in
WSL2 can reach your files and your LAN.

This setup provides two independent boundaries:

- **Filesystem**: only the repository workspace is bind-mounted into the container;
  the rest of your Windows filesystem is invisible to it.
- **Network**: an egress firewall (iptables + ipset) runs inside the container on every
  start. It is default-deny for outbound traffic and allows only the destinations Claude
  Code actually needs (Anthropic API, GitHub, PyPI, npm). Everything else is rejected.

This is defense-in-depth, not a full sandbox: a compromised or mistaken agent can still
modify anything in the bind-mounted workspace and can still send data to the explicitly
allowlisted destinations (GitHub, PyPI, npm, the Anthropic API). The container and
firewall bound the blast radius; they do not eliminate it.

WSL2 itself is just the Linux kernel Docker Desktop uses under the hood. You interact
with it only through Docker; you do not need a WSL terminal.

## Mental model

A devcontainer is a Docker container the devcontainer CLI (or an IDE) treats as your
development machine. Key points:

- The repository folder is **bind-mounted** into the container at `/workspaces/arxii`.
  Edits you make on the host in PyCharm appear instantly inside the container and vice
  versa.
- `.venv` and `frontend/node_modules` are **named volumes** (container-local). This
  prevents Windows-format binaries from leaking into the Linux environment.
- The database lives in the `arxii-pgdata` named volume. It is test-only and safe to
  wipe.
- Your Claude Code login persists in the `arxii-claude-home` named volume (mounted at
  `~/.claude`), so you authenticate once — it survives `dc-down` and `dc-build`.
- "Run Claude Code" means: get a bash shell inside the `app` container, then run
  `claude --dangerously-skip-permissions`.
- Your host shell stays PowerShell. Your editor stays PyCharm (or whatever you use).
  You do not need to touch WSL at all.

## Host bootstrap

Run this once per machine. Re-run it only if you reinstall Docker Desktop or set up a new machine — a routine reboot does not require re-running it.

```powershell
.\scripts\bootstrap-devcontainer-host.ps1
```

If PowerShell blocks the script with an execution-policy error, allow local scripts for your user once with `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`, then re-run it.

The script is **idempotent and detection-first**: it checks what is already installed
before doing anything. It handles:

- WSL2 detection (distro present, default version = 2)
- Docker Desktop detection + install via winget
- `@devcontainers/cli` detection + install via npm

What it **cannot** do for you (and will tell you about with instructions):

- Run commands that require an Administrator shell (e.g. `wsl --install`)
- Trigger a reboot (required after WSL2 install)
- Complete Docker Desktop's interactive first-run (EULA acceptance and enabling
  WSL integration in Settings -> Resources -> WSL Integration)

**Exit codes:** `0` = host ready; `1` = manual action required. The script prints
exactly what to do. Re-run it after completing each action; it will tell you when
everything is ready.

## Path B: terminal only (primary / recommended)

This is the supported, editor-agnostic path. PyCharm stays open on the host for editing;
you interact with the container entirely from PowerShell.

### Prerequisites

- Docker Desktop running with WSL integration enabled
- `devcontainer` CLI on PATH (`npm i -g @devcontainers/cli`)
  (the bootstrap script installs this for you)

### Daily workflow

**Start the stack (first time or after `dc-down`):**

```powershell
just dc-up
```

The first run is slow — it builds the Docker image, bakes the mise toolchain (Python,
Node, uv, pnpm) into the image layer, installs Python and frontend dependencies, and
runs database migrations. This can take several minutes. Subsequent starts are fast
because the image layer is cached and only the firewall re-initialization runs.

**Get a shell inside the container:**

```powershell
just dc-shell
```

You are now in a bash shell at `/workspaces/arxii` inside the `app` container. This is
where you run Claude Code:

```bash
claude --dangerously-skip-permissions
```

**Run the test suite from the host (without entering the container):**

```powershell
just dc-test
just dc-test world.magic --keepdb
```

**Stop the stack:**

```powershell
just dc-down
```

The database volume (`arxii-pgdata`) is preserved by the pinned compose project name
(`arxii-devcontainer`). To stop and destroy everything including volumes:

```powershell
docker compose -p arxii-devcontainer -f .devcontainer/docker-compose.yml down -v
```

**Full rebuild (after editing the `Dockerfile` or `.devcontainer/init-firewall.sh`):**

```powershell
just dc-build
```

The firewall script is copied into the image at build time and `postStartCommand` runs
that baked copy, so workspace edits to `init-firewall.sh` only take effect after
`just dc-build`. This passes `--build-no-cache --remove-existing-container` to the
devcontainer CLI.

### Do not use raw docker commands for daily use

`docker compose up` and `docker exec` skip the devcontainer hooks. That means:

- The `claude-code` devcontainer feature is not installed
- `post-create.sh` (deps + migrations) does not run
- The firewall (`postStartCommand`) does not run

Always enter via `just dc-*` recipes or VS Code "Reopen in Container".

## Path A: VS Code (alternative)

1. Install the **Dev Containers** extension.
2. Open the repository folder.
3. Command palette: "Dev Containers: Reopen in Container".
4. VS Code's integrated terminal opens inside the `app` container.
5. Run `claude --dangerously-skip-permissions` in that terminal.

## PyCharm note

PyCharm Professional has devcontainer support (backend-in-container + thin-client
model). Community edition does not have a remote-dev backend and cannot use this.

The Professional integration is less seamless than VS Code for projects that use
compose + devcontainer features (a known rough edge). It is optional. The recommended
approach is: keep editing in PyCharm on the host (edits sync via the bind mount) and
use terminal Path B for anything that needs to run inside the container.

## What is isolated and what is not

| What | Isolation |
|---|---|
| Windows filesystem | Isolated — only `/workspaces/arxii` is visible inside the container |
| `.venv` | Container-local named volume — Linux binaries, not Windows |
| `frontend/node_modules` | Container-local named volume — same reason |
| Database (`arxii-pgdata`) | Named volume — persists across `dc-down`, safe to wipe |
| Claude Code login (`~/.claude`) | Named volume (`arxii-claude-home`) — auth/config persists across rebuilds; log in once |
| Network | Default-deny egress — see firewall section below |
| Host LAN / other services | Blocked by the firewall default-deny policy |

## The egress firewall

`init-firewall.sh` runs on every container start via `postStartCommand`. It uses
iptables + ipset to enforce **default-deny egress**: all outbound connections are
rejected unless the destination is on the allowlist.

The container requires `NET_ADMIN` and `NET_RAW` capabilities (set in
`.devcontainer/docker-compose.yml` `cap_add`) to manipulate iptables. The `vscode`
user has a passwordless sudo entry for this specific script only.

### Always-open rules (not in the ipset)

- Loopback (lo) — unrestricted
- DNS (UDP + TCP port 53) — needed to resolve allowlist domains
- SSH (TCP port 22) — for git-over-SSH
- `172.16.0.0/12` — the Docker bridge network range; keeps the `app` container able
  to reach the `db` service regardless of which bridge address Docker assigns at runtime

### Allowed egress destinations (ipset `allowed-domains`)

The firewall populates the ipset before applying the default-deny policy, using
published IP-range data so CDN edge nodes are covered:

| Destination group | Hosts | Resolution method |
|---|---|---|
| Anthropic API | `api.anthropic.com` | dig A record |
| Anthropic telemetry | `statsig.anthropic.com`, `statsig.com`, `sentry.io` | dig A record |
| PyPI index | `pypi.org` | dig A record |
| GitHub | `github.com`, `api.github.com`, git, packages | GitHub meta API (`api.github.com/meta` git+api+web+packages CIDRs) |
| GitHub CDN / PyPI files | `objects.githubusercontent.com`, `files.pythonhosted.org` | Fastly published ranges (`api.fastly.com/public-ip-list`) |
| npm registry | `registry.npmjs.org` | Cloudflare published ranges (`cloudflare.com/ips-v4`) |

If any required fetch fails during initialization the script exits 1 **before**
applying the default-deny policy, so the container retains open egress rather than
locking itself out of its own dependencies.

### Symptom of a missing destination

A hang or network error when running `uv sync`, `pnpm install`, or any Claude Code
network call usually means a needed host is not in the allowlist (or the
`172.16.0.0/12` db rule is not matching).

To add a destination:

1. Edit `.devcontainer/init-firewall.sh` — add a `resolve_and_add "hostname"` call for
   small/stable hosts, or add a new published-ranges fetch for CDN-backed hosts.
2. Rebuild: `just dc-build`.

### ngrok

ngrok is intentionally not in the allowlist. The container is not designed for
integration tests that need an inbound tunnel. If you need that, add the relevant
ngrok API and tunnel hosts to `init-firewall.sh` and rebuild.

## Phone access (optional)

You can drive the container from your phone using the Claude mobile app's remote
control feature. Inside the container (from `just dc-shell`):

```bash
claude remote-control
```

Scan the QR code with the Claude mobile app. You get the same isolated environment on
your phone. The machine running the container must stay running and connected for the
session to persist.

## Running tests

Inside the container (from `just dc-shell`), use `arx test` normally:

```bash
arx test
arx test world.magic --keepdb
```

From the host, use the `dc-test` recipe:

```powershell
just dc-test
just dc-test world.magic --keepdb
```

## Troubleshooting

**First `just dc-up` is slow** — expected. The image build bakes the entire toolchain.
Subsequent starts skip the build and are much faster.

**Migration failure or db connection error on first start** — the `post-create.sh`
script waits up to 90 seconds for the db service. If the container exits with "db
service did not become ready within 90s", run `just dc-up` again; Docker sometimes
needs a moment on first run.

**Network call hangs or fails inside the container** — a needed host is not in the
firewall allowlist. Check `.devcontainer/init-firewall.sh`, add the host, then
`just dc-build`.

**`permission denied` running the firewall** — the container is missing `NET_ADMIN`
or `NET_RAW` capabilities. Verify the `cap_add` block in
`.devcontainer/docker-compose.yml` is present and that you started via `just dc-up`
(not raw `docker run`).

**Windows `.venv` or `node_modules` errors** — the named-volume shadow is not mounted.
This can happen if the container was started with raw `docker compose up` instead of
`just dc-up`. Run `just dc-down` then `just dc-up` to re-provision.

**`devcontainer: command not found`** — the CLI is not installed. Run:
```powershell
npm install -g @devcontainers/cli
```
Or re-run `.\scripts\bootstrap-devcontainer-host.ps1`.
