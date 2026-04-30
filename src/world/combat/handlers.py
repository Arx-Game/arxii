"""Per-character combat-pull handler (Spec A §3.7).

Wires onto the ``Character`` typeclass alongside ``character.threads``.
A `CombatPull` row is "active" while its ``round_number`` matches its
encounter's current ``round_number``; ``expire_pulls_for_round`` (Phase 13)
deletes stale rows on round advance, but the comparison is the canonical
liveness check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import F, Prefetch
from django.utils.functional import cached_property

from world.combat.models import CombatPull, CombatPullResolvedEffect
from world.magic.constants import EffectKind

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.combat.models import CombatEncounter


class CharacterCombatPullHandler:
    """Handler for a character's currently-active CombatPull rows."""

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _active(self) -> list[CombatPull]:
        sheet = self.character.sheet_data
        return list(
            CombatPull.objects.filter(
                participant__character_sheet=sheet,
                round_number=F("encounter__round_number"),
            )
            .select_related("encounter", "participant", "resonance")
            .prefetch_related(
                Prefetch(
                    "resolved_effects",
                    queryset=CombatPullResolvedEffect.objects.select_related(
                        "source_thread",
                        "granted_capability",
                    ),
                    to_attr="resolved_effects_cached",
                ),
            )
        )

    def active(self) -> list[CombatPull]:
        """Return all currently-active pulls across all encounters."""
        return self._active

    def active_for_encounter(self, encounter: CombatEncounter) -> list[CombatPull]:
        """Narrow the active set to a specific encounter."""
        return [p for p in self._active if p.encounter_id == encounter.pk]

    def active_pull_vital_bonuses(self, vital_target: str) -> int:
        """Sum scaled VITAL_BONUS values across active pulls for one target.

        Used by ``recompute_max_health_with_threads`` and
        ``apply_damage_reduction_from_threads`` (both Phase 13). Filters by
        both effect kind and ``vital_target`` so MAX_HEALTH and
        DAMAGE_TAKEN_REDUCTION rows stay independent.
        """
        total = 0
        for pull in self._active:
            for eff in pull.resolved_effects_cached:
                if (
                    eff.kind == EffectKind.VITAL_BONUS
                    and eff.vital_target == vital_target
                    and eff.scaled_value
                ):
                    total += eff.scaled_value
        return total

    def invalidate(self) -> None:
        """Clear the cached active-pull list. Called by mutation services."""
        self.__dict__.pop("_active", None)
