"""Motif style-binding actions — bind/unbind/list (#2030).

Three REGISTRY actions share the ``motif`` namespace. Both telnet
(``commands/motif.py``) and the web (``MotifStyleViewSet``) converge on
``action.run()`` with already-resolved ``style``/``resonance`` objects,
delegating to ``world/magic/services/motif_style.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.magic.exceptions import (
    StyleBindingCapExceeded,
    StyleNotBound,
    StyleResonanceUnclaimed,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

_BIND_EXCEPTIONS = (StyleResonanceUnclaimed, StyleBindingCapExceeded)
_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_OPERATION_FAILED = "Operation failed."


@dataclass
class MotifStyleActionBase(Action):
    """Shared base for the three motif style-binding verbs."""

    key: str = ""
    name: str = ""
    icon: str = ""
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def _sheet(self, actor: ObjectDB) -> Any:
        try:
            return actor.sheet_data
        except AttributeError:
            return None

    @staticmethod
    def _fail(message: str) -> ActionResult:
        return ActionResult(success=False, message=message)


@dataclass
class BindMotifStyleAction(MotifStyleActionBase):
    """Bind a Style to one of the actor's claimed resonances.

    Expects kwargs: ``style`` (Style), ``resonance`` (Resonance).
    """

    key: str = "bind_motif_style"
    name: str = "Bind Motif Style"
    icon: str = "sparkles"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.motif_style import bind_motif_style  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        style = kwargs["style"]
        resonance = kwargs["resonance"]
        try:
            binding = bind_motif_style(sheet, style, resonance)
        except _BIND_EXCEPTIONS as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message=f"'{style.name}' is now bound to your {resonance.name} resonance.",
            data={"binding_id": binding.pk, "style_id": style.pk, "resonance_id": resonance.pk},
        )


@dataclass
class UnbindMotifStyleAction(MotifStyleActionBase):
    """Remove the actor's binding of a Style. Expects kwarg: ``style``."""

    key: str = "unbind_motif_style"
    name: str = "Unbind Motif Style"
    icon: str = "x"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.motif_style import unbind_motif_style  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        style = kwargs["style"]
        try:
            unbind_motif_style(sheet, style)
        except StyleNotBound as exc:
            return self._fail(getattr(exc, "user_message", _MSG_OPERATION_FAILED))  # noqa: GETATTR_LITERAL
        return ActionResult(
            success=True,
            message=f"'{style.name}' is no longer bound.",
            data={"style_id": style.pk},
        )


@dataclass
class ListMotifStylesAction(MotifStyleActionBase):
    """List the actor's style bindings."""

    key: str = "list_motif_styles"
    name: str = "List Motif Styles"
    icon: str = "list"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.motif_style import motif_style_bindings  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        bindings = motif_style_bindings(sheet)
        data = {
            "bindings": [
                {
                    "style_id": b.style_id,
                    "style_name": b.style.name,
                    "audacity": b.style.get_audacity_display(),
                    "resonance_id": b.motif_resonance.resonance_id,
                    "resonance_name": b.motif_resonance.resonance.name,
                }
                for b in bindings
            ]
        }
        return ActionResult(success=True, message=_build_list_message(bindings), data=data)


def _build_list_message(bindings: list) -> str:
    """Compose the telnet listing for ``ListMotifStylesAction``."""
    if not bindings:
        return "You have no styles bound. Use 'motif bindstyle <style>=<resonance>'."
    lines = ["|wYour style bindings:|n"]
    lines.extend(
        f"  {b.style.name} ({b.style.get_audacity_display()}) → {b.motif_resonance.resonance.name}"
        for b in bindings
    )
    return "\n".join(lines)
