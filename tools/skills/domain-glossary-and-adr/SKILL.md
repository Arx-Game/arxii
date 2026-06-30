---
name: domain-glossary-and-adr
compatibility: polytoken
description: Use when introducing or sharpening a domain term, when a design conversation lands a hard-to-reverse decision, or when working in an app whose AGENT_GLOSSARY.md or docs/adr/ needs updating — keeps the glossary and ADR log current and used.
---

# Domain Glossary & ADR

Two living records of *how this game is built and named*: the **glossaries**
(`AGENT_GLOSSARY_MAP.md` + per-app `src/<app>/AGENT_GLOSSARY.md`) hold the ubiquitous
language; **`docs/adr/`** holds the hard-to-reverse decisions and their "why." This
skill keeps both current and used. Pair with `design-vocabulary` for the seam/depth
terms — the ADR log is where the architectural *why* lives, alongside commit messages
and private agent-memory.

## Use the glossary before you design

- Before designing in an app, **read its `src/<app>/AGENT_GLOSSARY.md` and the root
  `AGENT_GLOSSARY_MAP.md`** (cross-cutting terms). Use those *exact* terms in code,
  specs, and ADRs — name models and interfaces after glossary concepts so code reads
  in the ubiquitous language.
- **Challenge a term that conflicts with the glossary.** If a design wants to call a
  thing something the glossary already names differently, that's a flag — converge on
  the canonical term or change the glossary deliberately, never silently fork.
- **Sharpen fuzzy or overloaded terms** to the one canonical word. The map lists
  rejected synonyms under `_Avoid_`; add to it when you retire a near-synonym.

## Keep it current (the tandem rule)

- When you **add or rename a domain concept, update the relevant `AGENT_GLOSSARY.md`
  in the same PR** (per CLAUDE.md "Docs Are Directives"). If the app has no glossary
  yet, create it lazily and link it from `AGENT_GLOSSARY_MAP.md`'s per-app list.
- A glossary is a **glossary only**: each entry says what a term **IS**, not what it
  does. No implementation details, no specs, no procedures — those live in code, system
  docs, and ADRs.

## Offer an ADR sparingly — the three-part bar

Propose an ADR **only when all three hold**:

1. **Hard to reverse** — undoing it later means a migration, a data reshape, or
   rewriting many callers.
2. **Surprising without context** — a newcomer would reasonably do it differently.
3. **The result of a real trade-off** — you chose this over a named alternative for
   stated reasons.

If any leg is missing, it isn't an ADR — it's a code comment, a glossary entry, or
nothing. Most decisions are not ADRs.

When it qualifies, write to `docs/adr/` in the existing one-paragraph format (see
`docs/adr/README.md` and entries like `0001`): a short title, the decision and the
rejected alternative in prose, then a `> Status: … · Source: …` line cross-referencing
the issue/roadmap. **Number = highest existing ADR + 1** (read the directory; don't
compute from memory).

## Spoiler wall

Glossaries and ADRs are **public repo artifacts.** Some domain terms are
spoiler-sensitive: the glossary marks them by giving a neutral definition plus an
`_Avoid_: restating its in-world purpose` note. For such a term, never put the secret
*purpose* it protects — or any in-world ceremonial wording — into a glossary, an ADR, or
a commit message. Name the term and its neutral mechanical surface only; the protected
rationale lives **only in private agent-memory**. When unsure whether a rationale is a
spoiler, leave it out of the repo and keep it in memory.
