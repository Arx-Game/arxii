"""Canonical event-name constants for the reactive layer.

Matched against Event.name rows at Trigger lookup time.
String constants (not an Enum) so they're JSON-serializable for legacy
FlowEvent.event_type compatibility and usable as migration data.
"""


class EventNames:
    ATTACK_PRE_RESOLVE = "attack_pre_resolve"
    ATTACK_LANDED = "attack_landed"
    ATTACK_MISSED = "attack_missed"
    DAMAGE_PRE_APPLY = "damage_pre_apply"
    DAMAGE_APPLIED = "damage_applied"
    CHARACTER_INCAPACITATED = "character_incapacitated"
    CHARACTER_KILLED = "character_killed"
    MOVE_PRE_DEPART = "move_pre_depart"
    MOVED = "moved"
    EXAMINE_PRE = "examine_pre"
    EXAMINED = "examined"
    CONDITION_PRE_APPLY = "condition_pre_apply"
    CONDITION_APPLIED = "condition_applied"
    CONDITION_STAGE_CHANGED = "condition_stage_changed"
    CONDITION_REMOVED = "condition_removed"
    TECHNIQUE_PRE_CAST = "technique_pre_cast"
    TECHNIQUE_CAST = "technique_cast"
    TECHNIQUE_AFFECTED = "technique_affected"

    @classmethod
    def all(cls) -> list[str]:
        return [v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)]
