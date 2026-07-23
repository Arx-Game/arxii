"""Progression actions — training allocation and unlock purchase.

All player-facing progression mutations converge on ``action.run()``; these
actions are thin wrappers around the existing service functions in
``world.skills.services``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


_UNSET = object()

_OPERATION_ADD = "add"
_OPERATION_REMOVE = "remove"
_OPERATION_UPDATE = "update"

_KWARG_OPERATION = "operation"
_KWARG_SKILL_ID = "skill_id"
_KWARG_SPECIALIZATION_ID = "specialization_id"
_KWARG_AP_AMOUNT = "ap_amount"
_KWARG_MENTOR_PERSONA_ID = "mentor_persona_id"
_KWARG_ALLOCATION_ID = "allocation_id"
_KWARG_MENTOR = "mentor"


@dataclass
class ManageTrainingAction(Action):
    """Create, update, or remove a weekly training allocation.

    Training allocations reserve AP from the character's weekly budget; the
    weekly cron consumes the reserved AP and applies development. Because the
    allocation itself only reserves budget, this action costs no AP to manage.
    """

    key: str = "manage_training"
    name: str = "Manage Training"
    icon: str = "book-open"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF
    ap_cost: int = 0

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.skills.models import (  # noqa: PLC0415
            Skill,
            Specialization,
            TrainingAllocation,
        )
        from world.skills.services import (  # noqa: PLC0415
            create_training_allocation,
            remove_training_allocation,
            update_training_allocation,
        )

        operation = kwargs.get(_KWARG_OPERATION)

        try:
            if operation == _OPERATION_ADD:
                return self._add(actor, kwargs, Skill, Specialization, create_training_allocation)
            if operation == _OPERATION_UPDATE:
                return self._update(
                    actor, kwargs, TrainingAllocation, Persona, update_training_allocation
                )
            if operation == _OPERATION_REMOVE:
                return self._remove(actor, kwargs, TrainingAllocation, remove_training_allocation)
        except (
            ValueError,
            Skill.DoesNotExist,
            Specialization.DoesNotExist,
            TrainingAllocation.DoesNotExist,
            Persona.DoesNotExist,
        ) as exc:
            if hasattr(exc, "user_message"):
                msg: str = str(exc.user_message)
            else:
                msg = str(exc)
            return ActionResult(success=False, message=msg)

        return ActionResult(
            success=False,
            message=(
                "Invalid or missing operation. "
                f"Expected '{_OPERATION_ADD}', '{_OPERATION_UPDATE}', or '{_OPERATION_REMOVE}'."
            ),
        )

    def _add(
        self,
        actor: ObjectDB,
        kwargs: dict[str, Any],
        skill_cls: type[Any],
        specialization_cls: type[Any],
        create_training_allocation: Any,
    ) -> ActionResult:
        """Create a new training allocation for skill or specialization."""
        skill_id = kwargs.get(_KWARG_SKILL_ID)
        specialization_id = kwargs.get(_KWARG_SPECIALIZATION_ID)

        has_skill = skill_id is not None
        has_specialization = specialization_id is not None
        if has_skill == has_specialization:
            return ActionResult(
                success=False,
                message="Provide exactly one of skill_id or specialization_id.",
            )

        ap_amount = kwargs.get(_KWARG_AP_AMOUNT)
        if ap_amount is None:
            return ActionResult(success=False, message="ap_amount is required.")

        if has_skill:
            skill = skill_cls.objects.get(pk=skill_id)
            specialization: Any = None
            target_name = skill.name
        else:
            skill = None
            specialization = specialization_cls.objects.get(pk=specialization_id)
            target_name = specialization.name

        mentor = self._resolve_mentor(kwargs.get(_KWARG_MENTOR_PERSONA_ID))
        allocation = create_training_allocation(
            character=actor,
            ap_amount=ap_amount,
            skill=skill,
            specialization=specialization,
            mentor=mentor,
        )
        return ActionResult(
            success=True,
            message=f"Training allocation set for {target_name}.",
            data={"allocation_id": allocation.pk},
        )

    def _update(
        self,
        actor: ObjectDB,
        kwargs: dict[str, Any],
        training_allocation_cls: type[Any],
        persona_cls: type[Any],
        update_training_allocation: Any,
    ) -> ActionResult:
        """Update an existing training allocation owned by the actor."""
        allocation = training_allocation_cls.objects.get(pk=kwargs.get(_KWARG_ALLOCATION_ID))
        if allocation.character_id != actor.pk:
            return ActionResult(
                success=False,
                message="You can only update your own training allocations.",
            )

        update_kwargs: dict[str, Any] = {}
        ap_amount = kwargs.get(_KWARG_AP_AMOUNT)
        if ap_amount is not None:
            update_kwargs[_KWARG_AP_AMOUNT] = ap_amount
        if _KWARG_MENTOR_PERSONA_ID in kwargs:
            mentor_persona_id = kwargs.get(_KWARG_MENTOR_PERSONA_ID)
            if mentor_persona_id is None:
                update_kwargs[_KWARG_MENTOR] = None
            elif isinstance(mentor_persona_id, persona_cls):
                update_kwargs[_KWARG_MENTOR] = mentor_persona_id
            else:
                update_kwargs[_KWARG_MENTOR] = persona_cls.objects.get(
                    pk=mentor_persona_id,
                )

        allocation = update_training_allocation(allocation, **update_kwargs)
        return ActionResult(
            success=True,
            message="Training allocation updated.",
            data={"allocation_id": allocation.pk},
        )

    def _remove(
        self,
        actor: ObjectDB,
        kwargs: dict[str, Any],
        training_allocation_cls: type[Any],
        remove_training_allocation: Any,
    ) -> ActionResult:
        """Remove an existing training allocation owned by the actor."""
        allocation_id = kwargs.get(_KWARG_ALLOCATION_ID)
        allocation = training_allocation_cls.objects.get(pk=allocation_id)
        if allocation.character_id != actor.pk:
            return ActionResult(
                success=False,
                message="You can only remove your own training allocations.",
            )
        remove_training_allocation(allocation)
        return ActionResult(
            success=True,
            message="Training allocation removed.",
            data={"allocation_id": allocation_id},
        )

    def _resolve_mentor(self, mentor_persona_id: Any) -> Any:
        """Resolve a mentor kwarg to a Persona, None, or no mentor."""
        from world.scenes.models import Persona  # noqa: PLC0415

        if mentor_persona_id is None:
            return None
        if isinstance(mentor_persona_id, Persona):
            return mentor_persona_id
        return Persona.objects.get(pk=mentor_persona_id)


@dataclass
class PurchaseUnlockAction(Action):
    """Purchase a class-level, thread XP-lock, or skill-breakthrough unlock with XP.

    All three unlock types spend account XP through their respective service
    functions; this action is a thin action.run() wrapper around them.
    """

    key: str = "purchase_unlock"
    name: str = "Purchase Unlock"
    icon: str = "lock-open"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF
    ap_cost: int = 0

    _UNLOCK_TYPE_CLASS_LEVEL = "class_level"
    _UNLOCK_TYPE_THREAD_XP_LOCK = "thread_xp_lock"
    _UNLOCK_TYPE_SKILL_BREAKTHROUGH = "skill_breakthrough"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AnchorCapExceeded,
            InvalidImbueAmount,
            XPInsufficient,
        )
        from world.magic.models import Thread  # noqa: PLC0415
        from world.magic.types.alterations import AlterationGateError  # noqa: PLC0415
        from world.progression.models import ClassLevelUnlock  # noqa: PLC0415
        from world.skills.models import Skill  # noqa: PLC0415

        unlock_type = kwargs.get("unlock_type")

        try:
            if unlock_type == self._UNLOCK_TYPE_CLASS_LEVEL:
                return self._purchase_class_level(actor, kwargs)
            if unlock_type == self._UNLOCK_TYPE_THREAD_XP_LOCK:
                return self._purchase_thread_xp_lock(actor, kwargs)
            if unlock_type == self._UNLOCK_TYPE_SKILL_BREAKTHROUGH:
                return self._purchase_skill_breakthrough(actor, kwargs)
        except (
            ClassLevelUnlock.DoesNotExist,
            Thread.DoesNotExist,
            Skill.DoesNotExist,
            CharacterSheet.DoesNotExist,
            AlterationGateError,
            InvalidImbueAmount,
            AnchorCapExceeded,
            XPInsufficient,
            ValueError,
            TypeError,
        ) as exc:
            if hasattr(exc, "user_message"):
                msg: str = str(exc.user_message)
            else:
                msg = str(exc)
            return ActionResult(success=False, message=msg)

        return ActionResult(
            success=False,
            message=(
                "Invalid or missing unlock_type. "
                f"Expected '{self._UNLOCK_TYPE_CLASS_LEVEL}', "
                f"'{self._UNLOCK_TYPE_THREAD_XP_LOCK}', or "
                f"'{self._UNLOCK_TYPE_SKILL_BREAKTHROUGH}'."
            ),
        )

    def _purchase_class_level(
        self,
        actor: ObjectDB,
        kwargs: dict[str, Any],
    ) -> ActionResult:
        """Purchase a class-level unlock for the actor."""
        from world.progression.models import ClassLevelUnlock  # noqa: PLC0415
        from world.progression.services.spends import spend_xp_on_unlock  # noqa: PLC0415

        class_level_unlock_id = kwargs.get("class_level_unlock_id")
        if class_level_unlock_id is None:
            return ActionResult(success=False, message="class_level_unlock_id is required.")
        unlock_target = ClassLevelUnlock.objects.get(pk=class_level_unlock_id)
        success, message, unlock = spend_xp_on_unlock(actor, unlock_target)
        if not success:
            return ActionResult(success=False, message=message)
        return ActionResult(
            success=True,
            message=message,
            data={
                "unlock_type": self._UNLOCK_TYPE_CLASS_LEVEL,
                "unlock_id": unlock.pk,
            },
        )

    def _purchase_thread_xp_lock(
        self,
        actor: ObjectDB,
        kwargs: dict[str, Any],
    ) -> ActionResult:
        """Purchase an XP-locked level boundary on a thread owned by the actor."""
        from world.magic.models import Thread  # noqa: PLC0415
        from world.magic.services.threads import cross_thread_xp_lock  # noqa: PLC0415

        thread_id = kwargs.get("thread_id")
        if thread_id is None:
            return ActionResult(success=False, message="thread_id is required.")
        thread = Thread.objects.get(pk=thread_id)
        character_sheet = actor.sheet_data
        if thread.owner_id != character_sheet.pk:
            return ActionResult(
                success=False, message="You can only purchase unlocks for your own threads."
            )
        boundary_level = kwargs.get("boundary_level")
        if boundary_level is None:
            return ActionResult(success=False, message="boundary_level is required.")
        thread_level_unlock = cross_thread_xp_lock(character_sheet, thread, int(boundary_level))
        return ActionResult(
            success=True,
            message=f"Thread boundary {boundary_level} unlocked.",
            data={
                "unlock_type": self._UNLOCK_TYPE_THREAD_XP_LOCK,
                "thread_level_unlock_id": thread_level_unlock.pk,
                "thread_id": thread.pk,
                "boundary_level": boundary_level,
            },
        )

    def _purchase_skill_breakthrough(
        self,
        actor: ObjectDB,
        kwargs: dict[str, Any],
    ) -> ActionResult:
        """Purchase a skill's XP-boundary breakthrough for the actor (#2115)."""
        from world.skills.models import Skill  # noqa: PLC0415
        from world.skills.services import purchase_skill_breakthrough  # noqa: PLC0415

        skill_id = kwargs.get("skill_id")
        if skill_id is None:
            return ActionResult(success=False, message="skill_id is required.")
        skill = Skill.objects.get(pk=skill_id)
        success, message = purchase_skill_breakthrough(actor, skill)
        if not success:
            return ActionResult(success=False, message=message)
        return ActionResult(
            success=True,
            message=message,
            data={
                "unlock_type": self._UNLOCK_TYPE_SKILL_BREAKTHROUGH,
                "skill_id": skill.pk,
            },
        )
