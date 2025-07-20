# AGENTS

This repository contains **Arx II**, a sequel to the Arx MUD. It is built on the Evennia framework and Django.

- **Testing**: run the suite with `arx test`. If you haven't activated the virtual environment, use `uv run arx test` instead.
- **Design goals**: gameplay rules should live in the database. Avoid hardcoding specific mechanics in code. The `flows` system under `src/flows` allows designers to create data-driven tasks. Flows emit events that triggers can listen to and spawn additional flows.
- We want extensive automation to support a narrative driven game world. Player choices should drive automated reactions defined via data.

Look for additional `AGENTS.md` files in subdirectories for directory-specific guidelines.
