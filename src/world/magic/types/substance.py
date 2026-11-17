"""Types for calling up a gift's substance (#5018, #5125): the plan a call-up reads and what it did.

A plan is a pure read: the cast card, the cast's charge, the power lines and the no-technique
call-up all read the same plan, so what a player is shown is what she pays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.magic.models import Gift, Substance
    from world.magic.types.primum import SourcePoints


class SubstanceBlock:
    """Why a plan calls nothing up although she asked to raise the place. Never a refusal."""

    NONE = ""
    #: The place has no room profile to hold a call-up.
    NO_PLACE = "no_place"
    #: The place already holds her substance at the top step; nothing more can be called up.
    AT_TOP = "at_top"


class SurroundingsKind:
    """The kinds of line a cast card shows about where she stands (``SurroundingsLine``)."""

    POWER = "power"
    #: "Fire around you" above the source lines (text only).
    HEADING = "heading"
    #: One source of Primum with its signed points in ``amount``.
    SOURCE = "source"
    CALL_UP = "call_up"
    BLOCKED = "blocked"
    NEEDS = "needs"


class MarkOutcome:
    """What a GM's mark did (``mark_substance_present``)."""

    MARKED = "marked"
    ALREADY = "already"
    REMOVED = "removed"
    NO_PLACE = "no_place"


@dataclass(frozen=True)
class SubstancePlan:
    """What calling up a gift's substance in one room would take and do (#5125).

    ``substance`` is ``None`` for an empty plan: the gift has no substance, the caster has no
    GIFT thread on it, or she stands nowhere. An empty plan changes nothing. ``lines`` are the
    cast's Primum sources with any call-up already counted in the place.
    """

    substance: Substance | None = None
    gift: Gift | None = None
    thread_level: int = 0
    room: ObjectDB | None = None
    room_profile: RoomProfile | None = None
    #: The Primum of her substance in the place now, before any call-up.
    current_amount: int = 0
    #: The Primum the call-up adds (0 when nothing is called up).
    call_up_amount: int = 0
    blocked: str = SubstanceBlock.NONE
    #: Anima the call-up adds before control is taken off (0 when nothing is called up).
    call_up_anima: int = 0
    #: How much of ``call_up_anima`` her spare control covers.
    covered_anima: int = 0
    #: Percent the place's own magic moves the cost: negative cheaper, positive dearer.
    place_shift_pct: int = 0
    lines: tuple[SourcePoints, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.substance is None

    @property
    def calls_up(self) -> bool:
        """True when this plan raises the place (and costs what it says)."""
        return self.call_up_amount > 0 and not self.blocked

    @property
    def already_present(self) -> bool:
        """She has her substance here already and the plan raises nothing."""
        return not self.is_empty and not self.blocked and self.call_up_amount == 0

    @property
    def uncovered_anima(self) -> int:
        return max(self.call_up_anima - self.covered_anima, 0)

    @property
    def label(self) -> str:
        return self.substance.name if self.substance is not None else ""


@dataclass(frozen=True)
class SubstanceCallUp:
    """What a call-up actually spent and did, for result lines (#5018, #5125)."""

    label: str
    anima: int
    room_changed: bool
    #: Why nothing was called up although she asked (``SubstanceBlock``); blank when it was.
    blocked: str = ""


@dataclass(frozen=True)
class SurroundingsLine:
    """One line the cast card shows under its cost (#5018, #5125).

    ``kind``: ``heading`` (text only), ``source`` (signed points in ``amount``), ``power``
    (signed power in ``amount``: the total, or a lone unperceived opposing source),
    ``call_up`` (``anima``; 0 means control covers it), ``blocked``, or ``needs`` (a
    technique's unmet surroundings restriction).
    """

    kind: str
    text: str
    amount: int = 0
    anima: int = 0
    #: The right-hand cost for a call-up line ("free, your control covers it", "3 anima");
    #: blank for the other kinds.
    detail: str = ""


@dataclass(frozen=True)
class CallUpOffer:
    """One gift she can call up the substance of with no technique, priced now (#5018).

    ``effective_cost`` is what she would be charged (her own control taken off, and capped
    at her anima in a non-lethal fight). Never a gate: an offer is shown and pressable
    whatever her anima.
    """

    plan: SubstancePlan
    effective_cost: int
    #: Her anima now, for the row's "Anima: 18 · after: 15" line.
    current_anima: int = 0

    @property
    def anima_after(self) -> int:
        if not self.plan.calls_up:
            return self.current_anima
        return max(self.current_anima - self.effective_cost, 0)

    @property
    def balance_line(self) -> str:
        """ "Anima: 18 · after: 15"."""
        return f"Anima: {self.current_anima} · after: {self.anima_after}"

    @property
    def gift_id(self) -> int:
        return self.plan.gift.pk if self.plan.gift is not None else 0

    @property
    def cost_line(self) -> str:
        if self.plan.blocked == SubstanceBlock.AT_TOP:
            return f"no more {self.plan.label} can be called up here"
        if self.plan.blocked == SubstanceBlock.NO_PLACE:
            return "this place cannot hold it"
        if not self.plan.calls_up:
            return f"{self.plan.label} is already here"
        if self.effective_cost == 0:
            return "free, your control covers it"
        return f"{self.effective_cost} anima"
