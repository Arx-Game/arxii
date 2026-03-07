---
name: codebase-indexing
description: Use when models have changed significantly, after migrations, or when cross-app relationship data in docs/systems/MODEL_MAP.md seems stale. Also use when you can't find how systems connect and need to regenerate the model map.
---

# Codebase Indexing

## Overview

Regenerate the auto-generated model relationship map that prevents expensive codebase searches. The map lives at `docs/systems/MODEL_MAP.md` and contains FK relationships, reverse relations, and service function signatures for every Django app.

## When to Regenerate

- After adding/removing models or foreign keys
- After running migrations that change relationships
- When MODEL_MAP.md data doesn't match what you find in source
- When a new app is added to the project

## How to Regenerate

```bash
uv run python tools/introspect_models.py > docs/systems/MODEL_MAP.md
```

The script (`tools/introspect_models.py`) introspects all Django apps and outputs:
- Every model's foreign keys with target app.Model and type (FK/OneToOne/M2M)
- Reverse relations showing what other models point to each model
- Public service function signatures from each app's `services.py`

## Adding New Apps

If a new Django app is created, add its label to the `TARGET_APPS` list in `tools/introspect_models.py`.

## Search Strategy

When looking for how systems connect:
1. **First:** Grep `docs/systems/MODEL_MAP.md` for the model or app name
2. **Second:** Check `docs/systems/INDEX.md` for concept-to-location mapping
3. **Third:** Check per-app `CLAUDE.md` for design rules and patterns
4. **Last resort:** Read source files directly
