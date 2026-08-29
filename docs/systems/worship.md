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
  Chosen patronage fields (#2550): `valence` (nullable PatronageValence:
  DEVOTIONAL/ANTAGONISTIC/PACT — null = ordinary worship), `established_at`
  (when the patronage was established), `released_at` (set when the patron
  released the Chosen — null = active). Favor is the single favor number for
  both ordinary worship and patronage; `bump_devotion` accrues it regardless.
- `WorshipDeclaration` — OneToOne sheet: `public_being` + `secret_being`
  (both optional) + the minted `secret` FK. Secret worship mints a `Secret`
  (`worship/secrets.py: mint_worship_secret`, mirrors the secret-distinction
  pattern). Set at CG (`CharacterDraft.public_worship`/`secret_worship`,
  created in `_create_worship_declaration` at finalization). `public_is_sincere`
  (BooleanField, default True, #2361) — the heart-vs-lip-service inward truth:
  whether the character genuinely believes the public declaration or it's
  performative only. PRIVATE — the sheet identity serializer only shows it to
  the owner/staff (`worship_sincere` in `IdentitySection`, same leak-table
  pattern as `current_mood`); the public record (`worship`) shows the being to
  everyone regardless.
- `ChosenFavorConfig` — singleton (pk=1, lazy-created via
  `get_chosen_favor_config()`). Staff-tunable favor thresholds for Chosen
  benefits (#2550): `anima_recovery_threshold`/`anima_recovery_bonus` (wired —
  the Chosen's anima ritual adds the bonus to recovery budget when favor meets
  the threshold), `ceremony_edge_threshold`/`ceremony_edge_bonus` (deferred —
  defined for shape stability but inert until a future issue wires them).
- `PatronageValence` — TextChoice (DEVOTIONAL/ANTAGONISTIC/PACT). Null on
  DevotionStanding.valence means ordinary worship.

**Services** (`worship/services.py`)

- `grant_worship(being, amount, *, granted_by, reason)` → pool + lifetime +
  ledger row.
- `bump_devotion(sheet, being, amount)` → standing upsert + the God's Favorite
  check: reaching or tying the being's top favor grants the gender-matched
  achievement (God's Favorite Princess / Prince / Chosen; leapfroggers earn it
  too, prior holders keep theirs; text never names the being).
- `gods_favorite_achievement_for(sheet)` — gender-variant row resolution.
- `get_chosen_favor_config()` — lazy-create the singleton (pk=1).
- `active_patronage_for(sheet)` → active patronages (valence set, released_at
  null), ordered by favor descending. Empty list for non-Chosen or a Chosen
  who lost all patrons.
- `best_patronage_favor(sheet)` → the highest-favor active patronage's favor,
  or 0. Read by `apply_anima_ritual_outcome` to gate the anima recovery bonus.
- `establish_patronage(sheet, being, *, valence)` → get-or-create a
  DevotionStanding and mark it as patronage (sets valence/established_at;
  idempotent; preserves existing favor). Called at CG when Path of the Chosen.
- `release_patronage(standing)` → sets `released_at` (graceful degradation —
  the Chosen keeps the Path but this patron's favor no longer gates benefits).
- `convert_public_worship(sheet, new_being, *, is_sincere=True)` → WorshipDeclaration
  (#2361) — the single write path for a post-CG public conversion. Get-or-creates the
  declaration (a first post-CG public declaration is the same code path as a
  conversion), repoints `public_being`, stores the heart-vs-lip-service choice on
  `public_is_sincere`. Never touches `DevotionStanding` (old favor history for either
  being survives untouched) or the secret side (`secret_being`/`secret` — an old
  secret faith's `Secret` row is left standing as history, still discoverable).
  Called from `world.ceremonies.services.finish_ceremony`'s CONVERSION branch.

### Miracles & Divine Intervention (#2360)

Gods spend their accumulated `resonance_pool` on miracles — authored effects that
fire automatically when a high-devotion PC is in danger, and faith-colored Audere
Majora crossings.

**Models** (`worship/models.py`)

- `Miracle` — authored catalog entry: `name`, `being` FK (PROTECT),
  `resonance_pool_cost`, `intervention_trigger` (MiracleTrigger: INCAPACITATED,
  NEAR_DEATH), `favor_threshold`, `narrative_text`, `is_active`, `sort_order`.
  Unique per `(being, name)`.
- `MiracleAppliedCondition` / `MiracleDamageProfile` —
  payload child rows inheriting `Abstract*` bases from `magic/models/techniques.py`.
  (The capability-grant sibling was stripped per ADR-0248 — capability-flavored miracle
  effects are authored as applied conditions.) `MiracleAppliedCondition` rows are
  the MVP mechanical effect surface. `MiracleDamageProfile` inherits
  `execute_missing_health_multiplier` from `AbstractDamageProfile` (#2643, see
  `docs/systems/magic.md`'s "The Damage Identity" section) — default 0, no wiring
  change needed here since it rides the shared column.
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
- `AudereMajoraFaithVariantAppliedCondition` — the payload child row, applied live at
  crossing. (The capability-grant sibling was stripped per ADR-0248.)
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
renown-only; Seance the third ghost-window handler, #2393; Wedding solemnizes
an active Betrothal on finish gated on WeddingConsentOffers, #2358/#2999;
Conversion repoints public worship on finish, #2361; Coronation solemnizes an
already-held title, #2358), `Ceremony` (officiant
Persona, TRUE `being` vs `presented_being` — see leak rule, location
RoomProfile, status OPEN/COMPLETED/ABANDONED, one-OPEN-per-location
constraint, quality_level, nullable `title` FK — CORONATION only),
`CeremonyHonoree`, `CeremonyOffering` (item
snapshot; the item is destroyed; `item_legend_value` snapshots the offered
item's legend at sacrifice time — #2359), `CeremonySpeech`, `CeremonyConfig`
singleton (all magnitudes PLACEHOLDER), `SeanceManifestationOffer` (#2393,
consent gate for a Seance honoree's manifestation), `WorshipConversionOffer`
(#2361, consent gate for a PC-officiated Conversion honoree — see below).

**Services** (`ceremonies/services.py`): `open_ceremony` (Decision-10
being/presented mapping: default = officiant's public declaration; explicit
override naming their `secret_being` = twisted rite presenting the public
front; any other override = open rite; validates honoree counts/liveness per
type — FUNERAL/SEANCE need every honoree dead, CONVERSION needs exactly one
honoree, the convert), `record_offering` (destroys items via
`hard_delete_item_instance`; snapshots `item.legend_value` before destruction
as `CeremonyOffering.item_legend_value` — #2359; pool always to the TRUE
being; devotion follows belief — Decision 11), `record_speech` (Performance/Oratory roll),
`finish_ceremony` (one Rites + tradition-spec quality roll → multiplier;
honoree deeds via the legend engine's `create_solo_deed`; offering legend
total added to honoree prestige base — #2359; officiant lesser
cut; funeral handler calls the `execute_will` **no-op seam** for #1985; WEDDING
handler solemnizes the honorees' active Betrothal; CONVERSION handler calls
`convert_public_worship` per confirmed honoree — see below),
`abandon_ceremony` (awards nothing), `open_funeral_for` (the ghost-container
lookup).

**Public conversion** (#2361, `CeremonyTypeKey.CONVERSION`): two routes reuse
the same generic ceremony action set (Open/Offering/Speech/Finish/Abandon), no
new Action classes for opening/finishing. (a) **PC-officiated**: clergy opens
the rite naming the convert as the sole honoree; `open_ceremony` mints a
`WorshipConversionOffer` (PENDING) since the officiant differs from the
honoree — the convert must accept it (`respond_to_conversion_offer`, the one
new Action: `conversion_offer_respond`) before `finish_ceremony` will convert
them; declining or leaving it unanswered means the rite concludes but honors
nothing for them (no deed, no worship repoint — mirrors a declined Seance
offer). The offer's own delivery surfaces mirror the Seance offer's byte for
byte: REST `/api/ceremonies/conversion-offers/` (`ConversionOfferViewSet`,
list + `accept`/`decline`, accept body takes optional `sincere`), telnet
`conversion` command (`commands/conversion.py`, offers/accept/decline — telnet
accept is always sincere, since there's no syntax slot for the choice there),
and the web `ConversionOfferBanner`/`ConversionOfferDialog`
(`frontend/src/ceremonies/`, mounted in `Layout.tsx` next to
`SeanceOfferBanner`; the dialog's Switch carries the heart-vs-lip-service
choice). (b) **Self-officiated solo** (the temple/no-officiant route): the
convert opens their own rite naming themself as both officiant and honoree —
`open_ceremony` skips the offer entirely (nobody consents to their own
choice); `finish_ceremony`'s optional `sincere` kwarg carries their
heart-vs-lip-service choice directly (defaults True). Both routes converge on
`world.worship.services.convert_public_worship`, called once per confirmed
honoree from `finish_ceremony`'s CONVERSION branch. The minted deed
(`_mint_ceremony_deed`, extended with optional `archetypes`/`scene` kwargs
passed straight through to `create_solo_deed`) carries the existing
"Treacherous Scandal" `PhilosophicalArchetype` (#1464's vocabulary — no new
archetype rows minted) when converting AWAY from an already-declared public
faith, so the ordinary scandal fork (`route_deed_reach`) judges it per
society; a first public declaration (no prior faith to betray) carries no
archetype tag and skips the scandal fork. **No temple/shrine location model
exists in this codebase** (verified by grep — worship has no location
substrate at all), so the solo route is NOT location-gated; it is simply the
self-officiated shape. **No location gate for the temple route** is a known
gap — flag for a future issue if a temple/shrine location primitive is ever
built. `DevotionStanding` rows and the old faith's `Secret` row (if any) are
never touched by a conversion — they stand as history (Decision 3/Ratified
amendment #3 of #2361; the secret-faith retarget/shed services proposed in the
draft spec were explicitly NOT built in this pass — only proven as a no-op).

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

**Wedding & Coronation (#2358).** WEDDING solemnizes a pre-existing
`Betrothal` (`world/societies/houses/pact_services.solemnize_wedding`) —
consent is gated at the CEREMONY, not the proposal: `open_ceremony` mints a
`WeddingConsentOffer` per spouse honoree at START (mirrors
`SeanceManifestationOffer`'s shape, shares `SeanceOfferStatus`);
`finish_ceremony`'s WEDDING branch refuses to solemnize (union + marriage
pact mint) until every offer is ACCEPTED, and a DECLINE
(`respond_to_wedding_consent_offer`, account-scoped) aborts the whole
ceremony via `abandon_ceremony`. CORONATION solemnizes an ALREADY-HELD
`Title` — no title-passing mechanics: `open_ceremony`'s precondition
requires exactly one honoree who holds `title` (or staff/GM fiat — a
non-holder without fiat is the contested-claim case, rejected rather than
auto-resolved), and `finish_ceremony` mints the permanent `Coronation`
record (`honoree_sheet`, `title`, unique together — one-off per title, not
per person: a later coronation for a DIFFERENT title still works). Neither
type adds flat ceremony prestige beyond the shared honoree-renown pass every
ceremony type gets — the event grandeur/prestige-influx pipeline (#2357) is
what drives the real payoff, reading the same ceremony deed this pass
mints. Divorce and the marriage-tier/pact mechanics themselves live in
`docs/systems/houses.md`'s "Org pacts, betrothal & the dossier" section.

**Bounded abandonment**: `ceremonies.auto_abandon` cron
(`game_clock/tasks.py: abandon_stale_ceremonies`, hourly) abandons OPEN
ceremonies whose scene finished, whose event completed/cancelled, or a real
day after opening.

**Actions** (`actions/definitions/ceremonies.py`; registry keys
`ceremony_open` / `ceremony_offering` / `ceremony_speech` / `ceremony_finish` /
`ceremony_abandon` / `seance_offer_respond` / `conversion_offer_respond` /
`wedding_consent_respond`):
anyone may officiate — skill shapes the outcome, not
permission; offering/speech/finish are officiant-only, abandon is
officiant-or-staff. `conversion_offer_respond` (#2361) and
`wedding_consent_respond` (#2358) are account-authorized (mirror
`seance_offer_respond`) — kwargs `offer_id`, `account`, `accept`, plus
`sincere` (bool, conversion-accept only). `ceremony_open` takes `title_name`
for CORONATION (resolved by name; `is_staff_fiat` derives from
`is_staff_observer(actor)`). Telnet: `ceremony` family
(`commands/ceremonies.py`, switch or space subverbs —
`ceremony/wedding <a>,<b>[=<being>]`, `ceremony/coronation <honoree>=<title>`);
`wedding` family (`commands/wedding.py`, mirrors `commands/seance.py`'s
`offers`/`accept`/`decline` shape) answers a pending `WeddingConsentOffer`;
`conversion` family (`commands/conversion.py`, same shape) answers a pending
`WorshipConversionOffer`. Web: read API `/api/ceremonies/ceremonies/`
(filter `location__objectdb` for the game-view room card,
`frontend/src/ceremonies/CeremonyRoomCard.tsx`); verbs ride the generic
action dispatch.

**LEAK RULE**: player-facing surfaces (serializers, command output, card)
render `presented_being` ONLY. The true `being` of a twisted rite never
leaves the model layer except via the clue path.

## Deferred (filed)

Coronation type (Wedding **shipped** — #2358/#2999, solemnizes `Betrothal` →
`Union`/`MarriagePact` on finish), event
grandeur/prestige investment (#2357), item legend value at offerings (#2359,
**shipped** — `ItemInstance.legend_deeds` M2M + `CeremonyOffering.item_legend_value`
+ finish-tally wiring), miracles +
audere coupling (#2360, **shipped**), post-CG public conversion (#2361,
**shipped** — see "Public conversion" above; secret-faith retarget/shed was
explicitly scoped OUT of the #2361 pass, proven a no-op rather than built),
getinline queue (#2356);
wills remain #1985 (the `execute_will` seam).
