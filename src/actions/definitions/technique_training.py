"""TrainTechniqueAction — the action.run() seam for check-based technique training (#2739).

Both the telnet ``train`` command and (a later task's) web endpoint converge on
this action's ``run()``. It is the missing production caller of
``resolve_training_check`` (#2727) — the check-resolution layer was built and
tested but unreachable by any player until this action existed.

Location policy (Decision 3a, issue #2739): self-study needs no location. A
teacher only contributes their skill bonus when their tenure's character is
co-present in the learner's room at session time; otherwise the session
silently falls back to self-study rates. This is true for BOTH PC-teacher
meters and Academy TRAIN meters — there is never a location hard-block.

AP handling: the seam (``resolve_training_check`` → ``contribute_to_technique_progress``)
spends AP in full itself and raises cleanly on pool/cap overruns
(``WeeklyTrainingCapExceeded`` / insufficient-AP). This action does not
pre-bound ``ap_to_invest`` beyond defaulting it when omitted and rejecting a
non-positive value — pre-bounding here would duplicate (and could contradict)
the seam's "AP is always spent in full" contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.magic.models import TechniqueProgress
    from world.roster.models import RosterTenure

# No "base training session cost" constant exists on GiftAcquisitionConfig or
# on the resolve_training_check seam today (verified 2026-08-07) — defaults to
# 1 AP per session until one is authored.
_DEFAULT_AP_TO_INVEST = 1


def _co_present_teacher(actor: ObjectDB, progress: TechniqueProgress) -> RosterTenure | None:
    """Return ``progress.teacher_tenure`` iff that tenure's character shares the actor's room.

    Silent fallback to ``None`` (self-study rates) whenever the tenure is unset, has
    no live character, or that character isn't co-present — never a hard block
    (Decision 3a).
    """
    tenure = progress.teacher_tenure
    if tenure is None:
        return None
    teacher_character = tenure.character
    if teacher_character is None:
        return None
    if teacher_character.location != actor.location:
        return None
    return tenure


@dataclass
class TrainTechniqueAction(Action):
    """Run one training session against an in-progress ``TechniqueProgress`` meter.

    kwargs:
        technique_id: PK of the ``Technique`` being trained (required). Resolved
            against the learner's own ``TechniqueProgress`` meter — a technique
            with no meter fails cleanly, naming the front doors that create one
            (accepting a teaching offer, or an Academy TRAIN offer).
        ap_to_invest: AP to invest this session. Omitted defaults to
            ``_DEFAULT_AP_TO_INVEST``; a supplied value of 0 or less is rejected.
            The seam itself spends this AP in full and raises on pool/cap
            overruns — this action maps those raises to failure results rather
            than pre-bounding.
    """

    key: str = "train_technique"
    name: str = "Train Technique"
    icon: str = "book"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        technique_id: int,
        ap_to_invest: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Resolve the learner's meter, the co-present teacher (if any), and train.

        Returns:
            ``success=True`` with ``data`` describing the session outcome when the
            session resolves (including a botch — a botch still spends AP and
            still "succeeds" as a session). ``success=False`` with a player-safe
            ``message`` when there's no meter to train, AP is non-positive, the
            weekly cap is hit, the learner can't afford the AP, or the session
            would complete a meter for a technique the learner already knows
            (a stale meter left open after the technique arrived by another
            route, e.g. a staff grant or a TechniqueGrant item).
        """
        from world.magic.exceptions import MagicError, WeeklyTrainingCapExceeded  # noqa: PLC0415
        from world.magic.models import TechniqueProgress  # noqa: PLC0415
        from world.magic.services.technique_training import resolve_training_check  # noqa: PLC0415

        if ap_to_invest is None:
            ap_to_invest = _DEFAULT_AP_TO_INVEST
        elif ap_to_invest <= 0:
            return ActionResult(
                success=False,
                message="You must invest a positive amount of AP.",
            )

        learner = actor.sheet_data

        progress = (
            TechniqueProgress.objects.filter(
                character_sheet=learner,
                technique_id=technique_id,
            )
            .select_related("technique", "teacher_tenure")
            .first()
        )
        if progress is None:
            return ActionResult(
                success=False,
                message=(
                    "You aren't training that technique. Accept a teaching offer or "
                    "an Academy TRAIN offer to start a meter first."
                ),
            )

        teacher = _co_present_teacher(actor, progress)
        technique_name = progress.technique.name
        points_before = progress.points_accumulated
        total_required = progress.total_required

        try:
            result = resolve_training_check(
                learner,
                progress,
                ap_to_invest=ap_to_invest,
                teacher=teacher,
            )
        except (WeeklyTrainingCapExceeded, MagicError) as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValueError as exc:
            # learn_technique (the meter-completion mint, reached via
            # contribute_to_technique_progress) raises a bare ValueError when the
            # learner already holds the CharacterTechnique — reachable when a meter
            # is left open and the technique arrives by another route (a staff
            # grant, a TechniqueGrant item). Map it to a clean failure instead of
            # letting it escape as a traceback to telnet/web.
            return ActionResult(success=False, message=str(exc))
        except TechniqueProgress.DoesNotExist:
            # contribute_to_technique_progress re-gets the meter by pk under
            # select_for_update (technique_progress.py:132-138) so two concurrent
            # sessions serialize on the weekly-tracker lock rather than racing --
            # but if the first session's contribution completed (and deleted) the
            # meter while this one was blocked on the lock, the re-get raises this
            # instead of returning a stale row. Same message shape as the
            # already-knows failure above: training just finished, nothing left
            # to train.
            return ActionResult(
                success=False,
                message=(
                    f"Your training in {technique_name} just completed. "
                    "There's no meter left to train."
                ),
            )

        points_after = min(points_before + result.dev_points_contributed, total_required)

        if result.technique_acquired is not None:
            message = f"Your training pays off — you've learned {technique_name}!"
        else:
            message = (
                f"You train {technique_name} ({result.outcome_name}): "
                f"{points_after}/{total_required}."
            )

        return ActionResult(
            success=True,
            message=message,
            data={
                "technique_id": technique_id,
                "outcome_name": result.outcome_name,
                "points_before": points_before,
                "points_after": points_after,
                "total_required": total_required,
                "technique_acquired": result.technique_acquired is not None,
                "self_study": teacher is None,
            },
        )
