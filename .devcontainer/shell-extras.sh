#!/usr/bin/env bash
# Interactive-shell setup for the arxii devcontainer.
#
# Installed to /usr/local/share/arxii/shell-extras.sh and sourced from the LAST
# line of ~/.bashrc (see Dockerfile). It must come last because both mise and
# atuin append to PROMPT_COMMAND, and atuin must bind Ctrl-R after fzf does --
# see the keybinding note below.
#
# This file is baked into the image rather than hand-edited in the container:
# /home/vscode is not a named volume (only ~/.claude, ~/.config/polytoken and
# ~/.local/share/polytoken are), so a runtime ~/.bashrc edit is lost on the next
# `just dc-build`. Same rationale as the SHELL/TERM entries in docker-compose.yml.

# Interactive shells only. Guards against `bash -c` / scp / rsync sessions, which
# break if a startup file writes to stdout.
[[ $- == *i* ]] || return 0

# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------
# Debian's defaults (HISTSIZE=1000, HISTFILESIZE=2000) truncate away most of a
# working session. Unlimited is fine here: the file lives on its own named
# volume and is plain text.
HISTSIZE=-1
HISTFILESIZE=-1
# ignoreboth = ignoredups + ignorespace; erasedups also drops older duplicates,
# so repeated `just test-fast ...` invocations collapse to one entry.
HISTCONTROL=ignoreboth:erasedups
HISTTIMEFORMAT='%F %T '
# histappend: never truncate the file on exit. cmdhist: keep a multi-line
# command as one entry rather than one entry per line.
shopt -s histappend cmdhist

# HISTFILE points into the arxii-shell-history volume (docker-compose.yml) so
# history survives `just dc-build`. Without this it lives at ~/.bash_history,
# which is image state and is destroyed on every rebuild.
HISTFILE=/home/vscode/.local/state/arxii/bash_history

# Flush after every command instead of only at exit. Several zellij tabs are
# normally open at once; without this the last shell to exit wins and the other
# tabs' history is silently discarded.
PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }history -a"

# --------------------------------------------------------------------------
# Completions
# --------------------------------------------------------------------------
# Generated at image-build time (Dockerfile) rather than by running
# `gh completion`/`just --completions`/... on every shell start, which would add
# four subprocess spawns to the prompt.
#
# Each file is named after its command and is sourced only when that command is
# actually on PATH. mise puts just/uv on PATH per-directory, so in a shell
# started outside the workspace they are absent -- and `just`'s generated
# completion is a runtime shim (`eval "$(JUST_COMPLETE=bash just)"`) that would
# print "just: command not found" on every such prompt.
if [[ -d /usr/local/share/arxii/completions ]]; then
    for _arxii_completion in /usr/local/share/arxii/completions/*.bash; do
        [[ -r $_arxii_completion ]] || continue
        _arxii_cmd=${_arxii_completion##*/}
        _arxii_cmd=${_arxii_cmd%.bash}
        command -v "$_arxii_cmd" >/dev/null 2>&1 || continue
        source "$_arxii_completion"
    done
    unset _arxii_completion _arxii_cmd
fi

# --------------------------------------------------------------------------
# fzf -- Ctrl-T (insert file path), Alt-C (cd into subdirectory)
# --------------------------------------------------------------------------
# ORDER MATTERS: fzf must load BEFORE atuin. Both bind Ctrl-R to their own
# history search and the last binding wins; with fzf second, fzf's Ctrl-R
# silently shadows atuin's and atuin becomes recall-only. Verified by inspecting
# `bind -X` with each ordering.
if command -v fzf >/dev/null 2>&1; then
    eval "$(fzf --bash)"
fi

# --------------------------------------------------------------------------
# atuin -- Ctrl-R history search, backed by SQLite
# --------------------------------------------------------------------------
# --disable-up-arrow: up-arrow stays vanilla bash history. Atuin's full-screen
#   TUI is deliberate on Ctrl-R but too heavy for a plain "previous command".
# --disable-ai: atuin otherwise binds the bare `?` key to `atuin ai`, an LLM
#   round-trip that would also hit the egress firewall. Nothing here should
#   reach a network service on a keypress.
# Atuin bundles its own copy of bash-preexec (__atuin_load_builtin_preexec), so
# no separate bash-preexec install is needed. Note that bash-preexec calls any
# user-defined preexec/precmd functions: the base image defines a pair for
# terminal titles, but only when TERM is exactly "xterm", and compose pins
# TERM=xterm-256color, so they never load and cannot collide.
if command -v atuin >/dev/null 2>&1; then
    eval "$(atuin init bash --disable-up-arrow --disable-ai)"
fi

# No directory-jumping (`z`) here: that is oh-my-zsh's z plugin, which is
# zsh-only. bash is the fallback shell for `devcontainer exec`, `bash -lc` and
# agent tooling rather than a place anyone navigates by hand, so it is not worth
# a second implementation. Atuin's Ctrl-R is shared between the two shells and
# records cwd, which covers finding your way back to a path from here.
