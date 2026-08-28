"""Constants for the action system."""

from enum import StrEnum

from django.db import models

from world.character_sheets.types import LifecycleState

# #2287 — the ghost interlude: a dead character keeps the puppet (spectator
# perception + OOC/channels) but IC verbs are whitelisted, not blacklisted.
# ``emit``/``pose`` are further bounded by GhostWindowPrerequisite (death
# scene / same IC day; funeral + seance containers (#2393)).
# ``say`` is deliberately absent — a corpse has no voice.
DEAD_ALLOWED_ACTION_KEYS: frozenset[str] = frozenset(
    {
        "look",
        "look_at_item",
        "inventory",
        "emit",
        "pose",
        "wake",
        "retire",
        "death_kudos",
    }
)

# #3412 — the offscreen-act gate: action keys whose service call is a "2.5
# act" — something a character in a degraded lifecycle state can still
# attempt off-scene (journals, goals, persona swaps, proclamations). Every
# other action key passes the gate as ALLOWED untouched. See
# ``actions/offscreen_gate.py`` for the lifecycle-state predicate.
OFFSCREEN_ACT_KEYS: frozenset[str] = frozenset(
    {
        "create_journal_entry",
        "edit_journal_entry",
        "respond_to_journal",
        "set_journal_disposition",
        "set_character_goals",
        "log_goal_progress",
        "set_active_persona",
        # #3412 slice 3 task 3 — IssueProclamationAction
        # (actions/definitions/organizations.py), shared by
        # ProclamationViewSet.proclaim (plain/org stance + domain-edict
        # enactment).
        "issue_proclamation",
    }
)


class OffscreenActState(StrEnum):
    """Disposition of an offscreen-act gate check (#3412).

    StrEnum (not TextChoices) — pure in-memory result of
    ``offscreen_gate.offscreen_act_state()``, never a database column,
    mirroring ``ResolutionPhase`` below. ``ROUTED`` is mechanically a refusal
    this slice (no channel-delivery mechanics exist yet) but is kept distinct
    from ``BLOCKED`` so the frontend renders world-voice prose instead of a
    flat "no", and so future mechanics can activate without an API
    resignature.
    """

    ALLOWED = "allowed"
    ROUTED = "routed"
    BLOCKED = "blocked"


# Channel names for a ROUTED disposition — identify *how* word could still
# travel, not a real messaging mechanism yet (#3412). Stable names; later
# tasks in #3412 key off these exact strings.
OFFSCREEN_CHANNEL_SMUGGLE: str = "smuggle"
OFFSCREEN_CHANNEL_DREAM: str = "dream"

# PLACEHOLDER world-voice prose (#3412) — told to the actor, describing what
# the world can still do on their behalf (or why it can't). Final author pass
# is a later task; see the "placeholders now, passes later" project pattern.
OFFSCREEN_REASON_CAPTURED: str = (
    "You are held captive. Word might be smuggled out by someone reaching you in the world."
)
OFFSCREEN_REASON_UNCONSCIOUS: str = "You are unconscious. You might be reached through dreams."
OFFSCREEN_REASON_DEAD: str = "The dead have no further word to send."
OFFSCREEN_REASON_UNKNOWN: str = (
    "Your whereabouts are unknown; there is no way to reach you right now."
)
OFFSCREEN_REASON_RETIRED: str = "You have stepped away from the story for now."

# Per-lifecycle-state disposition for an OFFSCREEN_ACT_KEYS action, consulted
# AFTER the DEAD and unconscious overlays (see
# ``offscreen_gate.offscreen_act_state`` for the full precedence: DEAD beats
# unconscious beats CAPTURED beats UNKNOWN/RETIRED beats ALIVE). ALIVE and
# the unwritten ``LifecycleState.COMA`` member both fall through to the
# ALLOWED default (no entry here) — COMA has no setter anywhere in the
# codebase yet (#3412 recon), so it is deliberately NOT keyed on.
OFFSCREEN_LIFECYCLE_DISPOSITIONS: dict[str, tuple[OffscreenActState, str | None, str]] = {
    LifecycleState.CAPTURED: (
        OffscreenActState.ROUTED,
        OFFSCREEN_CHANNEL_SMUGGLE,
        OFFSCREEN_REASON_CAPTURED,
    ),
    LifecycleState.UNKNOWN: (OffscreenActState.BLOCKED, None, OFFSCREEN_REASON_UNKNOWN),
    LifecycleState.RETIRED: (OffscreenActState.BLOCKED, None, OFFSCREEN_REASON_RETIRED),
}


class EnhancementSourceType(models.TextChoices):
    """The type of model that provides an ActionEnhancement."""

    DISTINCTION = "distinction", "Distinction"
    CONDITION = "condition", "Condition"
    TECHNIQUE = "technique", "Technique"


class TransformType(models.TextChoices):
    """Named transforms for kwarg modification."""

    UPPERCASE = "uppercase", "Uppercase"
    LOWERCASE = "lowercase", "Lowercase"


class Pipeline(models.TextChoices):
    """Resolution pattern for ActionTemplate."""

    SINGLE = "single", "Single Check"
    GATED = "gated", "Gated (with prerequisite checks)"


class GateRole(models.TextChoices):
    """Semantic role of an ActionTemplateGate."""

    ACTIVATION = "activation", "Activation"


class ActionTargetType(models.TextChoices):
    """Target type for data-driven ActionTemplates (mirrors TargetType StrEnum)."""

    SELF = "self", "Self"
    SINGLE = "single", "Single Target"
    AREA = "area", "Area"
    FILTERED_GROUP = "filtered_group", "Filtered Group"


class TargetKind(models.TextChoices):
    """Entity-type axis for action targeting.

    Orthogonal to ActionTargetType (cardinality). Kind = what type of entity
    the action targets; cardinality = how many / how they're selected.
    """

    PERSONA = "persona", "Persona"
    CHARACTER = "character", "Character"
    ITEM = "item", "Item"
    ROOM = "room", "Room"


class ActionBackend(models.TextChoices):
    """Which backend system resolves a PlayerAction."""

    CHALLENGE = "challenge", "Challenge"
    COMBAT = "combat", "Combat"
    REGISTRY = "registry", "Registry"
    SCENE_ADAPTIVE = "scene_adaptive", "Scene-adaptive"
    # Bare-object affordance (#2503): a synthesized action with no ChallengeInstance
    # yet — dispatch mints one from (application_id, target_object_id) before
    # resolving through the same CHALLENGE pipeline. See ActionRef's docstring.
    WORLD_INTERACTION = "world_interaction", "World interaction"


class ActionCategory(models.TextChoices):
    """Physical/social/mental arena for any action (magical or not).

    The single canonical axis: techniques classify into it, combat actions
    carry it (focused/attack category), and fatigue pools key off it. Climbing
    a wall is physical, flirting is social, a feat of memory is mental.
    """

    PHYSICAL = "physical", "Physical"
    SOCIAL = "social", "Social"
    MENTAL = "mental", "Mental"


class CombatActionSlot(models.TextChoices):
    """Which combat round-action slot a declared COMBAT technique fills.

    ``FOCUSED`` is the actor's single primary action; the passive slots carry
    auto-running techniques per arena. Values intentionally match the frontend
    ``ActionSlot`` strings so the wire round-trips without translation.
    """

    FOCUSED = "focused", "Focused"
    PASSIVE_PHYSICAL = "passive-physical", "Passive (Physical)"
    PASSIVE_SOCIAL = "passive-social", "Passive (Social)"
    PASSIVE_MENTAL = "passive-mental", "Passive (Mental)"


class PlayerDecision(StrEnum):
    """Player decisions for paused resolution pipelines."""

    CONFIRM = "confirm"
    ABORT = "abort"
    REROLL = "reroll"


class ResolutionPhase(StrEnum):
    """Phase of the action resolution state machine.

    StrEnum (not TextChoices) because this is in-memory state machine state,
    never stored in a database column.
    """

    GATE_PENDING = "gate_pending"
    GATE_RESOLVED = "gate_resolved"
    MAIN_PENDING = "main_pending"
    MAIN_RESOLVED = "main_resolved"
    CONTEXT_PENDING = "context_pending"
    COMPLETE = "complete"
