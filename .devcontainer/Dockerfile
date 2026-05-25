# Standard Debian/Ubuntu devcontainer base (NOT alpine: musl breaks binary
# Python wheels; NOT the evennia runtime image: it fights our mise toolchain).
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# Firewall + build prerequisites. iptables/ipset/dnsutils are required by
# init-firewall.sh; build-essential for any source wheels.
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
 && apt-get install -y --no-install-recommends \
      iptables ipset dnsutils jq postgresql-client git curl ca-certificates build-essential sudo \
 && rm -rf /var/lib/apt/lists/*

# Install our firewall script at a non-colliding path. The claude-code
# devcontainer feature ships its own /usr/local/bin/init-firewall.sh that
# runs *after* this Dockerfile, so if we used the same path the feature
# would silently overwrite ours. Our version (a) pre-fetches IP ranges
# before lockdown and (b) explicitly never flushes the nat table, which
# the upstream version does — flushing nat breaks Docker's embedded DNS
# resolver and the next firewall reapply can't recover. Keep paths
# distinct and reference this path explicitly from postStartCommand.
COPY --chown=root:root .devcontainer/init-firewall.sh /usr/local/bin/arxii-firewall.sh
COPY --chown=root:root .devcontainer/fix-volume-perms.sh /usr/local/bin/fix-volume-perms.sh
RUN chmod 0755 /usr/local/bin/arxii-firewall.sh /usr/local/bin/fix-volume-perms.sh

# The base image ships a non-root "vscode" user. Allow it to run the
# firewall script and the volume-perms fix (and only those) without a
# password prompt.
RUN printf '%s\n' \
      'vscode ALL=(root) NOPASSWD: /usr/local/bin/arxii-firewall.sh' \
      'vscode ALL=(root) NOPASSWD: /usr/local/bin/fix-volume-perms.sh' \
      > /etc/sudoers.d/devcontainer-helpers \
 && chmod 0440 /etc/sudoers.d/devcontainer-helpers

USER vscode

# Pre-create the Claude home dir as the vscode user so the arxii-claude-home
# named volume (mounted here in compose) inherits vscode ownership on first
# use. Otherwise Docker creates the mountpoint root-owned and `claude` login
# cannot write its credentials.
RUN mkdir -p /home/vscode/.claude

# Install mise, then bake the project toolchain at build time. Network is
# unrestricted during build, so the runtime firewall never needs mise's
# download hosts. Only mise.toml is copied so the layer caches well.
RUN curl -fsSL https://mise.run | sh \
 && echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc \
 && echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bash_profile
COPY --chown=vscode:vscode mise.toml /tmp/mise/mise.toml
# Python 3.13.0 predates mise's GitHub attestation publishing, so skip that
# check during the build. Other tools in mise.toml still verify normally.
RUN cd /tmp/mise && ~/.local/bin/mise trust \
 && MISE_PYTHON_GITHUB_ATTESTATIONS=false ~/.local/bin/mise install
