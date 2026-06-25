# Reactive behavior is a separate flows/triggers/events engine

"Something happens when X" — curses, hazards, item reactions, condition decay — is authored as
Events → Triggers → Flows in `src/flows/`, a reactive layer distinct from the action layer that
player intents drive; we rejected inlining reactive effects into Actions. Keeping reaction
data-driven lets designers author it without editing action code.

> Status: accepted · Source: src/flows/, ROADMAP
