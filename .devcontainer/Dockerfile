# Standard Debian/Ubuntu devcontainer base (NOT alpine: musl breaks binary
# Python wheels; NOT the evennia runtime image: it fights our mise toolchain).
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# Firewall + build prerequisites. iptables/ipset/dnsutils are required by
# init-firewall.sh; build-essential for any source wheels.
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
 && apt-get install -y --no-install-recommends \
      iptables ipset dnsutils git curl ca-certificates build-essential sudo \
 && rm -rf /var/lib/apt/lists/*

# The base image ships a non-root "vscode" user. Allow it to run the
# firewall script (and only that) without a password prompt.
RUN echo 'vscode ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh' \
      > /etc/sudoers.d/init-firewall && chmod 0440 /etc/sudoers.d/init-firewall

USER vscode

# Install mise, then bake the project toolchain at build time. Network is
# unrestricted during build, so the runtime firewall never needs mise's
# download hosts. Only mise.toml is copied so the layer caches well.
RUN curl -fsSL https://mise.run | sh \
 && echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
COPY --chown=vscode:vscode mise.toml /tmp/mise/mise.toml
RUN cd /tmp/mise && ~/.local/bin/mise install
