---
name: verify-against-code
description: Use when a feature design, spec, or implementation plan is about to propose a new code surface (model, dataclass, enum, serializer, component, hook, helper, field, endpoint), or when relying on a systems/architecture/roadmap doc's claim about what exists or doesn't — before committing the spec or writing code.
---

# Verify Against Code

## Overview

**Existing code is the only source of truth. Docs are stale hints.** Before you propose building anything new — or accept that something "doesn't exist" — prove it by reading the code and finding (or failing to find) a live caller. Never let a doc, an index, or a prior summary stand in for that proof.

This is the code-verified half of the Anti-Reinvention Pass (CLAUDE.md). It exists because trusting docs over code repeatedly causes the most expensive failure mode in this repo: rebuilding systems that already exist, or designing against fields/flows that don't.

## When to use

- A design/spec/plan introduces ANY new surface (model, dataclass, enum, `TextChoices`, serializer, ViewSet, component, hook, helper, field, endpoint, migration).
- You're about to write "X doesn't exist / isn't built / needs building" — or "X already does this" — based on a doc, `INDEX.md`, `MODEL_MAP.md`, an architecture doc, or your own memory.
- An Explore-agent summary says something is built/not-built and you haven't seen the code.

## The check (per proposed surface)

1. **Read the actual definition** (grep + open the file). Don't infer from a name or a doc.
2. **Find a live caller.** Grep for real usages outside tests/migrations.
3. **Label it** — exactly one:
   - **`[BUILT & WIRED]`** — exists AND has a live caller. *Quote the caller* `file:line`. → reuse it; do not build.
   - **`[BUILT, NOT WIRED]`** — exists, no live consumer (model/stub only). → wire/extend it; do not duplicate.
   - **`[ABSENT]`** — grep + read confirm it genuinely isn't there. → legitimately new.
4. **Docs are hints, never proof.** `INDEX.md` / `MODEL_MAP.md` / architecture & roadmap docs and prior agent summaries can be stale or wrong. Use them to find *where to look*, then confirm against code. A doc claim alone never earns a label.
5. **When a doc is wrong, fix it at the source** as part of this work (correct the stale section + note it), so it stops misleading the next person.
6. **Emit the ledger** (below) and consolidate: prefer **reuse-with-extension** over **build-new**; present consolidations for ratification before committing the spec.

## Anti-reinvention ledger (embed in the spec)

| Proposed surface | Verdict | Evidence (file:line + caller) |
|---|---|---|
| `Thing` | BUILT & WIRED | `app/models.py:120`; called at `app/services.py:88` |
| `OtherThing` | BUILT, NOT WIRED | `app/models.py:200`; no caller found |
| `NewThing` | ABSENT | grep `NewThing` → 0 hits; genuinely new |

## Recurring traps

- A new `AvailableX` / `XDescriptor` / `XAvailability` dataclass mirroring an existing one.
- A new `TextChoices`/`IntegerChoices` overlapping an existing one on a different axis.
- A UI component when `frontend/src/components/ui/` already has the primitive.
- A method on a base class when an existing field already carries the data.
- A boolean field duplicating info derivable from another (e.g. `is_targeted` vs `target_spec is not None`).
- "Derive from `x.y.category`" when no such field exists — confirm the field before designing on it.

## Red flags — STOP and verify against code

- "The doc says it's not built." → Open the code. Docs go stale.
- "The Explore agent said it exists/doesn't." → Did you see the file + a caller?
- "I'll just add a new <surface> for this." → Searched for an existing one first?
- "It's basically greenfield." → Greenfield is a grep result, not a vibe.

| Rationalization | Reality |
|---|---|
| "INDEX/MODEL_MAP/arch doc covers this" | Curated docs lag the code; verify, then fix the doc. |
| "Summary said it's absent" | A summary is a hint; a label needs file:line + caller. |
| "BUILT means I can reuse it" | Only BUILT & WIRED is safe reuse; BUILT-NOT-WIRED may be a stub. |
| "No time to grep" | Rebuilding an existing system costs far more than the grep. |

## Real-world impact

In one 2026-05-29 session, four near-rebuilds traced to trusting docs over code: a `property-capability-action` architecture doc listed built-and-wired models as "Not Built," an agent summary invented a non-existent `obstacles` app, and two frontend issues assumed technique fields/flows that didn't exist (or already did). Each was caught only by reading the code. This skill makes that reading mandatory.
