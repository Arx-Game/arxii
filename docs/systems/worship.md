# Worship & Ceremonies

Gods as authorable data with worship economies (#2355), and ceremonies as
lightly-structured freeform RP bookended by commands (#2289). Specs live in the
issue bodies; the model decision is ADR-0132.

## Worship foundation (`world/worship`, #2355)

**Models**

- `WorshipTradition` — lookup: name, description, `rites_specialization` FK →
  `skills.Specialization`. Bridges a being to the Rites specialization its
  ceremonies roll with. Seeded (PLACEHOLDER names): Church Liturgy,
  Spiritcalling, Druidry, Occultism.
- `WorshippedBeing` — the primitive (ADR-0132): name, PLACEHOLDER description,
  tradition FK, `resonance_pool` (BigInteger, spendable by future miracles
  #2360), `lifetime_worship` (monotonic audit), nullable OneToOne
  `avatar_sheet` → CharacterSheet (rare played gods), `is_active`.
- `WorshipGrant` — audit ledger (being, amount, granted_by sheet, reason).
- `DevotionStanding` — one-way PC→god favor, unique (character_sheet, being).
- `WorshipDeclaration` — OneToOne sheet: `public_being` + `secret_being`
  (both optional) + the minted `secret` FK. Secret worship mints a `Secret`
  (`worship/secrets.py: mint_worship_secret`, mirrors the secret-distinction
  pattern). Set at CG (`CharacterDraft.public_worship`/`secret_worship`,
  created in `_create_worship_declaration` at finalization).

**Services** (`worship/services.py`)

- `grant_worship(being, amount, *, granted_by, reason)` → pool + lifetime +
  ledger row.
- `bump_devotion(sheet, being, amount)` → standing upsert + the God's Favorite
  check: reaching or tying the being's top favor grants the gender-matched
  achievement (God's Favorite Princess / Prince / Chosen; leapfroggers earn it
  too, prior holders keep theirs; text never names the being).
- `gods_favorite_achievement_for(sheet)` — gender-variant row resolution.

**Skill & seeds** (`seeds/worship_content.py`, cluster `worship`)

- Rites skill (Trait-backed, open to all paths) + the four tradition
  specializations; "Ceremony Rites" CheckType (presence + Rites); Devotion
  `Aspect` with `PathAspect(Path of the Chosen)` + `CheckTypeAspect` weights —
  the Chosen's ceremony edge rides the existing aspect formula, no new
  mechanism. The `secret-investigation` consent category seeds with the
  antagonism tree (`seeds/consent.py`, parented under All Antagonism).

**API**: `/api/worship/beings/` — read-only reference catalog (id, name,
tradition name only; pools/avatars never serialized). Sheet identity section
exposes the **public** worship name only.

## Ceremonies (`world/ceremonies`, #2289)

A ceremony bookends freeform RP: open → offerings/speeches (freeform poses
carry the scene) → finish (or abandon). No Scene/Event required — nullable FKs
to both; normally it runs inside them.

**Models**: `CeremonyType` (data rows: Funeral full handler; Blessing/Sermon
renown-only; Wedding/Coronation are later rows, #2358), `Ceremony` (officiant
Persona, TRUE `being` vs `presented_being` — see leak rule, location
RoomProfile, status OPEN/COMPLETED/ABANDONED, one-OPEN-per-location
constraint, quality_level), `CeremonyHonoree`, `CeremonyOffering` (item
snapshot; the item is destroyed; `item_legend_value` snapshots the offered
item's legend at sacrifice time — #2359), `CeremonySpeech`, `CeremonyConfig`
singleton (all magnitudes PLACEHOLDER).

**Services** (`ceremonies/services.py`): `open_ceremony` (Decision-10
being/presented mapping: default = officiant's public declaration; explicit
override naming their `secret_being` = twisted rite presenting the public
front; any other override = open rite), `record_offering` (destroys items via
`hard_delete_item_instance`; snapshots `item.legend_value` before destruction
as `CeremonyOffering.item_legend_value` — #2359; pool always to the TRUE
being; devotion follows belief — Decision 11), `record_speech` (Performance/Oratory roll),
`finish_ceremony` (one Rites + tradition-spec quality roll → multiplier;
honoree deeds via the legend engine's `create_solo_deed`; offering legend
total added to honoree prestige base — #2359; officiant lesser
cut; funeral handler calls the `execute_will` **no-op seam** for #1985),
`abandon_ceremony` (awards nothing), `open_funeral_for` (the ghost-container
lookup).

**Ghost window**: an OPEN funeral honoring a dead character at their location
is the third recognized container in `GhostWindowPrerequisite`
(`actions/prerequisites.py`) alongside the death scene and IC death-day
(ADR-0131; seance #2290 is the remaining hook).

**Twisted-rite leak** (`ceremonies/leak.py`): when the rite secretly serves
the officiant's hidden god, each witness passing the consent gate
(`secret-investigation` category, mirrors `accusation_permitted`) rolls a
hidden Search check; success mints a `Clue` → `CharacterClue` against the
officiant's worship Secret. Failures silent.

**Corpse gear**: `_dead_owner_trusts` in
`flows/service_functions/inventory.py` — a dead owner's items still require
`steal`, unless the dead player's tenure friended the taker (friends-list
trusted handler; direction matters — trust flows from the dead).

**Bounded abandonment**: `ceremonies.auto_abandon` cron
(`game_clock/tasks.py: abandon_stale_ceremonies`, hourly) abandons OPEN
ceremonies whose scene finished, whose event completed/cancelled, or a real
day after opening.

**Actions** (`actions/definitions/ceremonies.py`; registry keys
`ceremony_open` / `ceremony_offering` / `ceremony_speech` / `ceremony_finish` /
`ceremony_abandon`): anyone may officiate — skill shapes the outcome, not
permission; offering/speech/finish are officiant-only, abandon is
officiant-or-staff. Telnet: `ceremony` family (`commands/ceremonies.py`,
switch or space subverbs). Web: read API `/api/ceremonies/ceremonies/`
(filter `location__objectdb` for the game-view room card,
`frontend/src/ceremonies/CeremonyRoomCard.tsx`); verbs ride the generic
action dispatch.

**LEAK RULE**: player-facing surfaces (serializers, command output, card)
render `presented_being` ONLY. The true `being` of a twisted rite never
leaves the model layer except via the clue path.

## Deferred (filed)

Wedding/Coronation types over `Union`/`MarriagePact` (#2358), event
grandeur/prestige investment (#2357), item legend value at offerings (#2359,
**shipped** — `ItemInstance.legend_deeds` M2M + `CeremonyOffering.item_legend_value`
+ finish-tally wiring), miracles +
audere coupling (#2360), post-CG conversion (#2361), getinline queue (#2356);
wills remain #1985 (the `execute_will` seam).
