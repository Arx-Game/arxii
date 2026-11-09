"""Types for a gift's substance (#5018): the plan a call-up reads and what it spent.

A plan is a pure read: the cast card, the cast's charge, the power line and the
no-technique call-up all read the same plan, so what a player is shown is what she pays.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.magic.models import Gift, GiftSubstance, Resonance


class SubstanceBlock:
    """Why a plan with steps still to go does not call anything up. Never a refusal."""

    NONE = ""
    #: A warded sanctum (or any fixed setting) holds the reading; nothing can move it.
    HELD_FIXED = "held_fixed"
    #: The place has no room profile to write a row on.
    NO_PLACE = "no_place"
    #: Her balance in her gift thread's resonance cannot pay the uncovered share.
    TOO_LITTLE_RESONANCE = "too_little_resonance"


class SurroundingsKind:
    """The kinds of line a cast card shows about where she stands (``SurroundingsLine``)."""

    POWER = "power"
    CALL_UP = "call_up"
    BLOCKED = "blocked"
    NEEDS = "needs"


class MarkOutcome:
    """What a GM's mark did (``mark_substance_present``)."""

    MARKED = "marked"
    ALREADY = "already"
    REMOVED = "removed"
    HELD_FIXED = "held_fixed"
    NO_PLACE = "no_place"


@dataclass(frozen=True)
class SubstancePlan:
    """What calling up a gift's substance in one room would take and do (#5018).

    ``substance`` is ``None`` for an empty plan: the gift has no substance, the caster
    has no GIFT thread on it, or she stands nowhere. An empty plan changes nothing.
    """

    substance: GiftSubstance | None = None
    gift: Gift | None = None
    thread_level: int = 0
    resonance: Resonance | None = None
    room: ObjectDB | None = None
    room_profile: RoomProfile | None = None
    #: Steps the room still needs, in her direction, to count as present.
    steps_needed: int = 0
    #: Steps the call-up actually moves the reading (0 when blocked or not needed).
    steps_moved: int = 0
    #: Her own row's new value (the full row, not a delta); meaningful when steps_moved.
    row_value: int = 0
    blocked: str = SubstanceBlock.NONE
    #: Anima the call-up adds before control is taken off.
    call_up_anima: int = 0
    #: How much of ``call_up_anima`` her spare control covers.
    covered_anima: int = 0
    resonance_cost: int = 0
    #: Percent the place's own magic moves the cost: negative cheaper, positive dearer.
    place_shift_pct: int = 0
    richness_before: Decimal = Decimal(0)
    richness_after: Decimal = Decimal(0)

    @property
    def is_empty(self) -> bool:
        return self.substance is None

    @property
    def calls_up(self) -> bool:
        """True when this plan moves the room (and costs what it says)."""
        return self.steps_moved > 0

    @property
    def already_present(self) -> bool:
        return not self.is_empty and self.steps_needed == 0

    @property
    def uncovered_anima(self) -> int:
        return max(self.call_up_anima - self.covered_anima, 0)

    @property
    def label(self) -> str:
        return self.substance.label if self.substance is not None else ""


@dataclass(frozen=True)
class SubstanceCallUp:
    """What a call-up actually spent and did, for result lines (#5018)."""

    label: str
    anima: int
    resonance: int
    resonance_name: str
    room_changed: bool
    #: Why nothing was called up although the room lacked it (``SubstanceBlock``), so the
    #: result can say "no resonance left to call up shadow"; blank when it was called up.
    blocked: str = ""


@dataclass(frozen=True)
class SurroundingsLine:
    """One line the cast card shows under its cost (#5018).

    ``kind``: ``power`` (signed ``amount``), ``call_up`` (``anima`` and ``resonance``;
    both 0 means control covers it), ``blocked`` (too little resonance, a fixed room),
    or ``needs`` (a technique's unmet surroundings restriction).
    """

    kind: str
    text: str
    amount: int = 0
    anima: int = 0
    resonance: int = 0
    #: The right-hand cost for a call-up line ("free, your control covers it", "3 anima,
    #: 1 Umbral resonance"); blank for the other kinds.
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
    #: Her anima now, and her balance in the gift's resonance now, for the row's
    #: "Anima: 18 · after: 18" line.
    current_anima: int = 0
    resonance_balance: int = 0

    @property
    def anima_after(self) -> int:
        return (
            max(self.current_anima - self.effective_cost, 0)
            if self.plan.calls_up
            else (self.current_anima)
        )

    @property
    def resonance_after(self) -> int:
        if not self.plan.calls_up:
            return self.resonance_balance
        return max(self.resonance_balance - self.plan.resonance_cost, 0)

    @property
    def balance_line(self) -> str:
        """ "Anima: 18 · after: 18 · Umbral resonance after: unchanged"."""
        name = self.plan.resonance.name if self.plan.resonance is not None else "gift"
        after = (
            "unchanged"
            if self.resonance_after == self.resonance_balance
            else str(self.resonance_after)
        )
        return (
            f"Anima: {self.current_anima} · after: {self.anima_after} · "
            f"{name} resonance after: {after}"
        )

    @property
    def gift_id(self) -> int:
        return self.plan.gift.pk if self.plan.gift is not None else 0

    @property
    def cost_line(self) -> str:
        if self.plan.already_present:
            return f"{self.plan.label} is already here"
        if not self.plan.calls_up:
            if self.plan.blocked == SubstanceBlock.TOO_LITTLE_RESONANCE:
                return "too little of your resonance"
            return "this place is held fixed"
        if self.effective_cost == 0 and self.plan.resonance_cost == 0:
            return "free, your control covers it"
        resonance = self.plan.resonance.name if self.plan.resonance is not None else ""
        parts = [f"{self.effective_cost} anima"]
        if self.plan.resonance_cost:
            parts.append(f"{self.plan.resonance_cost} {resonance} resonance")
        return ", ".join(parts)
