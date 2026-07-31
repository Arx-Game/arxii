"""Feeding actions (#2853): the blood bite and the essence drain.

Two skins over one transfer (`world.magic.services.feeding.feed_anima`).
PC targets ride the consent request flow (the command opens a
`SceneActionRequest`; the registered `feed`/`drain` resolvers perform the
transfer on an accepted, successful roll — NPC targets auto-resolve through
the same seam). Direct dispatch here is the NPC-only path with an explicit
amount mode (sip/drink/gorge) — a PC target is refused with a pointer at the
consent flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class _FeedBaseAction(Action):
    """Shared NPC-direct feeding dispatch; subclasses set key/flavor/template."""

    category: str = "social"
    target_type: TargetType = TargetType.SINGLE
    costs_turn: bool = True
    appetite_verb: ClassVar[str] = "feed"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.services.feeding import FeedMode, feed_anima  # noqa: PLC0415
        from world.species.appetites import AppetiteKind, appetite_for  # noqa: PLC0415

        actor_sheet = actor.character_sheet
        if actor_sheet is None:
            return ActionResult(success=False, message="You have no hunger to feed.")
        if appetite_for(actor_sheet) == AppetiteKind.NONE:
            return ActionResult(
                success=False, message="You carry no appetite — nothing in you feeds this way."
            )
        target = kwargs.get("target_character")
        if target is None:
            return ActionResult(
                success=False,
                message=f"Use the {self.appetite_verb} command on a target.",
            )
        if target.db_account is not None:
            return ActionResult(
                success=False,
                message=(
                    "Feeding on another player's character goes through their "
                    f"consent — use `{self.appetite_verb} <name>` in a scene."
                ),
            )
        target_sheet = target.character_sheet
        if target_sheet is None:
            return ActionResult(success=False, message="There is nothing there to draw from.")
        mode = str(kwargs.get("amount_mode") or FeedMode.DRINK)
        outcome = feed_anima(actor_sheet, target_sheet, amount_mode=mode)
        return ActionResult(
            success=outcome.taken > 0,
            message=outcome.message,
            data={
                "taken": outcome.taken,
                "glut_gained": outcome.glut_gained,
                "lost_control": outcome.lost_control,
                "was_lethal": outcome.was_lethal,
            },
        )


@dataclass
class FeedAction(_FeedBaseAction):
    """Drink blood (Appetite: Blood — vampires, dhampir)."""

    key: str = "feed"
    name: str = "Feed"
    icon: str = "droplet"
    template_name: str = "Feed"
    appetite_verb: ClassVar[str] = "feed"
    description: str = "Drink from a living target, taking their anima as your own."


@dataclass
class DrainAction(_FeedBaseAction):
    """Drain essence by touch or glamour (Appetite: Essence — Vulpi, Vesperi, shades)."""

    key: str = "drain"
    name: str = "Drain"
    icon: str = "sparkles"
    template_name: str = "Drain"
    appetite_verb: ClassVar[str] = "drain"
    description: str = "Draw the living warmth out of a target through touch or glamour."
