# ADR-0292: There is no player-trust axis; per-thing permissions if we ever want one

Eight surfaces across character creation, the roster, distinctions, vacancies and stories gated
content on a player's "trust" — `StartingArea.minimum_trust`, `Beginnings.trust_required`,
`OriginTemplate.trust_required`, `OriginTemplateSlotChoice.trust_required`,
`Vacancy.trust_required`, `Distinction.trust_value`, `StoryTrustRequirement`, and the game-invite
threshold on `PlayerTrust` — and #3726 removed all of them along with `PlayerTrust`,
`PlayerTrustLevel` and `TrustLevel`. Seven read `account.trust`, an attribute no account type ever
carried, so each one failed closed: an authored `trust_required > 0` row was unreachable by every
player, and the eighth (invites) required a `PlayerTrustLevel` row nothing ever granted. The
ruling (2026-09-08, during #3725's review) is that trust is not coming: the Golden Rule covers
what these gates were reaching for, and if we ever want to restrict a specific thing we design an
independent permission for that thing at that time rather than keeping a dormant number that every
new feature is tempted to gate on. A dormant gate is worse than no gate, because it reads as
policy — `StartingArea` kept a whole `TRUST_REQUIRED` access level and a fail-closed
`AttributeError` guard (#3046) to stop an admin flipping it from 500ing the origin stage for
everyone, which is a lot of machinery in service of an option no one could ever satisfy.

`TrustCategory` and `TrustCategoryFeedbackRating` deliberately survive, keeping the name: they are
the authored dimensions a story performance is *rated* along, and those ratings are evidence, not
permission — they feed GM Story Reward XP (#2123) and the GM trust-ladder evidence view. GM
authority remains `GMProfile.level`, staff-set and audited (ADR-0097), and per-story authority
remains `StoryParticipation.trusted_by_owner`, granted by that story's owner. Both are already the
shape this ruling prefers: a specific permission over a specific thing, granted by a named person.

We rejected keeping the columns as inert scaffolding for a system that might arrive (the seven
years of `# TODO: Implement trust system` comments they carried are the evidence against that), and
rejected replacing the invite gate with a staff-permission check (nobody asked for invites to be
restricted; `registration_open` already decides whether the game is taking new players at all).
`docs/trust-based-permissions.md`, a design document for the system that is not being built, was
deleted rather than left to read as a plan.

> Status: accepted · Source: issue #3726, the reviewer's 2026-09-08 ruling during #3725's review ·
> Amends ADR-0097 (which scoped `PlayerTrust`/`TrustCategory` to per-category content trust; the
> `PlayerTrust` half of that is now gone, the `TrustCategory` half stands) · Related ADR-0237,
> ADR-0141
