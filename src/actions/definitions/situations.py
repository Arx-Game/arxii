"""JUNIOR-GM-tier Actions: place authored scenario content into the actor's room.

``SetSituationAction`` (#1895) instantiates a whole ``SituationTemplate``;
``PlaceChallengeAction`` (#2865) places a single authored ``ChallengeTemplate``
against a named thing in the room, for the impromptu beat no authored situation
covers. Both mint the same class of live ``ChallengeInstance`` row (ADR-0091),
so both gate at JUNIOR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.definitions.gm_shift import difficulty_label, resolve_severity_shift
from actions.prerequisites import MinimumGMLevelPrerequisite
from actions.types import ActionContext, ActionResult, TargetType
from world.gm.constants import GMLevel
from world.mechanics.challenge_resolution import instantiate_challenge
from world.mechanics.models import ChallengeTemplate, SituationTemplate
from world.mechanics.situation_services import (
    create_challenge_target_object,
    instantiate_situation,
)

_CHALLENGE_CATALOG_HINT = "Place which challenge? (try `setsituation find <term>`)"
_NO_SUCH_CHALLENGE = "That challenge template does not exist."
_TARGET_NAME_REQUIRED = "Name what embodies the challenge (e.g. 'the barred gate')."
_TARGET_NAME_MAX_LENGTH = 100


@dataclass
class SetSituationAction(Action):
    """JUNIOR-tier GM action: instantiate a SituationTemplate into the actor's current room.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="set_situation"``,
    ``situation_template_id=<SituationTemplate.pk>``.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (#2117; staff
    bypass preserved) -- this mints live ``Challenge``/``ChallengeInstance``
    rows (ADR-0091), one tier above bare approval.
    """

    key: str = "set_situation"
    name: str = "Set Situation"
    icon: str = "map"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        template_id = kwargs.get("situation_template_id")
        if template_id is None:
            return ActionResult(success=False, message="Set which situation?")

        try:
            template = SituationTemplate.objects.get(pk=template_id)
        except SituationTemplate.DoesNotExist:
            return ActionResult(success=False, message="That situation template does not exist.")

        try:
            instantiate_situation(template, actor.location)
        except ObjectDoesNotExist:
            return ActionResult(
                success=False,
                message="This room isn't set up to hold that situation's traps.",
            )

        return ActionResult(success=True)


@dataclass
class PlaceChallengeAction(Action):
    """JUNIOR-tier GM action: place ONE authored ChallengeTemplate in this room (#2865).

    The lightweight path #2866 left missing. A JUNIOR GM funnelled off
    ``InvokeCatalogCheckAction`` (SENIOR-gated) previously had only
    ``SetSituationAction``, which needs a whole pre-authored ``SituationTemplate``
    — nothing to reach for when an impromptu moment needs real stakes right now.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="place_challenge"``,
    ``challenge_template_id=<ChallengeTemplate.pk>``,
    ``target_object_name="<what embodies it>"``, and optionally exactly one of
    ``edge_reason`` / ``setback_reason``.

    Still catalog-only (ADR-0110): the GM picks an *authored* challenge and names
    what embodies it. The approaches offered against it, its consequences, and its
    discovery type are the template's own — nothing here composes a challenge, an
    approach, or a consequence pool. The single adaptation permitted is the bounded,
    reason-carrying one-band shift the module invariant already allows, persisted on
    the instance so resolution and the audit trail read the same number.

    Mints a standalone ``ChallengeInstance`` (``situation_instance=None``) — a legal
    row shape since the field was made nullable, and the same shape the reactive
    combat challenges have always used.
    """

    key: str = "place_challenge"
    name: str = "Place Challenge"
    icon: str = "flag"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        template = self._resolve_template(kwargs.get("challenge_template_id"))
        if isinstance(template, ActionResult):
            return template

        target_name = str(kwargs.get("target_object_name") or "").strip()
        if not target_name:
            return ActionResult(success=False, message=_TARGET_NAME_REQUIRED)
        target_name = target_name[:_TARGET_NAME_MAX_LENGTH]

        location = actor.location
        if location is None:
            return ActionResult(success=False, message="You are nowhere to place that.")

        shift = resolve_severity_shift(
            template.severity,
            str(kwargs.get("edge_reason") or "").strip(),
            str(kwargs.get("setback_reason") or "").strip(),
        )
        if isinstance(shift, ActionResult):
            return shift
        adjustment, reason, shift_note = shift

        # One transaction: a failed adjustment write must not strand the target
        # object it was created for.
        with transaction.atomic():
            target = create_challenge_target_object(target_name)
            instance = instantiate_challenge(template, location=location, target_object=target)
            if adjustment:
                instance.severity_adjustment = adjustment
                instance.adjustment_reason = reason
                instance.save(update_fields=["severity_adjustment", "adjustment_reason"])

        hidden_note = "" if instance.is_revealed else " (hidden until discovered)"
        message = (
            f"{template.name} placed on {target_name} "
            f"({difficulty_label(instance.effective_severity)}){shift_note}{hidden_note}."
        )
        return ActionResult(success=True, message=message)

    @staticmethod
    def _resolve_template(template_id: Any) -> ChallengeTemplate | ActionResult:
        if template_id is None:
            return ActionResult(success=False, message=_CHALLENGE_CATALOG_HINT)
        try:
            return ChallengeTemplate.objects.get(pk=template_id)
        except (ChallengeTemplate.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_CHALLENGE)
