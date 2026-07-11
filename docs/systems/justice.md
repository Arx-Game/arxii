# Justice — local law, crime taxonomy, persona pursuit heat (#1765)

**Heat** is *how actively local forces hunt a specific persona in a specific place* —
distinct from `SocietyReputation` (how a group regards you). Laws are per-area data;
knowledge propagation is the accrual engine; jurisdiction scopes everything to the
enforcing society's dominion. ADR-0080 records the jurisdiction decision.

## Models (`world/justice/models.py`, all SharedMemoryModel)

- **`CrimeKind`** — the normalized crime vocabulary (`slug`, `name`, `description`).
  Data rows (seeded via `world/seeds/justice.py`; 2 PLACEHOLDER rows). **CONTENT
  RULE (user-ratified): no sexual crimes of any nature, ever** — see the model
  docstring.
- **`AreaLaw`** — `(area FK, crime_kind FK, heat_weight, exempts, punishment)`.
  One area's posture toward one crime kind; unique per pair. `exempts=True` =
  explicitly legal here despite an ancestor's ban. `heat_weight` doubles as "how
  hard the local authority pursues it" (feudal local paramountcy — the winning
  local row IS the posture). `punishment` is admin-editable flavor (PLACEHOLDER).
- **`DeedCrimeTag`** — `(deed FK → societies.LegendEntry, crime_kind FK)`. Marks a
  legend deed as an instance of a crime. Lives in justice so `societies` stays
  dependency-free (FK specific→general).
- **`PersonaHeat`** — `(persona FK → scenes.Persona, area FK, society FK, value)`.
  One warrant: accumulated pursuit heat for a persona in an area under an enforcing
  society (captured at mint time, so the warrant survives later dominance changes).
  **Deliberately no established-or-primary guard** — TEMPORARY masks soak heat
  (burning the mask sheds pursuit; the cost is a mask holds no reputation/renown).
- **`HeatSource`** — allegation provenance per heat row (`deed` nullable, `amount`).
  Never verifies actorship: a false accusation is a divergence between allegation
  and truth, not a stored flag.
- **`AccusationCrimeClaim`** — `(secret OneToOne → secrets.Secret, crime_kind FK,
  real_deed nullable → societies.LegendEntry)`. The bridge that makes a
  player-authored ACCUSATION secret (frame-jobs, #1825) bite the *justice* system,
  not only reputation. The tier is emergent from the deed: `real_deed` null = a
  **wild L2** (a named crime with nothing underneath → fragile, easily refuted);
  `real_deed` set = an **L3 frame** (a crime that genuinely happened, pinned on
  someone who didn't do it → robust, because refuting it means proving innocence,
  not disproving the crime). Lives justice-side (FK into `secrets.Secret`) so
  `secrets` stays dependency-free (ADR-0010).

## Services (`world/justice/services.py`)

- `law_for(area, crime_kind)` — most-specific-wins up the parent chain (mirrors the
  `locations.effective_value` cascade); `exempts` short-circuits to None. Walks
  `parent` FKs directly (identity-map cheap), **not** the `AreaClosure` matview, so
  it behaves identically on the SQLite test tier.
- `enforcing_society_for(area)` — nearest `Area.dominant_society` walking up.
- `accrue_heat(*, persona, crime_kind, area, deed=None, scale=1)` — the one mint
  path. Judges the law at the knowledge/allegation location; enforcing society =
  nearest dominant society of the *winning law's* area; mints only when the
  location itself lies in that society's dominion (no extradition). Sanctuary (a
  guild-dominated building inside a hot city) and cross-border immunity are the
  same mismatch.
- `accrue_for_deed_knowledge(*, deed, room, new_knower_count)` — the knowledge-seam
  writer; scaled by new knowers. Falloff is **emergent from knowledge locality** —
  no distance math by design (ADR-0080).
- `heat_for(persona, room, *, include_sources=False) -> HeatReading` — the one read
  seam: sums the persona's rows on the room's ancestor chain whose society matches
  the room's own nearest dominant society.
- `associate_heat(*, from_persona, to_persona)` — the outing/identification seam
  (copies warrants; the mask keeps its own). Callers: the mission-report
  association chance today; the #1334 secrets-outing writer later.
- `tag_deed_crimes(deed, crime_kinds)` — idempotent tagging.
- `heat_decay_tick()` — daily cron (`justice.heat_decay` in `game_clock/tasks.py`),
  decays toward zero and deletes cold rows. Magnitudes PLACEHOLDER.
- **Accusation heat bridge (#1825):**
  - `record_accusation_crime(*, secret, crime_kind, real_deed=None)` — attaches (or
    updates, idempotent per secret) the alleged crime to an ACCUSATION secret.
  - `accrue_accusation_heat(*, secret, area, scale=1)` — reads the claim and defers
    to `accrue_heat`, landing heat on `secret.subject_sheet.primary_persona` where
    `area`'s law criminalizes the alleged kind. Returns None if there's no claim,
    no subject persona, or nothing is criminal there.
  - `file_criminal_accusation(*, accuser_persona, subject_sheet, content, crime_kind,
    level=WHISPERS, real_deed=None, area=None, scale=1)` — the one-move composition:
    `secrets.mint_accusation` + `record_accusation_crime` + (when `area` given)
    `accrue_accusation_heat`. Lives justice-side because it depends on both systems
    (justice → secrets is the allowed direction, ADR-0010), keeping `secrets`
    unaware of justice.

## Writers (accrual)

1. **Deed knowledge** — `societies.knowledge_services.grant_deed_knowledge(room=…)`
   calls `accrue_for_deed_knowledge` when word of a crime-tagged deed lands
   somewhere (scene witnesses at deed birth, tellings via spread).
2. **Mission report** — `missions.integrations.crime_watch.flag_crime` (the live
   CRIME_WATCH sink): `MissionDeedRewardLine.ref` = CrimeKind slug → heat against
   the deed-time persona (`MissionInstance.accepted_as_persona` when the actor's,
   else active persona) at the report room + a `bump_society_reputation` sting.
   `ReportStyle.MOSTLY_ACCURATE` runs a dodge check (PROVISIONAL Persuasion) to
   skip both; reporting a masked run barefaced risks the association check.

**Criminality is declared at deed birth** (user-ratified): mission runs tag every
legend entry minted at renown emission with the run's CRIME_WATCH kinds
(`renown_emission._tag_criminal_entries` — the crime belongs to the run, so each
participant soaks their own heat as word of their part spreads), and scene-born
deeds accept `crime_kinds=` on `create_solo_deed` / `create_legend_event`.

## Surfaces (all self-only — leak table on #1765)

- Room desc line (`Room.return_appearance`) + `heat` field on the web room-state
  payload — tier only, nothing rendered when SAFE.
- Safe-now relief line on movement (`Character.at_post_move`) when dropping from
  ≥ HEAT_IS_ON to SAFE.
- `sheet/crime` telnet section + web **Crime** tab (own sheet only) over
  `GET /api/justice/heat/?viewer=<roster-entry>` (`PersonaHeatViewSet` — owner
  validated via `for_account`, scoped via `active_persona_for_sheet`, tiers only).
  `PersonaHeatSerializer` also exposes `society` (id) so the web Reputation tab
  can join heat against its own org/society standing rows client-side (#1446).

## Constants

`HeatTier` ladder (SAFE / TENSE / DANGEROUS / HEAT_IS_ON / EXTREME_HEAT — names user-ratified), `HEAT_TIER_FLOORS`, `tier_for_value`, `DEFAULT_HEAT_WEIGHT`,
`HEAT_DECAY_PER_DAY` — all magnitudes PLACEHOLDER for the tuning pass.

## Deferred (verified against code at spec time)

Guard-encounter spawning (combat domain — no pursuit-NPC surface exists);
#1334 secrets-outing writer (calls `associate_heat`); allied-society warrant
sharing; active heat-clearing (bribe/pardon — #1826); wanted-poster/public-knowledge
surfaces. (Accusation minting + its heat bridge are now **built** — #1825,
`file_criminal_accusation`; a criminal-accusation *player surface* that lets a
player pick a crime kind / anchor a real deed is the next slice.)

## Authored law postures (Apostate, 2026-07-03 — transcribe to AreaLaw when the grid lands)

The kind vocabulary is seeded; law rows await authored `Area` rows. Ratified
postures: **the victim decides the kind at the tagging seam** (assault is a
crime *upon the gentle*; caste transgression is Luxen's khati-touch line; joy
is contraband only for those low enough to prosecute); **weak crowns, strong
local control** — author the interesting rows at duchy/barony level, thin
kingdom defaults. Heat: the abyssal statutes VERY hot wherever they are law;
murder hot everywhere; most else low and target-dependent. Realm sketches:
Luxen outlaws all abyssal practice (capital), sacrilege, and nearly every
pleasure for the lower castes; Umbros/Ariwn/Inferna/Aythirmok outlaw
demon-summoning and unbonded great works, and require puissant-or-greater
abyssal mages to announce themselves with their soul-tether on entry
(failure-to-announce); sacrilege elsewhere is a *local* law only where a
domain is sworn to its god (much of Inferna holds Envala as patron).
