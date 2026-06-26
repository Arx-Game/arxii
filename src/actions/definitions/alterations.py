"""Magical alteration (Mage Scar) resolution action.

`ResolveAlterationAction` is the action.run() seam for resolving a pending
Mage Scar, shared by the web ``PendingAlterationViewSet.resolve`` action and the
upcoming telnet ``CmdMageScar``. It validates the pending alteration, dispatches
to ``validate_alteration_resolution`` + ``resolve_pending_alteration``, and
returns a user-safe ``ActionResult`` for both surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import PendingAlteration


@dataclass
class ResolveAlterationAction(Action):
    """Resolve a pending Mage Scar from the library or from scratch."""

    key: str = "resolve_alteration"
    name: str = "Resolve a Mage Scar"
    icon: str = "scar"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def _resolve_library(
        self,
        pending: PendingAlteration,
        library_template_id: int,
        account: AccountDB | None,
        is_staff: bool,
        sheet: CharacterSheet,
    ) -> tuple[Any, str]:
        """Resolve via a library entry; return (resolution_result, error_message)."""
        from world.magic.models import MagicalAlterationTemplate  # noqa: PLC0415
        from world.magic.services import (  # noqa: PLC0415
            resolve_pending_alteration,
            validate_alteration_resolution,
        )

        try:
            library_template = MagicalAlterationTemplate.objects.select_related(
                "condition_template"
            ).get(pk=library_template_id, is_library_entry=True)
        except MagicalAlterationTemplate.DoesNotExist:
            return None, "That library entry was not found."

        errors = validate_alteration_resolution(
            pending_tier=pending.tier,
            pending_affinity_id=pending.origin_affinity_id,
            pending_resonance_id=pending.origin_resonance_id,
            payload={"library_entry_pk": library_template.pk},
            is_staff=is_staff,
            character_sheet=sheet,
        )
        if errors:
            return None, "; ".join(errors)

        result = resolve_pending_alteration(
            pending=pending,
            name=library_template.condition_template.name,
            player_description=library_template.condition_template.player_description,
            observer_description=library_template.condition_template.observer_description,
            weakness_damage_type=library_template.weakness_damage_type,
            weakness_magnitude=library_template.weakness_magnitude,
            resonance_bonus_magnitude=library_template.resonance_bonus_magnitude,
            social_reactivity_magnitude=library_template.social_reactivity_magnitude,
            is_visible_at_rest=library_template.is_visible_at_rest,
            resolved_by=account,
            library_template=library_template,
        )
        return result, ""

    def _resolve_scratch(
        self,
        pending: PendingAlteration,
        kwargs: dict[str, Any],
        account: AccountDB | None,
        is_staff: bool,
        sheet: CharacterSheet,
    ) -> tuple[Any, str]:
        """Resolve via player-authored scratch fields; return (result, error_message)."""
        from world.magic.services import (  # noqa: PLC0415
            resolve_pending_alteration,
            validate_alteration_resolution,
        )

        name = kwargs.get("name", "")
        player_description = kwargs.get("player_description", "")
        observer_description = kwargs.get("observer_description", "")
        weakness_damage_type = kwargs.get("weakness_damage_type")
        weakness_magnitude = kwargs.get("weakness_magnitude", 0)
        resonance_bonus_magnitude = kwargs.get("resonance_bonus_magnitude", 0)
        social_reactivity_magnitude = kwargs.get("social_reactivity_magnitude", 0)
        is_visible_at_rest = kwargs.get("is_visible_at_rest", False)
        parent_template = kwargs.get("parent_template")
        is_library_entry = kwargs.get("is_library_entry", False)

        weakness_damage_type_id = weakness_damage_type.pk if weakness_damage_type else None
        parent_template_id = parent_template.pk if parent_template else None
        payload = {
            "tier": pending.tier,
            "origin_affinity_id": pending.origin_affinity_id,
            "origin_resonance_id": pending.origin_resonance_id,
            "name": name,
            "player_description": player_description,
            "observer_description": observer_description,
            "weakness_damage_type_id": weakness_damage_type_id,
            "weakness_magnitude": weakness_magnitude,
            "resonance_bonus_magnitude": resonance_bonus_magnitude,
            "social_reactivity_magnitude": social_reactivity_magnitude,
            "is_visible_at_rest": is_visible_at_rest,
            "parent_template_id": parent_template_id,
            "is_library_entry": is_library_entry,
        }
        errors = validate_alteration_resolution(
            pending_tier=pending.tier,
            pending_affinity_id=pending.origin_affinity_id,
            pending_resonance_id=pending.origin_resonance_id,
            payload=payload,
            is_staff=is_staff,
            character_sheet=sheet,
        )
        if errors:
            return None, "; ".join(errors)

        result = resolve_pending_alteration(
            pending=pending,
            name=name,
            player_description=player_description,
            observer_description=observer_description,
            weakness_damage_type=weakness_damage_type,
            weakness_magnitude=weakness_magnitude,
            resonance_bonus_magnitude=resonance_bonus_magnitude,
            social_reactivity_magnitude=social_reactivity_magnitude,
            is_visible_at_rest=is_visible_at_rest,
            resolved_by=account,
            parent_template=parent_template,
        )
        return result, ""

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.magic.constants import PendingAlterationStatus  # noqa: PLC0415
        from world.magic.models import PendingAlteration  # noqa: PLC0415
        from world.scenes.scene_admin_services import resolve_actor_account  # noqa: PLC0415

        result = None
        message = "You can't resolve that Mage Scar right now."

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            message = "Only characters can resolve Mage Scars."
        else:
            pending_id = kwargs.get("pending_id")
            if not isinstance(pending_id, int):
                message = "Which pending alteration do you want to resolve?"
            else:
                try:
                    pending = PendingAlteration.objects.select_related("character").get(
                        pk=pending_id,
                        character=sheet,
                        status=PendingAlterationStatus.OPEN,
                    )
                except PendingAlteration.DoesNotExist:
                    message = "You have no open pending alteration with that id."
                else:
                    account = resolve_actor_account(actor)
                    is_staff = bool(account and account.is_staff)
                    library_template_id = kwargs.get("library_template_id")
                    if library_template_id is not None:
                        result, message = self._resolve_library(
                            pending,
                            library_template_id,
                            account,
                            is_staff,
                            sheet,
                        )
                    else:
                        result, message = self._resolve_scratch(
                            pending,
                            kwargs,
                            account,
                            is_staff,
                            sheet,
                        )

        if result is not None:
            return ActionResult(
                success=True,
                message=f"You resolve the Mage Scar '{result.template.condition_template.name}'.",
                data={"status": "RESOLVED", "event_id": result.event.pk},
            )
        return ActionResult(success=False, message=message)
