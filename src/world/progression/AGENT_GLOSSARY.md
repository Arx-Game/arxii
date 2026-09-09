# Progression glossary

> Durance, XP, and Development Points are cross-cutting terms — see the root `AGENT_GLOSSARY_MAP.md`.
> Kudos, Nomination, and the four settlement paths are defined below — they're the
> applause-economy axes native to this app (see ADR-0115, amended by ADR-0286, for how
> they relate to `InteractionReaction`, the sibling axis defined in
> `scenes/AGENT_GLOSSARY.md`).

**Unlock**:
An authored advancement target a character can spend XP to acquire — e.g. `ClassLevelUnlock` (a class level) or `TraitRatingUnlock` (a major trait threshold) — whose availability is governed by Requirements.
_Avoid_: perk, purchase, upgrade.

**Requirement**:
An authored gate attached to an Unlock, evaluated per character through `is_met_by_character(character) -> (bool, str)`. Concrete kinds include Trait, Level, ClassLevel, MultiClass, Tier, Achievement, Relationship, Legend, Item, and MajorGiftTechnique requirements. New kinds MUST be added to the hardcoded `requirement_types` list in `services/spends.py` — an omitted entry silently never evaluates (see `reference-requirement-types-hardcoded-list`).
_Avoid_: prerequisite, condition (reserve "condition" for the conditions system).

**MajorGiftTechniqueRequirement** (#2440 ruling 4):
The level-2 Durance gate: a character must know >= `minimum_techniques` (default 3) techniques of their single MAJOR gift (`Gift.kind == GiftKind.MAJOR`, resolved via `CharacterGift`) — a COUNT, not completeness (a gift can grow many, several level-gated, techniques over a character's life). Minor-gift techniques never count. Seeded onto the level-2 `ClassLevelUnlock` by `seed_major_gift_technique_level_requirement` (`world.progression.seeds`).
_Avoid_: "starter pool complete" (CG only hands out 1-3 picks; the rest are meant to be filled out in play via Academy/Archive TRAIN offers, #2440).

**ClassLevelAdvancement**:
The receipt for a single within-tier class-level advance performed through the Ritual of the Durance; it records level_before/after, officiant, ritual, and scene, and survives character death. Its tier-crossing sibling is `AudereMajoraCrossing`, both sharing `AbstractClassLevelAdvancement`.
_Avoid_: level-up event, training record.

**PathIntent**:
A character's mutable declared intention for their next Path — one row per sheet, overwritten on re-declaration — which the Audere Majora offer pre-selects when it is among the eligible paths.
_Avoid_: path receipt, path choice (it is an aspiration, not a committed record).

**Kudos**:
An unlimited, GM- or player-awarded "good sport" currency (`award_kudos`,
`KudosTransaction`) recognizing graciousness — someone was a good sport, wrote a
great post, played fair through a loss. Distinct from `Nomination` (the invisible
popularity signal, #3738) and `InteractionReaction` (cosmetic/relationship
expression) — see ADR-0115 for why all three stay separate axes. Every award pushes
a real-time `kudos_received` WS toast to the recipient (`notify_kudos_received`,
#2161); the awarder's identity is never exposed to the recipient
(`KudosTransactionSerializer` drops `awarded_by`, ADR-0033).
_Avoid_: applause, upvote, like (reserve those for `Nomination`/`InteractionReaction`).

**Nomination** (#3738):
A player's OOC "I am voting this person for good RP because of this": a `Nomination` row
by the **account** (alts and personas collapse to one) naming the **character** whose
prose it was, hung off a pose or a public journal entry from the current `GameWeek` that
the nominator could see. One account nominating one character in one week is one
nomination however many pieces it cites; the extra rows only cite more prose. No budget;
the scarcity is what you could see this week. **Invisible**: no toast, no count, no
names; the nominee learns only the settled XP. Replaced `WeeklyVote` + `WeeklyVoteBudget`
(the Arx I shape: a capped weekly budget rewarding scene volume). Frontend: `NominateButton`
beside the reaction row on each `PoseUnit` and on public journal rows; `NominationsPanel`
(your own list) on `/xp-kudos`.
_Avoid_: vote, upvote, like, kudos, favorite (favoriting is the private `InteractionFavorite`
bookmark, unrelated to this axis).

**Stepped curve** (#3738):
`stepped_xp(count, first_xp)`: the reviewer's tier floors to 133 (1 | 2-3 | 4-6 | 7-10 |
11-16 | 17-25 | 26-38 | 39-58 | 59-88 | 89-133), then each tier widens by half; one XP per
tier from `first_xp`. The curve is the only cap.
_Avoid_: diminishing-returns formula, vote XP cap.

**Nominations in general / Most nominated prose / Best in scene / Most nominated journal**
(#3738): the four settlement paths `process_weekly_nominations` pays on the weekly
rollover. In general: distinct people who nominated the character, curve from 3
(`NOMINATION_FIRST_XP`). Most nominated prose: the character's own most-cited piece, one
instance per week, flat 1. Best in scene: scenes in which their pose was the most
nominated (ties count for every tied writer), curve from 1. Most nominated journal: the
one journal entry game-wide with the most nominators, flat 1, ties pay all. The reviewer's
examples: one scene, one friend = 5; twenty scenes, a hundred people, best in all = 19.
_Avoid_: Memorable Pose, memorable poses top three (the 3/2/1 placings went with votes),
top pose, featured pose (that's the highlight reel's *featured* slot, which can headline a
GM-tagged pose with zero nominations — a different selection rule).

**trainer-of-record**:
The `CharacterSheet` stored on a `DuranceTrainingSite` as the room's designated officiant.
The actual eligibility gate (`assert_can_officiate`) runs on this trainer, not on any
live-present character, so an inductee can self-conduct their Durance at the site.
_Avoid_: static officiant, pre-assigned trainer.

**training site**:
A room registered as a place where the Ritual of the Durance can be conducted without a
live higher-level PC, by binding a trainer-of-record to the room (`DuranceTrainingSite`).
The rite still runs through the full ritual session lifecycle — only the officiant source
differs between a site-convened session and a live-officiant ceremony.
_Avoid_: self-serve durance, training room.
