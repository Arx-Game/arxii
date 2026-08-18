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

**Propaganda Campaign** (`PropagandaCampaignTier` / `PropagandaDetails`, #1621):
A funded PROPAGANDA-kind project that converts coin into the sponsor's fame/prestige — the ONLY sanctioned project→renown path (the #1574 resolution: ordinary project contribution never grants prestige). Launched at an authored scale (tier) whose renown config snapshots onto the campaign; instant-completes at threshold (RANSOM pattern) and fires `fire_renown_award` for `Project.owner_persona` exactly once; the sponsor's orgs benefit through the existing membership-inflow stream. Under-funded deadline resolution awards nothing and refunds nothing — the sink keeps what it swallowed. Distinct from the deed-spread "Propaganda" Persuasion form, which amplifies the telling of an EXISTING deed; the campaign *mints* a new award. They compose.
_Avoid_: advertisement, PR campaign, prestige purchase (it is a project, funded like any other), conflating with spread-Propaganda.

**Organization Obligation** (`OrganizationObligation`, #2428):
A personal debt of one `currency.FavorTokenDetails` ("Golden Hare") owed by a `CharacterSheet` (`debtor`) to an `Organization` (`creditor`) — distinct from `currency.OrgObligation`'s org-to-org standing tithe/tax. Starts `OWED` (e.g. an Unbound Prospect's Academy-entrance debt, no Tradition sponsor to cover it) or `SETTLED_BY_SPONSOR` (a sponsor literally spent a Hare on the debtor's behalf at CG finalize — a deed-coin transaction, not an abstract waiver). `settle_obligation` redeems the Hare via the issuing org and flips `OWED` → `SETTLED`, stamping `settled_at`/`settled_by_token`; rows are never deleted, so a settled obligation is permanent history. `has_open_obligation` is the read-only gate other systems (e.g. Academy trainers) check before doing business with a debtor.
_Avoid_: debt (ambiguous with `currency.DebtInstrument`, money debt), fee, IOU.

**Neighborhood Turf** (`NeighborhoodTurf` + `turf_services`, #2862):
Who holds a crime neighborhood and how hard — one row per NEIGHBORHOOD-level `Area`: `controlling_org` + `grip` (0-100). `apply_turf_push` owns the arithmetic (own pushes deepen, rival pushes erode, breaking grip flips control to a shallow `FLIP_START_GRIP` hold). Control is consequential: the area's `StatKey.CRIME` cascade modifier tracks grip (guard-encounter pressure scales off it), the area's `CRIME_KICKUP` income streams re-target to the controller, and a push against held ground opens a Gang Retaliation crisis (CRIMINAL_ORG audience) against the pusher. Fed by the gang-turf project machinery (`complete_gang_turf` tier completions × `TURF_PUSH_FACTOR`) and by turf-mission PROJECT reward lines. Gangs are plain `Organization`s of the `gang` `OrganizationType`; an "NPC gang" is one with no player members, not a separate model.
_Avoid_: territory model, gang model, faction control (it is org + area + grip, nothing more).

**Stature (HouseStature)**:
A landed org's deterrence (#3091): TRUE strength (renown of the people who stand with the house + military + economic + one-hop allied net − open-threat drag, recomputed weekly) versus PERCEIVED strength (converges toward truth with lag; jumps on public deaths/pact changes/surfaced crises; spycraft manipulates the gap). Predation targets perceived weakness. Named "Stature" precisely because "standing" is Reputation's avoid-word.
_Avoid_: standing, power level, might score.

**StatureBand**:
Authored qualitative tier (Unassailable … Imperiled) assigned by percentile within a (continent × org-category) cohort; supplies the org page's headline template and the ambient-threat multiplier predation reads.
_Avoid_: stature tier, threat level.

**StatureShift**:
One row of the "why it moved" ledger (death, pact signed/dissolved, crisis opened/resolved, whispers, convergence, band change); the tidings feeds read it.
_Avoid_: stature log, history entry.

**PrestigeRankBand**:
Authored rank-relative benefit tier (#3091, ADR-0210): benefits key on 1-based contextual RANK (declining over the top 100, minimal 101–1000, penalties for negative standing), never raw prestige, and pay through bounded domain prosperity.
_Avoid_: prestige threshold, wealth tier.

**PredatorBand / MenaceStage**:
A named NPC antagonist (#3093, ADR-0211) on the SLOW menace ladder (rumors, lawlessness, robbery, raids, terror — roughly ten weekly crons rumor to raid), advancing only while unanswered; counterplay knocks it down and burns strength. Deliberately a thin dedicated model in `world/predators/`, never an Organization (orgs are the player-holding construct).
_Avoid_: predator org, threat group, mob.

**Affliction**:
A deterrence-blind crisis class (#3093): `DomainCrisisType.ignores_stature` rows whose outbreaks are announced by a week of SIGNS and spread slowly (capped) while unresolved. Stature means nothing to the dead.
_Avoid_: plague event, zombie crisis (content names live in the catalog).

**Grand Display**:
The upward half of the bluffing game (#3093): an event whose catering PROVISION score OR grandeur score clears the bar elevates the host org's PERCEIVED stature, bounded above true by the bluff cap (#2357 added the grandeur input; both scores are independent and can fire on the same completed event). Whispers push down; displays push up.
_Avoid_: propaganda event, fame party.

**Grandeur** (`world/events`):
Event-scoped prestige/wealth investment for once-in-a-lifetime events — royal wedding,
coronation, grand ball (#2357). A catering-shaped sibling of `EventCatering`: hosts spend
real coppers (a `world.currency.services.transfer` sink) across VENUE/ENTERTAINMENT/
FAVORS/DECOR categories (food stays catering's Hospitality lane); at `complete_event` the
spend converts through a sqrt-diminishing-returns curve into the host's "Grandeur" deed —
same `create_solo_deed` + Grand Display pipeline catering uses — plus an additive honoree
cut when the event is linked to a WEDDING or CORONATION `Ceremony` (in addition to, never
instead of, whatever `finish_ceremony` itself awards the honoree). Orthogonal to the
ceremony mechanics — ceremonies handle the rite, grandeur handles the party. No
`is_milestone` flag: for a ceremony-linked event the spend's own cost is the once-in-a-
lifetime gate.
_Avoid_: milestone score, wedding tier, event prestige (that's the broader unbuilt system
grandeur's deed pipeline feeds, not a synonym for it).

**OrgPact / PactKind**:
The signed-paper diplomacy instrument (#2999, ADR-0212) — a sibling of MarriagePact, never a generalization. PactKind rows are LEVERS (allied stature share, income tithe, non-aggression, mutual defense; ADR-0178 payload rule). Proposed by one org's leadership, ratified by the other's; BETRAYAL is a stamped dissolution reason with a permanent prestige cost, auto-flagged by hostile acts between partners.
_Avoid_: treaty model, alliance row, generalized pact.

**Betrothal**:
A promised union (#2999): negotiated CommitmentSpec terms held in draft, a 25% stature preview both ways, broken at a standing cost, and solemnized by the WEDDING ceremony (union + marriage pact + marrying-up prestige in one rite).
_Avoid_: engagement record, pre-marriage.

**Match Dossier**:
The full-information review of a candidate house (#2999 hard requirement): band/perceived/ranks, standing instruments, betrothals, known troubles (covert ones only through the VIEWER org's CrisisIntel), shifts, consort capacity. Readable by any authenticated player — reviewing rivals is the point.
_Avoid_: org report, house profile.

**Nobiliary Particle**:
The realm-signature word between a noble's first and house name ("du", "arn", "za"), keyed per realm × family-type × tier band (`NobiliaryParticle`, #3261 canon). Each realm carries a **born form** (born/founding members) and a **taken-in form** (married, adopted, legitimized, granted — e.g. Luxen `dau`, Ariwn `vosk`). Apostrophe-terminal particles attach unspaced ("D'Regente"). Arx has none by canon — a bare noble name reads as Arx.
_Avoid_: prefix, honorific, surname marker.

**Née Segment**:
The continental birth-family marker in a full formal name — `ne <BirthFamilyName>`, bare, *replacing* the birth family's particle ("Sharlotte ne Regente dau Vaelmont"). Renders only at the full-formal degree and only when a prior family exists.
_Avoid_: maiden name, birth suffix.

**Degree of Address**:
How much of a composed name a persona leads with (`NameDegree`: familiar / common / styled / full formal), a per-Persona preference orthogonal to the **Title Suffix** (`TitleSuffixMode`: none / primary / all held titles). Formal contexts render full formal regardless of preference.
_Avoid_: name length setting, verbosity.
