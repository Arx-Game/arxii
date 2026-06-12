"""Reaction-window registry + services (#904).

The primitive: a scene event (Interaction) carries a ReactionWindow of some
KIND; present players react once each; the kind's config supplies the choice
vocabulary and the effects. Two effect channels:

- ``on_reaction`` — fires immediately, inside the reaction's transaction
  (entrance endorsements grant on the spot, per Spec C).
- ``on_settle`` — fires once when the scene closes (deferred-tally kinds
  like spread-assist).

Kinds register from their owning app's ``AppConfig.ready()`` (mirrors
``world.npc_services.effects.register_offer_effect_handler``) so scenes
never imports consumer apps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from world.scenes.interaction_services import can_view_interaction
from world.scenes.models import SceneParticipation
from world.scenes.reaction_models import ReactionWindow, WindowReaction

if TYPE_CHECKING:
    from world.scenes.models import Interaction, Persona, Scene


@dataclass(frozen=True)
class ReactionChoice:
    """One selectable reaction (a chip in the strip)."""

    slug: str
    label: str


@dataclass(frozen=True)
class ReactionKindConfig:
    """Behavior bundle for one ReactionWindowKind.

    ``choices_for`` returns the live vocabulary for a window (binary kinds
    return a static pair; entrance returns the poser's claimed resonances).
    ``on_reaction`` runs inside the reaction's transaction — raise
    ``ValidationError`` to reject the reaction (the row rolls back).
    ``on_settle`` (optional) runs once at scene close.
    ``public``: reactions render with attribution; hidden kinds tally only.
    ``lazy_open``: the window may be opened on-demand by the first reactor
    (kudos-style any-pose kinds); explicit-only kinds (entrance) stay False
    so arbitrary interactions can't grow their windows.
    """

    choices_for: Callable[[ReactionWindow], list[ReactionChoice]]
    on_reaction: Callable[[ReactionWindow, WindowReaction], None]
    on_settle: Callable[[ReactionWindow], None] | None = None
    public: bool = True
    lazy_open: bool = False


_KIND_REGISTRY: dict[str, ReactionKindConfig] = {}


def register_reaction_kind(kind: str, config: ReactionKindConfig) -> None:
    """Register (or re-register, idempotently) a kind's behavior bundle."""
    _KIND_REGISTRY[kind] = config


def get_reaction_kind(kind: str) -> ReactionKindConfig:
    config = _KIND_REGISTRY.get(kind)
    if config is None:
        msg = f"No ReactionKindConfig registered for kind '{kind}'."
        raise ValidationError(msg)
    return config


def open_reaction_window(*, interaction: Interaction, kind: str) -> ReactionWindow:
    """Idempotently open a window of ``kind`` on ``interaction``."""
    window, _ = ReactionWindow.objects.get_or_create(
        interaction=interaction,
        kind=kind,
        defaults={
            "timestamp": interaction.timestamp,
            "scene": interaction.scene,
        },
    )
    return window


def _account_id_for_persona(persona: Persona) -> int | None:
    from world.scenes.interaction_services import _get_account_for_persona  # noqa: PLC0415

    return _get_account_for_persona(persona)


def react_to_window(
    *,
    window: ReactionWindow,
    reactor_persona: Persona,
    choice: str,
) -> WindowReaction:
    """Record one persona's reaction and fire the kind's immediate effect.

    Eligibility: the window is open, the reactor is a scene participant who
    can see the event (audience rule from #903/#900 via
    ``can_view_interaction``), isn't the event's writer, hasn't already
    reacted, and picked a live choice. Kind handlers may impose further
    domain rules (raise ValidationError → the reaction rolls back).
    """
    if not window.is_open or not window.scene.is_active:
        msg = "This moment has passed — the scene has moved on."
        raise ValidationError(msg)

    interaction = window.interaction
    if interaction.persona_id == reactor_persona.pk:
        msg = "You cannot react to your own moment."
        raise ValidationError(msg)

    account_id = _account_id_for_persona(reactor_persona)
    is_participant = (
        account_id is not None
        and SceneParticipation.objects.filter(scene=window.scene, account_id=account_id).exists()
    )
    if not is_participant:
        msg = "Only those present in the scene may react."
        raise ValidationError(msg)

    if not can_view_interaction(interaction, reactor_persona):
        msg = "You did not witness that."
        raise ValidationError(msg)

    config = get_reaction_kind(window.kind)
    valid_slugs = {c.slug for c in config.choices_for(window)}
    if choice not in valid_slugs:
        msg = "That is not a possible reaction here."
        raise ValidationError(msg)

    try:
        with transaction.atomic():
            reaction = WindowReaction.objects.create(
                window=window,
                reactor_persona=reactor_persona,
                choice=choice,
            )
            config.on_reaction(window, reaction)
    except IntegrityError as exc:
        msg = "You have already reacted to this."
        raise ValidationError(msg) from exc
    return reaction


def react_to_interaction(
    *,
    interaction: Interaction,
    kind: str,
    reactor_persona: Persona,
    choice: str,
) -> WindowReaction:
    """Open (idempotently) a lazy kind's window on ``interaction`` and react.

    Only kinds registered with ``lazy_open=True`` may be opened this way —
    explicit-only kinds (entrance) raise. The open + reaction run atomically
    so a rejected reaction never leaves a stray empty window behind.
    """
    config = get_reaction_kind(kind)
    if not config.lazy_open:
        msg = "That kind of moment can't be started from a reaction."
        raise ValidationError(msg)
    if interaction.scene is None:
        msg = "Reactions need a scene."
        raise ValidationError(msg)

    with transaction.atomic():
        window = open_reaction_window(interaction=interaction, kind=kind)
        return react_to_window(
            window=window,
            reactor_persona=reactor_persona,
            choice=choice,
        )


def settle_windows_for_scene(scene: Scene) -> int:
    """Close every open window in ``scene``, firing per-kind settlement.

    Returns the number of windows settled. Unregistered kinds (consumer app
    removed?) still get closed — settlement must never wedge scene finish.
    """
    settled = 0
    now = timezone.now()
    for window in ReactionWindow.objects.filter(scene=scene, settled_at__isnull=True):
        config = _KIND_REGISTRY.get(window.kind)
        if config is not None and config.on_settle is not None:
            config.on_settle(window)
        window.settled_at = now
        window.save(update_fields=["settled_at"])
        settled += 1
    return settled
