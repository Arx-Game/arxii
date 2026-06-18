# Investigation & Discovery

**Status:** in-progress — core loop shipped. Epic: #1143. System doc:
[`docs/systems/investigation_and_discovery.md`](../systems/investigation_and_discovery.md).

## Why this matters

Mystery and investigation are the core loop — Arx 1's clue/research system was its most
beloved feature. Arx 2 is built around incremental discovery: hidden lore as a puzzle-box,
clues that always point at something real, and a discovery spine that lore, missions, and
rescues all reuse rather than each reinventing.

## The model

A **clue is a pointer** on three independent axes: a **target** (codex entry / mission /
rescue-a-captive; never empty), an **acquisition** (room search or passive trigger), and a
**resolution** (granted automatically, or won through a collaborative research project).
Every player-facing detail — clue text, difficulties, eligibility, research magnitudes — is
**authored data**, never agent-generated; code ships the mechanism, GMs fill the menu.

## Shipped

- **Clue model** (#1144) — Target-polymorphic pointer; absorbs the old codex `CodexClue`.
- **Investigation skill + Search/Research CheckTypes** (#1145) — seed data.
- **`search` action + declarative AP/fatigue cost on the `Action` base** (#1154 A/B).
- **Eligibility gating** (#1154 C) — predicate access layer over the skill check.
- **RESEARCH project kind** (#1146) — collaborative, AP-funded, floored progress, cron setbacks.
- **Rescue-as-clue** (#931 / #1159) — capture plants a discoverable rescue clue; closes the
  captivity arc.
- **Passive enter-room triggers** (#1160 slice A) — clues revealed on entry by precondition.

## Remaining

- **More trigger sources** (#1160) — item-acquisition / resonance / past-life soul-tie. Needs
  a verify-against-code pass on which predicate leaves exist before designing (likely a
  "flag the holes" moment — resonance probably exists, soul-tie may not).
- **Clue journal UI** — the web surface where players see held clues, known-target flags, and
  pursue research. Frontend; wants a UX design pass.
- **Secret / scandal target kinds** — the social-information targets; informational shapes not
  yet settled (deliberately stubbed in the discriminator).
- **Error-handling service** (#1164) — replace the interim log-and-continue in the trigger
  hooks with a Sentry-style report + user-facing error, per TehomCD's review.

## Design principles

- **No red herrings, no empty clues** — a clue always points at something real; a known
  target is surfaced ("you already know this"), not hidden.
- **Two-layer gating** — capability (the skill check) *and* access (an eligibility predicate);
  magic/threads raise effective capability so gifts light up options without per-gift wiring.
- **Reuse the spine** — search → acquire → resolve is one machine; rescue and research are
  consumers, not parallel systems.
