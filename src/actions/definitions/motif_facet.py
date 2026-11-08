"""Motif facet-binding actions: bind and unbind (#5021).

Two REGISTRY actions in the ``motif`` namespace beside the style-binding ones
(``motif_style.py``). Telnet (``commands/motif.py``) and the web (``MotifStyleViewSet``)
both converge on ``action.run()`` with already-resolved ``facet``/``resonance`` objects,
delegating to ``world/magic/services/motif_facet.py``. The listing is shared:
``ListMotifStylesAction`` lists styles and facets together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.definitions.motif_style import _MSG_NO_ACTIVE_CHARACTER, MotifStyleActionBase
from actions.types import ActionResult
from world.magic.exceptions import (
    FacetBindingCapExceeded,
    FacetNeededByFlourish,
    FacetNotBound,
    StyleResonanceUnclaimed,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class BindMotifFacetAction(MotifStyleActionBase):
    """Tie a Facet to one of the actor's claimed resonances.

    Expects kwargs: ``facet`` (Facet), ``resonance`` (Resonance).
    """

    key: str = "bind_motif_facet"
    name: str = "Bind Motif Facet"
    icon: str = "sparkles"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.motif_facet import bind_motif_facet  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        facet = kwargs["facet"]
        resonance = kwargs["resonance"]
        try:
            binding = bind_motif_facet(sheet, facet, resonance)
        except (StyleResonanceUnclaimed, FacetBindingCapExceeded) as exc:
            return self._fail(exc.user_message)
        return ActionResult(
            success=True,
            message=f"{facet.name} is now tied to your {resonance.name} resonance.",
            data={"binding_id": binding.pk, "facet_id": facet.pk, "resonance_id": resonance.pk},
        )


@dataclass
class UnbindMotifFacetAction(MotifStyleActionBase):
    """Remove the actor's tie of a Facet to a resonance.

    Expects kwargs: ``facet`` (Facet), ``resonance`` (Resonance).
    """

    key: str = "unbind_motif_facet"
    name: str = "Unbind Motif Facet"
    icon: str = "x"

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.services.motif_facet import unbind_motif_facet  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return self._fail(_MSG_NO_ACTIVE_CHARACTER)
        facet = kwargs["facet"]
        resonance = kwargs["resonance"]
        try:
            unbind_motif_facet(sheet, facet, resonance)
        except (FacetNotBound, FacetNeededByFlourish) as exc:
            return self._fail(exc.user_message)
        return ActionResult(
            success=True,
            message=f"{facet.name} is no longer tied to your {resonance.name} resonance.",
            data={"facet_id": facet.pk, "resonance_id": resonance.pk},
        )
