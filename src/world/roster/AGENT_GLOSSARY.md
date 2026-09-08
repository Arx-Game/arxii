# Roster / Kinship glossary

Domain-local vocabulary for `world.roster` (character lifecycle + the #2062
kinship graph). Root terms live in `AGENT_GLOSSARY_MAP.md`.

- **Kinsperson** — a person-node in the kinship graph, at one of five
  definition tiers aligned with the real NPC ladder (name-only →
  functionary → standing → sheeted → PC). Never owned by a family; promoted
  up-tier only. _Avoid:_ family member (the retired family-scoped model).
- **Definition tier** — how real a Kinsperson is: NAME_ONLY (a string,
  never referenced again), FUNCTIONARY (room-referenced NPC via
  `npc_services.Functionary`), STANDING (permanent character object),
  SHEETED (staff-piloted CharacterSheet, never roster-appable), PC.
- **Parentage edge** — a typed child→parent fact: BIOLOGICAL /
  TREE_OF_SOULS / VAMPIRIC_EMBRACE / ADOPTIVE / FOSTER / ACKNOWLEDGED.
  N per child, any composition. **Adoptive changes lineage in law; foster
  changes who raised you, not whose line you are** (no inheritance claim by
  default); **acknowledged** is legitimation of an existing blood tie.
  _Avoid:_ mother/father slots (retired binary model).
- **Parent Dominance** (#2815) — the species-inheritance rule set in
  `services/heredity.py`: a child is the mother's species unless the
  father's power band strictly exceeds hers; chimeric (a unique authored
  species) is possible only when both parents are Grand+. Roles are derived
  at computation time (gender for BIOLOGICAL, ritual invoker for
  TREE_OF_SOULS), never stored. Validation is one-directional and
  creation-time only (ADR-0173). _Avoid:_ "crossing" for species mixing —
  that word is the magic-progression threshold (levels 3/6/11/16/21).
- **Power band** — `Kinsperson.power_band` (`PowerBand` choices mirroring
  PathStage names + QUIESCENT). Null = unspecified, assumed sub-Puissant;
  staff/GM-authored only — players can never set it. Everything below
  Puissant is one dominance tier; the finer bands are story color.
- **Ritual invoker** — `ParentageEdge.is_ritual_invoker` on a TREE_OF_SOULS
  edge: the parent who invoked the ritual, and therefore the dominant line
  regardless of gender (the Tree exists partly so same-sex couples can have
  children). At most one per child. _Avoid:_ treating it as a gender slot.
- **Pinned trait value** — a `KinspersonTraitValue` row: a parent stub's
  known appearance color. Written by CG approval back-inference (a child's
  off-palette pick is attributed to the cross-species parent) or staff
  authoring; the first child to draw on an unpinned trait defines it, and
  pins constrain later siblings. Children of *fully*-pinned parents work
  from the family look (`base_trait_options`): a trait every parent line
  has pinned collapses to the parents' values, mother's first; an unpinned
  side keeps the palette open. _Avoid:_ heredity service named "lineage"
  (that word already means the CG stage, display-lineage, and roadmap
  lineage powers).
- **Step-parent / in-law** — DERIVED relations (a parent's union partner
  with no parentage edge to you; a spouse's blood kin), never stored — the
  fix for Arx 1's unmarked-in-law ambiguity.
- **Union** — a marriage/partnership edge between 2+ Kinspeople; kinds are
  authorable `UnionKind` rows (realm vocabulary) carrying
  `confers_wedlock`. Births stamp `born_within_union` for legitimacy law
  (#1884). _Avoid:_ marriage as a boolean on a person.
- **Public record vs truth** — every edge/union/incarnation carries
  `is_public_record` + `is_true`. A public-false fact is what the world
  wrongly believes; the hidden-true fact behind it anchors a
  `secrets.Secret` (who-knows rides secrets machinery). Hidden with no
  secret = staff-only. _Avoid:_ per-viewer belief tables.
- **Subject-unaware secret** — `Secret.subject_aware=False`: a truth about
  a character that even they don't start knowing (Misbegotten parentage);
  off their own-secrets shelf until granted.
- **Soul / incarnation** — reincarnation is a `Soul` with ordered
  `SoulIncarnation` memberships; "reincarnation of" derives from shared
  soul membership, knowledge is **per-life** (learning your own membership
  reveals public lives, not hidden intermediates). _Avoid:_ past-life
  edges (pairwise model, rejected — ADR-0097).
- **Appable slot / slot pool** — the app-in mountain: a pre-authored
  Kinsperson with claim constraints (gender set, age band, name lock), or a
  `KinSlotPool` ("8 children among these parents") minting nodes on claim.
  CG claims bind the new sheet at finalization. _Avoid:_ placeholder (the
  retired member_type).
- **Deferred definition** - a CG choice to leave kin slots (e.g.
  parents) deliberately undefined, recorded via `deferred_definer`; filling
  them later is holder-only and review-gated ("would everyone have already
  known this" is a human judgment). _Avoid:_ retcon slot.
- **Family membership (claim)** — how a Kinsperson belongs to a `Family`:
  basis (born / married-in / adopted / legitimized / granted / founding) +
  end reasons (disowned / married-out / renounced / annulled), with dates.
  `Kinsperson.family` is only the surname denorm of the active primary
  claim. _Avoid:_ family as a container that owns people.
- **Family Kind** (#3617): `FamilyKind`, an authored kind of family
  (Commoner, Noble, Crime, or any kind staff add): a row, not a code list.
  `styles_as_house` makes materialized orgs rooted in the kind named
  "House <name>"; nobiliary particles come from `NobiliaryParticle` rows
  authored per realm and kind, independent of this flag. Canonical rows
  come from migration 0219 in a real deploy; test tiers never replay
  migration `RunPython`, so a caller that needs a canonical kind without
  assuming a migrated database calls `world.roster.seeds.ensure_family_kinds()`
  (tests use `FamilyKindFactory`). _Avoid:_ family type (the retired code
  list `Family.kind` replaced).
- **Influence** (#3617): `Family.influence`, how much authority a family
  holds over the world. 0 = none; player-named families are always 0; only
  staff-authored families are ever above 0. The price base for claim-path
  Upbringing Choices (`cost_per_influence x influence`). See
  `docs/systems/family-authoring-recipes.md`. _Avoid:_ stature (House
  Stature, #3091, is a live computed org-level deterrence score; influence
  is a staff-set, CG-pricing-only number on the family itself).
- **Upbringing** (#3617): `OriginTemplate`, the authored card a player picks
  in the Lineage stage within a Beginning: a CG point cost, a trust gate,
  and which Family Paths it allows. The code keeps the `OriginTemplate*`
  class names (Decision 4 on #3617); "Upbringing" is the player- and
  staff-facing word. _Avoid:_ origin option, household.
- **Family Path** (#3617, #3648): `FamilyPath`, the shape an Upbringing gives a
  character's family record: claimed (a staff-authored family of an offered
  Family Kind, entered through a Vacancy when one is offered), named (a new
  family built from a Family Template, influence 0), or none (the tarot
  surname ritual). Resolved per-draft by `CharacterDraft.resolve_family_path()`.
  The Lineage page order is Upbringing picker, any-scoped Prompts, the family
  block (path picker when more than one path is allowed, then the path body),
  path-scoped Prompts. _Avoid:_ family-known flag (the retired
  `Beginnings.family_known`; the job is now the Upbringing's paths).
- **Prompt (Upbringing)** (#2478, #3617, #3648): `OriginTemplateSlot`, an
  authored question scoped to a Family Path (`applies_to`) or shown on every
  path (`any`); `allows_text` controls whether a free-text write-in is offered
  alongside any pick-list Choices. Rendered as `any`-scoped prompts above the
  family block and path-scoped prompts below it (#3648's page-order change).
  _Avoid:_ slot alone outside kinship app-in context (that word already names
  the appable-slot mountain here).
- **Choice (Upbringing)** (#3617): `OriginTemplateSlotChoice`, one authored
  pick-list answer on a Prompt, priced `cg_point_cost + cost_per_influence x
  influence` (`cost_for()`); influence is 0 on the name and none Family
  Paths. _Avoid:_ option (reserved for `HouseAspectOption`/`FormTraitOption`
  elsewhere in this codebase).
- **Family Template** (#3648): `HouseTemplate`, the type a named family is
  built from: kind, org type, society, aspect questions, served house
  choices, and (title path only) a liege and succession law. An Upbringing's
  `family_templates` M2M names which template(s) its name path offers; one
  auto-picks, more than one shows a picker. See
  `docs/systems/family-authoring-recipes.md`. _Avoid:_ house template as the
  general term (the model stays named `HouseTemplate` in code, but every kind
  of family uses it, not only houses); charter for a non-noble kind (charter
  stays the noble-title-founding term).
- **Vacancy** (#3648): `societies.Vacancy`, a staff-authored opening on a
  staff-minted family's org: what the holder does, two authored importance
  axes (below), and a price. Kin when it links the kinship tree (a
  `KinSlotPool` or an appable `Kinsperson`), retainer otherwise; a blank
  capacity (`count_remaining`) is a standing vacancy, always open. Taken at CG
  finalize via `take_vacancy`, which stamps `OrganizationMembership.vacancy`.
  _Avoid:_ position, appointment, seat, station, role, slot (each already
  means something else in this codebase; see ADR-0273).
- **Importance / Presumed importance** (#3648): the two authored axes on a
  Vacancy: `importance` (how much the family truly cares about the holder,
  visible only to the holder and staff) and `presumed_importance` (what
  outsiders assume, the public-facing number). Descriptors with no consumer
  yet as of #3648. _Avoid:_ standing (`StandingDeclaration` is a live
  reputation nudge), regard (`NpcRegard`, an NPC's opinion), stature
  (`HouseStature`, an org-level computed deterrence score).
- **Served house** (#3648): the staff `Organization` a name-path family swore
  fealty to, from `HouseTemplate.served_house_choices`; recorded on
  `CharacterDraft.served_house` and, at materialization, as the org's fealty
  edge. _Avoid:_ patron (an `OrgPact` between two organizations is the
  patronage relationship; served house is a fealty declaration on a
  brand-new family).
- **Mail (PlayerMail)** - a `PlayerMail` row: private, OOC, tenure-to-tenure
  correspondence between players (`sender_tenure` -> `recipient_tenure`,
  threaded via `in_reply_to`), routed by `RosterTenure` rather than
  `AccountDB` so it preserves player-anonymity: the recipient is addressed
  and displayed as the current player of a character, never by account
  (#124/#146, reaffirmed #3303, ADR-0226). Web is the mail surface -
  compose/inbox at `/profile/mail`, an in-scene "Message the player"
  quick-compose from the character card, an unread badge, and a
  `MAIL_ARRIVED` websocket push on send; there is deliberately no telnet
  mail command. _Avoid:_ letters/missives/correspondence for this surface
  (that framing belongs to #3289's separate, not-yet-built IC messaging
  system - see ADR-0226); "mail Ariel" as a telnet verb (retired
  aspiration, never built); messenger/courier (part of that same
  not-yet-built IC delivery layer).

**Consort**:
A realm-recognized OFFICIAL secondary partner (#3091) — a realm-scoped `UnionKind` row carrying the stature vocabulary fields (`stature_share_pct=50`, `contributes_to_origin_house=False`, `requires_landed_title=True`, `max_concurrent` = the realm cap: Inferna 3, Umbros/Ariwn/Aythirmok 1). A consort's renown weighs half toward the senior party's house, only while the senior holds a landed `Title`, and never flows back to the consort's origin house. Luxen recognizes no consorts — expressed as the ABSENCE of a Luxen consort row, never a flag. Realm rows carry realm display names; "consort" is the mechanical term in code/docs only (Arx 1 used "consort" for a title holder's spouse — that sense is styled by courtesy titles here, not this word).
_Avoid_: concubine, secondary spouse, mistress.

**Paramour**:
An unofficial lover — a `UnionKind` with `stature_share_pct=0`; socially real, mechanically weightless for house stature.
_Avoid_: consort (that is the official institution), affair record.

**gifted_rating (Kinsperson)**:
Staff-authored 0–5 Gifted weight for kin WITHOUT sheets (#3091). Sparse by design: only PCs and staff-defined significant figures are Gifted; the wider population stays 0. Sheet-bound kin rate from their sheet (best class level). Feeds house stature renown and the `MOST_POWERFUL_GIFTED` succession rater; a PC adopted from a kin stub enters at level 1.
_Avoid_: power level, magic score.

**Selection**:
The durable server-side fact of which `RosterEntry` an account is currently
browsing as (state 2.5 in the four-state model: logged out / logged in-no-selection
/ selected / puppeting) — `PlayerData.selected_entry`, mutated only through
`world.roster.services.selection.set_selected_entry`, mirrored client-side by
`gameSlice` (#3412). Selection is a fact, not an action: it carries zero
lifecycle, session, or puppeting side effects — see ADR-0241. Player-facing
state label ratified by Apostate (refined 2026-08-28): **Playing: Currently
Offscreen** (see below).
_Avoid_: active character (ambiguous with puppeting/session state); current
character (same ambiguity); taken up (retired working label); Playing: Not In
World (first-pass label, refined same session — "offscreen" is the established
project word for this).

**Playing: Currently Offscreen**:
Ratified player-facing label for Selection (state 2.5), by Apostate 2026-08-28 —
a character is being played but is not in the world (vs. state 3, in-world play).
Chosen over "Not In World" for consistency with the project's established
"offscreen" vocabulary (offscreen acts, IC-but-offscreen). The ratification
carries a UI ruling with it: the load-bearing state signal is the **selected
character's portrait, prominently displayed** — played-by portraits are one of
the game's most popular features and effectively every player sets them, so the
docked portrait itself tells the player who they are playing; the text label is
supporting copy and the accessible equivalent (some blind players skip
portraits — the label/alt text must always carry the same fact). Design chrome
around the portrait, not a subtle text badge.
_Avoid_: taken up (retired); Playing: Not In World (superseded); subtle
text-only state indicators.

**Log out / quit / Clear Active Character** (the exit triad, Apostate
2026-08-28): three distinct exits that must never share a label. **Log out** =
leave the ACCOUNT (site logout; lives in the account menu). **quit** = the
standard-MU telnet verb: the character stops being actively in the world
(state 3 → 2.5) but STAYS selected on the website. **Clear Active Character** =
drop the selection entirely (state 2.5 → 2): logged in on the account with no
character — the control lives with the character list (the Hall's "Your
Characters" band), NOT in the header chip. Use case: browsing journals/events
while certain nothing gets posted as the wrong character.
_Avoid_: step away (retired — read as logout when placed next to "Enter the
world"); using any one of the three where another is meant.

**Offscreen act**:
A "2.5 act" (#3412 slice 3, ADR-0246) — one of a narrow set of action keys
(`actions.constants.OFFSCREEN_ACT_KEYS`: journal entries, character goals,
persona swaps, proclamations) the player can still perform on a degraded-
lifecycle character's behalf without that character being in-world. Gated by
`actions.offscreen_gate.offscreen_act_state`, keyed on
`CharacterSheet.lifecycle_state` (CAPTURED/UNKNOWN/RETIRED/DEAD) plus the
unconscious overlay; resolves ALLOWED / ROUTED / BLOCKED. Deliberately
distinct from an ordinary IC action (which the dead gate, #2287, and this
gate both refuse outright) and from Selection (state 2.5 is a durable fact
with no side effects; an offscreen act is a real mutation the gate decides
whether to permit).
_Avoid:_ 2.5 act as the only name (that's the state, not the act); treating
every action a state-2.5 account can trigger as an offscreen act — most
action keys never enter the gate's `OFFSCREEN_ACT_KEYS` set at all.

**Routed channel**:
PLACEHOLDER naming (Dan's to finalize) for how a `ROUTED` offscreen-act
disposition names *how* word could still travel for a degraded-lifecycle
character — `OFFSCREEN_CHANNEL_SMUGGLE` (CAPTURED) and
`OFFSCREEN_CHANNEL_DREAM` (unconscious) are the two implemented channel
constants (`actions/constants.py`); séance (DEAD) is named in prose and ADR-
0245 but has no channel constant yet. This slice (#3412 slice 3) ships zero
delivery mechanics for any channel — `ROUTED` is refusal-with-API-room, not a
working feature; the channel name is currently only ever seen in refusal
text (backend `OFFSCREEN_REASON_*` strings, and separately the Hall's own
display copy in `OffscreenActsPlate`).
_Avoid:_ treating a routed channel as a built messaging surface; conflating
the backend `OFFSCREEN_REASON_*` refusal strings with the Hall's own display
prose — the two registers are written independently and are allowed to
diverge.

**the Hall**:
PLACEHOLDER name for the state-2 logged-in home surface — mounts at `/` for any
authed account (visitors keep the pre-login Gatefold, byte-identical). Built in
the Commonplace Book idiom (ADR-0245): the "Your Characters" band (portrait
cards, per-character tidings `CountChip`s, `PersonaTiles`, select-on-click,
"Clear Active Character"), "Your Attention" (OOC mail + per-character pending
groups), and "The World" (clock, upcoming occasions, the Crier tidings skim).
Naming is deliberately unfinished — Apostate's to finalize; don't treat "the
Hall" as a canon term to build further copy/UI around until ratified.
_Avoid_: treating the name as final; "home page" (loses the in-fiction voice
the rest of the frontend maintains).

**Connection** (#3660):
The tie a "pick a group" Upbringing prompt records: which real
`societies.Organization` it names (its Anchor), what kind of tie it was
(`ConnectionKind`, a tag: raised by, taught by, served, sailed with, owes,
sworn to, hunted by), when it formed (`LifeStage`: childhood, youth, at the
Glimpse, since the Glimpse), and the player's Stance toward it. Stored as a
`character_creation.CharacterOriginSlot` row with `organization` set;
evaluated everywhere through `questionnaire.py`, never re-derived per caller.
_Avoid:_ tie, bond, mentor, patron, position, seat, station, role, standing,
regard; "pool" for anything but the POOL anchor source below.

**Anchor** (#3660):
The Organization a Connection resolves to. Which groups a "pick a group"
question offers comes from its authored source rule (`AnchorSource`): a pool
of every active org matching a type/society filter, a named list, the same
group an earlier group question resolved to, the house the character's
family served, or the character's own family. The last two need no stored
pick at all: `questionnaire.anchor_for` derives the Anchor fresh from the
draft every time, so a family-path switch can never leave a stale one behind.
_Avoid:_ tie, bond, mentor, patron, position, seat, station, role, standing,
regard; "pool" for anything but the POOL source specifically.

**Stance** (#3660):
An answer (`OriginTemplateSlotChoice`) on a Connection's "pick a group"
prompt: it may carry a price (against the resolved Anchor's own family
influence, 0 when that group has no Family), grant a Distinction bundled at
no extra cost, and seed the Anchor's opinion of the character
(`reputation_seed`, applied through `bump_organization_reputation` at
finalize). Distinct from a plain "pick one answer" Choice, which carries a
price and grant but never a seed. _Avoid:_ tie, bond, mentor, patron,
position, seat, station, role, standing, regard.

**Follow-up** (#3660):
An Upbringing prompt shown only once an earlier one is answered
(`OriginTemplateSlot.follow_up_to`), optionally narrowed to specific answers
on that earlier prompt (`shown_for_choices`; empty means any answer reveals
it). A hidden prompt's stored answer is ignored everywhere: pricing,
validation, and finalize persistence. _Avoid:_ branch as the field name (the
field is `follow_up_to`); treating a follow-up with no `shown_for_choices` as
unconditional in a different sense than "shown after any answer".

**Question kind** (#3660):
`OriginTemplateSlot.kind` (`QuestionKind`): TEXT (a write-in), PICK (a priced
pick-list, both pre-#3660), GROUP (a Connection to an Anchor), or PERSON (a
named figure, optionally scoped inside a GROUP question via
`same_anchor_as`). _Avoid:_ tie, bond, mentor, patron, position, seat,
station, role, standing, regard.

**Offer** (#3675):
One `character_creation.DistinctionOffer` row: says which chapter shows a
distinction, what opens it there, and how it arrives. The only surface a CG
picker reads or a player's pick validates against (`offer_id`) - there is no
plain "add this distinction" path left in CG. Authored on the Distinction
Builder, the tradition slate page, an Upbringing answer, or a Glimpse tag's own
change form; any of the four may add one for the same distinction. _Avoid:_
grant, unlock, requirement - an offer only says where a distinction is shown
and priced, never that the player already holds it.

**Opener** (#3675, #3709):
The thing an offer line hangs off, which both gates it and groups it on the leaf: a
chosen Glimpse tag (`glimpse_tag`), a picked Upbringing answer (`origin_choice`), a
living tradition's schooling stance (`schooling_line`), the question it answers on the
Actor's Sheet (`prompt`, `ActorSheetPrompt`), the enemy's picked reason (`enemy_reason`)
or marking degree (`enemy_degree`, ruined or destroy) on the enemy chapter, or the
section it sits in on Appearance (`appearance_section`). Every chapter's offers have
one; `DistinctionOffer.opener_fields` names the kinds a chapter accepts (the enemy
chapter accepts two), a row sets exactly one, and `opener_key` is the stable string
(`prompt:fear`, `reason:<id>`, `degree:ruined`, `section:<id>`) the leaf groups by.
_Avoid_: trigger, gate, tag (the Glimpse's tag is one kind of opener, not the word for all)

**Enemy reason** (#3709):
One row of the shared, authored list of why a person or group wants the character to
fail (`character_creation.EnemyReason`: `name`, `player_line`, `fits` person/group/
either). Picked on the Actor's Sheet before the character's own words; pinned per
Beginning enemy offer (`BeginningEnemyOffer.reason`); carried on `CharacterEnemy.reason`;
the enemy chapter's opener. Never seeded, always authored.
_Avoid_: motive, grudge, why (the free-text box is "in your own words", not the reason)

**Appearance section** (#3709):
An authored heading the Appearance chapter groups its offers under
(`character_creation.AppearanceSection`: `name`, `player_line`, `sort_order`); the
Appearance chapter's opener. Three or four rows for the whole game.
_Avoid_: category (the catalogue's own `DistinctionCategory` is a different axis), group

**First look** (#3709):
The few offer lines a block shows at rest. A Beginning pins a line into its first look
(`DistinctionOffer.first_look`, M2M through `OfferFirstLook`); a Beginning that pinned
nothing sees the first three by `sort_order`. The rest fold under "See N more"
(`ChapterOffers`); a block under five lines never folds.
_Avoid_: featured, recommended, suggested (the game never speaks for the player)

**Held** (#3709):
An offer line whose distinction the draft already has from a different line
(`VisibleOffer.held`); the leaf prints it pressed with the held word and no toggle,
never offers it twice. Distinct from a locked line (mutual exclusion).
_Avoid_: taken, owned, duplicate

**Awards** (#3709):
The price word for a negative cost, "Awards N": what the world owes the character for
carrying the trait, printed green; a cost prints in the realm ink. Every offer line,
tradition entry, Upbringing card and rail line uses it.
_Avoid_: refunds, reimburses, rebate

**Add from a table** (#3709):
The Distinction Builder's additions-only bulk entry (`web/admin/distinction_builder/
paste.py`): pasted rows resolved against existing rows, previewed (create / skip / error),
created in one transaction behind a digest-guarded confirm. Never updates, deletes or
creates a referenced row.
_Avoid_: import, load, bulk edit (there is no edit mode)

**Arrives as** (#3675):
`DistinctionOffer.arrives_as` (`OfferArrival`): CHOICE (a priced pick a player
must make explicitly), BUNDLED (free the moment its opener is satisfied,
alongside the opener - a group answer's own distinction), or CARRIED (free the
moment a tradition-state pick is made - a tradition-step drawback with no
`DistinctionOffer` row of its own, keyed by the synthetic
`"state:<TraditionState value>"` source). _Avoid:_ auto-add, auto-grant - both
BUNDLED and CARRIED still go through `reconcile_offer_picks`, never a bespoke
grant path.

**Chapter** (#3675):
`DistinctionOffer.chapter` (`OfferChapter`): which CG section shows the offer -
the Gift tradition step, the Glimpse, a Lineage answer, Appearance, or the
Actor's Sheet. Not a CG stage: several offer chapters can live inside one CG
stage (Gift holds both the tradition step and the Glimpse), and a stage may
hold no offers at all.

**Tradition state** (#3675):
`BeginningTradition.state` (`TraditionState`): SELF_TAUGHT, TEACHERS_GONE, or
LIVING_MASTERS - which standard line a Beginning's tradition-step entry prints
and which drawback, if any, picking it carries into the draft
(`world.character_creation.offers.tradition_is_self_taught`/`slate_state`,
never a name match against a tradition's own name). Replaces the pre-#3675
`required_distinction` FK.

**Standard lines** (#3675):
The shared, staff-authored wording every Beginning's tradition-step entries
draw from, so no CG line is ever written per-Beginning by accident:
`TraditionStateLine` (one row per Tradition state, its `entry_line` and the
drawback it `carries`) and `SchoolingLine` (the shared schooling set under a
living tradition). A Beginning may override a state line's words with its own
`own_wording`, never its own price - the price always reads through to the
carried/granted `Distinction`.

**Schooling line** (#3675):
One `SchoolingLine` row (rank 0-2): the standard stance a player picks under a
LIVING_MASTERS tradition, what it grants at that rank, and the derived price
(`grants.cost_per_rank * rank`). Shared by every Beginning; a schooling line's
own `DistinctionOffer` (chapter TRADITION_STEP) is kept in sync with it by the
tradition slate page's save, never authored separately.

**Closed by route** (#3675):
An Upbringing's `closed_distinctions` M2M (with its own `closed_reason` line):
distinctions this route never offers, in any chapter, regardless of whether
some other opener would otherwise satisfy it. Read by
`world.character_creation.offers.closed_for` for every chapter alike; a route
closes by field on `OriginTemplate`, never by matching a distinction's name.
