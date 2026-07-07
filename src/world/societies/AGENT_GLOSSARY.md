# Societies glossary

**Society**:
A socio-political stratum within a Realm, defined by six Principle Axes; characters relate to it through their Personas (memberships, reputation, legend awareness).
_Avoid_: faction, org, culture.

**Organization**:
A specific group within a Society — a noble family, guild, gang, business, or standalone covenant — carrying rank titles and optional principle overrides. It belongs to (or stands apart from) exactly one Society.
_Avoid_: faction, guild (guild is one OrganizationType, not the general term).

**OrganizationType**:
A template categorizing organizations and supplying their default five-rank title set (e.g. noble_family, guild, secret_society, covenant).
_Avoid_: org category, kind.

**Reputation / ReputationTier**:
A persona's hidden numeric standing (−1000 to +1000) with a Society or Organization. The raw value is never shown; players see only the named `ReputationTier` (Reviled … Unknown … Revered).
_Avoid_: standing, favor, rep score.

**Principle Axes**:
The six −5..+5 value axes — mercy, method, status, change, allegiance, power — that define a Society's (or Organization's) moral character; archetype vectors dot-product against them to produce reputation deltas.
_Avoid_: alignment, morals, stats.

**LegendEntry / Deed**:
A single notable accomplishment ("deed") earned by a persona, carrying a base legend value that further telling can extend up to a spread cap. Legend itself is the permanent, accumulating metric of remarkable accomplishment.
_Avoid_: feat, achievement (Achievement is a separate system), accomplishment record.

**LegendSpread**:
A single instance of a deed being retold or embellished, adding value (clamped to the deed's remaining spread capacity) and widening which societies are aware of it.
_Avoid_: rumor, telling event, gossip record.

**Renown**:
The live award *mechanism* — `fire_renown_award` reading an authored `RenownAwardConfig` (Magnitude / Risk / Reach / Archetypes) — that fires a deed's downstream consequences: fame buffer, permanent prestige, the legend `base_value`, and per-society reputation deltas. Distinct from Legend, which is the metric Renown feeds.
_Avoid_: fame (fame is one output of Renown), reputation, the Legend total.

**OrganizationRank**:
A per-organization rung on the five-tier rank ladder (tier 1 highest, tier 5 lowest). Carries the diegetic name for that rung and capability flags (`can_invite`, `can_kick`, `can_manage_ranks`, `can_lead_rituals`). Generic organizations auto-create a default ladder from their `OrganizationType` titles on first save; covenants do not use this model. `can_lead_rituals` mirrors `CovenantRank.can_lead_rituals` (#708) but has no consuming org-ritual dispatch yet — see the needs-design follow-up on generic organization-ritual dispatch.
_Avoid_: rank row, rank level.

**OrganizationMembershipOffer**:
A pending or resolved invitation or application to join a generic organization. `INVITE` offers are directed at a specific persona (`to_persona`); `APPLICATION` offers are directed at the organization by an applicant (`from_persona`, `to_persona` null). Invites are resolved through the shared offer registry (`accept org` / `decline org`); applications are resolved by an authorized member.
_Avoid_: org invite, join request.

**Active Membership**:
An `OrganizationMembership` whose `left_at` and `exiled_at` are both null. Only active memberships count for permissions, blocks, and public lists. `left_at` records a voluntary departure; `exiled_at` records a forced removal.
_Avoid_: current member, valid membership.

**Rank Tier / Rank Ladder**:
The numeric authority ordering (1 highest, 5 lowest) shared by `OrganizationType` defaults and `OrganizationRank` overrides. Higher authority (lower tier) is required to promote, demote, or expel lower authority.
_Avoid_: rank number, rank value.

**Exiled**:
A membership whose `exiled_at` is set. A new membership is a separate row; exiled history is retained for audit.
_Avoid_: kicked, removed.

**Scandal**:
A per-society judgment, never a taxonomy: an act whose archetype dot-product against that society's principles falls below the scandal threshold (#1464). Derived at deed birth from the same vectors reputation uses; what one society finds scandalous another may celebrate.
_Avoid_: scandal type, scandal category, outrage score

**Containment**:
The after-the-act half of concealment (#1464): a check against the crowd size that routes a public scandalous act to a contained Secret instead of society awareness. Rolled with a declared Witness Approach when one was chosen (#1824), else the actor's best social tool. Distinct from act-time concealment (Stealth/magic reducing who witnesses at all).
_Avoid_: cover-up roll (informal), suppression (that's gossip heat)

**Witness Approach**:
One entry of the #1824 capability list — a named tool for dealing with witnesses (intimidation, seduction, manipulation, bribery, household command), each resolving to a seeded CheckType; bribery's attempt also tags the deed with the `bribery` CrimeKind. `witness_approaches_for` is the single eligibility predicate (visibility = selectability).
_Avoid_: containment option, hush method.

**Reach (act)**:
Where knowledge of an act lands at birth — contained (a Secret) or the realm walk's societies — always derived from room privacy + containment + the fame of those involved, never authored per act (ADR-0082). Continental/world are escalation (gemit, common knowledge, legend), never minted.
_Avoid_: stakeholders, audience list

**Gang Turf (GANG_TURF)**:
A `TIERED_PERIOD` `Project` kind — the first of its mode (#1891) — representing a gang organization's ongoing territorial pressure over a period, graded at deadline into a `CheckOutcome` tier by accumulated progress. The tier applies a data-driven reputation delta to the owning gang org via `bump_organization_reputation` (relational channel, not the archetype dot-product). Opened only by a leader-rank member (`OrganizationRank.can_lead_rituals`). "Turf" here is abstract menace/standing, **not** literal map control — a dedicated territory model is deferred (see the #1891 spec follow-ups).
_Avoid_: territory (literal), zone control, gang influence (until the territory model lands).

**House**:
An `Organization` rooted in a kinship `Family` (`Organization.family`, #1884, ADR-0098) — noble, merchant, or crime; the type is the family's, the machinery is one. Never a standalone model.
_Avoid_: House model, family org (ambiguous), dynasty (that's the soul-chain concept).

**Recognition (birth)**:
A realm's law deciding whether a newborn belongs to a parent's house — `HouseRecognitionRule` rows applied to public-record parentage edges by `recognize_birth`. The mother's-option case is an explicit human call (`acknowledge_into_family`), never auto-resolved.
_Avoid_: legitimacy check (wedlock is one input, not the concept), auto-enrollment.

**Succession Law**:
Candidate derivation + ordering for a title (`SuccessionLaw`): house default on the org, per-title override (Imperial Tanistry). Runs on the omniscient public record; an empty candidate list is a succession crisis — story fuel, deliberately unresolved.
_Avoid_: heir formula, inheritance rule (that's estates/wills, #1985).

**Fealty**:
The org→org vassal→liege edge (`FealtyEdge`, one liege per vassal, cycle-refused) forming the realm tree. Cascades the house channel audience downward.
_Avoid_: allegiance (that's a principle axis), parent org.

**Marriage Pact**:
The alliance bound to a `Union` (`MarriagePact`, senior/junior house) that dies instantly with a spouse (the CK2 rule). Its `PactCommitment` rows are coded and fire mechanically — DOWRY (treasury transfer at signing), SUBSIDY (`OrgObligation`), RESIDENCY (marry-in membership), CRISIS_RESPONSE/CUSTOM (recorded; social). Breach stamps the commitment and stops the machinery; the scandal is staff-authored through Secrets.
_Avoid_: alliance object, treaty, marriage contract (contracts are a different system).

**Domain**:
An org-owned decoration on a DOMAIN-level `Area` — PLACEHOLDER civ stats plus `DomainHolding` rows that each materialize an `OrgIncomeStream`. Abstract by design; visitable grids are a later phase.
_Avoid_: province model, land parcel, estate (that's buildings/dwellings).

**House Feed**:
The pull feed of a household's own deeds and revealed scandals (`house_feed_for`, tidings) — the Arx 1 informs replacement. No feed model; query-and-merge like the public feed.
_Avoid_: org informs, house inbox, notifications (it is not push).

**House Claim**:
The CG-only application defining the house behind a set-aside claimable `Title` (#1884 Phase D) — the character enters play as a representative of a house that has always existed. Automated thematic gates at submission, staff review in admin, materialization at CG finalization only. Founding a new house *in play* is a different, future loop.
_Avoid_: house founding (in-play), ennoblement (future loop), house application (ambiguous with roster apps).

**Aspect (house)**:
A required, normalized catalog choice on a house template (#2079, ADR-0101) — `HouseAspectDefinition` (prompt, min/max picks) + its `HouseAspectOption` catalog, answered at CG by picks alone (never free text; the authored list IS the thematic fence). Picks become permanent `OrganizationAspect` identity facets at materialization.
_Avoid_: trait, flaw, house perk, custom aspect (there is no free-text path).

**Feature (house)**:
A structural cultural fact about houses of a template (#2079) — `HouseFeature` (unique slug = stable code anchor) stamped as `OrganizationFeature` at materialization. No player input; orients the founder at CG and anchors future systems (a ledger UI checks slug `black-ledger`).
_Avoid_: perk, ability, house power (features may be flavor-only), aspect (that's the choice concept).
