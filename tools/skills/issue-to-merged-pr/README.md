# issue-to-merged-pr

A Claude Code skill that takes a GitHub issue through to a merged PR with
minimal human gating. Lives in version control so both maintainers use the
same workflow inside the devcontainer.

## What it does

1. **Pickup** — fetches the issue, infers type from labels, creates a
   `<type>-<N>-<slug>` branch.
2. **Design** — runs `superpowers:brainstorming` → spec →
   `superpowers:writing-plans` → plan, unless the issue is small enough
   to skip (chore, docs, dep-bump, typo fixes).
3. **Implementation** — works through the plan.
4. **Sync with main** — rebases, surfaces cross-issue overlap.
5. **Push & PR** — opens the PR with a templated body and links to
   follow-up issues filed during implementation.
6. **CI watch** — polls per a smart cadence (~25 min cap).
7. **CI fix** — reads failure logs, fixes, pushes; bails after 3 same-check
   failures or 5 total pushes.
8. **PR-comment phase** — on re-invocation, reads unread comments via a
   PR-body marker, addresses each, pushes, bumps the marker.
9. **Post-merge cleanup** — checks out main, pulls, deletes the branch
   (squash-merge-aware), verifies linked-issue auto-close.

GitHub holds the workflow truth; no on-disk state to maintain. Multi-
invocation: a typical session does Pickup → Push and exits while CI runs;
re-invoke against the PR to enter later phases.

## Activation

Invoked by Claude Code when the user says something like:
- "work on issue 47"
- "pick up #47"
- "open a PR for the friction-skill rework"

The `description:` frontmatter in `SKILL.md` is what triggers selection.

## Setup

### Devcontainer (primary path)

The skill is automatically symlinked into `~/.claude/skills/` by
`.devcontainer/post-create.sh` on container creation. The same script
also installs the required `superpowers` plugin via
`claude plugin install superpowers@claude-plugins-official`.

No manual setup needed. If you've just pulled a branch that adds this
skill into an existing container, recreate the container
(`just dc-down && just dc-up`) to pick up the symlink.

### Bare-metal

1. Symlink the skill into your Claude skills directory (Linux/macOS):
   ```bash
   ln -sfn "$(pwd)/tools/skills/issue-to-merged-pr" "$HOME/.claude/skills/issue-to-merged-pr"
   ```
   Windows: copy instead of symlink (symlinks need developer mode):
   ```cmd
   xcopy /E /I tools\skills\issue-to-merged-pr %USERPROFILE%\.claude\skills\issue-to-merged-pr
   ```
2. Install the `superpowers` plugin in any Claude Code session:
   ```
   /plugin install superpowers@claude-plugins-official
   ```
   Or from a shell:
   ```bash
   claude plugin install superpowers@claude-plugins-official
   ```
3. Ensure `gh` and `jq` are installed and `gh auth login` is complete with
   a token carrying the scopes listed in the design doc
   (`references/design.md` § "Auth and token").

If you skip step 2, `pickup-issue.sh` will fail fast (exit 2) with the
install command in the error message.

## Design and rationale

See `references/design.md` for
the full design: phase-detection table, CI watch cadence, bail conditions,
cross-issue overlap detection, token scopes, distribution model.

## Updating

Edit files in this directory. In the devcontainer, the symlink picks up
changes instantly — no copy step. On bare-metal, repeat the symlink (or
re-copy on Windows).
