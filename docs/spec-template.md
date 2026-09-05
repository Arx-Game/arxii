# Spec template

> **This file is a reference TEMPLATE, not a spec instance.** Real feature specs
> live in the **GitHub issue body** (between `<!-- spec:start -->` and
> `<!-- spec:end -->`), per ADR-0020 — never as a committed file. Copy the sections
> below into the issue body and fill them in; don't commit a filled-out copy here.

Fill in every section. Delete a section only after deciding it genuinely doesn't
apply — don't default to skipping. Use canonical vocabulary from
`AGENT_GLOSSARY_MAP.md` (+ the app's `AGENT_GLOSSARY.md`); check `docs/adr/` for any
decision that already constrains this work.

---

## <Title> (#<issue-number>)

**Status:** spec-draft / spec-review / approved · **Branch:** `<branch>` · **Date:** <YYYY-MM-DD>

### Goal

One or two paragraphs: the problem, who has it, and what "done" looks like in
player- or staff-facing terms. State the outcome, not the implementation.

### Walkthrough (required for anything player- or staff-facing)

Link the demo page (see the `demoing-a-feature` skill), then list its screens in
order, one line each, in the user's words. Every user story below names one of
these screens. Every working assumption the spec makes on an open fork is listed
as pending in Decisions; the reviewer answers in chat, not on the page.

- Demo: <artifact URL>
- Screen 1: <stage> · <what the user does>
- Screen 2: …
- Screen N: what finalize writes (the rows table)

### User Stories

A numbered list, extensive — one line each:

1. As a `<actor>`, I want `<feature>`, so that `<benefit>`.
2. As a `<actor>`, I want `<feature>`, so that `<benefit>`.
3. …

Cover the primary actor and the secondary ones (other players, GM/staff, observers).

### Decisions (user-ratified)

Numbered, stakeholder-approved constraints this spec is built on. Each is a settled
choice the design must respect — link the ADR if one exists, or flag a decision that
should become one.

1. <constraint>
2. <constraint>

### Test seams

Where the feature is exercised. Prefer existing seams; use the **highest** seam
possible; the ideal is **one** (this repo's `action.run()` / dispatch seam, where
telnet and web converge). List the seam(s) and the user journey each covers.

### Verified leak analysis

Privacy / RP-leak prevention is MVP-gating (ADR-0033). Table every surface that
could expose IC or private content and confirm it's contained:

| Surface | What could leak | Contained by |
|---|---|---|
| <surface> | <data> | <mechanism / "n/a"> |

### Anti-reinvention ledger

Run the `verify-against-code` pass. For every new surface the design proposes, state its
**role** first, then label it against the code (not docs/summaries) with file:line evidence:

| Proposed surface | Role (what it lets someone express) | Verdict | Evidence (file:line + caller) |
|---|---|---|---|
| `<surface>` | <what it lets someone express; who sets it, who reads it> | BUILT & WIRED / BUILT, NOT WIRED / ABSENT | `<file:line>`; <caller or "no caller"> |

Prefer reuse-with-extension over build-new; drop any stub whose user goal is already
wired elsewhere. **Caller-absence is never a finding on its own** — a row asserting a
surface is unneeded states its role and what breaks without it.

**Surfaces this change removes or strands** — required whenever the change deletes,
deprecates, replaces or orphans anything. An empty table is fine; an absent one means
the spec isn't finished.

| Removed / stranded | Traced intent | What breaks if it goes |
|---|---|---|
| `<surface>` | <issue / header comment / ADR> | <concrete consequence, or "nothing — superseded by X"> |

### Design

The spec body: models, service functions, actions, flows, API/UI surfaces, and how
they fit the existing architecture. Reference the canonical terms and the relevant
ADRs. Note any new ADR this work should add.

### Testing

The test plan and tier: SQLite fast tier (`just test-fast <app>`) for local
iteration, Postgres parity (CI) for the gate. Prefer big journey/E2E tests over
fine-grained unit tests; add focused unit tests only for fiddly parse/error paths the
E2E doesn't reach.

### Scope / follow-ups

- **In scope:** <what this PR delivers>
- **Deferred:** <out-of-scope items> — verify each deferral's premise against code
  before filing it as an issue (a deferral is a proposed future surface); file
  design-open items as `needs-design` questions, not asserted work.
