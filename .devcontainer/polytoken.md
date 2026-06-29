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
    max_tokens: 131072                     # umans max_completion_tokens for GLM-5.2
```

The `context_window` / `max_tokens` above are umans's own caps for `umans-glm-5.2`
(below Z.ai's native 1M), read from the authoritative
`GET https://api.code.umans.ai/v1/models/info` endpoint — query it for the current
per-model `context_window`, `max_completion_tokens`, and reasoning levels rather
than guessing.

Validate with `polytoken config validate --user` before relying on it.
Polytoken also ships a built-in `umans_messages` protocol, so a catalog-based
provider may be even simpler — `polytoken config ui` is the path of least
resistance.

**Token handling:** the umans token already lives in `~/.umans/config.json`
(`api_token`). Reference it via the `${UMANS_API_TOKEN}` env substitution (set
the var in your local, gitignored env) or paste it through `polytoken config ui`.
Never commit the token.

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
