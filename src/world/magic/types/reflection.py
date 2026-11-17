"""Reflection result types (#5124): what a "Reflecting on" row can name, and what it named."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.magic.constants import ReflectionTargetKind

if TYPE_CHECKING:
    from world.magic.models import Resonance, ResonanceGrant
    from world.relationships.models import CharacterRelationship


@dataclass(frozen=True)
class ReflectableDeed:
    """One kindled deed the character has not reflected on, with the line a player reads."""

    grant: ResonanceGrant
    label: str


@dataclass(frozen=True)
class ReflectableBurden:
    """The Mire a Sineater carries for one Sinner, as a thing to reflect on (#5177).

    ``tether`` is the Sineater's own side toward the Sinner; ``label`` is the line a player
    reads; ``has_waiting`` is true when a reflection on this burden already waits.
    """

    tether: CharacterRelationship
    label: str
    has_waiting: bool = False


@dataclass(frozen=True)
class ReflectionOption:
    """One entry of the "Reflecting on" row: a deed, the unsettling resonance or a burden.

    ``id`` is the grant's id for a deed, the resonance's id for the unsettling resonance and
    the Sineater's relationship side's id for a burden. ``replaces_waiting`` is true when a
    reflection on this resonance or burden is already waiting, so posting a new one replaces
    it; a deed never replaces anything.
    """

    kind: ReflectionTargetKind
    id: int
    label: str
    replaces_waiting: bool = False


@dataclass(frozen=True)
class Reflectable:
    """What a character can reflect on now: unreflected deeds (kindled, or succumbing to the
    Mire), newest first, the resonance unsettling them (None when they are settled), and the
    Mire they carry for each Sinner (#5177).

    ``unsettling_has_waiting`` is true when a reflection on that resonance already waits.
    """

    deeds: tuple[ReflectableDeed, ...]
    unsettling: Resonance | None
    unsettling_has_waiting: bool = False
    burdens: tuple[ReflectableBurden, ...] = ()

    @property
    def options(self) -> tuple[ReflectionOption, ...]:
        """The "Reflecting on" row's entries: the deeds (newest first), then the unsettling
        resonance, then the burdens, the order Screen 5 draws them in."""
        rows = [
            ReflectionOption(kind=ReflectionTargetKind.DEED, id=deed.grant.pk, label=deed.label)
            for deed in self.deeds
        ]
        if self.unsettling is not None:
            rows.append(
                ReflectionOption(
                    kind=ReflectionTargetKind.RESONANCE,
                    id=self.unsettling.pk,
                    label=unsettling_label(self.unsettling),
                    replaces_waiting=self.unsettling_has_waiting,
                )
            )
        rows.extend(
            ReflectionOption(
                kind=ReflectionTargetKind.BURDEN,
                id=burden.tether.pk,
                label=burden.label,
                replaces_waiting=burden.has_waiting,
            )
            for burden in self.burdens
        )
        return tuple(rows)


@dataclass(frozen=True)
class ReflectionTarget:
    """What one reflection names: exactly one of a deed's grant, a resonance, or the
    Sineater's side of a tether whose Mire is the burden."""

    grant: ResonanceGrant | None = None
    resonance: Resonance | None = None
    tether: CharacterRelationship | None = None

    @property
    def kind(self) -> ReflectionTargetKind:
        """Which kind of thing this names."""
        if self.grant is not None:
            return ReflectionTargetKind.DEED
        if self.tether is not None:
            return ReflectionTargetKind.BURDEN
        return ReflectionTargetKind.RESONANCE


@dataclass(frozen=True)
class PendingReflection:
    """A reflection a pose or entry asked for, checked and ready to record once it is posted."""

    target: ReflectionTarget
    choice: str


def unsettling_label(resonance: Resonance) -> str:
    """The player's line for the unsettling resonance."""
    return f"Your {resonance.name} · unsettling you"


def burden_label(sinner_name: str) -> str:
    """The player's line for the Mire a Sineater carries for one Sinner (#5177)."""
    return f"The Mire you carry for {sinner_name}"
