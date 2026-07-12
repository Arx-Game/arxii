# Societies & Organizations

**Status:** in-progress
**Depends on:** Relationships, Progression (legend/reputation), Areas (territory)

## Overview
The social hierarchy of the game world — from massive NPC-backed societies too large for any player to control, down to player-run organizations like noble houses, covens, and adventuring companies. Reputation and legend flow through these structures, and political maneuvering between them drives the Game of Thrones-style intrigue layer.

## Key Design Points
- **Societies (large-scale):** Huge NPC-backed factions like the entire Umbros peerage or a magical tradition. Too big for any player to control — prevents bullying. Represent massive swaths of NPCs with shared principles
- **Organizations (player-scale):** Noble houses, covens, adventuring companies, criminal gangs. Player-controllable with domains, armies, wealth, and power. Fit within larger societies
- **Reputation system:** Characters build hidden reputation (-1000 to 1000) with societies and organizations, displayed as intuitive tiers. Actions, missions, and RP all affect reputation
- **Legend:** Deeds and accomplishments tracked as LegendEntries with base value. Legend can be spread through retelling (LegendSpread) to increase its reach and impact. Retelling reach scales with the room's traffic (`room_activity_band`), so an owner-upgradeable **Social Hub** room feature (#1694) draws bigger crowds and thereby wins more fame and prestige from deeds spread there
- **Fame & prestige as a pair:** a successful retelling grows both the deed subject's **fame** (the fast, larger, *decaying* modifier) and **prestige** (the slow, smaller, *permanent* base) (#2168), each traffic-scaled — so a Social Hub amplifies both. Fame tier also acts as a display multiplier on prestige
- **Alter egos:** Characters can build reputation under masked/alternate identities. A sweet catgirl maid from Luxen might secretly be a terror in the underworld under her masked criminal name
- **Political game:** Game of Thrones-style maneuvering between noble houses, societies, and factions. Territory control, alliances, betrayals
- **Six principle axes:** Societies have values on 6 axes (-5 to +5), with organizations inheriting and optionally overriding them
- **Organization types:** Templates with rank titles (1-5) for different kinds of groups
- **Territory and domain:** Organizations can control areas, generating resources and projecting influence

## What Exists
- **Models:** Society (groupings within realms with 6 principle axes), OrganizationType (templates with rank titles), Organization (specific groups with principle overrides), OrganizationRank (five-tier authority ladder with capability flags), OrganizationMembership (persona membership with rank FK and voluntary/left/exiled timestamps), OrganizationMembershipOffer (pending/resolved invitations and applications), SocietyReputation and OrganizationReputation (hidden reputation shown as tiers), LegendEntry (deeds with base value and society awareness), LegendSpread (embellished tales with added value)
- **Membership lifecycle:** Generic (non-covenant) organizations support invite/apply join paths, accept/decline via the offer registry, voluntary leave, promote/demote, and expel/exile. All transitions are shared Action subclasses on the `action.run()` / `dispatch_player_action()` seam, with a namespaced `org <subverb>` telnet command. A member with a `can_lead_rituals` rank may additionally lead a ceremonial ritual-dispatched induction (#1868), riding the generic `RitualSession` machinery; telnet-only for now.
- **Tests:** Model tests, membership lifecycle service tests, action/command tests, API read-view tests, fixture integrity tests
- **Houses (#1884, ADR-0098):** a house IS an Organization with a `family` FK into the kinship graph (#2062). Built: nobiliary-particle naming (`full_display_name`), per-realm birth recognition (`HouseRecognitionRule` + `recognize_birth`; mother's-option explicit), first-class `Title` rows with `SuccessionLaw` (house default + per-title override; primogeniture/matrilineal/female-line/chosen-heir/tanistry derivations, eldest or pluggable most-powerful-Gifted ordering), the fealty tree (`FealtyEdge`, cycle-refused, vassal cascade), union-bound `MarriagePact` with coded commitments (dowry treasury transfer, subsidy `OrgObligation`, residency marry-in; dies with a spouse; breach stamps + stops machinery), abstract `Domain`s on Areas whose `DomainHolding`s materialize `OrgIncomeStream`s, `DOMAIN_IMPROVEMENT` projects (crisis on bad outcomes), the house feed (`house_feed_for`, tidings — the informs replacement), the house channel (`sync_house_channel`), the `/orgs/:id` house page block + feed endpoint, `sheet/house`, and the `houses` seed cluster. Phase D house creator SHIPPED (CG-only per Apostate ruling): HouseTemplate charters + HouseClaim gates/admin review, full-package materialization at CG finalization, the CG "Define a House" panel + seeds. In-play founding/ennoblement remains a future loop. **Regional flavor framework SHIPPED (#2079, ADR-0101):** required catalog-only Aspects (`HouseAspectDefinition`/`Option` per template, picks validated at submission, materialized as `OrganizationAspect` facets) + slug-anchored cultural Features (`HouseFeature` → `OrganizationFeature`), org-level stylings (words/colors/sigil on every org type), lands writeup onto `Domain.description`; the CG panel renders requirements dynamically. Per-region content catalogs (2 aspects + ≥1 advantageous feature per region) await the per-region brainstorms; ledger/trophy/geas-enforcement systems are separate future builds.

## What's Needed for MVP
- Territory control mechanics — organizations claiming, defending, and losing areas (Domain rows exist, #1884; contested control is not built)
- ~~Domain management integration~~ — DONE for the abstract tier (#1884): domains + holdings feed OrgIncomeStream→treasury; material exports/imports remain
- ~~In-play domain management + delegation~~ — DONE (#2239): the CG/seed-only `add_holding`/`start_domain_improvement` are reachable in play via `actions/definitions/domains.py` + telnet `CmdDomain`, gated on `can_administer_domain` (org leader OR `domain-steward` office). Delegation lands as `OrganizationOffice` (a named portfolio orthogonal to rank — "Minister of the Domains"). The office's `feeds_check` trait is declared schema; wiring it into the improvement check (a Minister lending their Stewardship) is a future increment — `perform_check` needs a live character actor + CheckType, not a Trait on a possibly-offline holder. A React domain panel is a separable follow-up.
- Political mechanics — marriage-pact alliances built (#1884); betrayal consequences beyond pact breach, faction warfare
- Army/military model — organizational military strength for territory and battle scenes
- Wealth and treasury — organizational resources, income, expenditure
- Alter ego integration — building reputation under masked identities, reveal mechanics
- Organization leadership — succession, challenges, abdication
- Legend integration with missions/combat — earning legend through gameplay actions
- Society influence on world events — how faction shifts affect the living grid
- Organization UI — management dashboard, membership, reputation tracking, domain overview

## Notes
