---
name: brainstorming
description: "Use this before any creative work — creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements, and design before implementation. Drafts the spec into the GitHub issue body for team review."
compatibility: polytoken-only
---

# Brainstorming Ideas Into Designs

Turn ideas into fully formed designs and specs through collaborative dialogue,
then post the spec to the **GitHub issue body** for review. This is the design
gate that prevents the failure mode of building the wrong thing: no code is
written until a design has been presented and approved.

Start by understanding the current project context, then ask questions one at a
time to refine the idea. Once you understand what you're building, present the
design and get user approval, then post it to the issue and **exit** — a member
must apply `spec:approved` before implementation begins.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project, or
take any implementation action until you have presented a design and the user
has approved it. This applies to EVERY project regardless of perceived
simplicity.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A todo list, a single-function utility,
a config change — all of them. "Simple" projects are where unexamined
assumptions cause the most wasted work. The design can be short (a few sentences
for truly simple projects), but you MUST present it and get approval.

## Where the spec lives

**The spec lives in the GitHub issue body**, between `<!-- spec:start -->` and
`<!-- spec:end -->` markers — never as a committed `docs/superpowers/` file.
This is project convention (ADR-0020, reflected in `docs/spec-template.md`):
GitHub-as-truth, no on-disk workflow state, review happens where the issue is.
Preserve the original problem statement above the markers; write the spec
between them via `gh issue edit <N> --body-file`.

This is a **deliberate alteration** of the upstream Superpowers brainstorming
skill, which writes specs to `docs/superpowers/specs/`. Do not do that.

## Checklist

You MUST work through these items in order:

1. **Explore project context** — check files, docs, recent commits, `docs/adr/`,
   `AGENT_GLOSSARY_MAP.md` for canonical terms.
2. **Ask clarifying questions** — one at a time, understand
   purpose/constraints/success criteria.
3. **Propose 2-3 approaches** — with trade-offs and your recommendation.
4. **Present design** — in sections scaled to their complexity, get user
   approval after each section.
5. **Run the `verify-against-code` pass** — for every new surface the design
   proposes, verify against code (not docs/summaries) and label it
   `[BUILT & WIRED]` / `[BUILT, NOT WIRED]` / `[ABSENT]` with file:line + caller
   evidence. This produces the **anti-reinvention ledger**, embedded as a
   section of the spec. A spec without a code-verified ledger is not finalized.
   (Skill at `tools/skills/verify-against-code/`.)
6. **Write the spec into the issue body** — between the `<!-- spec:start -->` /
   `<!-- spec:end -->` markers, using the section layout in
   `docs/spec-template.md`. Preserve the original problem statement above the
   markers.
7. **Spec self-review** — quick inline check (see below).
8. **Dispatch the spec reviewer** — using the prompt at
   `tools/skills/issue-to-merged-pr/spec-document-reviewer-prompt.md`
   (project-local; extends the canonical reviewer with contract-completeness,
   implied-condition, and external-constraint checks). If invoked standalone
   (not via the orchestration skill), run the review inline or via a subagent.
9. **Hand off for spec review and exit** — flip the issue label and post a
   review-request comment (see below). Do NOT proceed to implementation.

## The Process

**Understanding the idea:**

- Check the current project state first (files, docs, recent commits, ADRs).
- Before asking detailed questions, assess scope: if the request describes
  multiple independent subsystems, flag this immediately. Don't spend questions
  refining details of a project that needs decomposition.
- If the project is too large for a single spec, help decompose into
  sub-projects: what are the independent pieces, how do they relate, what order
  should they be built? Then brainstorm the first sub-project through the normal
  design flow. Each sub-project gets its own spec → plan → implementation cycle.
- For appropriately-scoped projects, ask questions one at a time to refine the
  idea.
- Prefer multiple choice questions when possible, but open-ended is fine too.
- Only one question per message — if a topic needs more exploration, break it
  into multiple questions.
- Focus on understanding: purpose, constraints, success criteria.

**Exploring approaches:**

- Propose 2-3 different approaches with trade-offs.
- Present options conversationally with your recommendation and reasoning.
- Lead with your recommended option and explain why.

**Presenting the design:**

- Once you believe you understand what you're building, present the design.
- Scale each section to its complexity: a few sentences if straightforward, up
  to 200-300 words if nuanced.
- Ask after each section whether it looks right so far.
- Cover: architecture, components, data flow, error handling, testing.
- Use canonical vocabulary from `AGENT_GLOSSARY_MAP.md`; reference relevant
  ADRs.
- Be ready to go back and clarify if something doesn't make sense.

**Design for isolation and clarity:**

- Break the system into smaller units that each have one clear purpose,
  communicate through well-defined interfaces, and can be understood and tested
  independently.
- For each unit, you should be able to answer: what does it do, how do you use
  it, and what does it depend on?
- Can someone understand a unit does without reading its internals? Can you
  change the internals without breaking consumers? If not, the boundaries need
  work.

**Working in existing codebases:**

- Explore the current structure before proposing changes. Follow existing
  patterns.
- Where existing code has problems that affect the work, include targeted
  improvements as part of the design — the way a good developer improves code
  they are working in.
- Don't propose unrelated refactoring. Stay focused on what serves the current
  goal.

## After the Design

**Write the spec to the issue body (not a committed file):**

1. Read the current issue body: `gh issue view <N> --json body --jq .body`.
2. Compose the new body: the original problem statement (preserved above the
   markers), then `<!-- spec:start -->`, the spec content using
   `docs/spec-template.md`'s section layout (including the
   **anti-reinvention ledger** from the verify-against-code pass), then
   `<!-- spec:end -->`.
3. Write it back: `gh issue edit <N> --body-file <tmpfile>` (write the composed
   body to a temp file first — `gh` reads the new body from a file more
   reliably than from a shell-quoted argument).

**Spec Self-Review:**
After writing the spec, look at it with fresh eyes:

1. **Placeholder scan:** Any "TBD", "TODO", incomplete sections, or vague
   requirements? Fix them.
2. **Internal consistency:** Do any sections contradict each other? Does the
   architecture match the feature descriptions?
3. **Scope check:** Is this focused enough for a single implementation plan, or
   does it need decomposition?
4. **Ambiguity check:** Could any requirement be interpreted two different ways?
   If so, pick one and make it explicit.
5. **Deferral verification:** Every "deferred" follow-up listed is a proposed
   future surface — verify its premise against code (the same
   verify-against-code pass). Drop it if already built/handled; write design-open
   items as `needs-design` questions, not asserted work.

Fix any issues inline. No need to re-review — just fix and move on.

## Hand off for spec review and exit

This is the exit gate. After the spec is written to the issue and self-reviewed:

1. `gh issue edit <N> --remove-label status:spec-draft --add-label status:spec-review`.
2. Post a comment that @-mentions the review target (default `@TehomCD`;
   configurable to a `@Arx-Game/<team>` handle) and links the spec section.
3. **Exit.** Spec review is async and on a human. Do NOT proceed to plan or
   implementation, and **do NOT apply `spec:approved`** — only a member does
   that.

The agent resumes (in a later invocation) once a member has applied
`spec:approved`; the plan from `writing-plans` is produced then and is
**ephemeral** (worktree-only, never committed).

## Key Principles

- **One question at a time** — don't overwhelm with multiple questions.
- **Multiple choice preferred** — easier to answer than open-ended when
  possible.
- **YAGNI ruthlessly** — remove unnecessary features from all designs.
- **Explore alternatives** — always propose 2-3 approaches before settling.
- **Incremental validation** — present design, get approval before moving on.
- **GitHub is the truth** — the spec lives on the issue, not on disk. No
  committed spec file, no on-disk workflow state.
