# Death off-ramp is automated and bounded; no resurrection path exists

Permanent character death resolves through an automated, player-paced off-ramp with no
staff hand required (#2287): the moment of death delivers an admin-editable condolence
message; the dead character remains puppetable as a spectator ghost (full perception,
OOC/channels, IC verbs whitelisted via `DEAD_ALLOWED_ACTION_KEYS`) whose emit/pose is
bounded by system-recognized containers — the death scene while it stays active, the IC
day of death, and (later issues) funerals and seances — never an open-ended timer; and
release is the player-fired `retire` action, staff-forceable for offscreen deaths, with
a scheduler backstop (`vitals.auto_retire`) after a config grace window. Death-kudos
lets witnesses honor a well-played death, aggregate-capped at the character's lifetime
XP spend so a beloved character's investment can be fully returned to the account. **No
resurrection code path exists anywhere** — death consequences only feel real if players
know there is no save condition; anything of that kind is a manual staff act, and
special-event returns are bounded *visits* via the future seance hook, not saves.

We rejected the Arx I model (staff manually negotiating character removal with the
player after a discussion period): it does not scale, burdens grieving players with
process, and makes death feel arbitrable. We also rejected an unbounded ghost mode
(emit forever = a de facto necromancy system) and a hard instant lockout (no space to
write the character's exit with dignity).

> Status: accepted · Source: #2287, ApostateCD's design session 2026-07-13
