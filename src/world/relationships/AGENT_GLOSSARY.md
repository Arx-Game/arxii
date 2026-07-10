# Relationships glossary

**RelationshipTrack**:
A named axis along which one character's relationship toward another develops (Trust, Respect, Rivalry, Fear), each carrying a positive or negative sign.
_Avoid_: dimension, stat, axis (when unqualified).

**RelationshipTier**:
A milestone threshold within a track (e.g. Wary → Acquaintance → Confidant), reached once developed points cross the tier's `point_threshold`.
_Avoid_: level, rank, stage.

**Absolute Value**:
The unsigned total magnitude of all of a relationship's track points (developed plus temporary), always positive; the permanent-only variant is the Developed Absolute Value.
_Avoid_: intensity, total score, magnitude.

**Affection**:
The signed sum of a relationship's track points — positive-sign tracks add, negative-sign tracks subtract — expressing its net warmth or hostility.
_Avoid_: sentiment, like/dislike, net score.

**Developed Signed Sums** (`developed_signed_sums`, #2034):
A `(positive_sum, negative_sum)` split of Developed Absolute Value by track sign — the two developed-points totals that Affection nets against each other, kept separate. Consumed by `world.magic`'s fraught pull term (see below); `pos + neg` always equals Developed Absolute Value.
_Avoid_: recomputing from scratch — read via the cached `cached_track_progress` path, never a fresh query.

**Fraughtness** (magic pull term, ADR-0110):
A `world.magic` thread-pull bonus for a bond invested heavily in BOTH positive and negative tracks at once (love/hate) — keyed on the smaller of Developed Signed Sums' two values, so a bond lopsided entirely in one direction earns nothing. Not a relationships-app concept in itself; documented here because it reads this app's data.
_Avoid_: conflating with Affection (net) or `HybridRelationshipType` (a display label, not this mechanic).

**Devotion** (magic pull term, ADR-0110):
A `world.magic` thread-pull bonus for a bond whose Developed Absolute Value clears a threshold well past the generic pull curve's own half-saturation point — depth alone, no ritual or ceremony gate. Distinct from the seeded "Devotion" `RelationshipTrack` row — the math never special-cases any specific track.
_Avoid_: implying a gate or ceremony requirement; implying it's specific to the "Devotion" track.

**Capacity**:
The per-track ceiling on developed (permanent) points; it is raised by Updates and Capstones.
_Avoid_: cap, max points, limit.

**Development vs Update**:
A Development adds permanent (developed) points up to capacity (capped at 7 per week, driven by a social roll, awards XP); an Update adds decaying temporary points (linear over 10 days) plus permanent capacity, and is unlimited.
_Avoid_: conflating the two; "edit", "change" (Change is its own model that redistributes existing points).

**RelationshipCapstone**:
A monumental, never-gated moment that adds both permanent points and capacity at once; the anchor that future magical-tether power is built around.
_Avoid_: milestone, climax, peak event.

**WriteupKudos** (writeup commendation):
A one-way, non-revocable commendation that the subject of a SHARED/PUBLIC writeup gives to its author; awards the author a small kudos grant via the existing progression kudos path. One commendation per (subject account, writeup). Only the subject may commend; the author cannot commend their own writeup.
_Avoid_: like, upvote, endorsement, approval.

**WriteupComplaint**:
A bad-faith-RP flag that any viewer of a SHARED/PUBLIC writeup files for staff triage. The model carries a free-text reason and a `resolved` staff flag. Zero player-facing signal — complainants do not learn the outcome and the flag is never shown to the writeup author.
_Avoid_: report, abuse report, flag (when used without qualification — "WriteupComplaint" is the canonical term).

**Bump** (`RelationshipBump`, #1699):
An ambient, permanent, ungated ±1 nudge to the actor's own regard for another character, anchored to the specific Interaction (pose) that prompted it. Telnet `relationship plus|neg <name>` backfill-anchors to the target's most recent unacknowledged visible pose; web valenced reaction emoji bump the pose's author. One bump per (relationship, interaction) — the unique constraint is the entire anti-spam mechanism; no counters, no decay, no consent gate (a bump is a private write to the actor's own relationship data, ADR-0024). Positive bumps land on the Regard system track, negative on Friction.
_Avoid_: like, rep, karma, rating, upvote (reactions are the *door*; the bump is the relationship write).

**System track** (`RelationshipTrack.system_key`, #1699):
One of the two seeded generic tracks — **Regard** (positive) and **Friction** (negative), names PLACEHOLDER — that ambient bumps write to, looked up by `TrackSystemKey` rather than name-string. Authored tracks (Friendship, Rivalry, …) have a null `system_key` and remain the deliberate layer players choose on the relationship screen.
_Avoid_: default track, generic track (in code — "system track" is canonical), builtin track.

**AffectionShift** (automatic affection shift, #1697):
A social action's built-in regard consequence — the generic, valence-signed SHIFT_AFFECTION effect: on success, the TARGET's relationship toward the actor moves on the Regard/Friction system tracks (Flirt +5, Seduce +50, PLACEHOLDER; future consent-gated offensive actions carry negative amounts). One shift per (relationship, scene, effect) — the first success of a given action per scene per pair shifts, repeats no-op while conditions still refresh. Distinct from a Bump (the actor's own one-keystroke write) — a shift is done TO you by someone else's action, the grievance precedent generalized.
_Avoid_: seduction bonus, auto-rep, per-action affection (it is per-scene-deduped), conflating with Bump.
