"""Reaction/favorite REGISTRY actions — the ``action.run()`` seam for the
three "upvote an interaction" surfaces (#1341).

Shared by telnet (``CmdReact``) and the web viewsets. The toggle actions wrap
``world.scenes.reaction_toggle_services``; ``ReactToWindowAction`` wraps the
existing ``react_to_window`` / ``react_to_interaction`` services, picking the
lazy-open path for ``lazy_open`` kinds with no existing window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError as DjangoValidationError

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class ToggleFavoriteAction(Action):
    """Toggle a private bookmark (favorite) on one interaction."""

    key: str = "toggle_interaction_favorite"
    name: str = "Favorite"
    icon: str = "star"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.reaction_toggle_services import (  # noqa: PLC0415
            toggle_interaction_favorite,
        )

        interaction = kwargs.get("interaction")
        sheet = actor.character_sheet
        roster_entry = sheet.roster_entry_or_none
        if sheet is None or roster_entry is None:
            return ActionResult(success=False, message="You have no roster entry to favorite with.")
        created, _favorite = toggle_interaction_favorite(
            interaction=interaction, roster_entry=roster_entry
        )
        if created:
            return ActionResult(success=True, message="Favorited.")
        return ActionResult(success=True, message="Favorite removed.")


@dataclass
class ToggleReactionAction(Action):
    """Toggle an emoji reaction on one interaction."""

    key: str = "toggle_interaction_reaction"
    name: str = "React"
    icon: str = "emoji"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.roster.selectors import get_account_for_character  # noqa: PLC0415
        from world.scenes.reaction_toggle_services import (  # noqa: PLC0415
            toggle_interaction_reaction,
        )

        interaction = kwargs.get("interaction")
        emoji = kwargs.get("emoji")
        account = get_account_for_character(actor)
        if account is None:
            return ActionResult(success=False, message="You have no account to react with.")
        created, _reaction = toggle_interaction_reaction(
            interaction=interaction, account=account, emoji=emoji
        )
        if created:
            return ActionResult(success=True, message=f"Reacted {emoji}.")
        return ActionResult(success=True, message=f"Removed your {emoji} reaction.")


@dataclass
class ReactToWindowAction(Action):
    """React to a reaction-window event on one interaction.

    Routes to ``react_to_interaction`` (lazy-open kinds, e.g. kudos) or
    ``react_to_window`` (an already-open window). ``ValidationError`` from the
    service (window closed, not a participant, didn't witness, self-reaction,
    bad choice, already reacted) is surfaced as a failure ``ActionResult``.
    """

    key: str = "react_to_window"
    name: str = "React to Moment"
    icon: str = "sparkles"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.reaction_models import ReactionWindow  # noqa: PLC0415
        from world.scenes.reaction_services import (  # noqa: PLC0415
            get_reaction_kind,
            react_to_interaction,
            react_to_window,
        )

        interaction = kwargs.get("interaction")
        kind = kwargs.get("kind")
        choice = kwargs.get("choice")
        sheet = actor.character_sheet
        persona = getattr(sheet, "primary_persona", None)  # noqa: GETATTR_LITERAL
        if persona is None:
            return ActionResult(success=False, message="You have no persona to react with.")

        try:
            config = get_reaction_kind(kind)
        except DjangoValidationError:
            return ActionResult(success=False, message=f"Unknown reaction kind '{kind}'.")

        existing = ReactionWindow.objects.filter(interaction=interaction, kind=kind).first()

        # Default the choice for kinds with a single static option (e.g. kudos).
        # Multi-choice kinds (entrance: the poser's resonances) require an
        # explicit choice — react_to_window will reject an empty/None choice.
        if choice is None and config.lazy_open:
            placeholder = ReactionWindow(
                interaction=interaction,
                kind=kind,
                scene=interaction.scene,
                timestamp=interaction.timestamp,
            )
            choices = config.choices_for(placeholder)
            if len(choices) == 1:
                choice = choices[0].slug

        try:
            if existing is None and config.lazy_open:
                reaction = react_to_interaction(
                    interaction=interaction,
                    kind=kind,
                    reactor_persona=persona,
                    choice=choice,
                )
            else:
                if existing is None:
                    return ActionResult(
                        success=False,
                        message="That kind of moment can't be started from a reaction.",
                    )
                reaction = react_to_window(
                    window=existing,
                    reactor_persona=persona,
                    choice=choice,
                )
        except DjangoValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else ["Unable to react."]
            return ActionResult(success=False, message=" ".join(messages))
        return ActionResult(
            success=True,
            message="Reaction recorded.",
            data={"reaction_id": reaction.pk},
        )
