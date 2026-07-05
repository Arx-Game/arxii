# ADR-0088: Companions are Character-typeclass ObjectDB instances gated by Thread/GIFT capacity

## Status
Accepted

## Context
The Companion system (#672) needed two hard-to-reverse calls: (1) what typeclass
a bound companion's live in-world object should be, and (2) what stat gates how
many/how powerful a PC's companions can be.

## Decision
1. `CompanionObject` extends `Character` (not `Object`), following the
   `GMCharacter`/`StaffCharacter` precedent of "a Character subtype that isn't a
   player" — `Character`'s handlers already degrade gracefully with no
   `sheet_data`. This makes a companion a valid future combat
   target/participant without a typeclass migration.
2. Companion Capacity reuses the existing `Thread`/`ThreadPullEffect`
   proficiency-gating mechanism (`TargetKind.GIFT` + `EffectKind.FLAT_BONUS`),
   anchored on the granting Gift's Thread — no new enum values were added.

## Alternatives rejected
- A plain `Object` typeclass for companions: simpler, but would require a
  typeclass migration the day combat participation is built.
- A bespoke "Companion Level" stat: would duplicate the Thread/proficiency
  system that every other Gift-gated capability already uses.

## Consequences
Other future summon-domain Gifts (necromancer, elementalist) can reuse both
the typeclass base and the capacity mechanism without redesign.
