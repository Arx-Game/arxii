# AGENTS

This repository contains **Arx II**, a sequel to the Arx MUD. It is built on the Evennia framework and Django.

- **Testing**: run the suite with `arx test`. If you haven't activated the virtual environment, use `uv run arx test` instead. Running tests with the plain `python` command can miss dependencies like `typer`.
- **Design goals**: gameplay rules should live in the database. Avoid hardcoding specific mechanics in code. The `flows` system under `src/flows` allows designers to create data-driven tasks. Flows emit events that triggers can listen to and spawn additional flows.
- **Service functions** should be generic utilities. They must not embed hardcoded gameplay logic. Use flows and triggers with data to implement specific rules.
- We want extensive automation to support a narrative driven game world. Player choices should drive automated reactions defined via data.
- **Docstrings**: Use Google style docstrings for Python code. Avoid Sphinx or reStructuredText markup.
- Prefer try/except blocks over hasattr/getattr checks when unsure if an object exposes an attribute.
- Avoid Evennia's lock system for permissions.
- Each object state class should expose small `can_<action>()` methods (e.g., `can_get`, `can_take_from`) for permission checks.
- Commands and handlers must emit an intent event before executing actions so triggers may cancel or modify them.
- Default implementations for permissions (for example, rooms and player characters cannot be "got") live in the relevant object state classes.

Look for additional `AGENTS.md` files in subdirectories for directory-specific guidelines.
