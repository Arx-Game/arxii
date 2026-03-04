# Societies & Organizations

**Status:** in-progress
**Depends on:** Relationships, Progression (legend/reputation), Areas (territory)

## Overview
The social hierarchy of the game world — from massive NPC-backed societies too large for any player to control, down to player-run organizations like noble houses, covens, and adventuring companies. Reputation and legend flow through these structures, and political maneuvering between them drives the Game of Thrones-style intrigue layer.

## Key Design Points
- **Societies (large-scale):** Huge NPC-backed factions like the entire Umbros peerage or a magical tradition. Too big for any player to control — prevents bullying. Represent massive swaths of NPCs with shared principles
- **Organizations (player-scale):** Noble houses, covens, adventuring companies, criminal gangs. Player-controllable with domains, armies, wealth, and power. Fit within larger societies
- **Reputation system:** Characters build hidden reputation (-1000 to 1000) with societies and organizations, displayed as intuitive tiers. Actions, missions, and RP all affect reputation
- **Legend:** Deeds and accomplishments tracked as LegendEntries with base value. Legend can be spread through retelling (LegendSpread) to increase its reach and impact
- **Alter egos:** Characters can build reputation under masked/alternate identities. A sweet catgirl maid from Luxen might secretly be a terror in the underworld under her masked criminal name
- **Political game:** Game of Thrones-style maneuvering between noble houses, societies, and factions. Territory control, alliances, betrayals
- **Six principle axes:** Societies have values on 6 axes (-5 to +5), with organizations inheriting and optionally overriding them
- **Organization types:** Templates with rank titles (1-5) for different kinds of groups
- **Territory and domain:** Organizations can control areas, generating resources and projecting influence

## What Exists
- **Models:** Society (groupings within realms with 6 principle axes), OrganizationType (templates with rank titles), Organization (specific groups with principle overrides), OrganizationMembership (guise membership with ranks 1-5), SocietyReputation and OrganizationReputation (hidden reputation shown as tiers), LegendEntry (deeds with base value and society awareness), LegendSpread (embellished tales with added value)
- **Tests:** Model tests, fixture integrity tests

## What's Needed for MVP
- Territory control mechanics — organizations claiming, defending, and losing areas
- Domain management integration — noble houses with material generation, exports/imports
- Political mechanics — alliance formation, betrayal consequences, faction warfare
- Army/military model — organizational military strength for territory and battle scenes
- Wealth and treasury — organizational resources, income, expenditure
- Alter ego integration — building reputation under masked identities, reveal mechanics
- Organization leadership — succession, challenges, abdication
- Legend integration with missions/combat — earning legend through gameplay actions
- Society influence on world events — how faction shifts affect the living grid
- Organization UI — management dashboard, membership, reputation tracking, domain overview

## Notes
