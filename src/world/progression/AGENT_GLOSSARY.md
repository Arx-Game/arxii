# Progression glossary

> Durance, XP, and Development Points are cross-cutting terms — see the root `AGENT_GLOSSARY_MAP.md`.
> Kudos, Weekly Vote, Vote Budget, and Memorable Pose are defined below — they're the
> applause-economy axes native to this app (see ADR-0115 for how they relate to
> `InteractionReaction`, the sibling axis defined in `scenes/AGENT_GLOSSARY.md`).

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
great post, played fair through a loss. Distinct from `WeeklyVote` (a scarce,
budgeted popularity signal) and `InteractionReaction` (cosmetic/relationship
expression) — see ADR-0115 for why all three stay separate axes. Every award pushes
a real-time `kudos_received` WS toast to the recipient (`notify_kudos_received`,
#2161); the awarder's identity is never exposed to the recipient
(`KudosTransactionSerializer` drops `awarded_by`, ADR-0033).
_Avoid_: applause, upvote, like (reserve those for `WeeklyVote`/`InteractionReaction`).

**Weekly Vote**:
A single cast of a player's weekly `WeeklyVote` on a piece of content (a pose,
scene participation, or journal entry) — the popularity axis of applause. Toggleable
(cast/uncast) until the weekly cron processes it; settles into `MEMORABLE_POSE` XP
for top-ranked poses and ranks the scene highlight reel by all-time vote count
(#2161, `SceneViewSet.highlight_reel`). Frontend surface: `VoteButton` on each
`PoseUnit` and the `/xp-kudos` `VotesPanel`.
_Avoid_: kudos, like, favorite (favoriting is the private, non-social
`InteractionFavorite` bookmark, unrelated to this axis).

**Vote Budget**:
`WeeklyVoteBudget` — how many `WeeklyVote`s an account can cast in a given
`GameWeek`: 7 base votes plus 1 bonus per scene attended that week
(`scene_bonus_votes`), minus `votes_spent`. Resets every game week; not a
carry-forward currency.
_Avoid_: vote balance, vote allowance.

**Memorable Pose**:
The weekly settlement outcome for the top-3 vote-ranked poses (via
`process_memorable_poses`): 1st/2nd/3rd place authors receive `MEMORABLE_POSE_XP`
([3, 2, 1]) XP, capped per-account by `VOTE_XP_CAP`. This is where a `WeeklyVote`'s
popularity signal cashes out into XP — kudos and reactions have their own,
independent settlement/effects.
_Avoid_: top pose, featured pose (that's the highlight reel's *featured* slot,
which can headline a GM-tagged pose with zero votes — a different selection rule).

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
