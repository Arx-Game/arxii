"""Canonical event-name choices for the reactive layer.

``EventName`` is a ``TextChoices`` used by ``TriggerDefinition.event_name``
(CharField with choices) and by ``emit_event`` callers. Labels match the
MVP seed data previously shipped in ``migrations/0002_mvp_events.py``.
"""

from django.db import models


class EventName(models.TextChoices):
    ATTACK_PRE_RESOLVE = "attack_pre_resolve", "Attack Pre-Resolve"
    ATTACK_LANDED = "attack_landed", "Attack Landed"
    ATTACK_MISSED = "attack_missed", "Attack Missed"
    DAMAGE_PRE_APPLY = "damage_pre_apply", "Damage Pre-Apply"
    DAMAGE_APPLIED = "damage_applied", "Damage Applied"
    CHARACTER_INCAPACITATED = "character_incapacitated", "Character Incapacitated"
    CHARACTER_KILLED = "character_killed", "Character Killed"
    MOVE_PRE_DEPART = "move_pre_depart", "Move: Pre-Depart"
    MOVED = "moved", "Moved"
    EXAMINE_PRE = "examine_pre", "Examine Pre"
    EXAMINED = "examined", "Examined"
    CONDITION_PRE_APPLY = "condition_pre_apply", "Condition Pre-Apply"
    CONDITION_APPLIED = "condition_applied", "Condition Applied"
    CONDITION_STAGE_CHANGED = "condition_stage_changed", "Condition Stage Changed"
    CONDITION_REMOVED = "condition_removed", "Condition Removed"
    TECHNIQUE_PRE_CAST = "technique_pre_cast", "Technique Pre-Cast"
    TECHNIQUE_CAST = "technique_cast", "Technique Cast"
    TECHNIQUE_AFFECTED = "technique_affected", "Technique Affected"
    # Corruption (Magic Scope #7) — see
    # docs/superpowers/specs/2026-04-25-magic-scope-7-corruption-design.md §3.5
    CORRUPTION_ACCRUING = "corruption_accruing", "Corruption accruing (pre-mutation)"
    CORRUPTION_ACCRUED = "corruption_accrued", "Corruption accrued (post-mutation)"
    CORRUPTION_WARNING = "corruption_warning", "Corruption warning (stage 3-4)"
    CORRUPTION_REDUCED = "corruption_reduced", "Corruption reduced"
    PROTAGONISM_LOCKED = "protagonism_locked", "Protagonism locked (stage 5 entry)"
    PROTAGONISM_RESTORED = "protagonism_restored", "Protagonism restored (stage 5 exit)"
    CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE = (
        "condition_stage_advance_check_about_to_fire",
        "Condition stage advance resist check about to fire",
    )
    # Outfit actions (Items / Outfits Phase A)
    BEFORE_APPLY_OUTFIT = "before_apply_outfit", "Before Apply Outfit"
    APPLY_OUTFIT = "apply_outfit", "Apply Outfit"
    BEFORE_UNDRESS = "before_undress", "Before Undress"
    UNDRESS = "undress", "Undress"
