# ADR-0279: An enemy is a priced flaw the world must collect, on two scales

**Status:** Accepted (#3621, 2026-09-07, Apostate's rulings on the demo). Related ADR-0277, ADR-0269, ADR-0010.

**Context.** Character generation had no way for a player to give their character an
antagonist that the world would act on, and no reason to: flaws bought nothing. The
free-text personality field that was meant to carry motivation was skipped by most
players, and the goals instrument sat apart from it. The Actor's Sheet (#3621) replaces
personality with three questions about action, folds goals in as numbered short and long
term entries, and adds one priced enemy.

**Decision.** An enemy awards CG points into the shared purse in proportion to how far
it reaches and how badly it wants the character to fail, and that award is a debt the
world collects. Two scales: a **person** is rated on the Path ladder with Quiescent below
Prospect (`EnemyPowerTier`), a **group** takes its reach from its `OrganizationType`
(`EnemyReach`: household, house or company, society or church, realm), overridable per
Beginning offer when a group cannot reach where the character plays. Four degrees
(`EnemyDegree`: annoyed, thwarted, ruined, "will relentlessly try to destroy you"); death
is not a tier, ruined includes it. The price tables are constants
(`ENEMY_PRICE_GROUP`, `ENEMY_PRICE_PERSON`, 1 at the bottom corner, 150 at the top).
Collection happens at finalize through seams that already exist: the group's opinion
(`bump_organization_reputation`, the same seam a Lineage answer's seed uses), a
Distinction at the two worst degrees through the bundled-Distinction path (#3660), and
pinned pursuit heat where the enemy's society enforces the character's start. An enemy
picked from the offered list (the Lineage's answered groups and persons, plus
`BeginningEnemyOffer` rows) is placed; a free-written one prices at one point and stays
pending until staff link it in admin, which recomputes the price.

**Why not a Distinction.** Difficulty pays and comfort costs on every CG stage (Apostate
with TehomCD, 2026-09-02); a Distinction catalog cannot price "the Republic of Luxen
wants me dead" against "a baron's son nags me" without a row per pair. The grid prices
itself, and staff place rather than price.

**Why the debt must be collectable.** Points now for trouble later is only honest if the
trouble arrives. Linking the row to a real Organization or Family is what lets heat,
crises, missions and standing act on it; a free-written enemy with nothing behind it is
priced at one for exactly that reason.

**Privacy.** The Actor's Sheet is public; the enemy row (name, scale, degree, price) is
owner, staff and assigned-GM reading, and the sheet shows the character's own public
line. Anything private about it is a Secret (the row's nullable `secret` link), never a
per-answer toggle: the Secrets system is the game's one privacy primitive.

**Consequences.** `Profile.personality` is removed (0107 carries any text into the
character's First Journal entry, ADR-0237 restructure). Goals lose their one-per-domain
key: any number may sit in any domain, numbered within short term and long term, and the
domain bonus is summed. The Introductions (First Journal, Application, Whispers) are
white journals found by `JournalEntry.kind`; each Whispers line is a Level-1 player-flavor
Secret with gossip heat (#1572), so the built rumor machinery carries them and no rumor
model is invented. Institution reading rooms (the First Journal at the Archive, the
Application at Shroudwatch) and in-play writing of a First Journal for a non-Arx start
are later surfaces the kind makes possible; general rumor authoring stays #2986.
