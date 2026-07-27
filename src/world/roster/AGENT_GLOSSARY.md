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
  pins constrain later siblings. _Avoid:_ heredity service named "lineage"
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
- **Letter (PlayerMail)** — a `PlayerMail` row: private, tenure-to-tenure
  correspondence (`sender_tenure` → `recipient_tenure`, threaded via
  `in_reply_to`), routed by `RosterTenure` rather than `AccountDB` so it
  preserves player-anonymity: the recipient is addressed and displayed as
  the current player of a character, never by account (#2160,
  ADR-0116). Web is the letters surface — compose/inbox at
  `/profile/mail`, an in-scene quick-compose from the character card, an
  unread badge, and a `MAIL_ARRIVED` websocket push on send; there is
  deliberately no telnet mail command. _Avoid:_ "mail Ariel" as a telnet
  verb (retired aspiration, never built); messenger/courier (a distinct,
  not-yet-built in-fiction delivery layer — see ADR-0116).
