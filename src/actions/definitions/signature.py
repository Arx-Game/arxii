"""Signature-bonus selection actions — set/clear/list (#1582).

Three REGISTRY actions share the ``signature`` namespace:

- ``SignatureSetAction``  — attach a :class:`SignatureMotifBonus` to a
  TECHNIQUE-kind Thread (calls ``set_signature_bonus``).
- ``SignatureClearAction`` — remove the current bonus from a TECHNIQUE-kind
  Thread (calls ``clear_signature_bonus``).
- ``SignatureListAction`` — list available bonuses + per-thread current settings
  (calls ``available_signature_bonuses``).

Both telnet (``commands/signature.py`` via ``dispatch_player_action``) and the web
converge on ``action.run()``.  The set/clear actions receive already-resolved
``thread`` and ``bonus`` objects — each surface resolves them independently —
and delegate to the Task-4 service functions in
``world/magic/services/signature.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.magic.exceptions import (
    NotATechniqueThread,
    SignatureBonusNotAvailable,
    TechniqueNotOwned,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


_SIGNATURE_SET_EXCEPTIONS = (NotATechniqueThread, SignatureBonusNotAvailable, TechniqueNotOwned)
_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_OPERATION_FAILED = "Operation failed."


@dataclass
class SignatureActionBase(Action):
    """Shared base for the three signature verbs."""

    key: str = ""
    name: str = ""
    icon: str = ""
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def _sheet(self, actor: ObjectDB) -> Any:
        """Return the CharacterSheet for *actor*, or None."""
        try:
            return actor.sheet_data
        except AttributeError:
            return None

    @staticmethod
    def _fail(message: str) -> ActionResult:
        return ActionResult(success=False, message=message)


@dataclass
class SignatureSetAction(SignatureActionBase):
    """Attach a SignatureMotifBonus to a TECHNIQUE-kind Thread.

    Expects kwargs:
        thread: A TECHNIQUE-kind ``Thread`` belonging to the actor.
        bonus: The ``SignatureMotifBonus`` to attach.

    Catches ``NotATechniqueThread``, ``SignatureBonusNotAvailable``, and
    ``TechniqueNotOwned`` from the service and returns a failure ActionResult
    (the web view maps the message to HTTP 400).
    """

    key: str = "signature_set"
    name: str = "Set Signature Bonus"
    icon: str = "star"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.signature import set_signature_bonus  # noqa: PLC0415

        thread = kwargs["thread"]
        bonus = kwargs["bonus"]
        try:
            set_signature_bonus(thread, bonus)
        except _SIGNATURE_SET_EXCEPTIONS as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message=f"Signature bonus '{bonus.name}' set on {thread.name}.",
            data={"thread_id": thread.pk, "bonus_id": bonus.pk},
        )


@dataclass
class SignatureClearAction(SignatureActionBase):
    """Remove the current SignatureMotifBonus from a TECHNIQUE-kind Thread.

    Expects kwargs:
        thread: The ``Thread`` whose bonus should be cleared.

    ``clear_signature_bonus`` is idempotent — safe to call when no bonus is set.
    """

    key: str = "signature_clear"
    name: str = "Clear Signature Bonus"
    icon: str = "x"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.signature import clear_signature_bonus  # noqa: PLC0415

        thread = kwargs["thread"]
        clear_signature_bonus(thread)
        return ActionResult(
            success=True,
            message=f"Signature bonus cleared from {thread.name}.",
            data={"thread_id": thread.pk},
        )


@dataclass
class SignatureListAction(SignatureActionBase):
    """List available SignatureMotifBonuses and current per-technique-thread settings.

    Reads from the actor's cached ``threads`` handler (same pattern as
    ``signature_bonus_for``) so the read is always consistent with the cached state.
    """

    key: str = "signature_list"
    name: str = "List Signature Bonuses"
    icon: str = "list"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.services.signature import available_signature_bonuses  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)

        available = available_signature_bonuses(sheet)
        technique_threads = [
            t
            for t in actor.threads.all()
            if t.target_kind == TargetKind.TECHNIQUE and t.retired_at is None
        ]

        return ActionResult(
            success=True,
            message=_build_list_message(available, technique_threads),
            data={
                "available_bonus_ids": [b.pk for b in available],
                "technique_threads": [
                    {
                        "thread_id": t.pk,
                        "thread_name": t.name,
                        "technique_name": (t.target_technique.name if t.target_technique else ""),
                        "current_bonus": (t.signature_bonus.name if t.signature_bonus else None),
                    }
                    for t in technique_threads
                ],
            },
        )


def _build_list_message(available: list, technique_threads: list) -> str:
    """Compose the telnet listing for ``SignatureListAction``."""
    bonus_lines: list[str] = (
        ["  (none — check your Motif facets and resonances)"]
        if not available
        else [f"  {b.name}" for b in available]
    )
    thread_lines: list[str] = (
        ["  (no active technique threads)"]
        if not technique_threads
        else [
            f"  {t.target_technique.name if t.target_technique else 'unknown'}"
            f" — signature: {t.signature_bonus.name if t.signature_bonus else 'none'}"
            for t in technique_threads
        ]
    )
    sections = [
        "|wAvailable signature bonuses:|n",
        *bonus_lines,
        "",
        "|wTechnique threads:|n",
        *thread_lines,
    ]
    return "\n".join(sections)
