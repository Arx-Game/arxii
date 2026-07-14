"""Player-authored false-scandal minting — the frame-job surface (#1825).

``MintAccusationAction`` (key ``mint_accusation``) lets a player author an ACCUSATION Secret
about *another* character — a false scandal that mints heat/reputation like a true one until
disproven. It is gated by the target's ``hostile`` antagonism consent category (via the #2170
consent tree): a played target must have opted into being antagonised; an NPC is always
frameable. The mint itself reuses ``world.secrets.services.mint_accusation``; falsity stays
emergent (divergence between the alleged deed and truth, never a stored flag).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext, ActionResult


@dataclass
class MintAccusationAction(Action):
    """Author a false accusation (ACCUSATION Secret) about a consenting target (#1825)."""

    key: str = "mint_accusation"
    name: str = "Accuse"
    icon: str = "scroll"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def execute(  # noqa: PLR0911 — each return is a distinct guard/route (consent, crime, mint)
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
        from world.secrets.constants import SecretLevel  # noqa: PLC0415
        from world.secrets.services import (  # noqa: PLC0415
            SecretError,
            accusation_permitted,
            mint_accusation,
        )

        content = (kwargs.get("content") or "").strip()
        if not content:
            return _ActionResult(success=False, message="Accuse them of what? (say the claim)")

        framer_sheet = getattr(actor, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if framer_sheet is None:
            return _ActionResult(success=False, message="You have no character identity.")

        target_persona = (
            Persona.objects.filter(pk=kwargs.get("target_persona_id"))
            .select_related("character_sheet")
            .first()
        )
        if target_persona is None:
            return _ActionResult(success=False, message="No such target.")
        target_sheet = target_persona.character_sheet

        if not accusation_permitted(framer_sheet=framer_sheet, target_sheet=target_sheet):
            return _ActionResult(
                success=False,
                message=(
                    f"{target_persona} has not opened themselves to being antagonised. "
                    "You can't manufacture a scandal against them."
                ),
            )

        accuser_persona = active_persona_for_sheet(framer_sheet)

        # A criminal accusation (a crime kind named) routes through the justice heat
        # bridge; a bare accusation stays reputation-only. This command path files a
        # *wild* accusation (no real deed underneath) — the fragile, easily-refuted tier
        # (#1825); anchoring a real deed (an L3 frame) is the evidence-assembly path.
        crime_slug = (kwargs.get("crime_kind_slug") or "").strip()
        if crime_slug:
            return _file_accusation_crime(
                actor=actor,
                kwargs=kwargs,
                crime_slug=crime_slug,
                accuser_persona=accuser_persona,
                target_sheet=target_sheet,
                target_persona=target_persona,
                content=content,
            )

        level = kwargs.get("level") or SecretLevel.UNCOMMON_KNOWLEDGE
        try:
            secret = mint_accusation(
                accuser_persona=accuser_persona,
                subject_sheet=target_sheet,
                content=content,
                level=int(level),
            )
        except SecretError as exc:
            return _ActionResult(success=False, message=exc.user_message)

        return _ActionResult(
            success=True,
            message=f"You mint a scandal against {target_persona}. Now to make it stick.",
            data={"secret_id": secret.pk},
        )


def _file_accusation_crime(  # noqa: PLR0913
    *,
    actor: ObjectDB,
    kwargs: dict[str, Any],
    crime_slug: str,
    accuser_persona: Any,
    target_sheet: Any,
    target_persona: Any,
    content: str,
) -> ActionResult:
    """Route a criminal accusation (a named crime kind) through the justice heat bridge.

    A bare accusation stays reputation-only; this command path files a *wild*
    accusation (no real deed underneath) — the fragile, easily-refuted tier
    (#1825); anchoring a real deed (an L3 frame) is the evidence-assembly path.
    """
    from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.justice.services import (  # noqa: PLC0415
        area_for_room,
        file_criminal_accusation,
    )
    from world.secrets.constants import SecretLevel  # noqa: PLC0415
    from world.secrets.services import SecretError  # noqa: PLC0415

    crime_kind = CrimeKind.objects.filter(slug=crime_slug).first()
    if crime_kind is None:
        no_crime = f"There's no such crime to accuse them of: {crime_slug!r}."
        return _ActionResult(success=False, message=no_crime)
    location = getattr(actor, "location", None)  # noqa: GETATTR_LITERAL
    area = area_for_room(location) if location is not None else None
    level = kwargs.get("level") or SecretLevel.WHISPERS
    try:
        secret = file_criminal_accusation(
            accuser_persona=accuser_persona,
            subject_sheet=target_sheet,
            content=content,
            crime_kind=crime_kind,
            level=int(level),
            area=area,
        )
    except SecretError as exc:
        return _ActionResult(success=False, message=exc.user_message)
    return _ActionResult(
        success=True,
        message=(
            f"You accuse {target_persona} of {crime_kind}. Where that's a crime, "
            "the law will start to look their way — until someone disproves it."
        ),
        data={"secret_id": secret.pk},
    )


@dataclass
class SmearAction(Action):
    """The one-move L1 smear — mint an accusation through the rumor mill (#1825).

    Thin over ``world.secrets.gossip.plant_smear``: hub + Gossip skill + the target's
    ``hostile`` consent gate live in the service; the action charges the smear's AP +
    social fatigue (finally making the light tier cost something).
    """

    key: str = "smear_accusation"
    name: str = "Smear"
    icon: str = "comment-slash"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    # PLACEHOLDER cost magnitudes — tuned in a later author pass.
    ap_cost: int = 1
    fatigue_cost: int = 1
    fatigue_category: str = ActionCategory.SOCIAL

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.secrets.gossip import GossipError, plant_smear  # noqa: PLC0415
        from world.secrets.services import SecretError  # noqa: PLC0415

        content = (kwargs.get("content") or "").strip()
        if not content:
            return _ActionResult(success=False, message="Smear them with what? (say the claim)")
        target_persona = (
            Persona.objects.filter(pk=kwargs.get("target_persona_id"))
            .select_related("character_sheet")
            .first()
        )
        if target_persona is None:
            return _ActionResult(success=False, message="No such target.")
        room = getattr(actor, "location", None)  # noqa: GETATTR_LITERAL
        if room is None:
            return _ActionResult(success=False, message="There's no one here to whisper to.")
        try:
            result = plant_smear(actor, target_persona.character_sheet, content, room=room)
        except (GossipError, SecretError) as exc:
            return _ActionResult(success=False, message=exc.user_message)
        if not result.success:
            return _ActionResult(
                success=True,
                message="PLACEHOLDER The rumor dies on your lips — nobody bites.",
            )
        return _ActionResult(
            success=True,
            message=(
                f"PLACEHOLDER You seed a poisonous little rumor about {target_persona}. "
                "It's making the rounds."
            ),
            data={"secret_id": result.surfaced_secret_id},
        )


@dataclass
class RefuteAccusationAction(Action):
    """Attack an accusation's credibility at a hub — the consentless defense (#1825).

    Thin over ``world.secrets.gossip.refute_accusation``: hub gating, the knowledge
    requirement, the one-attempt rule, and the partial reputation reversal all live in
    the service. No consent gate — defending the accused is open (the Tom/Bob/Fred rule).
    """

    key: str = "refute_accusation"
    name: str = "Refute"
    icon: str = "scale-balanced"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    # PLACEHOLDER cost magnitudes — tuned in a later author pass.
    ap_cost: int = 1
    fatigue_cost: int = 1
    fatigue_category: str = ActionCategory.SOCIAL

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.secrets.gossip import GossipError, refute_accusation  # noqa: PLC0415
        from world.secrets.models import Secret  # noqa: PLC0415

        secret_id = kwargs.get("secret_id")
        secret = Secret.objects.filter(pk=secret_id).first() if isinstance(secret_id, int) else None
        if secret is None:
            return _ActionResult(success=False, message="There's no such rumor to refute.")
        room = getattr(actor, "location", None)  # noqa: GETATTR_LITERAL
        if room is None:
            return _ActionResult(success=False, message="There's no one here to argue to.")
        try:
            result = refute_accusation(actor, secret, room=room)
        except GossipError as exc:
            return _ActionResult(success=False, message=exc.user_message)
        if not result.success:
            return _ActionResult(
                success=True,
                message="PLACEHOLDER Your case fails to land — the rumor keeps its teeth.",
            )
        return _ActionResult(
            success=True,
            message=(
                "PLACEHOLDER You pick the story apart in front of everyone. "
                "Some of the mud washes off its subject."
            ),
            data={"secret_id": secret.pk},
        )


mint_accusation = MintAccusationAction()
