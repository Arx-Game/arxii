"""Blackmail leverage → coerce a sheeted NPC into an asset (#1680).

``CoerceAssetAction`` (key ``coerce``) spends standing leverage (minted by a prior
Blackmail) to extract the target as a COERCION ``NPCAsset`` of the blackmailer's chosen
kind. Auto-succeeds against an un-played NPC; a PC or an *actively-piloted* NPC is never
auto-coerced — they keep player-style agency and must be pressed via Blackmail's response
register instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.prerequisites import Prerequisite
    from actions.types import ActionContext, ActionResult

# The relationship kinds a coerced asset may take — the blackmailer's "list of options".
# Cultivation-only kinds (guard / fan / minor_ally) are deliberately excluded.
_COERCIBLE_ROLE_CONTEXTS = frozenset({"informant", "contact", "personal_favor"})


@dataclass
class CoerceAssetAction(Action):
    """Extract a blackmailed NPC as a coerced asset (#1680)."""

    key: str = "coerce"
    name: str = "Coerce"
    icon: str = "lock"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        from actions.prerequisites import LeverageHeldPrerequisite  # noqa: PLC0415

        return [LeverageHeldPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.assets.services import CoercionError, coerce_into_asset  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import persona_for_character  # noqa: PLC0415

        role_context = kwargs.get("role_context")
        if role_context not in _COERCIBLE_ROLE_CONTEXTS:
            return _ActionResult(
                success=False,
                message="Coerce them as what? (informant / contact / personal-favor)",
            )
        target_persona = (
            Persona.objects.filter(pk=kwargs.get("target_persona_id"))
            .select_related("character_sheet__character")
            .first()
        )
        if target_persona is None:
            return _ActionResult(success=False, message="No such target.")

        target_character = target_persona.character_sheet.character
        if target_character is None:
            return _ActionResult(success=False, message="There's no one there to coerce.")
        # A played character (has an account) or an actively-piloted NPC (live session) is
        # never auto-coerced — they get player-style agency via Blackmail's resist register.
        if target_character.db_account is not None or target_character.sessions.count() > 0:
            return _ActionResult(
                success=False,
                message="They're being played — press them with blackmail, where they answer.",
            )

        try:
            asset = coerce_into_asset(
                coercer_persona=persona_for_character(actor),
                target_persona=target_persona,
                role_context=role_context,
            )
        except CoercionError as exc:
            return _ActionResult(success=False, message=exc.user_message)
        kind = asset.get_role_context_display().lower()
        return _ActionResult(
            success=True,
            message=f"You now hold {target_persona} as a coerced {kind}.",
        )


@dataclass
class RevealSecretAction(Action):
    """Play the blackmail card — reveal a secret you hold leverage from (#1680).

    Exposes the secret to the subject's societies (the exposure→renown bridge) and spends
    the leverage founded on it. A one-time card: coerced assets you already extracted stay,
    but the standing threat is gone once the secret is out.
    """

    key: str = "reveal_secret"
    name: str = "Reveal Secret"
    icon: str = "megaphone"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.prerequisites import resolve_actor_sheet  # noqa: PLC0415
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.secrets.models import Secret  # noqa: PLC0415
        from world.secrets.services import reveal_leveraged_secret  # noqa: PLC0415

        actor_sheet = resolve_actor_sheet(actor)
        secret = Secret.objects.filter(pk=kwargs.get("secret_id")).first()
        if actor_sheet is None or secret is None:
            return _ActionResult(success=False, message="Reveal what?")
        if reveal_leveraged_secret(revealer_sheet=actor_sheet, secret=secret):
            return _ActionResult(
                success=True,
                message="You reveal it. The secret is out — and no longer your hold over them.",
            )
        return _ActionResult(success=False, message="You hold no leverage from that secret.")


coerce = CoerceAssetAction()
reveal_secret = RevealSecretAction()
