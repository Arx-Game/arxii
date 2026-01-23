# Societies System - Social Structures and Reputation

Social structures (Realms, Societies, Organizations) with reputation and legend tracking for character personas. Characters interact with the social world through their Guises (identities).

## Key Files

### `models.py`
- **`Realm`**: Nation-state containers (e.g., Umbral Empire, Luxen Dominion, Arx) - uses SharedMemoryModel
- **`Society`**: Social groupings within a Realm with 6 principle axes - uses SharedMemoryModel
- **`OrganizationType`**: Templates defining rank titles for organization categories - uses SharedMemoryModel
- **`Organization`**: Specific groups within societies (families, guilds, gangs) - uses SharedMemoryModel
- **`OrganizationMembership`**: Links Guise to Organization with rank (1-5)
- **`SocietyReputation`**: Reputation standing with a society per-guise
- **`OrganizationReputation`**: Reputation standing with an organization per-guise
- **`LegendEntry`**: Deeds and accomplishments that earn legend
- **`LegendSpread`**: Instances of spreading/embellishing deeds

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

Tracks character deeds and fame accumulation:
- **LegendEntry**: Base deed with `base_value`, linked to a Guise
- **LegendSpread**: Embellishments that add `value_added` to entries
- **Total calculation**: `base_value + sum(spreads.value_added)`
- **societies_aware**: Which societies know about a deed

## Key Constraints

- Only default (`is_default=True`) or persistent (`is_persistent=True`) guises can:
  - Hold organization memberships
  - Have reputation with societies/organizations
- Temporary disguises cannot join organizations or build reputation

## Integration Points

- **`character_sheets.Guise`**: Identity for memberships, reputation, and legend
- **`character_creation.Beginnings`**: Links to societies for character backgrounds
- **Future**: Missions/events as legend sources, grid locations for deeds
