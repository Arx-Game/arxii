#!/usr/bin/env bash
# Chowns the Docker named-volume mountpoints inside the workspace back to
# vscode. Docker creates them root-owned because their target paths
# (/workspaces/arxii/.venv, /workspaces/arxii/frontend/node_modules) are
# sub-paths of a bind mount and so don't exist in the image to inherit
# ownership from. Run once from post-create.sh via NOPASSWD sudo.
set -euo pipefail

for p in /workspaces/arxii/.venv /workspaces/arxii/frontend/node_modules; do
  if [[ -d "$p" ]]; then
    chown -R vscode:vscode "$p"
  fi
done
