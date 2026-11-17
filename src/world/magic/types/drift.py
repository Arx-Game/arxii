"""Drift types: the unsettled reading and focus check (#4732, #5123); correction (#4733)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.constants import ComponentMode
    from world.magic.models import Affinity
    from world.magic.models.affinity import Resonance


@dataclass(frozen=True)
class DriftReading:
    """Whether a character is unsettled: affinities grown past who they are (#5123).

    Read on the true aura. ``shares`` is each affinity's percent of the character's
    lifetime resonance; ``settled_shares`` is who they are, per affinity. ``main_affinity``
    is the largest settled share. ``excess_percent`` is how far the non-main affinities
    stand past their settled shares plus the range before Unsettled; ``steps_past`` is how
    many ``unsettled_step_percent`` bands that is (0 when settled). ``leading_excess_resonance``
    is the resonance contributing most to the excess. ``main_affinity`` is None, and every
    number 0, when she has no settled aura to measure against. ``excess_points`` is the
    excess per affinity pk in lifetime points, which is what atoning may convert.
    """

    steps_past: int
    main_affinity: Affinity | None
    leading_excess_resonance: Resonance | None
    excess_percent: Decimal
    shares: dict[int, Decimal]
    settled_shares: dict[int, Decimal]
    excess_points: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AcceptAuraResult:
    """What accepting the changes to the aura did.

    ``settled_shares`` is who they are now, per affinity pk. ``grown_affinity`` is the
    affinity they grew toward: the affinity of the resonance that made them unsettled, read
    before accepting. It is what "You become more ..." names.
    """

    main_affinity: Affinity | None
    grown_affinity: Affinity | None
    settled_shares: dict[int, Decimal]


@dataclass(frozen=True)
class FocusOutcome:
    """The result of one focus check against being unsettled.

    ``steps`` is the severity the check was rolled at; ``applied_severity`` is the
    severity added to the conflict condition (0 when she kept her focus). ``lines`` are the
    sentences the player is told, in order: telnet prints them as they happen and the web
    cast result carries them, so the wording lives in one place.
    """

    success_level: int
    steps: int
    applied_severity: int
    lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualifyingComponent:
    """An item that counts toward a target-resonance ritual component, and the route it took."""

    item: ItemInstance
    mode: ComponentMode


@dataclass(frozen=True)
class ReflectionEffect:
    """What the rite of settling did for one reflection, as the line its writer is told."""

    reflection_id: int
    line: str


@dataclass(frozen=True)
class RiteNotice:
    """A line the rite tells another character privately (#5177): a Sinner learns that their
    Sineater succumbed or fell, and what it paid them. Sent by the action once the rite has
    committed, never from inside it."""

    sheet: CharacterSheet
    line: str


@dataclass(frozen=True)
class SettlingRiteResult:
    """The outcome of one rite of settling (#5124).

    ``share`` is the fraction of each reflection the rite carried out, from the rolled
    tier's ``DriftCorrectionOutcomeShare``. ``effects`` holds one entry per reflection the
    rite took, in the order it applied them. ``notices`` are the private lines for other
    characters (#5177).
    """

    outcome_name: str
    success_level: int
    share: Decimal
    focus_bonus: int
    effects: tuple[ReflectionEffect, ...]
    notices: tuple[RiteNotice, ...] = ()

    @property
    def lines(self) -> tuple[str, ...]:
        """The sentences the performer is told: the roll, then one per reflection."""
        return tuple(effect.line for effect in self.effects)


@dataclass(frozen=True)
class RiteOffering:
    """A carried item that can be the rite's offering, and the resonance it is offered for.

    ``focus_bonus`` is what the performer's worn focus adds to the roll toward that resonance.
    """

    component: QualifyingComponent
    resonance: Resonance
    focus_bonus: int


@dataclass(frozen=True)
class ReflectionReading:
    """One waiting reflection as the sheet's aura card and the rite dialog show it.

    ``kind`` is ``deed``, ``resonance`` or ``burden`` (the Mire a Sineater carries for one
    Sinner, #5177); ``title`` is "Embrace <what>", "Disown <what>", "Absolve the Mire you carry
    for <Sinner>", "Condemn ..." or "Succumb to ..."; ``where`` names the writing that carries
    it for the sheet's list (a journal entry's title, or the scene a pose was in) and
    ``from_line`` says the same as the rite dialog's "from ..." clause; ``excerpt`` is the start
    of that writing. All three are blank when the writing is gone. ``effect_line`` says what
    the rite will do at a full share.
    """

    id: int
    choice: str
    kind: str
    title: str
    where: str
    from_line: str
    excerpt: str
    effect_line: str


@dataclass(frozen=True)
class SettlingRiteReading:
    """What the rite of settling would take and what it asks for, read for one character."""

    reflections: tuple[ReflectionReading, ...]
    offerings: tuple[RiteOffering, ...]
    rite_ready: bool
    not_ready_message: str
    check_name: str
