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

    def execute(
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

        level = kwargs.get("level") or SecretLevel.UNCOMMON_KNOWLEDGE
        try:
            secret = mint_accusation(
                accuser_persona=active_persona_for_sheet(framer_sheet),
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


mint_accusation = MintAccusationAction()
