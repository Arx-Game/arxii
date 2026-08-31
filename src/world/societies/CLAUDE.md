# Societies System - Social Structures and Reputation

Social structures (Societies, Organizations) with reputation and legend tracking for character personas. Characters interact with the social world through their Personas (identities).

**Note:** Realm model is defined in `realms` app - Society has a FK to `realms.Realm`.

## Key Files

### `models.py`
- **`Society`**: Social groupings within a Realm with 6 principle axes - uses SharedMemoryModel
- **`OrganizationType`**: Templates defining rank titles for organization categories - uses SharedMemoryModel
- **`Organization`**: Specific groups within societies (families, guilds, gangs) - uses SharedMemoryModel
- **`OrganizationRank`**: A single rung on an organization's five-tier rank ladder - uses SharedMemoryModel
- **`OrganizationMembershipOffer`**: Pending or resolved invitation/application to join an organization - uses SharedMemoryModel
- **`OrganizationMembership`**: Links Persona to Organization with an `OrganizationRank` rung; active rows have `left_at` and `exiled_at` null
- **`OrganizationOffice`** (#2239): A named portfolio (`slug`, `title`, `holder` Persona, optional `feeds_check` Trait) orthogonal to rank — "Minister of the Domains". A leader appoints/vacates it; reusable for any "who runs X for this house" role. `feeds_check` is the declared trait the office is meant to lend to the checks it stewards (schema only — the check-lending wiring is a follow-up; a live `perform_check` needs an online character actor + a CheckType, not a Trait on a possibly-offline holder).
- **`SocietyReputation`**: Reputation standing with a society per-persona
- **`OrganizationReputation`**: Reputation standing with an organization per-persona
- **`LegendSourceType`**: Categories of legend-generating events (combat, story, discovery, etc.) - uses SharedMemoryModel
- **`SpreadingConfig`**: Singleton server-wide config for spreading mechanics - uses SharedMemoryModel
- **`LegendEvent`**: Group events that generate deeds for multiple participants
- **`LegendEntry`**: Individual deeds with base_value, spread cap, active flag, optional event/scene/story FKs
- **`LegendSpread`**: Spreading actions that add value to entries, clamped to spread cap
- **`LegendDeedStory`**: Player-written narratives for deeds (one per author per deed)
- **`CharacterLegendSummary`**: Materialized view for fast character legend totals (managed=False)
- **`PersonaLegendSummary`**: Materialized view for fast persona legend totals (managed=False)
- **`LegendLevelCalibration`** (#3466): Per-level dials for honoring a deed and deed-granted
  titles (`honor_hares_required`, `honor_value_added`, `deed_title_threshold`). Authored
  content, deliberately unguarded lookups (a missing row raises, surfacing on the admin
  required-content panel rather than silently mispricing an honor) - uses SharedMemoryModel
- **`LegendHonor`** (#3466): One paid, written testimony to one deed - who honored it, the
  Hares spent, the value actually added (post-ceiling clamp), whether this honor established
  the deed. Distinct from `LegendDeedStory`, the free account anyone may write. Story-
  significant, never hard-deleted; struck via the deed's `is_active` flag instead

### `services.py`
- **`create_solo_deed()`**: Create a deed not tied to an event
- **`create_legend_event()`**: Create a shared event with deeds for multiple personas
- **`spread_deed()`**: Record a spread, clamped to remaining capacity
- **`spread_event()`**: Spread all active deeds in an event
- **`get_character_legend_total()`**: Fast lookup via materialized view
- **`get_persona_legend_total()`**: Fast lookup via materialized view

### `membership_services.py`
- **`ensure_default_rank_ladder()`**: Create the default five-tier `OrganizationRank` ladder for a generic organization (covenants are skipped)

### `obligation_services.py` (#2428)
- **`settle_obligation(obligation, token)`**: settle an OWED `OrganizationObligation` by redeeming a Golden Hare (`currency.FavorTokenDetails`) to the creditor org; stamps `settled_at`/`settled_by_token`. Settled rows are history — never deleted. **Live caller** (whole-branch fix): `world.npc_services.effects.run_settle_obligation_offer`, dispatched by the Academy Registrar's ungated `OfferKind.SETTLE_OBLIGATION` offer (`world.npc_services.seeds.ensure_academy_registrar_role`) — this is the in-game front door that lets an Unbound Prospect pay off the debt.
- **`has_open_obligation(sheet, org)`**: cheap `.exists()` gate used by training/access flows (#2440).
- `OrganizationObligation` (models.py) is a **character→org personal debt** (e.g. Academy entrance); distinct from `currency.OrgObligation`, the org↔org percent-of-income tithe (#926).
- **CG-finalize hook lives in `character_creation`, not here** (#2428 Task 3):
  `world.character_creation.services._finalize_academy_entrance_obligation`
  creates the row (`OWED` for Unbound, `SETTLED_BY_SPONSOR` otherwise) against
  the "Shroudwatch Academy" org seeded by
  `world.seeds.character_creation.ensure_shroudwatch_academy`
  (`tradition=None` — deliberate NULL, #2426 ruling).

### `office_services.py` (#2239)
- **`appoint_office(*, organization, slug, holder, title="", feeds_check=None)`**: install/replace an office holder (idempotent per org+slug)
- **`vacate_office(*, organization, slug)`**: clear the holder (no-op when absent)
- **`office_holder(organization, slug)`** / **`holds_office(persona, organization, slug)`**: read seams. Domain management (`houses.services.can_administer_domain`) gates on `holds_office` for the `domain-steward` slug.

### `honors.py` (#3466)
The Rite of Honors. **`honor_deed(*, character_sheet, ritual, honoree_persona, deed=None,
event=None, deed_title=None, journal_title, journal_body, **kwargs)`** — the ritual's
`SERVICE`-dispatched target (`HONORS_SERVICE_PATH`), spending Golden Hares and a public
journal entry to raise a witnessed deed's `base_value`, or to establish a fresh solo deed
under an event that never credited it. Runs all eligibility and affordability checks inside
one `transaction.atomic()` before any write. Every raise is a `HonorRefused` subclass
carrying a player-safe `user_message`. Sized within the ceiling the anchoring `LegendEvent`
already proved (**ADR-0251** — never above it), unrestricted by life-state (honoring the
dead is by design, #3466 Decision 7). See `docs/systems/societies.md`'s Legend System
section for the ceiling rule in full.

### `seeds.py` (#3466)
**`ensure_rite_of_honors_ritual()`**: idempotent `authored_or_sample` lookup/seed of the
"Rite of Honors" `magic.Ritual` row — `SERVICE` execution kind dispatching to
`HONORS_SERVICE_PATH`, single-actor, `hedge_accessible=False` (a Gifted rite by ruling: the
Golden Hare cost doesn't change who may speak it). `RITE_OF_HONORS_NAME` is the natural-key
constant both this seed and telnet's `ritual.py` lookup share.

### `types.py`
- **`ReputationTier`**: Enum mapping hidden reputation values to named tiers

## Principles System

Six value axes on a -5 to +5 scale. Organizations can override society values.

| Principle | Negative (-5) | Positive (+5) |
|-----------|---------------|---------------|
| Mercy | Ruthlessness | Compassion |
| Method | Cunning | Honor |
| Status | Ambition | Humility |
| Change | Tradition | Progress |
| Allegiance | Loyalty | Independence |
| Power | Hierarchy | Equality |

## Reputation System

Hidden -1000 to +1000 values displayed as named tiers:

| Tier | Range |
|------|-------|
| Reviled | -1000 to -750 |
| Despised | -749 to -500 |
| Disliked | -499 to -250 |
| Disfavored | -249 to -100 |
| Unknown | -99 to +99 |
| Favored | +100 to +249 |
| Liked | +250 to +499 |
| Honored | +500 to +749 |
| Revered | +750 to +1000 |

Reputation is normally driven by deeds (`fire_renown_award`). Two **public application seams** in
`renown.py` let other systems (e.g. the secret reveal→reputation bridge, #1429) feed it directly:
- `apply_archetype_society_reputation(persona, societies, archetypes)` — the diffuse channel:
  archetype dot-product against each society's principles; one delta per society.
- `bump_organization_reputation(persona, organization, delta)` — the relational channel: a direct
  clamped `OrganizationReputation` hit, independent of the org's philosophy.
- `bump_society_reputation(persona, society, delta)` — the relational channel for Society,
  symmetric with `bump_organization_reputation`: a direct clamped `SocietyReputation` hit,
  independent of the society's principles (#1760).

## Organization Types

Six standard types with default rank titles (1=highest, 5=lowest):
- `noble_family`: Traditional noble houses
- `commoner_family`: Non-noble family structures
- `business`: Commercial enterprises
- `guild`: Professional associations
- `secret_society`: Clandestine organizations
- `gang`: Criminal organizations

## Legend System

**The bar: would bards make songs about this?** (#3463, ADR-0249)

Legend is **settled at the end of a story unit**, never minted at the moment of an
act. `legend_settlement.settle_legend_for` is the one seam that prices a deed, and
it applies four rules in order:

1. **Per-person peril floor** — each earner's risk priced against their OWN level
   (`SettlementParticipant.personal_risk`), not the party average. Below
   `LegendSettlementConfig.risk_floor` they mint **zero**, not a reduced award. A
   level-10 who obliterates level-1 mooks earns nothing while the level-1 beside
   them earns, from the same lethal scene.
2. **Held-objective share** — the shared deed pays the severity-weighted fraction
   of stakes actually held. Beat the monsters, lose the town, get paid for the
   monsters.
3. **Station** — `min(earner level, threat level)`, stamped as
   `LegendEntry.earned_at_level`. **Not** folded into `base_value`: the tale is
   worth the same whoever tells it, and `station_multiplier()` is applied on read
   by `LegendRequirement`, so retuning never requires recomputing history.
4. **Standout pass** — a crucial contribution resolved brilliantly pays a solo
   deed even on a LOST unit (ADR-0122, generalized past `Battle`).

`LegendContribution` is the ledger settlement reads: what each character did during
a staked unit, written at the `perform_check` chokepoint. Its `success_level` is
**server-only** — never serialize it to another player.

**Dependency direction:** `societies` is the reusable primitive. The seam takes
system-agnostic inputs; `stories`/`battles`/`missions` each adapt their own world
into it (ADR-0010). `world.stories.services.legend_settlement` is the
stakes-contract adapter.

**Every number is authored**, with the Python constants demoted to fallbacks:
`RiskCalibration.legend_award` (what a risk tier pays), `RenownMagnitudeAward`
(fame/prestige per magnitude), `LegendSettlementConfig` (peril floor + standout
dials). All four surface on the Game Setup inventory under `progression`, because
nothing *breaks* when they are unauthored — the failure mode is silent blandness.
The station multiplier stays a code constant deliberately: it is the rule, not a knob.

**A deed's `earned_at_level = 0`** means it was won outside a perilous stakes
contract. It is still real Legend for fame, murmur, spread and item legend — it
simply qualifies no advancement at any level. That is how "safe play cannot
advance you" is enforced, and it is why per-act sites (lockpicking, theft, feeding
kills) still write their deed rows for crime tags and witnesses while being worth
nothing.

**The Rite of Honors** (#3466, ADR-0251/ADR-0252) lets a character spend Golden Hares and
write a public journal to raise a witnessed deed's `base_value` toward what its anchoring
`LegendEvent` itself paid, or to establish a fresh solo deed for an extraordinary act the
automatic settlement never credited. **Honoring is always clamped to the event's own
ceiling** — `anchor_event.base_value - existing_base_value` — because peer judgment
redistributes recognition inside an envelope a settled event already proved, and can never
invent peril that did not happen; this is why the rite does not reopen what ADR-0249 closed.
Establishing refuses when the honoree already has an active deed anchored to that event (one
deed per act, not one per honorer — the event row is locked to serialize concurrent
establishes), and ALSO refuses when the honoree was never a witness of that event
(`HonoreeNotPresentToEstablishError`) — the honorer's presence alone is not enough, or a
witness could mint peril for someone who was never there. A struck (`is_active=False`) deed
neither proves peril, counts toward the station max, nor blocks a fresh deed, and cannot be
amplified (`DeedNotActiveError`). The `LegendHonor.honorer` recorded is always the acting
character's PRIMARY persona, never whatever face is active — the rite is always performed as
yourself (mirrors `_grant_title`'s reasoning). Unrestricted by life-state: honoring the dead is
by design (`honors.py` adds no death check anywhere). See `honors.py` above for the service
function and `docs/systems/societies.md` for the full write-up.

**Titles hang on `Persona`, not `CharacterSheet`** (ADR-0252) — `achievements.PersonaTitle`
retargeted #3466 so a deed earned behind a mask titles the mask and can never surface on the
character sheet. Achievement-sourced titles still resolve to the PRIMARY persona, never the
active one (a stat crossing a threshold is a fact about the character, not whatever disguise
they happened to be wearing).

---

Permanent, monotonically increasing metric of a character's remarkable accomplishments:
- **Per-persona**: Each Persona has its own legend total; character total sums all personas
- **LegendEntry**: Individual deed with `base_value`, optional `LegendEvent` link, spread multiplier
- **LegendSpread**: Spreading actions add `value_added` clamped to remaining capacity (default multiplier 9 = max 9x base value in spreads)
- **LegendEvent**: Group deeds shared across participants; spreading an event spreads for all
- **LegendDeedStory**: Player-written narratives per deed (one per author)
- **LegendSourceType**: Categorizes deed sources (combat, story, discovery, audere, etc.)
- **Materialized views**: `CharacterLegendSummary` and `PersonaLegendSummary` for fast totals, refreshed after mutations via `refresh_legend_views()`
- **Total calculation**: `base_value + sum(spreads.value_added)` for active deeds only
- **societies_aware**: Which societies know about a deed

## Key Constraints

- Only personas with `persona.is_established_or_primary` (PRIMARY or ESTABLISHED) can:
  - Hold organization memberships
  - Have reputation with societies/organizations
- Temporary disguises cannot join organizations or build reputation

## Integration Points

- **`scenes.Persona`**: Identity for memberships, reputation, and legend
- **`character_creation.Beginnings`**: Links to societies for character backgrounds
- **`progression.LegendRequirement`**: Path leveling gates that check character legend total
- **`skills.Skill`**: Optional FK on LegendSpread for the skill used when spreading
- **`scenes.Scene`**: Optional FK on entries/events/spreads for scene linking
- **`stories.Story`**: Optional FK on entries/events for story linking
