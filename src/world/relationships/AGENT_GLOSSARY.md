# Relationships glossary

The vocabulary of ties (#3957, ADR-0308). Everything below is per **side** unless it
says otherwise.

**Tie**:
The relationship between two characters, taken as a whole: two directed sides, the labels
each holds, and the one depth they pool. There is no `Tie` model — a tie is the pair of
`CharacterRelationship` rows plus what hangs off them. The player-facing word on every
surface (the sheet section is "Ties", the page is the tie page).
_Avoid_: bond (reserved for the combat/magic reading of a tie), connection, link, pairing.

**Side** (`CharacterRelationship`):
One character's directed row toward another character (`target`) or toward their own bonded
companion (`target_companion`) — exactly one is set. It owns that character's labels, its own
added depth (`scene_depth` + `invested_depth`), its claimed `tier`, its two gauges and its
`summary`. `is_active=False` freezes a side: it takes no new credit of either kind and cannot
count toward mutual, but it keeps the depth it earned.
_Avoid_: relationship (ambiguous between the side and the tie), direction, half.

**Label** (`RelationshipLabel`):
One side naming one `RelationshipType` — "Lover", "Rival", "Mentor" — at one awareness, with
`since`, an optional `note`, an optional `replaced` self-FK, and an `ended_at`. A side may
hold any number of open labels, at most one open per type
(`UniqueConstraint(relationship, type)` partial on `ended_at IS NULL`). Labels carry no
points and are **never deleted**.
_Avoid_: track, designation, tag, relationship kind (the *type* is the kind; the label is
this side holding it).

**RelationshipType**:
The staff-authored catalogue row a label names: `family` (how the picker groups it),
`valence` (WARM / HOSTILE / NEUTRAL — what consent, journals and the surge engine read),
`counterpart` (null meaning itself), `fuels_escalation_spikes`. Credited content
(`CreditedContent` + `NaturalKeyMixin`), seeded as eighteen PLACEHOLDER types in five
families by `world/seeds/relationship_scale.py`.
_Avoid_: RelationshipTrack (the retired name), category, tag.

**Awareness** (`LabelAwareness`):
Who knows a label exists. **Private** — only the declarer (and staff). **Clandestine** — the
other side may see it too. **Public** — anyone may. It moves **forward only**
(`advance_awareness`: Private → Clandestine → Public, or Private → Public), never back; a
reverse raises `AwarenessBackwardError`, because a known thing cannot be unsaid IC. New
labels default to Private. `KNOWN_AWARENESS` is the Clandestine-or-Public pair — the stages
the other side may read and the only ones that count toward mutual.
_Avoid_: visibility (that word belongs to journals' own rule), secrecy level, privacy flag,
"make secret" (there is no such move).

**Depth**:
How much play the tie has had, in three readings. **Scene depth** (`scene_depth`) is credited
by `credit_scene_depth(scene)` once per game week per side for the first scene the two both
*posed* in. **Invested depth** (`invested_depth`) comes from a weekly AP allocation turned
into depth by `process_weekly_relationship_allocations()`. A side's own added depth is the
sum of the two (`CharacterRelationship.depth`); the **pair depth** is both sides' added depth
summed (`pair_depth()`) and is what a tier threshold, the magic pull term and the tie page's
"340 / 500" all read. No decay, no weekly cap, no per-label points. Every award writes a
`RelationshipDepthTransaction` audit row.
_Avoid_: points, affection points, absolute value, capacity, temporary points (all retired).

**Tier** (`CharacterRelationship.tier`, `RelationshipTier`):
The rung this side has **claimed** on the one ladder every tie shares (`RelationshipTier`:
`tier_number`, `depth_threshold`, `combat_bonus`; seeded 25 / 100 / 500 / 2000, names
PLACEHOLDER). A tier is claimed, never reached: `advance_tier` requires the pair depth to
clear the next rung's threshold, a capstone entry, and XP. Each side claims its own; the
combat bond and the thread gate read the claimer's own tier, training reads the lower of the
two.
_Avoid_: level, rank, tier-per-track (the ladder is no longer per type), stage.

**Capstone** (`RelationshipCapstone`):
The **receipt** of one advance: the `journal_entry` the player marked (their own, about the
other, top-level, unused by any other capstone), the `tier_claimed` and the `xp_spent`. A
ritual capstone (soul-tether formation) has no entry and sets `is_ritual_capstone`. The
receipt keeps its own pk because `Thread.target_capstone` and the rituals picker depend on it.
_Avoid_: writeup, monumental moment, milestone event (the prose lives in the journal entry;
the capstone is the receipt that points at it).

**Affection** / **Conflict**:
Two unsigned gauges on the side row, **moved only by play** and never set by a player:
`move_gauges(side=..., amount=...)` adds a positive amount to Affection and the magnitude of
a negative one to Conflict. The movers are ambient bumps (`RelationshipBump`), automatic
affection shifts (`AffectionShift`, Flirt/Seduce and boon drains), grievances
(`register_grievance`) and the NPC regard mirror. Owner-and-staff-only on every read. Net
affection still feeds the social difficulty bands; `min(affection, conflict)` is what magic's
fraught term keys on.
_Avoid_: signed affection, regard score, sentiment, Regard/Friction tracks (retired), dial,
slider.

**Counterpart** (`RelationshipType.counterpart`):
The type the *other* side must hold for a label to be mutual. Null means the type pairs with
itself (Friend ↔ Friend); the seeded asymmetric pairs are Beloved ↔ Admirer, Ward ↔ Guardian,
Liege ↔ Vassal, Mentor ↔ Student, Patron ↔ Protege. Read through `counterpart_or_self`.
_Avoid_: reciprocal type, mirror type, inverse.

**Mutual**:
Derived, never stored: `is_mutual(side, type)` is true when this side holds an open label of
`type` and the reverse side holds an open label of its counterpart, both at Clandestine or
Public, both declared under a roster tenure that is still open, and both side rows active.
`public_only=True` narrows both to Public — the predicate a third party reads, so a "mutual"
marker can never reveal a Clandestine label. `mutual_hostile(a, b)` is the same test over
HOSTILE-valence types and is the *one* predicate consent's RIVALS mode and the journals'
Retort/Condemn gate read.
_Avoid_: reciprocated, confirmed, consented (mutual is a derivation, not a handshake),
two-way.

**Former label**:
A label with `ended_at` set. It stays on the card and the page marked former, stops counting
toward mutual, and is never removed. Produced by `end_label`, and by `shift_label` on the row
it replaces.
_Avoid_: deleted label, removed label, archived (nothing archives).

**Relationship Shift** (`shift_label`):
Changing one label into another: the old row ends and a **new** row is created whose
`replaced` points back at it, carrying the old awareness and dates forward and an optional
`note`. The arc (Enemy became Lover) is readable off the chain. `_replaced_type_name` only
names the replaced type to an audience that could have seen it.
_Avoid_: edit, rename, retype, Change (the retired `RelationshipChange` model redistributed
points and is gone).

**Advance** (`advance_tier`):
Claiming the next tier: pair depth must clear `next_tier().depth_threshold`, the capstone
entry must be the claimer's own top-level entry about the other side and not already a
capstone, and the cost is `RelationshipGrowthConfig.xp_per_tier × the new tier`, spent
through `spend_xp_for_character`. Writes the receipt and sets `tier` in one transaction.
_Avoid_: level up, unlock, promote.

**Allocation** (`RelationshipAllocation`):
This week's AP set against one side, one row per side (`OneToOne`), mirroring
`TrainingAllocation`. `set_allocation` checks the pool can afford it; the weekly turn spends
it and converts it at `depth_per_ap`.
_Avoid_: investment (use "invested depth" for the result), contribution, weekly spend.

**Audience** (`TieAudience`):
Who is looking, decided server-side in `reads.tie_audience` and never by the client: OWNER
(everything, including Private labels and both gauges), OTHER_SIDE (known labels, pair depth,
both tiers, breakdown without gauges), THIRD_PARTY (Public labels and the summary, **no
number**; a tie with no open Public label is absent and 404s), STAFF (everything).
_Avoid_: permission level, visibility tier, role.

**Summary** (`CharacterRelationship.summary`):
The player's own paragraph on their side of the tie. Its first line is the only prose a third
party ever gets on a card. The game never writes it.
_Avoid_: description, bio, blurb.

**Bump** (`RelationshipBump`, #1699):
An ambient, permanent, ungated ±1 nudge anchored to the specific `Interaction` (pose) that
prompted it. Telnet `relationship plus|neg <name>` backfill-anchors to the target's most
recent unacknowledged visible pose; a valenced web reaction emoji bumps the pose's author.
One bump per (relationship, interaction) — the unique constraint is the whole anti-spam
mechanism. Now moves the gauges: +1 adds Affection, -1 adds Conflict.
_Avoid_: like, rep, karma, rating, upvote (the reaction is the *door*; the bump is the write).

**AffectionShift** (#1697, boon mode #2540):
A social action's built-in consequence on its **target's** side toward the actor: the
valence-signed `SHIFT_AFFECTION` effect (Flirt +5, Seduce +50, PLACEHOLDER; gated offensive
actions carry negative amounts, which add Conflict). Effect-keyed rows dedup per
(relationship, scene, effect); boon-keyed rows dedup on the Boon, so serial granted boons
stack. Distinct from a Bump: a shift is done *to* you by someone else's action.
_Avoid_: seduction bonus, auto-rep, per-action affection (it is per-scene-deduped).

**Companion tie** (#3575, ADR-0272):
A side whose `target_companion` is set (and `target` null): the bonded owner's tie toward
their own `Companion`. Owner-only on every surface (a companion has no player to weigh being
named publicly), no reverse side, so no mutual and no pair depth beyond its own. It earns
depth and tiers; combat bond for companions is a later expansion (Decision 14). Read
`target_name`, never `target.character`, anywhere a row may be about a companion.
_Avoid_: pet bond, companion relationship model (there is no separate model).

**Grievance** (`GrievanceOption`, `register_grievance`, #1429):
A wronged character's one-sided registration of a wrong: an authored preset's
`conflict_points` (or a custom amount) added to the victim's **Conflict** on their own side.
Never needs the other side's consent, never touches the other side's row.
_Avoid_: revenge, penalty, report.

**RelationshipCondition** / **TemporaryRelationshipCondition** (#1696, #1697):
Unchanged by #3957. A condition on a side ("Attracted To", "Fears") gates which modifier
targets apply during a check; the temporary variant carries an `expires_at` and is pruned by
the `relationships.temp_condition_cleanup` game_clock task.
_Avoid_: status, buff, effect (those words belong to conditions/mechanics).

## Retired vocabulary (#3957) — do not reintroduce

`RelationshipTrack` (→ `RelationshipType`), tier-per-track (→ the one ladder), **capacity**,
**temporary points** and their decay, **developed points** / **absolute value** /
`developed_absolute_value` / `developed_signed_sums`, **Update** (`RelationshipUpdate`),
**Development** (`RelationshipDevelopment`), **Change** (`RelationshipChange`), **hybrid
type** (`HybridRelationshipType`, `HybridRequirement`), **writeup** and its feedback
(`WriteupKudos`, `WriteupComplaint`, the `relationship_writeup` kudos category), **system
track** (`RelationshipTrack.system_key`, `TrackSystemKey`, the Regard and Friction rows),
**deceit display** (`displayed_track`, `displayed_tier`, `is_deceitful`), **pending** and
reciprocation (`is_pending`), `UpdateVisibility`, `FirstImpressionColoring`, and
`scenes.Rivalry` / `declare_rival` / `is_rival` (folded into the Rival label).
