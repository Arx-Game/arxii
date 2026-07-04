"""Registry Actions for the NPC-service hire/commission loop (#1493).

Three stateless Actions wrap the existing ephemeral ``InteractionSession`` state machine.
Each surface (web viewset, telnet ``hire``) manages its own session container and delegates
the actual interaction lifecycle to ``action.run()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.missions.services.offer_handler import MissionRiskUnacknowledgedError

# Kwarg spellings accepted as "yes, I acknowledge the risk" (#1770 PR4) —
# telnet passes strings, the web dispatcher may pass a bool.
_TRUTHY_VALUES = frozenset({"yes", "y", "true", "1"})


def _truthy(value: Any) -> bool:
    """Interpret an acknowledge_risk kwarg from either surface."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY_VALUES if value is not None else False


def _risk_prompt_message(exc: MissionRiskUnacknowledgedError) -> str:
    """The informed-consent prompt for a risky mission offer (#1770 PR4).

    When a staked linked beat drives the gate (#1780), the concrete stakes
    carry the danger, so we don't foreground the template ``risk_tier`` number
    — it can understate a low-tier template that resolves a high-risk beat.
    The numeric tier is shown only when there are no named stakes to speak for
    themselves.
    """
    if exc.stake_summaries:
        lines = ["This job is dangerous. At stake:"]
        lines.extend(f"  - {summary}" for summary in exc.stake_summaries)
    else:
        lines = [
            f"This job is dangerous (risk tier {exc.risk_tier}). At stake:",
            "  - The usual hazards of work at this tier.",
        ]
    lines.append("Accept again with acknowledge_risk=yes to take the job anyway.")
    return "\n".join(lines)


@dataclass
class StartNPCInteractionAction(Action):
    """Begin an NPC-service interaction with a role."""

    key: str = "npc_start"
    name: str = "Start NPC Interaction"
    icon: str = "handshake"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.npc_services.models import NPCRole  # noqa: PLC0415
        from world.npc_services.services import start_interaction  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import (  # noqa: PLC0415
            MissingPrimaryPersonaError,
            persona_for_character,
        )

        role_id = kwargs.get("role_id")
        npc_persona_id = kwargs.get("npc_persona_id")

        if role_id is None:
            return ActionResult(success=False, message="No NPC role specified.")

        role = NPCRole.objects.filter(pk=role_id).first()
        if role is None:
            return ActionResult(success=False, message="That NPC role was not found.")

        npc_persona = None
        if npc_persona_id is not None:
            npc_persona = Persona.objects.filter(pk=npc_persona_id).first()
            if npc_persona is None:
                return ActionResult(success=False, message="That NPC persona was not found.")

        try:
            persona = persona_for_character(actor)
        except (AttributeError, ObjectDoesNotExist, MissingPrimaryPersonaError):
            return ActionResult(
                success=False,
                message="No active character sheet.",
                data={"invariant_breach": True},
            )

        session = start_interaction(
            role=role,
            persona=persona,
            character=actor,
            npc_persona=npc_persona,
        )
        return ActionResult(
            success=True,
            message=f"You begin speaking with {role.name}.",
            data={"session": session},
        )


@dataclass
class ResolveNPCOfferAction(Action):
    """Resolve an offer in the current NPC-service interaction."""

    key: str = "npc_resolve"
    name: str = "Resolve NPC Offer"
    icon: str = "scroll"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(  # noqa: PLR0911 - distinct guard failures read clearest as early returns
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.missions.services.offer_handler import (  # noqa: PLC0415
            MissionRiskUnacknowledgedError,
            acknowledge_mission_risk,
        )
        from world.npc_services.models import NPCServiceOffer  # noqa: PLC0415
        from world.npc_services.services import ResolveOfferError, resolve_offer  # noqa: PLC0415

        session = kwargs.get("session")
        offer_id = kwargs.get("offer_id")

        if session is None:
            return ActionResult(success=False, message="No interaction is in progress.")
        if session.closed:
            return ActionResult(success=False, message="This interaction has ended.")
        if offer_id is None:
            return ActionResult(success=False, message="No offer specified.")

        offer = NPCServiceOffer.objects.filter(pk=offer_id).first()
        if offer is None:
            return ActionResult(
                success=False,
                message="That offer was not found.",
                data={"not_found": True},
            )

        # #1770 PR4: the two-phase risk opt-in lives inside npc_resolve. The
        # first resolve attempt mints NOTHING — the risk gate sits behind
        # resolve_offer's session/role/eligibility validation, so reaching
        # MissionRiskUnacknowledgedError proves the offer was currently
        # resolvable. Only then, and only with acknowledge_risk passed, is
        # the idempotent ack row written and the resolve retried; without
        # the kwarg the gate error becomes the informed-consent prompt. An
        # ineligible offer can therefore never mint an ack row.
        acknowledge = _truthy(kwargs.get("acknowledge_risk"))
        try:
            result = resolve_offer(session, offer)
        except MissionRiskUnacknowledgedError as exc:
            if not acknowledge:
                return ActionResult(
                    success=False,
                    message=_risk_prompt_message(exc),
                    data={
                        "requires_risk_acknowledgement": True,
                        "risk_tier": exc.risk_tier,
                        "stake_summaries": list(exc.stake_summaries),
                    },
                )
            acknowledge_mission_risk(offer, session.persona)
            try:
                result = resolve_offer(session, offer)
            except ResolveOfferError as retry_exc:
                return ActionResult(success=False, message=retry_exc.user_message)
        except ResolveOfferError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=result.message,
            data={"session": session, "last_result_message": result.message},
        )


@dataclass
class EndNPCInteractionAction(Action):
    """End the current NPC-service interaction."""

    key: str = "npc_end"
    name: str = "End NPC Interaction"
    icon: str = "door-open"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.npc_services.services import end_interaction  # noqa: PLC0415

        session = kwargs.get("session")
        if session is None:
            return ActionResult(success=False, message="No interaction is in progress.")

        end_interaction(session)
        return ActionResult(
            success=True,
            message="You conclude the conversation.",
            data={"session": session},
        )


# Module-level singletons registered in actions.registry._ALL_ACTIONS.
start_npc_interaction = StartNPCInteractionAction()
resolve_npc_offer = ResolveNPCOfferAction()
end_npc_interaction = EndNPCInteractionAction()
