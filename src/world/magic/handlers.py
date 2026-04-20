"""Per-character handlers for the resonance/thread surface (Spec A §3.7).

These handlers wire onto the ``Character`` typeclass alongside the established
``character.traits`` etc. handlers. They cache per-character data via
``functools.cached_property`` and rely on service functions to call
``.invalidate()`` after mutation.
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from world.magic.models import CharacterResonance, Thread

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.magic.models import Resonance


class CharacterThreadHandler:
    """Handler for a character's owned threads (Spec A §3.7).

    Cached list of all threads owned by the character's CharacterSheet, with
    select_related on the resonance + each typed-FK target column so anchor
    walks don't fire follow-up queries.
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _all(self) -> list[Thread]:
        sheet = self.character.sheet_data
        return list(
            Thread.objects.filter(owner=sheet).select_related(
                "resonance__affinity",
                "target_trait",
                "target_technique",
                "target_object",
                "target_relationship_track",
                "target_capstone",
            )
        )

    def all(self) -> list[Thread]:
        """Return all threads owned by this character."""
        return self._all

    def by_resonance(self, resonance: Resonance) -> list[Thread]:
        """Return threads filtered to a single resonance."""
        return [t for t in self._all if t.resonance_id == resonance.pk]

    def with_anchor_involved(self, action_context: object) -> list[Thread]:
        """Return threads whose anchor is in scope for the given action.

        Spec §3.7 lines 974–976. Implementation is deferred to Phase 13's
        VITAL_BONUS routing work, which lands the action-context plumbing
        needed to decide "anchor in scope" outside the pull pipeline.
        """
        msg = "Phase 13: with_anchor_involved awaits VITAL_BONUS routing."
        raise NotImplementedError(msg)

    def passive_vital_bonuses(self, vital_target: str) -> int:
        """Sum tier-0 VITAL_BONUS scaled values across in-scope threads.

        Spec §3.7 lines 977–979. Implementation is deferred to Phase 13,
        which adds passive VITAL_BONUS aggregation alongside max-health
        recompute.
        """
        msg = "Phase 13: passive_vital_bonuses awaits VITAL_BONUS routing."
        raise NotImplementedError(msg)

    def invalidate(self) -> None:
        """Clear the cached thread list. Called by mutation services."""
        self.__dict__.pop("_all", None)


class CharacterResonanceHandler:
    """Handler for a character's CharacterResonance rows (Spec A §3.7).

    Cached ``{resonance_pk: CharacterResonance}`` dict for O(1) balance and
    lifetime lookups. Empty dict when the character has earned no resonances.
    """

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _by_resonance(self) -> dict[int, CharacterResonance]:
        sheet = self.character.sheet_data
        return {
            cr.resonance_id: cr
            for cr in CharacterResonance.objects.filter(character_sheet=sheet).select_related(
                "resonance__affinity"
            )
        }

    def all(self) -> list[CharacterResonance]:
        """Return all CharacterResonance rows for this character."""
        return list(self._by_resonance.values())

    def balance(self, resonance: Resonance) -> int:
        """Return the spendable balance for ``resonance``; 0 if no row exists."""
        cr = self._by_resonance.get(resonance.pk)
        return cr.balance if cr else 0

    def lifetime(self, resonance: Resonance) -> int:
        """Return the lifetime_earned value for ``resonance``; 0 if no row exists."""
        cr = self._by_resonance.get(resonance.pk)
        return cr.lifetime_earned if cr else 0

    def get_or_create(self, resonance: Resonance) -> CharacterResonance:
        """Return the CharacterResonance row, creating it lazily if absent."""
        cr = self._by_resonance.get(resonance.pk)
        if cr is None:
            cr, _ = CharacterResonance.objects.get_or_create(
                character_sheet=self.character.sheet_data,
                resonance=resonance,
                defaults={"balance": 0, "lifetime_earned": 0},
            )
            self._by_resonance[resonance.pk] = cr
        return cr

    def most_recently_earned(self) -> CharacterResonance | None:
        """Return the row with the highest lifetime_earned; ties broken by ``-pk``.

        Used by Mage Scars (`_apply_magical_scars`) to derive origin
        affinity / resonance from the character's magical history. Returns
        ``None`` when the character has earned no resonances yet.
        """
        rows = list(self._by_resonance.values())
        if not rows:
            return None
        return max(rows, key=lambda cr: (cr.lifetime_earned, cr.pk))

    def invalidate(self) -> None:
        """Clear the cached resonance dict. Called by mutation services."""
        self.__dict__.pop("_by_resonance", None)
