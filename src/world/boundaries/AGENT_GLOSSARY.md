# Boundaries glossary

**Content Theme**:
A staff-authored, coarse content category (`ContentTheme`, NaturalKey on `key`) used
for automatic hard-line matching — tagged onto a `StakeTemplate` (`content_themes`
M2M) and picked by players as a `PlayerBoundary`'s `theme`. A category match, not a
specific-entity match: it doesn't matter *which* NPC/location/item is at risk, only
that the *kind of content* intersects.
_Avoid_: content warning, trigger tag (this app never uses "trigger" — see Hard Line).

**Hard Line**:
A `PlayerBoundary` with `kind=HARD_LINE` — a content theme a player never wants
staked against their character, under any narrative frame. Structurally forced
`PRIVATE` visibility (`clean()` + serializer `validate()` both raise otherwise) and
readable by no one but its owner, not even staff (`IsOwnPlayerData` has no staff
carve-out). A theme match on any staked `StakeTemplate` **blocks the whole stakes
contract**; the block reason (`blocked_reason_private`) is staff/audit-only and
never surfaced to the GM or any player (ADR-0033, ADR-0086).
_Avoid_: trigger warning, content warning, veil (a Hard Line is never communicated,
only enforced — a Veil, if this codebase used the term, would be the shareable
opposite; this app uses **Advisory** for that instead), consent limit (see
Player Boundary's `_Avoid_` note — a Hard Line is a content limit, not a per-action
consent decision).

**Advisory**:
A `PlayerBoundary` with `kind=ADVISORY` — a communicated (optionally shareable)
content preference that never blocks anything. Distinct from a Hard Line
(auto-blocked, always private): an Advisory may be shown to scene participants via
the [lines & veils](../stories/AGENT_GLOSSARY.md) aggregate, `scene_lines_and_veils`.
_Avoid_: soft limit, content warning.

**Player Boundary**:
The model (`PlayerBoundary`) carrying both Hard Line and Advisory rows, owned by
`PlayerData` so it persists across every character the person plays (an OOC content
limit is about the *player*, not any one persona). Not itself a term for either kind
alone — say "Hard Line" or "Advisory" when the kind matters.
_Avoid_: consent preference (that's the ADR-0024 social-consent app —
`SocialConsentPreference` gates *behavior-altering effects between PCs*; a Player
Boundary gates *what content themes may be staked against a character at all*, a
different axis), trigger warning.

**Treasured Subject**:
A specific entity (`TreasuredSubject` — an NPC ally, an heirloom item, a location, a
faction relationship, or a freeform custom subject) a player flags as
devastating-if-lost, owned by the `RosterTenure` (the specific character-instance
whose attachment it is — distinct from Player Boundary's `PlayerData` ownership,
since this is a per-persona attachment, not an account-wide OOC limit). Matched
against a `Stake`'s wagered subject by **specific-entity identity**
(`_subject_identity` — typed FK equality, or `subject_label` for untyped kinds),
never by Content Theme. A match never blocks a stake outright; it requires an
explicit **Treasured Sign-off** first — losing a treasured subject is often exactly
the narrative beat the player is opting into, unlike a Hard Line theme, which is
never wanted.
_Avoid_: veil (a Treasured Subject flag can be shared/veiled per scene, but the term
this app uses for the shared read is "lines & veils," not "veil" for the flag
itself), stake (a Stake is the GM-authored wager on a Beat; a Treasured Subject is
the player's private flag that a Stake may or may not match against).

**Treasured Sign-off**:
`TreasuredSignoff` — a player's explicit, per-beat consent to stake one of their
Treasured Subjects. Required before a matching stake can activate for that player
(`check_stake_boundaries` adds the sheet id to `requires_signoff` until an active
sign-off exists); soft-withdrawable only (`withdrawn_at`, never hard-deleted —
story-significant data). Withdrawing mid-story routes *only* the matching stake to
the `WITHDRAWAL` resolution column at completion — sibling stakes on the same
contract grade normally.
_Avoid_: consent (see Player Boundary's `_Avoid_` note — a Sign-off is a per-beat
opt-in to a *specific* wager, not the ADR-0024 social-consent mechanism), approval,
opt-in (reserve "Opt-in / Commit Step" for the stakes-contract-wide moment
documented in `world/stories/AGENT_GLOSSARY.md`).

**Lines & Veils** (scene aggregate):
The anonymized, per-scene read (`scene_lines_and_veils` →
`world.boundaries.types.SceneLinesAndVeils`) unioning every participant's shared
Advisory `PlayerBoundary` rows and shared `TreasuredSubject` rows, owner stripped.
Hard Lines are structurally excluded — the underlying query only ever selects
`kind=ADVISORY`, so a Hard Line cannot appear even in principle. Named for the
tabletop-RP safety-tool convention (lines = hard limits, veils = fade-to-black
content) but this codebase's actual Hard Line/Advisory vocabulary is what the model
layer uses; "lines & veils" names only this one aggregate read, not the underlying
mechanisms.
_Avoid_: content digest, safety card.
