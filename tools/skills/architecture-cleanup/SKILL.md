---
name: architecture-cleanup
description: Use when asked to find architectural friction / deepening opportunities in the codebase, or to periodically audit a subsystem for shallow modules and leaky seams. Produces a markdown report of candidate refactors.
---

# Architecture Cleanup

Audit a subsystem for architectural friction — shallow modules, leaky seams,
broken locality — and produce a **ranked markdown report of candidate refactors**.
This skill finds and proposes; it does not refactor unprompted. Pair it with the
`design-vocabulary` skill (its terms are used throughout) and `superpowers:brainstorming`
once a candidate is chosen.

**Markdown only.** This is a headless, telnet-first repo. The report is plain
markdown — no HTML, no Tailwind, no Mermaid, no browser-open ritual. Describe
before/after in prose, with small ASCII sketches where a diagram genuinely helps.
Write it to the OS temp dir (e.g. `$TMPDIR/arch-cleanup-<subsystem>.md`) or print it
inline; do not add files to the repo.

## Process

1. **Read the recorded decisions first.** Open `AGENT_GLOSSARY_MAP.md` (and the
   touched app's `AGENT_GLOSSARY.md`) plus any `docs/adr/` entries covering the area.
   You are auditing against the vocabulary and the decisions already on record — not
   from a blank slate.

2. **Dispatch Explore subagents to walk the subsystem and note friction.** Read-only,
   fan-out. Have them flag, with `file:line`:
   - **Understanding requires bouncing** across many small modules to follow one
     concept (broken locality).
   - **Shallow modules** — interface nearly as large as the implementation;
     pass-through wrappers; helpers that re-expose every internal.
   - **Pure functions extracted only for testability** with no locality benefit (the
     logic's only home is one caller, but it lives apart "to test it").
   - **Leaky seams** — callers that must know the *how* behind a doorway (reaching past
     `dispatch_player_action()` into a backend's internals, depending on ordering the
     interface doesn't promise).
   - **Untested through the current interface** — behaviour reachable only by poking
     internals, a sign the public interface is the wrong shape.

3. **Apply the deletion test** to each candidate (see `design-vocabulary`): would
   deleting/inlining it make complexity *vanish* (it's a pass-through — propose
   removal) or *reappear duplicated across N callers* (it earns its keep — leave it)?

4. **Present candidates as a ranked markdown list.** One block per candidate:

   ```
   ### <short title>   [Strong | Worth-exploring | Speculative]
   - **Files:** path:line, path:line
   - **Problem:** the friction, in design-vocabulary terms (shallow / leaky seam / broken locality)
   - **Solution:** the proposed reshape (deepen the module / move the seam / inline the pass-through)
   - **Benefit:** stated as locality + leverage gained (fewer files to change, smaller interface to learn)
   - **Recommendation:** why this strength; what would raise/lower it
   ```

   Rank by confidence: **Strong** (clear win, low risk), **Worth-exploring** (real
   friction, needs a design pass), **Speculative** (a smell, may not pay off).

5. **On a chosen candidate, switch to design mode.** Run `superpowers:brainstorming`
   and reason with the `design-vocabulary` terms before proposing a concrete change.
   Don't jump from "smell found" to "code edited."

6. **If a candidate contradicts an ADR, flag it explicitly.** Name the ADR, state the
   conflict, and surface it only when the friction is large enough to warrant
   *reopening* the decision — not as a quiet override. A recorded decision is reopened
   in the open, never silently refactored around.

## Guardrails

- Respects the `design-vocabulary` rule: **no renaming "module" to mean "component."**
  Use the concepts (depth, seam, leverage, locality); keep the repo's nouns.
- Report is a proposal for a human to ratify — recommend, don't auto-apply.
- "Shallow" and "for testability only" are *candidates*, not verdicts: stubs and
  extracted helpers can be intentional placeholders mid-development (see CLAUDE.md
  dead-code caution). When in doubt, rank lower and ask.
