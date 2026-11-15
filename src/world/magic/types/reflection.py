"""Reflection result types (#5124): what a "Reflecting on" row can name, and what it named."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.magic.constants import ReflectionTargetKind

if TYPE_CHECKING:
    from world.magic.models import Resonance, ResonanceGrant


@dataclass(frozen=True)
class ReflectableDeed:
    """One kindled deed the character has not reflected on, with the line a player reads."""

    grant: ResonanceGrant
    label: str


@dataclass(frozen=True)
class ReflectionOption:
    """One entry of the "Reflecting on" row: a deed or the unsettling resonance.

    ``id`` is the grant's id for a deed and the resonance's id for the unsettling resonance.
    ``replaces_waiting`` is true when a reflection on this resonance is already waiting, so
    posting a new one replaces it; a deed never replaces anything.
    """

    kind: ReflectionTargetKind
    id: int
    label: str
    replaces_waiting: bool = False


@dataclass(frozen=True)
class Reflectable:
    """What a character can reflect on now: unreflected kindled deeds, newest first, and the
    resonance unsettling them (None when they are settled).

    ``unsettling_has_waiting`` is true when a reflection on that resonance already waits.
    """

    deeds: tuple[ReflectableDeed, ...]
    unsettling: Resonance | None
    unsettling_has_waiting: bool = False

    @property
    def options(self) -> tuple[ReflectionOption, ...]:
        """The "Reflecting on" row's entries: the unsettling resonance first, then the deeds."""
        rows: list[ReflectionOption] = []
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
            ReflectionOption(kind=ReflectionTargetKind.DEED, id=deed.grant.pk, label=deed.label)
            for deed in self.deeds
        )
        return tuple(rows)


@dataclass(frozen=True)
class ReflectionTarget:
    """What one reflection names: exactly one of a deed's grant or a resonance."""

    grant: ResonanceGrant | None = None
    resonance: Resonance | None = None


@dataclass(frozen=True)
class PendingReflection:
    """A reflection a pose or entry asked for, checked and ready to record once it is posted."""

    target: ReflectionTarget
    choice: str


def unsettling_label(resonance: Resonance) -> str:
    """The player's line for the unsettling resonance."""
    return f"Your {resonance.name} · unsettling you"
