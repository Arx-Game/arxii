# Proclamations & Stances

Public statements with philosophy-vector reputation effects, riding into domain edicts.

## Overview

Characters issue public **proclamations** aligned to authored **stance
archetypes** — six-axis principle vectors that dot-product against each
society's principles to produce asymmetric reputation deltas. Aligned
societies warm; opposed societies are provoked. The outcome of an
oratory/persuasion check scales the effect: a skilled orator wins allies and
mitigates offense; a failed roll wins nobody and offends fully.

**Domain edicts** ride proclamations: an `EdictKind` carries a mechanical
payload (income percentage, weekly unrest, weekly upkeep) that applies while
a `DomainEdict` is active on a domain.

## Key Models

### `StanceArchetype`
Authored public position on the six principle axes (mercy, method, status,
change, allegiance, power). Sibling of `PhilosophicalArchetype` with the same
field shape but independent vocabulary. Natural key: `name`.

### `Proclamation`
A public statement by a `Persona`, optionally on behalf of an `Organization`.
FKs to `StanceArchetype` (the principle vector) and stores the `CheckOutcome`
name from the issue roll. `prose` is display-only — never parsed by mechanics.

### `EdictKind`
Catalog of domain edicts. Each carries an inherent `StanceArchetype` (the
social bill) plus payload columns: `income_gross_pct`, `weekly_unrest_delta`,
`weekly_upkeep_coppers`. Natural key: `name`.

### `DomainEdict`
An active or revoked edict on a `Domain`. One active per domain — enacting
replaces the current active edict. `is_active` property checks `revoked_at`.

## Service Functions

### `issue_proclamation(persona, stance, *, org=None, prose="", character=None)`
- Rolls oratory/persuasion check (closest seeded CheckType)
- For each society the persona has standing with:
  - **aligned** (dot > 0): reputation gain scaled by success level
  - **opposed** (dot < 0): reputation loss mitigated by success, full on failure
- Creates `Proclamation` row, returns `ProclamationResult`

### `enact_edict(domain, kind, proclamation)`
- Revokes any existing active edict on the domain
- Creates a new active `DomainEdict`

### `revoke_edict(domain)`
- Revokes the active edict, returns it (or `None` if none active)

## Integration Points

- **societies.renown**: `bump_society_reputation` applies the reputation deltas
- **checks.services**: `perform_check` resolves the oratory/persuasion roll
- **tidings**: `PROCLAMATION` feed kind in `FeedItemKind`; proclamations appear
  in `public_feed_for_societies`
- **currency.services**: `accrue_income_stream` applies active edict
  `income_gross_pct`
- **game_clock.tasks**: `_run_edict_effects` weekly processor applies
  `weekly_unrest_delta` and `weekly_upkeep_coppers`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/proclamations/stances/` | List stance archetypes |
| GET | `/api/proclamations/proclamations/` | List proclamations |
| POST | `/api/proclamations/proclamations/issue/` | Issue a proclamation |
| GET | `/api/proclamations/edict-kinds/` | List edict kinds |
| GET | `/api/proclamations/edicts/` | List domain edicts |
| POST | `/api/proclamations/edicts/enact/` | Enact an edict |
| POST | `/api/proclamations/edicts/revoke/` | Revoke an edict |

## Seeds

The `proclamations` cluster (`world.seeds.proclamations`) seeds ~9 stance
archetypes and ~6 edict kinds. PLACEHOLDER vectors and payloads — designer
to tune. Authoritative on reseed (`update_or_create`).
