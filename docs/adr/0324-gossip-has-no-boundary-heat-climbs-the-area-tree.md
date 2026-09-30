# 0324 — Gossip has no boundary: heat climbs the area tree and every room below hears it

**Status:** accepted (2026-09-30, #4085)

Gossip (#1572) scoped a rumor's heat to "the region": the `Area` at `AreaLevel.REGION` above
the hub, one fixed rung that gossip, counter-clues, frame jobs, spy trails and the character
creation Whispers all looked up, and that gossip refused to work without. Building the area
tree showed the flaw: the area a rumor spreads across is one street for a faint rumor and a
kingdom for a scandal, so no rung fits it, and pinning it at 50 forced every city that carried
gossip to sit inside something smaller than a county. **The ruling:** a rumor has a *reach*,
the highest area its heat has carried it to. A plant starts it at the hub room's own area;
`climb_gossip` moves it up one parent each time its heat meets that level's threshold
(`GOSSIP_CLIMB_THRESHOLDS`, keyed by level so skipped rungs do not matter), merging with a row
already there so one secret has one row per reach; every hub inside the reach hears it; and it
never climbs back down, because you cannot unring a bell and suppression to zero is the
counter-play that already exists. The other readers pass the room's own area and follow the
same rule, so no tree needs a special rung for any of them to work. **Rejected:** (a) a
*marking* on any area ("word travels across this one") with readers taking the nearest marked
ancestor, which keeps a boundary staff must remember to place and still cannot say how far a
hot rumor goes; (b) moving REGION up the ladder, which keeps one fixed size for a thing that has
none; (c) a rumor that sinks as heat decays, which needs the row to remember its path and makes
the clock, not a player, the thing that quiets a scandal. Fame of the subject is a later lever
on the plant roll, never on the thresholds. Related: ADR-0325 (the ladder is sizes only).
