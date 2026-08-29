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
- **Deferred definition** — a CG choice to leave kin positions (e.g.
  parents) deliberately undefined, recorded via `deferred_definer`; filling
  them later is holder-only and review-gated ("would everyone have already
  known this" is a human judgment). _Avoid:_ retcon slot.
- **Family membership (claim)** — how a Kinsperson belongs to a `Family`:
  basis (born / married-in / adopted / legitimized / granted / founding) +
  end reasons (disowned / married-out / renounced / annulled), with dates.
  `Kinsperson.family` is only the surname denorm of the active primary
  claim. _Avoid:_ family as a container that owns people.
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
