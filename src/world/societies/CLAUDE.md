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
- **`settle_obligation(obligation, token)`**: settle an OWED `OrganizationObligation` by redeeming a Golden Hare (`currency.FavorTokenDetails`) to the creditor org; stamps `settled_at`/`settled_by_token`. Settled rows are history — never deleted.
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
