# Polytoken in the devcontainer

[Polytoken](https://docs.polytoken.dev/) is a second coding-agent harness (a
daemon + CLI/TUI) installed alongside Claude Code. It is a separate binary with
its own config and session store, so it stays fully distinct from the
Claude-Code-via-umans setup.

## What this change adds

- **Dockerfile** — installs the polytoken binary at image-build time
  (`curl -fsS https://get.polytoken.dev | bash` → `~/.local/bin/polytoken`,
  already on `PATH`, no sudo). Pre-creates `~/.config/polytoken` and
  `~/.local/share/polytoken` so the named volumes inherit `vscode` ownership.
- **docker-compose.yml** — two named volumes persist polytoken across rebuilds:
  - `arxii-polytoken-config` → `~/.config/polytoken` (config **and** provider
    credentials — the part that hurts to lose on a rebuild)
  - `arxii-polytoken-data` → `~/.local/share/polytoken` (session history)
- **init-firewall.sh** — allowlists `api.code.umans.ai` (umans's
  Anthropic-compatible endpoint). This same entry also restores durable
  Claude-Code-via-umans access, which the runtime firewall otherwise blocks.
  The installer hosts (`get`/`dl.polytoken.dev`) are **not** allowlisted because
  install happens at build time, when egress is unrestricted.

## Configuring the umans provider

Recommended: run `polytoken config ui` and add a provider. Umans is reached as a
**custom Anthropic-compatible** provider. Equivalent hand-written config
(`~/.config/polytoken/config.yaml`), verified against polytoken 0.3.3's
`schemas app-config` and a live `polytoken exec` smoke test:

```yaml
defaults:
  full: umans-glm-5.2              # a full-class model must be the default
  mini: umans-flash               # fast/cheap model for compaction + permission classifier
providers:
  umans:
    kind:
      type: custom_anthropic_compatible   # tagged object, not a bare string
    url: https://api.code.umans.ai
    protocol: anthropic_messages
    auth:
      type: static_key                     # required discriminator
      key: ${UMANS_API_TOKEN}              # do NOT hardcode the sk-... token here
      format: anthropic_x_api_key
models:
  umans-glm-5.2:
    provider: umans
    provider_name: umans-glm-5.2
    class: full                            # required for custom models
    context_window: 405504                 # umans-side cap; Z.ai native is 1M
    max_tokens: 131071                     # recommended_max_tokens (must be < the 131072 cap)
  umans-flash:                             # mini default — silences mini-fallback warnings
    provider: umans
    provider_name: umans-flash
    class: mini
    context_window: 262144
    max_tokens: 32768                      # recommended_max_tokens for flash
  umans-kimi-k2.7:                         # used by the cross-model review subagents below
    provider: umans
    provider_name: umans-kimi-k2.7
    class: full
    context_window: 262144
    max_tokens: 32768                      # recommended_max_tokens for kimi
```

The `context_window` / `max_tokens` above are umans's own caps per model (GLM-5.2's
context is below Z.ai's native 1M), read from the authoritative
`GET https://api.code.umans.ai/v1/models/info` endpoint — query it for the current
per-model `context_window`, `max_completion_tokens`, and reasoning levels rather
than guessing. **`max_tokens` must be strictly *less than* the model's
`max_completion_tokens`** — umans rejects a request where they're equal
(`max_tokens (131072) is at or above the model's max output tokens`), which is why
each value uses the published `recommended_max_tokens` (one under the cap for
GLM-5.2; 32768 for flash/kimi).

**Models live in the global (user) config only** — polytoken forbids `models` and
`defaults` in the project config layer (`ProjectLayerModelsAndDefaultsForbidden`),
so this block can't be committed to the repo. It lives on the `arxii-polytoken-config`
volume (persists across rebuilds) and is reproduced here as the recovery recipe.

Validate with `polytoken config validate --user` before relying on it.
Polytoken also ships a built-in `umans_messages` protocol, so a catalog-based
provider may be even simpler — `polytoken config ui` is the path of least
resistance.

**Token handling:** the umans token already lives in `~/.umans/config.json`
(`api_token`). Reference it via the `${UMANS_API_TOKEN}` env substitution (set
the var in your local, gitignored env) or paste it through `polytoken config ui`.
Never commit the token.

## Cross-model review subagents (Kimi reviews GLM)

Polytoken has no built-in "adversarial reviewer model" knob — model roles are only
`full` / `mini` / `nano`. Cross-model review is done with **subagents that pin their
own model** via `polytoken.model`. The default full model (`umans-glm-5.2`) does the
work; a reviewer subagent runs on a *different* model (`umans-kimi-k2.7`) so the
critique isn't the author grading itself.

Two project-level subagents ship in the repo at **`.polytoken/subagents/`** (this
directory is in version control and bind-mounted into the container, so it is durable
across rebuilds and shared with every contributor — unlike the global model config
above):

- **`plan-reviewer.md`** — shadows polytoken's built-in plan reviewer (same name →
  project layer wins) but pinned to Kimi. The `plan` facet auto-runs it at the
  plan→execution handoff, so planning gets a cross-model critique for free.
- **`code-reviewer.md`** — an adversarial code/diff reviewer (no shipped equivalent).
  Nothing auto-runs it; invoke it via the `subagent` tool / a session prompt
  ("use the code-reviewer subagent on the current diff"). Read-only; emits
  severity-classified findings.

Both declare `fallback_models: [default_model:full]`, so on any machine where the
global config lacks `umans-kimi-k2.7` they degrade gracefully to the default full
model instead of erroring. Confirm discovery with
`polytoken --working-dir /workspaces/arxii doctor` (look for the subagent count).

## Verified at first `dc-build` (2026-06-29)

All four checks below passed on the first no-cache rebuild after in-flight work
wrapped:

1. ✅ `polytoken --version` → `0.3.3` (binary installed, on `PATH`).
2. ✅ `~/.config/polytoken/config.yaml` writes to the `arxii-polytoken-config`
   volume; the dir is `vscode`-owned and shows as a mount in `/proc/mounts`.
3. ✅ Session history lands under **`~/.local/share/polytoken/sessions/`** (the
   `arxii-polytoken-data` volume), **not** `~/.local/state/polytoken`. **No third
   volume is needed** — the XDG data-vs-state question is settled.
4. ✅ After the firewall reapplies, `api.code.umans.ai` is reachable (a direct
   Anthropic `/v1/messages` call returned a GLM-5.2 message) and `polytoken exec`
   ran a full session through umans, while a non-allowlisted host (`google.com`)
   stayed blocked — confirming default-deny is intact and both harnesses ride the
   one `api.code.umans.ai` allowlist entry.
