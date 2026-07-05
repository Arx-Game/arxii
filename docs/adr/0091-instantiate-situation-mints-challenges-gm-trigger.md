# instantiate_situation mints Challenges via an authored target-object name; GM triggers it with a plain staff Action

ADR-0090 left `instantiate_situation` traps-only because minting a
`ChallengeInstance` needs a `target_object`, and the only existing caller
(`instantiate_challenge` via positioning's "Catch the Faller") always points at
an already-existing entity — there was no answer for Situation-authored
challenges with nothing pre-existing to point at. We added a required
`target_object_name` field to `SituationChallengeLink` instead of requiring GM
pre-placement of a real prop: the field is authored once at design time,
`instantiate_situation` auto-creates a bare `ObjectDB` from it (the same
`ObjectDB.objects.create(db_key=..., db_typeclass_path=...)` pattern already
used for Room/Exit creation in `world/buildings/services.py`), and this is
safe specifically because `target_object.db_key` is the only player-visible
surface a Situation-authored Challenge's target has — there is no room
description or prop identity to get wrong. For the trigger, we chose a plain
staff `Action` (`SetSituationAction` + `CmdSetSituation`) that mirrors
`SetTheStageAction`/`CmdSetStage` exactly rather than inventing an event-driven
or room-entry mechanism, since no such precedent exists in this codebase and
the existing GM-verb shape already solves it. We deliberately did not add a
duplicate-instantiation guard: `setsituation` triggered twice at the same room
mints two independent `SituationInstance`s — a staff-only, in-scene,
immediately-visible mistake with low blast radius, not worth the extra
mechanism.

> Status: accepted · Source: issue #1895, supersedes ADR-0090
