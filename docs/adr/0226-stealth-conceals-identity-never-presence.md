# ADR-0226: Stealth conceals identity, never presence — and disclosure is one-way

**Status:** Accepted (2026-08-21, ruled by ApostateCD on #3288)

**Decision.** No stealth mechanic may ever OOC-conceal a *presence* from the players
in a room. Mundane stealth (`sneak`/`unsneak`, #3288) hides *who* — the concealed
character drops off IC surfaces via the #1225 `Concealed` seam — but every room a
hidden character occupies discloses an identity-free unseen presence: a room-derived
`has_unseen_presence` flag on `room_state` (scene or no scene) plus a mandatory
anonymous arrival echo. The disclosure carries an always-available report affordance
whose identity resolution happens server-side, staff-eyes-only. Disclosure is
**one-way**: arrivals always announce; departures are silent (no echo, normal "X
leaves" broadcast suppressed) — the guarantee protects against unannounced
*watchers*, not unannounced *exits*, and quiet exits are a legitimate social use.
Concealment rolls are per room per visit, never re-rollable in place.

**Why.** RP observed by a watcher the room cannot detect is a harassment vector and
a comfort problem no gameplay value justifies (ADR-0033 territory); but full
player-visible stealth would gut infiltration play. Splitting identity from presence
keeps both: burglars get a real loop (guards contest the SNEAK oracle; `search`
pierces per-observer), rooms always know *something* unseen is there and can act on
it OOC. The persona system already draws exactly this line for player identity.

**Rejected alternative.** v1 of the spec applied full concealment with only the
scene-scoped unseen-observer banner (#1225/ADR-0083) as disclosure — rejected
because the banner is scene-gated (a room of players with no formal Scene got no
disclosure) and because per-event echoes, not just a banner, are needed for telnet
parity. Also rejected: an NPC-only stance with zero player-facing concealment (v2) —
it protected comfort but killed the infiltration loop for no gain once anonymous
disclosure existed.

**Consequences.** Any future concealment producer (invisibility techniques, scrying,
disguise-pierce) must register the same presence disclosure and report path; new
discovery verbs must extend `search`/`SearchAction` rather than minting siblings.
