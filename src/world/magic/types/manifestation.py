"""The technique picker's read model (#4341): what each manifesting technique a character
knows can bring into a fight, and whether its bond holds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.companions.models import Companion
    from world.magic.models import Technique, TechniqueManifestOption


@dataclass(frozen=True)
class ManifestOptionChoice:
    """One option on the picker.

    ``label`` is what the player reads ("Hesk (your patron)", "Fang (your Wolf)").
    ``available`` is whether the bond holds now; ``reason`` says why not when it does
    not. ``companion`` is the companion an archetype option would bring.
    """

    option: TechniqueManifestOption
    label: str
    available: bool
    reason: str = ""
    companion: Companion | None = None


@dataclass(frozen=True)
class ManifestChoice:
    """One manifesting technique the character knows, its options and the current pick."""

    technique: Technique
    technique_name: str
    options: tuple[ManifestOptionChoice, ...]
    chosen: TechniqueManifestOption | None = None
    chosen_companion: Companion | None = None
