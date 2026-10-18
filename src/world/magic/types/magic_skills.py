"""Result type for resolving a magical roll's check type plus its skill terms (#4450)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.checks.types import ExtraTraitTerm


@dataclass(frozen=True)
class CastCheck:
    """What a technique cast rolls: the check type and the skill terms added to it.

    ``check_type`` follows the cast precedence (the caster's personal magic check,
    else the technique's action template check). ``extra_traits`` is passed straight to
    the check engine's ``extra_traits`` argument; it is empty when no skill is mapped.
    """

    check_type: CheckType
    extra_traits: tuple[ExtraTraitTerm, ...]
