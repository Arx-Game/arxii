"""Ritual performance action — the action.run() seam for SERVICE/FLOW rituals.

`PerformRitualAction` composes component validation, atomic consumption, and
dual dispatch (SERVICE → service function; FLOW → FlowDefinition) into a single
`Action`. Both telnet (`commands.ritual.CmdRitual`) and the web
(`world.magic.views.RitualPerformView`) converge on this action's `run()`, so
ritual performance no longer bypasses the action layer (G3 closure, #1331).

The dispatch switch itself (SERVICE/FLOW/CEREMONY) lives in
`world.magic.services.ritual_dispatch.dispatch_ritual` (#2705 Task 5) — split
out so a ritual conducted across combat rounds can consume its components at
declaration and dispatch later at maturation without a second copy of the
switch. `world.combat.services.try_declare_sustained_ritual` is the deferral
gate this action calls between component consumption and dispatch.

All `world.magic` / `world.items` / `world.combat` imports are done lazily
inside `execute()` to avoid import cycles (the action registry is imported
very early; magic/combat models pull in much of the world graph).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class PerformRitualAction(Action):
    """Validate components, consume them, and dispatch a ritual.

    Dispatch kinds in scope: SERVICE (imports + calls a service function with
    ``character_sheet=`` + the ritual kwargs) and FLOW (runs the ritual's
    ``FlowDefinition``). Known ritual-surface exceptions are caught and returned
    as a failure ``ActionResult`` so both telnet (prints ``message``) and web
    (maps ``message`` → HTTP 400) get a uniform, user-safe failure.

    kwargs:
        ritual: The ``Ritual`` to perform (required).
        components_provided: ``ItemInstance`` rows the actor contributes;
            pruned to the minimum the ritual needs. Default ``[]``.
        **kwargs: Forwarded to the service function / flow (e.g. ``thread``).
    """

    key: str = "perform_ritual"
    name: str = "Perform Ritual"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Perform the ritual, returning a structured result."""
        from django.db import transaction  # noqa: PLC0415

        from world.combat.services import try_declare_sustained_ritual  # noqa: PLC0415
        from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AnchorCapExceeded,
            GhostTutorError,
            InvalidImbueAmount,
            ResonanceInsufficient,
            RitualComponentError,
            RitualPoolError,
            XPInsufficient,
        )
        from world.magic.services.ritual_dispatch import dispatch_ritual  # noqa: PLC0415
        from world.societies.honors import HonorRefused  # noqa: PLC0415

        ritual = kwargs.pop("ritual", None)
        if ritual is None:
            return ActionResult(success=False, message="Perform which ritual?")

        components = kwargs.pop("components_provided", [])
        sheet = actor.sheet_data

        # #3001: visibility IS eligibility — a non-hedge rite is closed to a
        # character with no magical profile, at browse and perform alike.
        from world.magic.exceptions import HedgeInaccessibleError  # noqa: PLC0415
        from world.magic.services.ritual_pool import ritual_visible_to  # noqa: PLC0415

        if not ritual_visible_to(sheet, ritual):
            return ActionResult(success=False, message=HedgeInaccessibleError.user_message)

        try:
            with transaction.atomic():
                self._validate_components(ritual, components, sheet)

                # #3001: a solo perform auto-channels the performer's own anima
                # toward the requirement, then gates. Spent like components —
                # a fizzle still consumed the pool (return inside the atomic
                # block commits). Deliberately NOT threaded through ``kwargs``:
                # any kwarg blocks sustained-ritual declaration below.
                pool_gate = self._resolve_anima_pool(ritual, sheet)
                if pool_gate is not None and not pool_gate.proceeded:
                    return ActionResult(success=False, message=pool_gate.message)

                # Components are consumed above — that is what makes a broken
                # sustained ritual genuinely spent (#2705, D2/Task 5). Must run
                # AFTER consumption and BEFORE dispatch.
                sustained = try_declare_sustained_ritual(sheet=sheet, ritual=ritual, kwargs=kwargs)
                if sustained is not None:
                    return ActionResult(
                        success=True,
                        message=f"You begin {ritual.name}, holding it together.",
                        data={
                            "execution_kind": ritual.execution_kind,
                            "sustained_rounds": (
                                sustained.resolves_round - sustained.declared_round
                            ),
                        },
                    )

                result = dispatch_ritual(ritual=ritual, performer_sheet=sheet, **kwargs)
        except (
            RitualComponentError,
            ResonanceInsufficient,
            AnchorCapExceeded,
            InvalidImbueAmount,
            XPInsufficient,
            GhostTutorError,
            RitualPoolError,
            HonorRefused,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        msg = (
            f"You begin {ritual.name}."
            if ritual.execution_kind == RitualExecutionKind.CEREMONY
            else f"You perform {ritual.name}."
        )
        return ActionResult(
            success=True,
            message=msg,
            data={
                "execution_kind": ritual.execution_kind,
                "result": result,
                "spectacular": bool(pool_gate is not None and pool_gate.spectacular),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_components(
        self, ritual: Any, components: list[Any], performer_sheet: Any
    ) -> None:
        """Validate and consume ``ritual``'s components via the shared helper."""
        from world.magic.services.ritual_components import (  # noqa: PLC0415
            resolve_and_consume_ritual_components,
        )

        resolve_and_consume_ritual_components(
            ritual=ritual, components=components, performer_sheet=performer_sheet
        )

    def _resolve_anima_pool(self, ritual: Any, performer_sheet: Any) -> Any:
        """Auto-channel the performer's anima and gate the rite on it (#3001).

        Returns ``None`` for folk rites (``anima_requirement == 0``), else a
        ``PoolGateResult``. Raises ``RitualPoolError`` when the performer has
        no anima at all to channel.
        """
        from world.magic.services.ritual_pool import (  # noqa: PLC0415
            contribute_channel,
            resolve_pool_gate,
        )

        if ritual.anima_requirement <= 0:
            return None
        contribution = contribute_channel(
            ritual=ritual,
            contributor_sheet=performer_sheet,
            amount=ritual.anima_requirement,
        )
        return resolve_pool_gate(
            ritual=ritual, performer_sheet=performer_sheet, pool=contribution.amount
        )
