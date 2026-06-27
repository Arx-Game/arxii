"""AuthorTechniqueAction — the action.run() seam for technique authoring (#1496).

Both the web technique-builder endpoint (Task 5) and the telnet ``technique``
command (Task 6) will converge on this action's ``run()``, so technique authoring
no longer needs to bypass the action layer.

Known domain exceptions (``TechniqueBudgetExceeded``, ``TechniqueAuthoringNotPermitted``,
``UnknownGift``, ``GiftNotOwned``, ``TechniqueDraftIncomplete``) are caught and returned
as failure ``ActionResult`` values so both telnet (prints ``message``) and web
(maps ``message`` → HTTP 400) get a uniform, user-safe failure.

All ``world.magic`` imports are done lazily inside ``execute()`` to avoid import
cycles — the action registry is imported very early; magic models pull in much of
the world graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.magic.types.technique_builder import TechniqueDesignInput


@dataclass
class AuthorTechniqueAction(Action):
    """Validate a technique design against the character's policy and author it.

    Player path (``as_staff=False``): enforces ``PlayerPolicy`` (budget cap +
    gift-ownership check), creates the ``Technique`` row, and binds a
    ``CharacterTechnique`` so the technique shows up in the character's repertoire.

    Staff path (``as_staff=True``): uses ``StaffPolicy`` (budget advisory only,
    ownership check skipped), creates the ``Technique`` row but does NOT bind a
    ``CharacterTechnique``.

    kwargs:
        design: A ``TechniqueDesignInput`` describing the technique to author (required).
        as_staff: When ``True`` uses the staff bypass policy. Defaults ``False``.
    """

    key: str = "author_technique"
    name: str = "Author Technique"
    icon: str = "scroll"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        design: TechniqueDesignInput,
        as_staff: bool = False,
        **kwargs: Any,
    ) -> ActionResult:
        """Validate the design and author the technique.

        Args:
            design: The fully-specified ``TechniqueDesignInput``.
            as_staff: When ``True`` routes through ``StaffPolicy`` (advisory budget,
                no ownership check) and calls ``author_staff_technique`` instead of
                ``author_technique``.

        Returns:
            ``success=True`` with ``data={"technique": ..., "breakdown": ...}`` when
            authoring succeeds.  ``success=False`` with a player-safe ``message``
            when any domain exception fires.
        """
        from world.magic.exceptions import (  # noqa: PLC0415
            GiftNotOwned,
            TechniqueAuthoringNotPermitted,
            TechniqueBudgetExceeded,
            TechniqueDraftIncomplete,
            UnknownGift,
        )
        from world.magic.services.technique_builder import (  # noqa: PLC0415
            PlayerPolicy,
            StaffPolicy,
            author_staff_technique,
            author_technique,
            validate_design_for_character,
        )

        character = actor.sheet_data
        policy = StaffPolicy() if as_staff else PlayerPolicy()

        try:
            # Single gift-ownership gate. Defensive on the web player path (the
            # serializer already enforced it) and a no-op for the staff path;
            # the telnet workbench relies on it as its only gate.
            validate_design_for_character(design, policy, character)
            if as_staff:
                technique, breakdown = author_staff_technique(design)
            else:
                technique, breakdown = author_technique(character, design)
        except TechniqueBudgetExceeded as exc:
            return ActionResult(
                success=False,
                message=exc.user_message,
                data={"breakdown": exc.breakdown},
            )
        except TechniqueAuthoringNotPermitted as exc:
            # data discriminator lets the web view map this failure to HTTP 403
            # rather than the default HTTP 400 (task 5 convergence contract).
            return ActionResult(
                success=False,
                message=exc.user_message,
                data={"error": "not_permitted"},
            )
        except (UnknownGift, GiftNotOwned, TechniqueDraftIncomplete) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You author {technique.name} (Tier {design.tier}).",
            data={"technique": technique, "breakdown": breakdown},
        )
