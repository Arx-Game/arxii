"""The technique picker action (#4341): choose what a manifesting technique brings into a
fight.

Web dispatch passes ``technique_id`` + ``option_id``; telnet (``manifest
<technique>=<option>``) passes ``technique_name`` + ``option_name``. Both resolve against
the character's own known manifesting techniques and converge on
``world.magic.services.manifestation.set_character_manifestation``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.companions.models import Companion
    from world.magic.models import Technique, TechniqueManifestOption

MSG_NO_SHEET = "You have no character sheet."
MSG_WHICH = "Choose what which technique brings? Usage: manifest <technique>=<option>"
MSG_NO_OPTION = "That technique cannot bring that."


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ManifestSetAction(Action):
    """Choose which bound being or companion a manifesting technique brings (#4341).

    kwargs:
        technique_id / option_id: the technique and option ids (web).
        technique_name / option_name: the technique's catalog or own name, and a being's,
            archetype's or own companion's name (telnet).
    """

    key: str = "manifest_set"
    name: str = "Choose What a Technique Brings"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.magic.exceptions import ManifestChoiceError  # noqa: PLC0415
        from world.magic.services.manifestation import (  # noqa: PLC0415
            MSG_UNKNOWN_TECHNIQUE,
            set_character_manifestation,
        )

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(success=False, message=MSG_NO_SHEET)

        technique_id = _as_int(kwargs.get("technique_id"))
        technique_name = str(kwargs.get("technique_name") or "").strip()
        option_id = _as_int(kwargs.get("option_id"))
        option_name = str(kwargs.get("option_name") or "").strip()
        if (technique_id is None and not technique_name) or (option_id is None and not option_name):
            return ActionResult(success=False, message=MSG_WHICH)

        technique = _technique(sheet, technique_id, technique_name)
        if technique is None:
            return ActionResult(success=False, message=MSG_UNKNOWN_TECHNIQUE)
        option, companion = _option(sheet, technique, option_id, option_name)
        if option is None:
            return ActionResult(success=False, message=MSG_NO_OPTION)

        try:
            row = set_character_manifestation(sheet, technique, option, companion)
        except ManifestChoiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        brought = (
            row.companion.name
            if row.companion is not None
            else str((option.being or option.archetype).name)
        )
        return ActionResult(
            success=True,
            message=f"{technique.name} will bring {brought} into a fight.",
            data={
                "technique_id": technique.pk,
                "option_id": option.pk,
                "companion_id": row.companion_id,
            },
        )


def _technique(
    sheet: CharacterSheet, technique_id: int | None, technique_name: str
) -> Technique | None:
    """The manifesting technique she named: by id (web) or by name (telnet)."""
    from world.magic.services.manifestation import (  # noqa: PLC0415
        manifesting_technique_by_id,
        manifesting_technique_named,
    )

    if technique_id is not None:
        return manifesting_technique_by_id(sheet, technique_id)
    return manifesting_technique_named(sheet, technique_name)


def _option(
    sheet: CharacterSheet, technique: Technique, option_id: int | None, option_name: str
) -> tuple[TechniqueManifestOption | None, Companion | None]:
    """The technique's option she chose, and the companion a name picked (or None)."""
    from world.magic.services.manifestation import manifest_option_named  # noqa: PLC0415

    if option_id is not None:
        option = (
            technique.manifest_options.select_related("being", "archetype")
            .filter(pk=option_id)
            .first()
        )
        return option, None
    found = manifest_option_named(sheet, technique, option_name)
    return found if found is not None else (None, None)
