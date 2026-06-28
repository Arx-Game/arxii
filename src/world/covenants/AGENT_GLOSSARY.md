# Covenants glossary

**Covenant**:
A magically-empowered group oath — a blood-bound pact that binds its members under shared roles and goals. It is a per-kind extension of an `Organization` (a `Covenant` always has a backing org and shares its pk), scoped by a `CovenantType`.
_Avoid_: guild, faction, party.

**Covenant of the Durance**:
The `CovenantType.DURANCE` covenant — the default, life-journey kind of oath, distinct from a battle covenant. "Covenant of the Durance" is the display label of that type.
_Avoid_: a Durance, durance covenant.

**War Covenant / Covenant of Battle**:
The `CovenantType.BATTLE` covenant — an oath sworn to a martial cause. A STANDING one can stand down into dormancy and *rise again* through a "call the banners" rise ritual; a CAMPAIGN one dissolves when its defining story concludes.
_Avoid_: setting active=true / "activating" a covenant (a dormant covenant rises via ritual, it is not flipped on).

**Covenant of the Court**:
The `CovenantType.COURT` covenant — a master/servants oath: a single powerful leader and the servants/apprentices/acolytes sworn to them across a wide power gulf (by design ≥1 power tier), explicitly not a co-adventuring party (e.g. "the Court of Shadows" serving the Shadowlord). Lets a peerless puissant hold a covenant role. (ADR-0057.)
_Avoid_: retinue covenant (descriptive only), guild, household, mentor bond.

**Covenant Role**:
The combat-power axis of membership: a role's archetype (Sword / Shield / Crown), speed_rank, role bonuses, and COVENANT_ROLE Thread-pull eligibility. Orthogonal to authority.
_Avoid_: rank, position, office.

**Covenant Rank**:
The administrative-authority axis of membership: a per-covenant tier on the rank ladder (lower tier number = higher authority) whose capability flags gate invite / kick / manage. Orthogonal to Role.
_Avoid_: role, level.

**Mentor's Vow / Mentor Bond**:
A consensual bond pairing a higher-level mentor with a lower-level sidekick so a level-mismatched party scales fairly; the `MentorBond` record is active while `dissolved_at` is null.
_Avoid_: master/apprentice (a future flavor display-label only, with no model surface), patron, sponsor.
