---
name: demoing-a-feature
compatibility: polytoken
description: Use when drafting the spec for anything a player or staff member will see or operate (a React surface, a CG stage, a telnet verb, an admin flow), before the spec is posted for approval, and whenever the human has asked "what would this look like" or the brainstorm is producing schema before screens.
---

# Demoing a feature

## Overview

For player- and staff-facing work the spec is approved off a **demo page**, not off
prose. The demo shows each screen the user meets, in order, drawn as if the rows
existed, in the real visual grammar of this repo; how one example is authored in
admin; and several scenarios run through the shape so the reviewer can see where it
holds and where it needs a piece. The reviewer's feedback comes in **chat**, not on
the page (TehomCD, 2026-09-05: a rulings form makes him jump around the data). The
demo is not content: nothing on it is authored data, and its two scoring axes are
how little staff must author and how few decisions a player makes.

Why: capable agents rush brainstorming to reach implementation; the spec is thin
exactly where it matters (what the user sees and does), the human gets
implementation detail instead of a feel for the feature, and the built thing gets
redone (#3659). The artifact-driven arcs (#3305, #3540, #3477) did not have that
problem.

**REQUIRED SUB-SKILLS:** `verify-against-code` (the last screen is the rows
finalize writes),
`artifact-design` and `artifact-capabilities` (before writing the page),
`deslop` for any copy that could read as lore.

## The demo page is

This is the **layout** of the finished page, top to bottom. The authoring order is
different and is in Procedure below (screens first, forks second). One artifact,
one page, no controls:

1. **Masthead.** Issue number first. One paragraph: what the feature is in the
   reviewer's own framing, that the page is examples only, that feedback goes in
   chat. A legend for the coverage chips: exists today, in the posted spec, new
   this round.
2. **The walkthrough.** Two to three screens, in the order the user meets them,
   each captioned `Screen N · <stage> · <what happens>`, followed by one more item
   captioned `Screen N · what finalize writes`, which is a table, not a drawing. Drawn in the project's
   own grammar (for CG that is `frontend/src/character-creation/cg.css`: Cinzel
   labels, EB Garamond body, paper pinned to Arx, realm ink), not a component
   library default. Each screen ends with one small line naming which pieces on it
   already exist and which are new. The finalize table lists each row written,
   marked existing, extended or new; it is the bridge to the ledger in the spec.
   Screens are web screens. When the feature is a play verb (something a player
   does in the world, not an authoring or CG tool), add a ruling asking whether
   telnet parity is required, and say which screens have a telnet equivalent.
3. **How the example is authored in admin.** A table: piece on the screen, admin
   page, model row and fields (each chip-marked today / proposed / new), what you
   edit to change it. End with the row count for one example of this size.
4. **Variety within one container.** When the feature is a set of authored
   options a user picks from (Upbringings on a Beginning, templates, presets),
   show one container offering three or four options of genuinely different
   shape, so the reviewer sees the range the schema carries, not one shape
   generalised.
5. **Scenarios through the shape.** Five to eight cards, each a scenario the
   shape must carry, one row per element with a type chip and a coverage chip,
   and a one-line verdict: holds, or holds with a named addition.
6. **Cheap to author, easy to play.** Two tables: authoring levers and player
   levers, each chip-marked, each saying what it saves. This is where ideas that
   reduce staff rows (shared sets, libraries, filters, defaults) belong.
7. **What the scenarios added to the shape.** One table of pieces, chip-marked,
   ending in a one-sentence statement of the shape.

The open forks go in the **chat message** that delivers the link, one line each,
recommendation first, and in the spec's Decisions section as pending.

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
5. **Publish** with no capabilities; the page is read-only.
6. **Post the spec with the demo link at the top**, its working assumptions on
   open forks listed as pending in Decisions, and each user story naming a
   screen. Flip to `status:spec-review`; the demo travels inside that stage, no
   extra label.
7. **Deliver the link in chat with the open forks**, one line each,
   recommendation first. Expect the reviewer to answer in chat and to widen the
   scenarios; rebuild the page from the feedback and republish to the same URL,
   then fold the answers into the spec and wait for `spec:approved`.

## When the human is not in the room

`superpowers:brainstorming` wants one question at a time. When the session is
autonomous, the chat message that delivers the link **is** that conversation: the
open forks, one line each, recommendation first, so the reviewer can answer them
in a single reply against the page. Do not block on `AskUserQuestion` for forks a
line can carry; do not decide them silently either.

## Common mistakes

| Mistake | Fix |
|---|---|
| Schema first, screens last, screens drawn from the schema | Draw the screen from the user's side, then derive the fields |
| A rulings form on the page | Examples only on the page; forks in the chat message that delivers the link |
| One scenario generalised to every container | Show one container offering several options of different shape |
| Drawing the screen with no admin table | The reviewer authors this; show where every piece lives and what changes it |
| Component-library defaults in the mockup | Read the project's CSS tokens; a CG leaf looks like a CG leaf |
| Placeholder copy that reads as authored lore | Mark it, deslop it, keep names out of content rows |
| Screens with no "what is written" table | The last screen is the finalize row table; it feeds the ledger |
| Deferring forks to "later" in prose | A fork is a ruling or a `needs-design` line, never a promise |
| Filing the demo's gaps as follow-up issues | Fold in or drop; file only separable scope with a stated reason |

## Trial record

First run: #3660 (2026-09-05), demo at
`https://claude.ai/code/artifact/e383d2a0-783e-400b-91c0-aaa8d640ac7d`. Baseline
without this skill: the agent surveyed code for an hour, designed the schema, and
drew the screen last. The first cut put ten rulings as controls at the top and one
trope per card; the reviewer rejected the form ("makes me jump around the data")
and the single-shape generalisation ("one type of structure ... then you're trying
to generalize it"), and asked for an admin authoring summary and several
backgrounds through the shape. The second cut is the layout above. The existing
`status:spec-review` label carried the demo with no new label.
