# Intent Provenance skill (design)

**Status:** approved · **Branch:** `worktree-intent-provenance-skill` · **Date:** 2026-07-04

## Goal

Add a new project skill, `intent-provenance`, that formalizes a process gap surfaced
during #708: when an agent finds code with no live caller, the reflexive move is to
label it a speculative stub and defer around it. That's wrong often enough to be
dangerous — `RoomFeatureKindOwnerType` (#708) looked exactly like an unused stub, but
tracing its git history showed it was authored in the *same* PR as the code that was
supposed to consume it, and the original design spec explicitly called for the
wiring that never happened. Absence of a caller means "investigate," not
"assume orphaned."

The skill has two halves:
1. **Reactive** — given an unwired/uncalled surface, trace its origin (git blame →
   introducing commit/PR → linked issue/spec → roadmap/architecture/ADR docs) and
   classify it before deciding what to do with it.
2. **Proactive** — an authoring convention: new classes/functions whose caller isn't
   obvious should say, in their docstring, why they exist and what's meant to call
   them (even if that caller doesn't exist yet), plus the issue/ADR they trace to.

## Relationship to existing skills

- **`verify-against-code`** already labels a surface `BUILT & WIRED` / `BUILT, NOT
  WIRED` / `ABSENT`. This skill is triggered by the `BUILT, NOT WIRED` case — it
  answers "why is this not wired" so `verify-against-code`'s reuse-vs-build decision
  is made on real information, not a guess. `verify-against-code`'s SKILL.md gets one
  new cross-reference line pointing here; no other change to that skill.
- **`domain-glossary-and-adr`** owns the ADR *format* and the three-part bar for when
  something qualifies as an ADR. This skill's classification step, when it concludes
  "this deserves a recorded decision," hands off to that skill rather than
  reimplementing ADR authoring.
- **`architecture-cleanup`** audits for shallow modules/leaky seams; when its sweep
  turns up an orphaned module, it can invoke this skill to classify it before
  recommending removal.

## Design

### Trigger conditions (→ becomes the skill's `description` frontmatter)

Reactive:
- Investigating a class/function/model with no live caller (typically surfaced by
  `verify-against-code`'s `BUILT, NOT WIRED` label).
- Encountering a confusing, seemingly-dead, or undocumented system and needing to
  decide whether it's safe to ignore, worth deleting, or actually load-bearing.
- About to file a deferred follow-up or `needs-design` issue whose premise asserts
  something is "unfinished" or "missing" (this skill supplies the verification step
  `verify-against-code` already requires for deferrals, but doesn't itself describe
  how to perform).

Proactive:
- Writing a new class/function/model whose caller doesn't exist yet, or isn't
  obvious from its name and immediate context.

### The investigation procedure (reactive half)

1. `git log --oneline --follow -- <file>` (or `git log -p -1 --follow -- <file> |
   head` for the earliest commit) to find the introducing commit.
2. Read that commit's message / linked PR description / linked issue for stated
   intent. A PR that introduces both a model and its would-be caller in the same
   changeset, where only the model landed, is the strongest single signal of
   "unfinished," not "abandoned."
3. Check `docs/roadmap/*.md`, `docs/architecture/*.md`, and `docs/adr/` for any
   content tying the surface to a plan or decision.
4. Search open and closed issues referencing the surface or the feature it's part of
   (`gh issue list --search`).
5. Classify — exactly one of:
   - **SUPERSEDED** — a later, identifiable change explicitly replaced it. Cite the
     replacing commit/PR/ADR. Safe to remove, or leave with a comment citing what
     replaced it, per CLAUDE.md's dead-code caution.
   - **ABANDONED** — a recorded decision (ADR, issue closed as won't-do, roadmap note)
     dropped it deliberately. Cite the decision. Safe to remove.
   - **UNFINISHED** — a spec/plan/PR documents intent to wire it, but no code does.
     This is real, already-designed scope: wire it now if it's cheap and touches code
     already being edited (CLAUDE.md "Fold In, Don't File"), or file it as a scoped,
     ready-to-build issue (not `needs-design` — the design already exists in the
     cited source).
   - **UNDESIGNED** — no spec/roadmap/ADR/issue ties to it at all; it exists only
     because someone wrote it (a scratch experiment, a speculative addition with no
     paper trail). File a `needs-design` issue capturing the rediscovered rationale
     (mirrors `verify-against-code`'s existing deferral-filing rule) rather than
     silently building on it or deleting it.
6. **Fix the stale doc, if any, at the source** — if a doc claimed the surface was
   wired when it wasn't (as `docs/systems/INDEX.md` did for `RoomFeatureKindOwnerType`
   in #708), correct it in the same pass, per CLAUDE.md "Docs Are Directives."

### The authoring convention (proactive half)

When writing a new class, function, or model whose caller isn't self-evident, state
in the docstring:
- **Why** it exists (the problem it solves, in one sentence).
- **What's meant to call it** — even a not-yet-built future caller ("the eventual
  generic org-ritual dispatch path — see #1868" is a legitimate answer).
- **The issue/ADR it traces to**, if one exists.

Not required for self-evident code — a getter, a small helper with an immediate
caller in the same commit, anything whose name and one-line docstring already answer
"why" without ambiguity. This is a judgment call, not a lint rule: the bar is "would a
future agent, six months from now, have to redo the investigation procedure above to
answer a question this docstring could have answered in one sentence?"

### Non-goals

- This skill does not replace `verify-against-code`'s reuse-vs-build decision, only
  informs it.
- This skill does not mandate ADRs for everything found via this procedure —
  `domain-glossary-and-adr`'s three-part bar still gates whether a classification
  result becomes an ADR.
- Not a lint rule enforced mechanically; a judgment-call convention like the rest of
  this repo's documentation-in-tandem rules.

## Testing / verification

Documentation-only skill; no automated tests. Verification is: does the skill file
read cleanly, match this repo's existing skill conventions (frontmatter, section
shape, cross-references), and would applying it to the #708 `RoomFeatureKindOwnerType`
case actually produce the UNFINISHED classification that happened in that session
(a worked-example gut-check, not an automated test).

## Scope / follow-ups

- **In scope:** one new skill file, `tools/skills/intent-provenance/SKILL.md`; one
  cross-reference line added to `tools/skills/verify-against-code/SKILL.md`.
- **Deferred:** nothing — this is a complete, self-contained deliverable.
