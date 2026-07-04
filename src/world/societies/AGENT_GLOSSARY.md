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
A per-organization rung on the five-tier rank ladder (tier 1 highest, tier 5 lowest). Carries the diegetic name for that rung and capability flags (`can_invite`, `can_kick`, `can_manage_ranks`). Generic organizations auto-create a default ladder from their `OrganizationType` titles on first save; covenants do not use this model.
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
