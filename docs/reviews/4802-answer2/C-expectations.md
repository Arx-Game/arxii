# #4802 / PR #4862, evidence-challenge round 2: expectations (written before the run)

HEAD: 5e0f33ae9e053e7c85f1c5f301d957e78b20f890
Branch: feature-4802-involuntary-control-loss-one-mechanism-m
Database: throwaway `rt_4802g` (created, schema built, seeded, dropped after).

These are written from the rulings and the challenge, before any command of the run.
None of them come from the code's own output.

## Case 1: Ruling 22 after the fix (C-r22.txt)

Setup: Mira carries Berserk at severity 3 and sits in an open encounter in the Pit with her
ally Tomas. Staff levers force her resist to land Partial Success: a roll modifier on her
sheet (rollmod) plus a flat check modifier on "Resist compulsion" from a staff-only
condition.

Mira types `combat cover Tomas`, staff resolves the round.

- The room reads "Berserk drags at Mira: Control -2." The line does not contain
  "to this action" and does not contain "-4". Cover makes no roll, so it has nothing to
  take an action penalty.
- Cover stands: no "you attack instead" outcome, no Rend at an enemy from Mira. Her
  declared action stays a cover of Tomas.
- Mira's CombatRoundAction row for that round, read from the database: maneuver `cover`,
  ally target Tomas, `declared_by_compulsion` False, `compulsion_penalty` = 0.

## Case 2: leave outside combat (C-leave-outside.txt)

Mira, still carrying Berserk, stands in a room with no encounter and has no seat in any
encounter. She types `combat leave`.

- She reads "You are not in an encounter you can leave right now."
- No resist line ("Against Berserk ...", "Resist compulsion ...") appears. No roll is made,
  because there is nothing to leave.

## Case 3: the clash contributor at HEAD (C-clash-api.json, C-clash-note.txt)

Garrick wears the mask "scarred sellsword" and commits to a clash on Gorr. Tomas, who does
not own Garrick, reads `GET /api/combat/<id>/` through the running server.

- The clash's contributor entry for Garrick shows `character_name` "scarred sellsword" and a
  `participant_id` equal to Garrick's seat (CombatParticipant) id.
- The entry has no `character_id` key.
- No value anywhere in the response equals Garrick's CharacterSheet id, unless the sheet id
  and the seat id coincide, in which case the run is re-seeded so they differ. The seed sets
  Garrick's sheet id well clear of every seat id and small counter, so a stray match is
  easy to see.
- The word "Garrick" does not appear in the response.
