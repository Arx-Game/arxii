# AGENTS

This repository contains **Arx II**, a sequel to the Arx MUD. It is built on the Evennia framework and Django.

- **Testing**: always run tests with `uv run arx test` (or `just` wrappers) to ensure the correct environment and dependencies. Using `python` directly can miss packages like `typer`. **For local iteration, use the SQLite fast tier** (`just test-fast <app>`) — the Postgres parity tier (`just test-parity` / bare `arx test`) is too slow for the devcontainer and will time out; let CI run it. See the `running-tests` skill for details.
- **Frontend**: when working on frontend code, run `pnpm typecheck` inside `frontend` in addition to the test suite to catch TypeScript errors early.
- **Git hooks**: do not bypass pre-commit or pre-push hooks with `--no-verify`. The pre-push hook runs `pnpm build` for the frontend; ensure the build succeeds before pushing.
- **Worktrees**: create git worktrees under `.claude/worktrees/` (the `arxii-worktrees` named volume in the devcontainer). Other paths land on the slow 9p bind mount, where a worktree's `uv sync` takes ~10 min instead of <1 s via hardlinks from the colocated `UV_CACHE_DIR`. The `using-git-worktrees` skill enforces this; see `docs/devcontainer-setup.md`.
- **Prettier**: frontend files are formatted via a pre-commit hook that runs `pnpm exec prettier --write`. Run `pnpm install` inside `frontend` so required plugins like `prettier-plugin-tailwindcss` are available. The hook currently fails when only one frontend file is provided; running `pnpm exec prettier <file>` manually works until the hook can be fixed.
- **Design goals**: gameplay rules should live in the database. Avoid hardcoding specific mechanics in code. The `flows` system under `src/flows` allows designers to create data-driven tasks. Flows emit events that triggers can listen to and spawn additional flows.
- **Service functions** should be generic utilities. They must not embed hardcoded gameplay logic. Use flows and triggers with data to implement specific rules.
- We want extensive automation to support a narrative driven game world. Player choices should drive automated reactions defined via data.
- **Docstrings**: Use Google style docstrings for Python code. Avoid Sphinx or reStructuredText markup.
- Prefer try/except blocks over `hasattr` or `getattr` checks when unsure if an object exposes an attribute.
- Avoid unnecessary attribute checks and only catch exceptions the call can raise.
- Never catch broad ``Exception`` types. Only catch specific exceptions you expect.
- Avoid ``getattr`` or ``hasattr`` when possible by exposing properties or methods that resolve attributes directly.
- Avoid Evennia's lock system for permissions.
- Each object state class should expose small `can_<action>()` methods (e.g., `can_get`, `can_take_from`) for permission checks.
- Commands and handlers must emit an intent event before executing actions so triggers may cancel or modify them.
- Default implementations for permissions (for example, rooms and player characters cannot be "got") live in the relevant object state classes.
- When creating migrations, check if Django generated migrations inside Evennia
  packages. If so, point your migration dependencies to the previous migration
  of that app so other environments can apply them without the extra files.

Look for additional `AGENTS.md` files in subdirectories for directory-specific guidelines.
