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
(`~/.config/polytoken/config.yaml`) for reference:

```yaml
providers:
  umans:
    kind: custom_anthropic_compatible
    url: https://api.code.umans.ai
    protocol: anthropic_messages
    auth:
      key: ${UMANS_API_TOKEN}      # do NOT hardcode the sk-... token here
      format: anthropic_x_api_key
models:
  umans-glm-5.2:
    provider: umans
    provider_name: umans-glm-5.2
    variant: other
    class: full
    context_window: 200000          # confirm GLM 5.2's actual window
```

**Token handling:** the umans token already lives in `~/.umans/config.json`
(`api_token`). Reference it via the `${UMANS_API_TOKEN}` env substitution (set
the var in your local, gitignored env) or paste it through `polytoken config ui`.
Never commit the token.

## Verify at first `dc-build` (deferred until in-flight work is done)

A devcontainer rebuild is the only disruptive step, so it waits until current
sessions are wrapped. On that rebuild:

1. `polytoken --version` resolves (binary installed, on `PATH`).
2. `polytoken config ui` writes to `~/.config/polytoken/` and that dir is on the
   `arxii-polytoken-config` volume (`docker volume ls | grep polytoken`).
3. Start a session, confirm its history lands under `~/.local/share/polytoken`.
   **If sessions land in `~/.local/state/polytoken` instead, add a third volume
   there** — XDG data-vs-state split is unconfirmed.
4. After the firewall reapplies, `polytoken` reaches umans and a fresh
   `claude` (via umans base URL) still works — both ride the one
   `api.code.umans.ai` allowlist entry.
