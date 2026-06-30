---
name: design-vocabulary
compatibility: polytoken
description: Use when designing or restructuring a subsystem's interface, deciding where a seam goes, judging whether a class/module earns its keep, or making code more testable — the shared deep-module design vocabulary.
---

# Design Vocabulary

A shared language for talking about interface design in this repo. These are
**concepts, not renames.** "Module" still means a Python module or Django app
submodule; "component", "service", "API", and "boundary" all keep their ordinary
meanings — use them freely. This skill adds vocabulary for *judging* a design; it
does not relabel the nouns we already have.

Every example anchors on the repo's canonical seam: the player-action doorway in
`src/actions/player_interface.py` (`dispatch_player_action()`), with `action.run()`
as one backend it routes to (ADR 0001).

## The concepts

- **Depth** — a lot of behaviour behind a small interface. `dispatch_player_action(actor, intent)`
  is two arguments; behind it sit registry lookup, permission checks, combat/scene
  routing, and effect resolution. A deep doorway: callers say *what they want*, not
  *how it happens*. The opposite — a shallow module — is one whose interface is almost
  as big as its implementation (a pass-through wrapper, a one-line helper exposing
  every internal).

- **Interface** — *everything a caller must know to use it correctly*: not just the
  signature, but invariants, ordering, error modes, and side effects. The action seam's
  interface includes "prereqs run before execution," "it raises on a failed permission
  check," "it emits events the flows engine reacts to." A signature you can call but
  not predict has a hidden interface — that hidden part is real complexity, just
  undocumented.

- **Seam** — a place you can change behaviour *without editing there*. The dispatcher
  is the canonical seam: add a backend, swap a routing rule, or stub the whole call in
  a test, and callers (web and telnet alike) are untouched. A seam is valuable exactly
  when something varies across it.

- **Leverage** — capability delivered per unit of interface a caller must learn. The
  action seam is high-leverage: one small doorway buys every player capability across
  both channels. A helper that exposes ten methods to do what one call could is
  low-leverage.

- **Locality** — change, bugs, and the knowledge needed to reason about something all
  concentrate in one place. Good locality means a change to how combat resolves lives
  inside the combat backend, not smeared across callers. When you find yourself editing
  five files to make one conceptual change, locality is broken.

- **The deletion test** — imagine deleting the module and inlining it at its callers.
  Does complexity *vanish* (it was a pass-through; delete it) or *reappear, duplicated,
  across N callers* (it was concentrating real work; it earns its keep)? Apply this
  before defending — or proposing — any wrapper, helper, or "for testability" extraction.

- **One adapter = a hypothetical seam; two = a real one.** Don't introduce a seam until
  something actually varies across it. A backend interface with a single implementation
  is speculation; the dispatcher earned its seam the moment web *and* telnet both needed
  it. Until the second case is real, the abstraction is cost without leverage —
  YAGNI with a precise test.

## Audience rule

"Seam", "depth", "leverage", "locality" are sanctioned here and in design docs, ADRs,
and skills. In **user-facing prose, lead with the plain principle, not the jargon** —
say "the one shared doorway both web and telnet go through," not "the dispatch seam."
(This reconciles the avoid-impl-jargon discipline: the vocabulary sharpens *our*
thinking; it is not how we explain a feature to a player or a non-engineer.)

## Where the decisions already live

- **`docs/adr/`** records hard-to-reverse design decisions. Before re-arguing where a
  seam goes or why a module is shaped as it is, check whether an ADR already settled it
  (e.g. ADR 0001 on the action seam) — don't re-litigate a recorded decision; if you
  think it's wrong, reopen it explicitly.
- **`AGENT_GLOSSARY_MAP.md`** (and per-app `AGENT_GLOSSARY.md`) hold the domain
  vocabulary. Name modules and interfaces after glossary concepts so the code reads in
  the ubiquitous language — see the `domain-glossary-and-adr` skill.
