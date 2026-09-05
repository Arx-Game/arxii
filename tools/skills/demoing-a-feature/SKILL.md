---
name: demoing-a-feature
compatibility: polytoken
description: Use when drafting the spec for anything a player or staff member will see or operate (a React surface, a CG stage, a telnet verb, an admin flow), before the spec is posted for approval, and whenever the human has asked "what would this look like" or the brainstorm is producing schema before screens.
---

# Demoing a feature

## Overview

For player- and staff-facing work the spec is approved off a **demo page**, not off
prose. The demo shows each screen the user meets, in order, built on the real rows
and the real visual grammar of this repo, and it carries every open design fork as
a control the reviewer can answer. The spec then cites those forks by id. A spec
posted without its demo is not finished.

Why: capable agents rush brainstorming to reach implementation; the spec is thin
exactly where it matters (what the user sees and does), the human gets
implementation detail instead of a feel for the feature, and the built thing gets
redone (#3659). The artifact-driven arcs (#3305, #3540, #3477) did not have that
problem.

**REQUIRED SUB-SKILLS:** `review-artifacts` (the page is a ruling form),
`verify-against-code` (the last screen is the rows finalize writes),
`artifact-design` and `artifact-capabilities` (before writing the page),
`deslop` for any copy that could read as lore.

## The demo page is

In this order, on one artifact, one page:

1. **Masthead.** Issue number first. One paragraph: what the feature is, what the
   reviewer does on this page, what happens after they save.
2. **Rulings.** Every fork the design cannot settle alone, as a collapsed
   `details` with radio, checkbox or textarea controls, recommended option first,
   a stable `data-ruling` id, and one line of why. Cap at about ten. Never a
   question in prose without a control.
3. **The walkthrough.** Three to four screens, in the order the user meets them,
   each captioned `Screen N · <stage> · <what happens>`. Drawn in the project's
   own grammar (for CG that is `frontend/src/character-creation/cg.css`: Cinzel
   labels, EB Garamond body, paper pinned to Arx, realm ink), not a component
   library default. Each screen ends with one small line naming which pieces on it
   already exist and which are new. The last screen is not a screen: it is the
   table of rows finalize writes, each marked existing, extended or new.
4. **Worked cases.** One card per trope, scenario or archetype the shape must
   carry, each with an inline verdict row (`data-optional="yes"`, counted
   separately) and a note box, and a one-line "out of bounds" fence saying what
   the user cannot do here.
5. **Costs and economy.** What each number does, who sets it, and how many rows
   staff must author for the feature to have content. Real counts from the
   database, not estimates.
6. **Schema delta in short.** The ledger's verdict column, one row per surface.
   The full ledger goes in the spec.
7. **Settled, FYI.** Decisions taken without a control, so nothing happens behind
   the reviewer's back.

## Procedure

1. **Inventory before drawing.** Query the real database for the rows the feature
   sits on (with `uv run arx shell`, read-only). Count anchors, catalogs, templates,
   what exists and what is placeholder. In #3660 this found 5 Organizations (4
   placeholders) and 3 Beginnings with no Upbringing, which changed the design
   from "link to anchors" to "authoring economy of anchors".
2. **Survey the code and the visual grammar** (read-only fan-out is fine): the
   models and serializers the screens read, the component tree of the page being
   extended, its CSS tokens, and the ADRs that constrain it.
3. **Write the screens first, then the forks.** Drawing the screen surfaces the
   forks; the forks do not surface the screen. Every control on a screen maps to a
   field in the schema delta or to a ruling.
4. **Copy on the leaf is placeholder for shape.** Say so on the page. Run `deslop`
   on it anyway; no em or en dashes anywhere on the page (grep for both before
   publishing). Never let placeholder names become content rows.
5. **Publish** with `capabilities: {downloads: true}`; the Save handler goes
   through `claude.use("downloads")`, with Copy as the fallback.
6. **Post the spec with the demo link at the top** and every working assumption
   tagged `[ruling: <id>]`. The spec's user stories each name a screen. Flip to
   `status:spec-review`; the demo travels inside that stage, no extra label.
7. **Pick up the rulings file** (`/workspaces/arxii/.claude/rulings/issue-<N>-rulings.json`),
   restate each answer in one line, fold changed assumptions into the spec, then
   wait for `spec:approved`.

## When the human is not in the room

`superpowers:brainstorming` wants one question at a time. When the session is
autonomous, the rulings section **is** that conversation: every question becomes a
control with the recommended answer first, and the page is the message. Do not
block on `AskUserQuestion` for forks a control can carry; do not decide them
silently either.

## Common mistakes

| Mistake | Fix |
|---|---|
| Schema first, screens last, screens drawn from the schema | Draw the screen from the user's side, then derive the fields |
| A page of forty rewrites and four questions in prose | Ten collapsed rulings at the top; per-item verdicts on the items |
| Component-library defaults in the mockup | Read the project's CSS tokens; a CG leaf looks like a CG leaf |
| Placeholder copy that reads as authored lore | Mark it, deslop it, keep names out of content rows |
| Screens with no "what is written" table | The last screen is the finalize row table; it feeds the ledger |
| Deferring forks to "later" in prose | A fork is a ruling or a `needs-design` line, never a promise |
| Filing the demo's gaps as follow-up issues | Fold in or drop; file only separable scope with a stated reason |

## Trial record

First run: #3660 (2026-09-05), demo at
`https://claude.ai/code/artifact/e383d2a0-783e-400b-91c0-aaa8d640ac7d`. Baseline
without this skill: the agent surveyed code for an hour, designed the schema, and
drew the screen last; the ten forks only became explicit when the page forced a
control for each. The existing `status:spec-review` label carried the demo with no
new label.
