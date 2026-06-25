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
