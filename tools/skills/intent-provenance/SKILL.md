---
name: intent-provenance
description: Use when a class/function/model has no live caller and you're deciding whether it's a speculative stub, dead code, or unfinished work — or when writing new code whose caller doesn't exist yet. Traces a surface's origin (git history, linked issue/spec, roadmap/ADR) before classifying it, and documents intent forward so the next reader doesn't have to redo the trace.
---

# Intent Provenance

**Absence of a caller means "investigate," not "assume orphaned."** A surface with no
live caller can be superseded, abandoned, genuinely unfinished, or never designed at
all — and only two of those four are safe to write off. This skill traces which one
you're looking at, and teaches the forward-looking habit (documenting *why* a new
surface exists) that makes the next investigation unnecessary.

## Why this exists

During #708, `RoomFeatureKindOwnerType` looked like a classic unused stub — zero
runtime callers anywhere in the codebase. The reflexive read was "speculative, defer
around it." Tracing its git history instead showed it was authored in the *same* PR
as Covenant Sanctification (the code that was supposed to consume it), and the
original approved design spec explicitly specified the eligibility check it was
built for. It wasn't a stub — it was an unfinished wire, and fixing it became real,
correctly-scoped work. The reflex that almost missed this is common enough to be
worth a skill: "no caller" is a question, not a verdict.

## Relationship to other skills

- **`verify-against-code`** labels a surface `BUILT & WIRED` / `BUILT, NOT WIRED` /
  `ABSENT`. This skill is what you run when you land on `BUILT, NOT WIRED` — it
  answers *why* nothing calls it, so the reuse-vs-build decision that skill asks for
  is made on real information instead of a guess.
- **`domain-glossary-and-adr`** owns the ADR format and the three-part bar for when a
  decision qualifies as one. When this skill's classification concludes "this
  deserves a recorded decision," hand off to that skill rather than reinventing ADR
  authoring here.
- **`architecture-cleanup`** audits for shallow modules and leaky seams; when its
  sweep turns up something orphaned, run this skill to classify it before
  recommending removal.

## The investigation procedure (reactive — found something unwired)

1. **Find the introducing commit.** `git log --oneline --follow -- <file>` (or `git
   log -p --follow -- <file> | tail` for the earliest one). This is almost always
   cheaper than guessing.
2. **Read its stated intent.** Open the commit message and, if there is one, the
   linked PR description or issue. A PR that introduces both a model and its
   would-be caller in the same changeset, where only the model actually landed, is
   the strongest single signal of "unfinished" — not "abandoned."
3. **Check for documented pedigree.** `docs/roadmap/*.md`, `docs/architecture/*.md`,
   `docs/adr/` — does anything tie this surface to a plan or a decision?
4. **Search issues.** `gh issue list --search "<surface name>"` (open and closed) —
   is there a tracked discussion this surface came out of, or a follow-up that never
   got picked up?
5. **Classify — exactly one:**

   | Verdict | What it means | What to do |
   |---|---|---|
   | **SUPERSEDED** | A later, identifiable change explicitly replaced it. | Cite the replacement (commit/PR/ADR). Safe to remove, or leave a comment naming what replaced it — don't leave it silently dead. |
   | **ABANDONED** | A recorded decision (ADR, issue closed won't-do, roadmap note) dropped it on purpose. | Cite the decision. Safe to remove. |
   | **UNFINISHED** | A spec/plan/PR documents intent to wire it, but no code does. | Real, already-designed scope. Wire it now if it's cheap and you're already touching the area (CLAUDE.md "Fold In, Don't File"); otherwise file it as a scoped, ready-to-build issue — **not** `needs-design`, since the design already exists in the source you found. |
   | **UNDESIGNED** | No spec/roadmap/ADR/issue ties to it at all. | File a `needs-design` issue capturing the rediscovered rationale (mirrors `verify-against-code`'s deferral rule). Don't build on it and don't delete it — the idea may still be worth having, it just never got its own tracked discussion. |

6. **Fix a stale doc at the source, in the same pass.** If a doc claimed the surface
   was already wired when it wasn't — as `docs/systems/INDEX.md` did for
   `RoomFeatureKindOwnerType` — correct it here, per CLAUDE.md "Docs Are Directives."
   A stale "this is handled" claim is worse than no claim.

## The authoring convention (proactive — writing new code)

When a new class, function, or model's caller isn't self-evident, its docstring
should say:

- **Why** it exists — the problem it solves, in one sentence.
- **What's meant to call it** — even a caller that doesn't exist yet is a legitimate
  answer ("the eventual generic org-ritual dispatch path — see #1868").
- **The issue/ADR it traces to**, if one exists.

Skip this for self-evident code — a getter, a small helper with an immediate caller
in the same commit, anything whose name plus a one-line docstring already answers
"why" without ambiguity. This is a judgment call, not a lint rule. The test: **would a
future agent, months from now, have to run the whole investigation procedure above to
answer a question this docstring could have answered in one sentence?** If yes, write
the sentence now.

## Non-goals

- Doesn't replace `verify-against-code`'s reuse-vs-build decision — only informs it.
- Doesn't mandate an ADR for everything this procedure turns up.
  `domain-glossary-and-adr`'s three-part bar (hard to reverse, surprising, a real
  trade-off) still gates whether a finding becomes one.
- Not mechanically enforced. Like the rest of this repo's documentation-in-tandem
  rules, it's a habit to apply with judgment, not a linter to satisfy.

## Red flags — the reflex this skill exists to interrupt

| Thought | Reality |
|---|---|
| "No caller anywhere, so it's a speculative stub." | Two greps (git log + issue search) tell you whether that's true. Check before writing it off. |
| "This looks unfinished, I'll just delete it." | Unfinished ≠ abandoned. If a spec called for it, deleting it un-does real, already-approved scope. |
| "I can't find a reason for this, so there isn't one." | Absence of a *documented* reason is itself the finding — file it as `needs-design`, don't silently prune the idea. |
| "I'll skip the docstring, the code is self-explanatory." | It's self-explanatory to you, right now, with full context. It won't be to whoever reads it after the caller you had in mind never got built. |
