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

### Miracles & Divine Intervention (#2360)

Gods spend their accumulated `resonance_pool` on miracles — authored effects that
fire automatically when a high-devotion PC is in danger, and faith-colored Audere
Majora crossings.

**Models** (`worship/models.py`)

- `Miracle` — authored catalog entry: `name`, `being` FK (PROTECT),
  `resonance_pool_cost`, `intervention_trigger` (MiracleTrigger: INCAPACITATED,
  NEAR_DEATH), `favor_threshold`, `narrative_text`, `is_active`, `sort_order`.
  Unique per `(being, name)`.
- `MiracleCapabilityGrant` / `MiracleAppliedCondition` / `MiracleDamageProfile` —
  payload child rows inheriting `Abstract*` bases from `magic/models/techniques.py`.
  Capability-grant rows are **inert** until a future read-path issue is built (mirrors
  `SignatureMotifBonusCapabilityGrant` inertness). `MiracleAppliedCondition` rows are
  the MVP mechanical effect surface.
- `MiraclePerformance` — immutable audit row (miracle, being, target_character,
  scene, resonance_spent, trigger_event, created_at).
- `DivineInterventionConfig` — singleton (pk=1): `favor_threshold` (default 50),
  `cooldown_hours` (default 24), `min_pool_for_intervention` (default 100).
- `MiracleTrigger` (TextChoices in `constants.py`): INCAPACITATED, NEAR_DEATH.

**Services** (`worship/services.py`)

- `spend_worship_pool(being, amount, *, reason)` → bool — the spend counterpart to
  `grant_worship`. Deducts from `resonance_pool` (floor at 0); returns False if
  insufficient. Does NOT create an audit row — the caller creates `MiraclePerformance`.
- `perform_divine_intervention(sheet, being, miracle, *, scene)` → MiraclePerformance —
  the commit seam: spends pool, applies `MiracleAppliedCondition` rows via
  `apply_condition`, creates audit row, broadcasts narrative EMIT.
- `maybe_fire_divine_intervention(character, payload)` — trigger handler: called by
  the `divine_intervention_on_incapacitated` TriggerDefinition's flow step when
  `CHARACTER_INCAPACITATED` fires. Checks favor + pool + cooldown, picks highest-
  priority miracle, calls `perform_divine_intervention`, applies cooldown condition.
- `install_divine_intervention_trigger(sheet, being)` / `remove_divine_intervention_trigger(sheet, being)` —
  installs/removes the `Trigger` row on the character's ObjectDB. Called from
  `bump_devotion` when favor crosses the config threshold. Mirrors Soul Tether's
  trigger installation pattern.

**Trigger lifecycle**: `bump_devotion` calls `install_divine_intervention_trigger`
when `standing.favor >= DivineInterventionConfig.favor_threshold`. The trigger
subscribes to `CHARACTER_INCAPACITATED` (priority 60, above combat escalation's 50).
When the event fires, the flow's `CALL_SERVICE_FUNCTION` step calls
`maybe_fire_divine_intervention`. Per-character cooldown via a timed
`ConditionInstance` ("Divine Intervention Cooldown").

**Seed content** (`worship/factories.py: wire_miracle_content()`): TriggerDefinition +
FlowDefinition, DivineInterventionConfig singleton, "Divine Intervention Cooldown"
ConditionTemplate, example Miracle rows per seeded being. Called from
`seed_worship_content()`.

**Admin**: `MiracleAdmin` (with payload inlines), `MiraclePerformanceAdmin` (read-only
audit), `DivineInterventionConfigAdmin` (singleton).

**API**: `GET /api/worship/miracles/` — staff-facing catalog browser
(`IsAdminUser`). No player-facing API — intervention is automatic.

### Audere Majora Faith Coupling (#2360)

When a faithful character crosses Audere Majora, the ceremony gets faith-specific
vision/manifestation text override + a mechanical bonus. Pool is spent at crossing
time (not offer creation), so a declined offer costs nothing.

**Models** (`magic/audere_majora.py`)

- `AudereMajoraFaithVariant` — per-being ceremony override: `threshold` FK (CASCADE),
  `being` FK → `worship.WorshippedBeing` (PROTECT), `vision_text` (spoiler-private),
  `manifestation_text`, `resonance_pool_cost`, `favor_threshold`, `is_active`.
  Unique per `(threshold, being)`.
- `AudereMajoraFaithVariantCapabilityGrant` / `AudereMajoraFaithVariantAppliedCondition` —
  payload child rows. Capability-grant rows are inert (same as MiracleCapabilityGrant).
  `AudereMajoraFaithVariantAppliedCondition` rows are the MVP bonus surface.
- `PendingAudereMajoraOffer.faith_variant` — nullable FK (SET_NULL), persisted at
  offer creation when a variant qualifies.

**Services** (`magic/audere_majora.py`)

- `maybe_apply_audere_faith_coupling(sheet, threshold, offer)` → variant | None —
  called from `maybe_create_audere_majora_offer` after offer creation. Checks
  DevotionStanding + pool sufficiency; if a variant qualifies, persists it on the
  offer FK and broadcasts the variant's `manifestation_text` (replacing the generic
  threshold text). Does NOT spend the pool — deferred to crossing time.
- `cross_threshold` extended with `offer=` kwarg: after the existing crossing logic,
  if `offer.faith_variant` is set, applies the variant's `AppliedCondition` rows via
  `apply_condition` and spends the pool via `spend_worship_pool` inside the same
  `transaction.atomic()`. Re-checks pool sufficiency (staleness guard); skips bonus
  but completes the crossing if pool is now insufficient.

**Serializer**: `PendingAudereMajoraOfferSerializer.vision_text` — SerializerMethodField;
returns `faith_variant.vision_text` when set, else `threshold.vision_text`.
`AudereMajoraCrossingResultSerializer` adds `faith_coupling_applied` + `faith_being_name`.

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
