# Societies System - Social Structures and Reputation

Social structures (Societies, Organizations) with reputation and legend tracking for character personas. Characters interact with the social world through their Guises (identities).

**Note:** Realm model is defined in `realms` app - Society has a FK to `realms.Realm`.

## Key Files

### `models.py`
- **`Society`**: Social groupings within a Realm with 6 principle axes - uses SharedMemoryModel
- **`OrganizationType`**: Templates defining rank titles for organization categories - uses SharedMemoryModel
- **`Organization`**: Specific groups within societies (families, guilds, gangs) - uses SharedMemoryModel
- **`OrganizationMembership`**: Links Guise to Organization with rank (1-5)
- **`SocietyReputation`**: Reputation standing with a society per-guise
- **`OrganizationReputation`**: Reputation standing with an organization per-guise
- **`LegendSourceType`**: Categories of legend-generating events (combat, story, discovery, etc.) - uses SharedMemoryModel
- **`SpreadingConfig`**: Singleton server-wide config for spreading mechanics - uses SharedMemoryModel
- **`LegendEvent`**: Group events that generate deeds for multiple participants
- **`LegendEntry`**: Individual deeds with base_value, spread cap, active flag, optional event/scene/story FKs
- **`LegendSpread`**: Spreading actions that add value to entries, clamped to spread cap
- **`LegendDeedStory`**: Player-written narratives for deeds (one per author per deed)
- **`CharacterLegendSummary`**: Materialized view for fast character legend totals (managed=False)
- **`GuiseLegendSummary`**: Materialized view for fast guise legend totals (managed=False)

### `services.py`
- **`create_solo_deed()`**: Create a deed not tied to an event
- **`create_legend_event()`**: Create a shared event with deeds for multiple guises
- **`spread_deed()`**: Record a spread, clamped to remaining capacity
- **`spread_event()`**: Spread all active deeds in an event
- **`get_character_legend_total()`**: Fast lookup via materialized view
- **`get_guise_legend_total()`**: Fast lookup via materialized view

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
- **Per-persona**: Each Guise has its own legend total; character total sums all personas
- **LegendEntry**: Individual deed with `base_value`, optional `LegendEvent` link, spread cap (`base_value * spread_cap_multiplier`)
- **LegendSpread**: Spreading actions add `value_added` clamped to remaining capacity (default cap = 9x base value)
- **LegendEvent**: Group deeds shared across participants; spreading an event spreads for all
- **LegendDeedStory**: Player-written narratives per deed (one per author)
- **LegendSourceType**: Categorizes deed sources (combat, story, discovery, audere, etc.)
- **Materialized views**: `CharacterLegendSummary` and `GuiseLegendSummary` for fast totals, refreshed after mutations via `refresh_legend_views()`
- **Total calculation**: `base_value + sum(spreads.value_added)` for active deeds only
- **societies_aware**: Which societies know about a deed

## Key Constraints

- Only default (`is_default=True`) or persistent (`is_persistent=True`) guises can:
  - Hold organization memberships
  - Have reputation with societies/organizations
- Temporary disguises cannot join organizations or build reputation

## Integration Points

- **`character_sheets.Guise`**: Identity for memberships, reputation, and legend
- **`character_creation.Beginnings`**: Links to societies for character backgrounds
- **`progression.LegendRequirement`**: Path leveling gates that check character legend total
- **`skills.Skill`**: Optional FK on LegendSpread for the skill used when spreading
- **`scenes.Scene`**: Optional FK on entries/events/spreads for scene linking
- **`stories.Story`**: Optional FK on entries/events for story linking
