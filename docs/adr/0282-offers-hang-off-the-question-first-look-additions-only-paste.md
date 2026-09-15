# ADR-0282: An offer line hangs off the thing the player is answering; the Beginning pins the first look; bulk entry is additions only

**Status:** Accepted (#3709, 2026-09-08). Amends ADR-0280 (one opener per chapter); supersedes the
constant degree marks of ADR-0279. Related ADR-0010, ADR-0238, ADR-0278.

**Context.** ADR-0280 put distinction picking in the chapter that earns it, with one opener FK per
chapter and none at all for Appearance and the Actor's Sheet, so those two chapters rendered every
offer in one flat block. The Actor's Sheet's three questions (#3621) had their personality offers
in one list under all three; the enemy's "why" was free text; the marks the two worst degrees grant
were two names in a constant (`ENEMY_DEGREE_DISTINCTION_NAMES`), resolved by string at finalize.
The reviewer's intent is a catalogue of scores of distinctions, "this is what draws me to a
character", which one flat list per chapter cannot carry. Staff also had no way to land scores of
new rows on production, since the content repo is downstream of the database (ADR-0238) and the
Builder writes one row at a time.

**Decision.** (1) *Every chapter's offer line names what opens it.* `DistinctionOffer` carries
seven opener fields, and `_OPENERS_FOR_CHAPTER` maps a chapter to the set it accepts, exactly one
of which must be set: `schooling_line`, `glimpse_tag`, `origin_choice` as before; `prompt`
(`ActorSheetPrompt`: never do / protect / fear) on the Actor's Sheet; `enemy_reason` (an authored
`EnemyReason` row) or `enemy_degree` (ruined or destroy) on the new `OfferChapter.ENEMY`;
`appearance_section` (an authored `AppearanceSection` row) on Appearance. The opener is a
grouping key on the leaf (`VisibleOffer.opener_key`) as much as a gate: one block per prompt, per
reason, per section. (2) *The degree marks are bundled offer lines opened by the degree*, read by
`offers.degree_marks`, and the constant is gone; the mark lands through `reconcile_offer_picks`
like every other bundle, so finalize has no second fold. (3) *The enemy's why is a shared authored
list*, filtered by `EnemyReason.fits`, pinned per `BeginningEnemyOffer.reason`, carried on
`CharacterEnemy.reason`; the free text stays as the character's own words. (4) *The first look is a
pin*: `DistinctionOffer.first_look` (M2M to `Beginnings` through `OfferFirstLook`) says which
Beginnings show a line at rest; `ChapterOffers` folds the rest under "See N more", stands the first
three by sort order in for a Beginning that pinned nothing, and never folds a block under five.
(5) *Prices read "Awards N" in green and costs in the realm ink, and effects print as a compact
`+X; -Y` line* (`VisibleOffer.effect_line`), the reviewer's grammar. (6) *Bulk entry is additions
only*: the Builder's "Add from a table" resolves every name a pasted row carries against rows that
already exist, previews per row (create / skip / error), refuses the batch on any error, and creates
in one transaction behind a digest-guarded confirm; it never updates, never deletes, never creates
a referenced row, and is superuser-only.

**Rejected: a third opener on the Actor's Sheet for the enemy.** The degree mark and the reason
are two different openers, so the enemy became its own chapter rather than the sheet growing a
second and third opener kind; a chapter maps to a set of openers now, not one.

**Rejected: reusing `DistinctionCategory` or `DistinctionTag` as the Appearance section.** The
category is the catalogue's own axis (Physical, Personality...) and a tag is a filter with no
player line and no order; neither says "what shows", and both would have coupled the leaf's
layout to the catalogue's taxonomy.

**Rejected: an update mode on the paste.** Matching an existing row by name and rewriting it is
the exact silent-overwrite class ADR-0201 guards the content loader against. Editing a row stays
the Builder's, one at a time; a bulk edit would need its own ruling.

**Rejected: seeding the reason list or any distinction row.** The catalogue is the reviewer's own
content pass, in the reviewer's voice, after this ships; nothing player-facing is authored by code.
