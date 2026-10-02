# Polytoken in the devcontainer

[Polytoken](https://docs.polytoken.dev/) is a second coding-agent harness (a
daemon + CLI/TUI) installed alongside Claude Code. It is a separate binary with
its own config and session store.

## What the devcontainer provides

- **Dockerfile** — installs the polytoken binary at image-build time
  (`curl -fsS https://get.polytoken.dev | bash` → `~/.local/bin/polytoken`,
  already on `PATH`, no sudo). Pre-creates `~/.config/polytoken` and
  `~/.local/share/polytoken` so the named volumes inherit `vscode` ownership.
  Upgrade in place with `polytoken update`.
- **docker-compose.yml** — two named volumes persist polytoken across rebuilds:
  - `arxii-polytoken-config` → `~/.config/polytoken` (user config)
  - `arxii-polytoken-data` → `~/.local/share/polytoken` (session history, and
    provider OAuth tokens under `auth/<provider>/<profile>.*`)
- **docker-compose.yml `webproxy`** — a Squid forward proxy for polytoken's
  web tools; see "Web fetch and search" below.
- **init-firewall.sh** — no polytoken-specific entry. The Codex provider talks
  to `chatgpt.com` / `auth.openai.com`, which sit behind Cloudflare, and the
  Cloudflare ranges are already allowlisted. The installer hosts
  (`get`/`dl.polytoken.dev`) are not allowlisted because install happens at
  build time, when egress is unrestricted.

## Configuring the Codex provider (ChatGPT subscription)

Polytoken ships a built-in `codex` catalog provider that uses a ChatGPT plan
through OAuth. User config (`~/.config/polytoken/config.yaml`), verified
against polytoken 0.8.17:

```yaml
default_permission_matcher: bypass   # safe here: sandboxed container + egress firewall
providers:
  codex:
    kind:
      type: catalog
      name: codex
    auth:
      type: codex_device
      profile: default
modelgroups:
  polytoken:default_model_full: codex/gpt-6.1-sol
  polytoken:default_model_mini: codex/gpt-6-luna
```

Then log in from a container shell:

```bash
polytoken auth provider login --provider codex   # prints a URL + code
polytoken auth provider status
```

The **device flow** is the default and it works inside the container: open the
printed URL in a host browser and enter the code. Nothing calls back into the
container. (The `--authorization-code` browser flow needs a localhost callback,
so it does not work here.) If ChatGPT refuses the code, enable device-code
login under ChatGPT Settings → Security.

Prefer the device login to copying a token from the host's `~/.codex/auth.json`.
OpenAI rotates the refresh token on each use, so two clients that share one
token log each other out at the first refresh. A separate device login gives
polytoken its own token.

Notes for 0.8:

- **Model selectors are `<provider>/<model>`** (`codex/gpt-6.1-sol`). List the
  catalog with `polytoken models`; each model also has effort variants such as
  `codex/gpt-6.1-sol(high)` and some have `-1m` context variants.
- **The top-level `defaults:` block is gone.** Default tiers are the reserved
  `polytoken:default_model_full` / `_mini` / `_nano` model groups.
- **Choose models for your plan's quota.** `gpt-6.1-sol` and `gpt-6-luna` are
  much cheaper than `gpt-6-sol`, and `gpt-6-astra` costs the most. Expensive
  models use up a small ChatGPT plan quickly; keep them out of defaults and out
  of model groups that run automatically.
- **Models and default tiers live in the user config only.** Polytoken forbids
  `models` and `defaults` in the project config layer
  (`ProjectLayerModelsAndDefaultsForbidden`); the project layer may define
  `modelgroups`.

Validate with `polytoken config validate --user`, then run
`polytoken --working-dir /workspaces/arxii doctor` (it also loads the project
subagents below).

## Web fetch and search

The egress firewall blocks most of the internet, so `web_fetch` fails
(`error sending request for url`) and `web_search` has no provider. The fix
routes only polytoken's web tools through a proxy; the firewall itself does not
change.

- **`webproxy`** (docker-compose.yml, config in `.devcontainer/webproxy/squid.conf`)
  is a Squid forward proxy that runs outside the app container's firewall. The
  firewall already allows the compose network (172.16.0.0/12), so app reaches
  it as `http://webproxy:3128`. Only ports 80 and 443 are allowed, and nothing
  is cached. No `HTTP(S)_PROXY` variable is set in app, so other tools still
  go through the firewall. **Trade-off:** any process in app that knows the
  address can reach any HTTPS host through it.
- Start it without touching app or db:
  `docker compose -f .devcontainer/docker-compose.yml up -d --no-deps webproxy`.
  A full `just dc-up` starts it with the rest of the stack.
- **Search** uses a hosted provider with an API key (`brave`, `tavily`, `exa`,
  `kagi`, `parallel`, `you`). Put the key in `.devcontainer/dev.env`
  (gitignored). `env_file` is only read when the container is created, so the
  config reads the key from the live bind mount (`/workspaces/arxii/src/.env`)
  instead, which needs `config_command_substitution` (user config only).

Add to the user config:

```yaml
config_command_substitution: true
daemon:
  web:
    http_proxy: http://webproxy:3128
    https_proxy: http://webproxy:3128
integrations:
  search:
    strategy: round_robin
    providers:
      tavily:
        enabled: true
        key: $(sed -n "s/^TAVILY_API_KEY=//p" /workspaces/arxii/src/.env)
```

Validate on a copy before you replace a live config: an enabled search
provider whose key resolves to empty fails validation
(`enabled search provider must configure an API key`), and an invalid user
config stops new sessions from starting.

## Demo pages

Polytoken cannot publish Claude artifacts, and terminal links do not open. The
`demoing-a-feature` skill therefore has polytoken write each demo to
`/workspaces/arxii/.demos/` (gitignored). That folder is on the host bind
mount, so it shows up in the host checkout's `.demos/`; bookmark it as a
`file:///` URL. Do not leave demos in a worktree: `.claude/worktrees/` is the
`arxii-worktrees` volume, which the host cannot see. A spec still needs a
published link, so ask Claude Code to publish the file before review.

## Cross-model review subagents

Polytoken has no built-in "adversarial reviewer model" knob. Cross-model review
is done with **subagents that pin their own model** via `polytoken.model`. Two
project-level subagents ship in the repo at **`.polytoken/subagents/`**:

- **`plan-reviewer.md`** — shadows polytoken's built-in plan reviewer (same name
  → project layer wins). The `plan` facet auto-runs it at the plan→execution
  handoff, so planning gets a cross-model critique for free.
- **`code-reviewer.md`** — an adversarial code/diff reviewer (no shipped
  equivalent). Nothing auto-runs it; invoke it via the `subagent` tool / a
  session prompt ("use the code-reviewer subagent on the current diff").
  Read-only; emits severity-classified findings.

Both pin `model: "@mg:reviewer"`, a model group defined in the project config
**`.polytoken/config.yaml`**:

```yaml
modelgroups:
  reviewer:
    - codex/gpt-6-luna                      # cheap; differs from the gpt-6.1-sol default
    - "@mg:polytoken:default_model_full"   # fallback for any other setup
```

A group uses its first configured entry, so a contributor without a Codex
provider gets their own default full model instead of a startup failure. A
user-layer `reviewer` group replaces this one, so you can choose a different
reviewer model without editing the repo.

Two polytoken rules shape this. Do not work around them:

- **A subagent that names an unknown model stops the daemon from starting**
  (`subagent registry load failed: ... references unknown model`).
  `fallback_models` does not prevent this: the name is checked before any
  fallback is tried. Always pin a group, never a bare model name.
- **A subagent with a group model cannot also set `fallback_models`.** Put the
  fallback in the group.
