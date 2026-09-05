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

The bar is **"would bards make songs about this"** (#3463, ADR-0249). Legend is settled at the END of a story unit from what was at stake and what was held — never asserted at the moment of an act. Safe play mints **zero**, not less.
_Avoid_: renown, fame, "legend total" when you mean the advancement subset, advancement points.

**Settlement**:
The one seam that prices a deed: `world.societies.legend_settlement.settle_legend_for`. Applies the per-person peril floor, the held-objective share, the station stamp and the standout pass, then mints. Every other system adapts its own world into this seam's system-agnostic inputs rather than minting directly.
_Avoid_: award, payout, granting legend.

**Station**:
`min(earner class level, threat level)`, stamped on each entry as `earned_at_level`. You cannot bank above your station, and you cannot bank by slumming. It is **not** folded into `base_value` — the tale is worth the same whoever tells it — and `station_multiplier()` is applied on read by the advancement gate, so retuning it never requires recomputing history. A station of 0 means the deed was won outside a perilous stakes contract and qualifies no advancement at any level.
_Avoid_: reach (a Renown axis on a different question), level, tier.

**Contribution**:
A `LegendContribution` row: what one character did during a staked unit, written at the `perform_check` chokepoint while a stakes contract is open. `success_level` is **server-only** and must never be serialized to another player. Read by settlement to find standouts.
_Avoid_: action log, roll history.

**Personal risk**:
Each earner's risk priced against their OWN level rather than the party average. The peril floor is applied per person, so a character who was never in danger earns nothing however lethal the scene was to everyone else. Table stakes for any Legend at all.
_Avoid_: party risk, effective risk (that is the contract-wide value).
_Avoid_: feat, achievement (Achievement is a separate system), accomplishment record.

**LegendSpread**:
A single instance of a deed being retold or embellished, adding value (clamped to the deed's remaining spread capacity) and widening which societies are aware of it.
_Avoid_: rumor, telling event, gossip record.

**Honor / Rite of Honors** (`LegendHonor`, `honor_deed`, #3466):
A character's paid, written testimony to another character's deed — a Golden Hare
surrendered, a public journal written, and legend added to `LegendEntry.base_value`, always
clamped to the ceiling the anchoring `LegendEvent.base_value` already proved (see
ADR-0252). Also the seam that *establishes* a fresh solo deed for an act the automatic
settlement never credited, when the honorer witnessed it. Unrestricted by life-state:
honoring a dead character's deed is by design, never a bug.
_Avoid_: **acclaim** — that word is taken: `ItemInstance.acclaim` is fashion esteem, whose
help_text says "NEVER legend." **Spread** — spread is reach (which societies become aware),
not size; an honor moves `base_value` directly, no spreading involved. **Deed story** —
`LegendDeedStory` is the free account anyone may write and rewrite about a deed; an honor's
mirrored journal costs a Hare and moves the number, the deed story does neither. Also NOT
`GiveDeathKudosAction`'s display name **"Honor a Death"** (OOC kudos to a player for how they
handled a death scene) and NOT `CeremonyHonoree` (the person a ceremony rite is held for).

**Renown**:
The live award *mechanism* — `fire_renown_award` reading an authored `RenownAwardConfig` (Magnitude / Risk / Reach / Archetypes) — that fires a deed's downstream consequences: fame buffer, permanent prestige, the legend `base_value`, and per-society reputation deltas. Distinct from Legend, which is the metric Renown feeds.

One event carries **three independent scales** (#676): Magnitude drives fame + prestige, Risk drives Legend, Archetypes drive reputation. They are orthogonal on purpose — a royal wedding is high Magnitude and NONE Risk: enormously famous, worth no Legend.

`risk` is a **declared wager, not a payout** (#3463, ADR-0249). It is the author's ceiling on how legendary an event type may be; Legend pays on the weaker of that declaration and the level-priced settled reality, and mints nothing at all without a settled context. An authored `risk=EXTREME` on a config with no stakes behind it pays zero.
_Avoid_: fame (fame is one output of Renown), reputation, the Legend total.

**OrganizationRank**:
A per-organization rung on the five-tier rank ladder (tier 1 highest, tier 5 lowest). Carries the diegetic name for that rung and capability flags (`can_invite`, `can_kick`, `can_manage_ranks`, `can_lead_rituals`, `can_declare_standing`). Generic organizations auto-create a default ladder from their `OrganizationType` titles on first save; covenants do not use this model. `can_lead_rituals` mirrors `CovenantRank.can_lead_rituals` (#708) but has no consuming org-ritual dispatch yet — see the needs-design follow-up on generic organization-ritual dispatch.
_Avoid_: rank row, rank level.

**Standing Declaration** (`StandingDeclaration`, #3290):
A leader's deliberate, audited act of officially declaring a persona favored or disfavored with an organization — the one player-facing writer of `OrganizationReputation` (every other write is an automated consequence: secret reveals, gang turf, stake resolution). Rank-gated (`OrganizationRank.can_declare_standing`); DISFAVOR additionally requires the target's `hostile` antagonism consent (#2170, the same category the frame-job denounce gate consults); rate-limited to one per (organization, target persona) per IC week. The delta applies through the existing `bump_organization_reputation` — the declaration row is an audit trail, never a parallel writer. Public by design, unlike the hidden reputation value it moves.
_Avoid_: standing bump (that conflates the act with the mechanism), favor grant, disfavor order.

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

**Material Source** (`HoldingMaterialSource`, #2540 slice 2):
One material-producing row on a `DomainHolding` — `material_category` + `quality` + `source_kind` (`MaterialSourceKind.BULK`/`GEM_MINE`, `world.items.constants`). Replaces the old flat `DomainHolding.mine_quality`/`common_gem_tier` fields so one holding can carry more than one production source, and so a non-gem bulk yield (farm, quarry) shares the exact same shape a gem mine used to hard-code. `GEM_MINE` sources still roll rare finds (`gems.mining.roll_gem_haul`); `BULK` sources produce flat value only. The weekly cycle (`items.materials_production.accrue_holding_materials`) iterates every source a holding carries, crediting the holding's `OrgIncomeStream` per category.
_Avoid_: mine (gem-only, superseded — a Material Source need not be a mine), production slot, yield row.

**House Feed**:
The pull feed of a household's own deeds and revealed scandals (`house_feed_for`, tidings) — the Arx 1 informs replacement. No feed model; query-and-merge like the public feed.
_Avoid_: org informs, house inbox, notifications (it is not push).

**House Claim**:
The CG-only application defining the house behind a set-aside claimable `Title` (#1884 Phase D) — the character enters play as a representative of a house that has always existed. Automated thematic gates at submission, staff review in admin, materialization at CG finalization only. Founding a new house *in play* is a different, future loop.
Materialization shares `world.societies.houses.creator.build_family_org` with the plain (name-path) family builder (#3648): the title path calls it, then additionally seats the title, reassigns the seat domain and holdings, and syncs the house channel.
_Avoid_: house founding (in-play), ennoblement (future loop), house application (ambiguous with roster apps).

**Vacancy**:
See `world.roster.AGENT_GLOSSARY.md`'s Vacancy entry (#3648), the canonical
definition, which lives there alongside Family Template since both are CG Lineage-step
concepts. In short: a staff-authored opening on a staff-minted family's org
(`societies.Vacancy`), kin or retainer, priced flat plus per-influence, with an
optional standing (uncapped) capacity. See ADR-0272.

**Aspect (house)**:
A required, normalized catalog choice on a house template (#2079, ADR-0101): `HouseAspectDefinition` (prompt, min/max picks) + its `HouseAspectOption` catalog, answered at CG by picks alone (never free text; the authored list IS the thematic fence). Picks become permanent `OrganizationAspect` identity facets at materialization. Also the recipe for a culture-specific family fact WITH variants (a house quiddity, #3617): see `docs/systems/family-authoring-recipes.md` Recipe 7.
_Avoid_: trait, flaw, house perk, custom aspect (there is no free-text path).

**Feature (house)**:
A structural cultural fact about houses of a template (#2079): `HouseFeature` (unique slug = stable code anchor) stamped as `OrganizationFeature` at materialization. No player input; orients the founder at CG and anchors future systems (a ledger UI checks slug `black-ledger`). Also the recipe for a FLAT culture-specific family fact (a Letter of Marque, #3617): see `docs/systems/family-authoring-recipes.md` Recipe 7.
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

**Appeal** (`OrgAppeal`, #3293):
The canonical IC term for a free-text ask lodged with an organization — any character may lodge one, members read and sign onto it, leadership resolves it (`GRANTED`/`DECLINED`) with a written answer, or the petitioner withdraws it. Mirrors `GroupStoryRequest`'s OPEN→resolved shape for a different target (org vs. GM pool). See ADR-0231.
_Avoid_: **petition** — that word is reserved for the unrelated OOC staff-contact ticket (`player_submissions.Petition`); never use it for this IC surface.

**Sign On** (`OrgAppealSignon`):
A member's public show of support for an open Appeal — visible to org members and the petitioner, distinct from resolving it. Recorded as one row per (appeal, member); re-signing on is idempotent, not an error.
_Avoid_: co-sign, endorse (Endorse is a separate scene-pose mechanic).

**can_resolve_appeals**:
The `OrganizationRank` capability flag gating who may grant or decline an Appeal for that organization — independent of `can_manage_ranks`; staff may always resolve regardless of rank.
_Avoid_: appeal permission, resolver flag.
