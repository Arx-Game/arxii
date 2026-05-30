---
name: verify-against-code
description: Use when a feature design, spec, or implementation plan is about to propose a new code surface (model, dataclass, enum, serializer, component, hook, helper, field, endpoint) OR wire up an existing stub (a "not wired" button/endpoint/flow), or when relying on a systems/architecture/roadmap doc's claim about what exists or doesn't — before committing the spec or writing code.
---

# Verify Against Code

## Overview

**Existing code is the only source of truth. Docs are stale hints.** Before you propose building anything new — or accept that something "doesn't exist" — prove it by reading the code and finding (or failing to find) a live caller. Never let a doc, an index, or a prior summary stand in for that proof.

This is the code-verified half of the Anti-Reinvention Pass (CLAUDE.md). It exists because trusting docs over code repeatedly causes the most expensive failure mode in this repo: rebuilding systems that already exist, or designing against fields/flows that don't.

## When to use

- A design/spec/plan introduces ANY new surface (model, dataclass, enum, `TextChoices`, serializer, ViewSet, component, hook, helper, field, endpoint, migration).
- An issue or stub asks you to **wire or build a user-facing action/capability** (a button, command, endpoint, or flow that accomplishes a user goal) — before wiring, verify that same capability isn't already shipped in another surface.
- You're about to write "X doesn't exist / isn't built / needs building" — or "X already does this" — based on a doc, `INDEX.md`, `MODEL_MAP.md`, an architecture doc, or your own memory.
- An Explore-agent summary says something is built/not-built and you haven't seen the code.

## The check (per proposed surface)

1. **Read the actual definition** (grep + open the file). Don't infer from a name or a doc.
2. **Find a live caller.** Grep for real usages outside tests/migrations.
3. **Label it** — exactly one:
   - **`[BUILT & WIRED]`** — exists AND has a live caller. *Quote the caller* `file:line`. → reuse it; do not build.
   - **`[BUILT, NOT WIRED]`** — exists, no live consumer (model/stub only). → wire/extend it; do not duplicate. **A "not wired" surface is a yellow flag, not a to-do:** before wiring it, run the capability check (step 4) — if the same user goal is already `[BUILT & WIRED]` elsewhere, wiring this stub creates a *parallel implementation*; **remove the stub instead.**
   - **`[ABSENT]`** — grep + read confirm it genuinely isn't there. → legitimately new.
4. **Capability check (for user-facing actions).** When the surface performs a *user goal* (a button, command, endpoint, or flow — "commit to a clash", "edit a profile", "lend resources"), restate it as that goal and grep for the goal *already being achievable in another surface* — not just whether this component/type exists. **Two surfaces that accomplish the same user goal are a parallel implementation even when neither's code is literally duplicated.** This is the check that catches a *proposed* duplicate before it's built.
5. **Docs are hints, never proof.** `INDEX.md` / `MODEL_MAP.md` / architecture & roadmap docs and prior agent summaries can be stale or wrong. Use them to find *where to look*, then confirm against code. A doc claim alone never earns a label.
6. **When a doc is wrong, fix it at the source** as part of this work (correct the stale section + note it), so it stops misleading the next person.
7. **Emit the ledger** (below) and consolidate: prefer **reuse-with-extension** over **build-new**; drop any stub whose user goal is already wired elsewhere; present consolidations for ratification before committing the spec.

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
- **Wiring a `NOT WIRED` stub (button/endpoint/flow) for a user goal that's already `BUILT & WIRED` in another surface** — e.g. a *second* "commit to X" UI when one already works. The duplicate is at the *capability* level, not the code level, so a component-existence grep misses it: restate the issue as the user goal and grep for *that*.
- **Recon framed around the proposed mechanism instead of the user goal.** Asking an Explore agent "where is the Commit button / how do I wire it" pre-bakes the build; ask "find EVERY surface that lets the user accomplish &lt;goal&gt; today" so an existing path surfaces.

## Red flags — STOP and verify against code

- "The doc says it's not built." → Open the code. Docs go stale.
- "The Explore agent said it exists/doesn't." → Did you see the file + a caller?
- "I'll just add a new <surface> for this." → Searched for an existing one first?
- "It's basically greenfield." → Greenfield is a grep result, not a vibe.
- "It's just not wired yet, so I'll wire it." → A NOT-WIRED stub may duplicate a WIRED path. Grep the *user goal* first.

| Rationalization | Reality |
|---|---|
| "INDEX/MODEL_MAP/arch doc covers this" | Curated docs lag the code; verify, then fix the doc. |
| "Summary said it's absent" | A summary is a hint; a label needs file:line + caller. |
| "BUILT means I can reuse it" | Only BUILT & WIRED is safe reuse; BUILT-NOT-WIRED may be a stub. |
| "The button exists but isn't wired, so wiring it is the task" | Check the *capability*: if the same user goal is wired elsewhere, wiring this is a parallel impl — delete the stub. |
| "No time to grep" | Rebuilding an existing system costs far more than the grep. |

## Real-world impact

In one 2026-05-29 session, four near-rebuilds traced to trusting docs over code: a `property-capability-action` architecture doc listed built-and-wired models as "Not Built," an agent summary invented a non-existent `obstacles` app, and two frontend issues assumed technique fields/flows that didn't exist (or already did). Each was caught only by reading the code.

The next day, issue #555 ("wire ActiveState's Commit button to dispatch") nearly added a **second** clash-commit path — the capability was already `BUILT & WIRED` in `YourTurn`'s `ClashContributionRow`. The surface-level ledger labeled the button `BUILT, NOT WIRED` and read it as "to-do." It was caught at writing-plans, one stage *after* the anti-reinvention pass — because the pass checked the building blocks, not whether the *user goal* ("commit to a clash") was already achievable elsewhere. The capability check (step 4) + the "NOT WIRED is a yellow flag" rule exist to catch that at spec time. This skill makes that reading mandatory.
