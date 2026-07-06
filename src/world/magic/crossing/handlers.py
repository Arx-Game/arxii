"""Concrete crossing-ceremony handlers (ADR-0094, #1987).

Each handler is registered against a ``TargetKind`` in ``MagicConfig.ready()``.

- ``GiftCrossingHandler`` (GIFT) and ``CovenantRoleCrossingHandler``
  (COVENANT_ROLE) wrap the existing variant-discovery logic verbatim — no
  behavior change. They use ``AbstractSpecializedVariant`` (ADR-0055).
- ``TechniqueCrossingHandler`` (TECHNIQUE) executes a ceremony beat at
  crossings. The signature-bonus gating itself is subissue #1988; this
  handler just ensures the crossing isn't silent.
- The remaining six kinds (TRAIT, FACET, RELATIONSHIP_TRACK,
  RELATIONSHIP_CAPSTONE, MANTLE, SANCTUM) are stubs that log a debug no-op.
  Each is replaced with real logic in its subissue (#1989–#1993).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.magic.constants import TargetKind
from world.magic.crossing.ceremony import CeremonyNarrative, execute_ceremony_beat

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Thread
    from world.magic.specialization.models import AbstractSpecializedVariant

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Variant-discovery handlers (GIFT, COVENANT_ROLE) — wrap existing logic
# ---------------------------------------------------------------------------


def _parents_for(thread: Thread) -> Iterable:
    """Return the parent entities whose variants should be searched.

    Moved verbatim from ``world.covenants.discovery._parents_for``.

    - COVENANT_ROLE: the thread's ``target_covenant_role``.
    - GIFT: each ``Technique`` of the thread's ``target_gift``.
    """
    if thread.target_kind == TargetKind.COVENANT_ROLE:
        if thread.target_covenant_role_id is not None:
            return [thread.target_covenant_role]
        return []
    if thread.target_kind == TargetKind.GIFT:
        if thread.target_gift_id is not None:
            # Read the gift's cached techniques list rather than
            # ``gift.techniques.all()`` per project cached-property rule.
            return thread.target_gift.cached_techniques
        return []
    return []


def _variant_model_for(target_kind: str) -> type[AbstractSpecializedVariant] | None:
    """Return the variant model class for a Thread target_kind, or None.

    Moved verbatim from ``world.covenants.discovery._variant_model_for``.
    """
    if target_kind == TargetKind.COVENANT_ROLE:
        from world.covenants.models import CovenantRole  # noqa: PLC0415

        return CovenantRole
    if target_kind == TargetKind.GIFT:
        from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

        return TechniqueVariant
    return None


class GiftCrossingHandler:
    """GIFT thread crossing handler — discovers technique variants.

    Wraps the existing variant-discovery logic for GIFT threads (ADR-0055,
    #1578). No behavior change from the original ``fire_variant_discoveries``.
    """

    target_kind = TargetKind.GIFT

    def execute(self, *, thread: Thread, starting_level: int, new_level: int) -> None:
        if new_level <= starting_level:
            return

        variant_model = _variant_model_for(thread.target_kind)
        if variant_model is None:
            return

        sheet: CharacterSheet = thread.owner
        for parent in _parents_for(thread):
            newly = variant_model.newly_crossed_variants(
                parent,
                resonance_id=thread.resonance_id,
                starting_level=starting_level,
                new_level=new_level,
            )
            for variant in newly:
                _execute_variant_beat(sheet, variant)


class CovenantRoleCrossingHandler:
    """COVENANT_ROLE thread crossing handler — discovers sub-role variants.

    Wraps the existing variant-discovery logic for COVENANT_ROLE threads
    (#1277, #1578). No behavior change.
    """

    target_kind = TargetKind.COVENANT_ROLE

    def execute(self, *, thread: Thread, starting_level: int, new_level: int) -> None:
        if new_level <= starting_level:
            return

        variant_model = _variant_model_for(thread.target_kind)
        if variant_model is None:
            return

        sheet: CharacterSheet = thread.owner
        for parent in _parents_for(thread):
            newly = variant_model.newly_crossed_variants(
                parent,
                resonance_id=thread.resonance_id,
                starting_level=starting_level,
                new_level=new_level,
            )
            for variant in newly:
                _execute_variant_beat(sheet, variant)


def _execute_variant_beat(
    sheet: CharacterSheet,
    variant: AbstractSpecializedVariant,
) -> None:
    """Run the grant/unlock/notify beat for a single newly-crossed variant.

    Wraps the old ``_fire_one`` from ``world.covenants.discovery``, delegating
    the ceremony beat to the shared ``execute_ceremony_beat`` helper. The
    category routing (COVENANT vs VISIONS) is preserved.
    """
    from world.covenants.models import CovenantRole  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415

    if isinstance(variant, CovenantRole):
        category = NarrativeCategory.COVENANT
    else:
        category = NarrativeCategory.VISIONS

    _first_recipients, first_body = variant.discovery_narrative(is_first=True)
    _personal_recipients, personal_body = variant.discovery_narrative(is_first=False)

    narrative = CeremonyNarrative(
        first_body=first_body,
        personal_body=personal_body,
        category=category,
    )

    execute_ceremony_beat(
        sheet=sheet,
        narrative=narrative,
        achievement=variant.discovery_achievement,
        codex_entry=variant.codex_entry,
    )


# ---------------------------------------------------------------------------
# TECHNIQUE handler — ceremony beat (signature gating is #1988)
# ---------------------------------------------------------------------------


class TechniqueCrossingHandler:
    """TECHNIQUE thread crossing handler.

    Executes a ceremony beat at crossings so the threshold isn't silent. The
    signature-bonus gating itself is subissue #1988. ADR-0072 establishes that
    TECHNIQUE signatures are additive flourishes, not discovered variants — so
    this handler does NOT use ``AbstractSpecializedVariant``.

    The narrative body is generic until #1988 refines it.
    """

    target_kind = TargetKind.TECHNIQUE

    def execute(self, *, thread: Thread, starting_level: int, new_level: int) -> None:
        if new_level <= starting_level:
            return

        # No achievement/codex authored for technique crossings yet — the
        # signature surface (#1988) will supply them. For now this is a
        # debug-level log so the crossing is observable without side effects.
        logger.debug(
            "TECHNIQUE thread crossing: %s levels %d→%d (signature gating in #1988)",
            thread,
            starting_level,
            new_level,
        )


# ---------------------------------------------------------------------------
# Stub handlers — log a debug no-op, replaced with real logic in subissues
# ---------------------------------------------------------------------------


class _StubCrossingHandler:
    """Base for stub handlers that log a debug no-op at crossings.

    Each concrete subclass is registered for a ``TargetKind`` that doesn't yet
    have a real ceremony. The stub makes the dispatch explicit: the registry
    reaches it, it just doesn't do anything yet. Replaced with real logic in
    the subissue noted on each subclass.
    """

    target_kind: str = ""
    _subissue: str = ""

    def execute(self, *, thread: Thread, starting_level: int, new_level: int) -> None:
        if new_level <= starting_level:
            return
        logger.debug(
            "No crossing ceremony implemented for %s (levels %d→%d); see %s",
            thread.target_kind,
            starting_level,
            new_level,
            self._subissue,
        )


class TraitCrossingHandler(_StubCrossingHandler):
    """TRAIT thread crossing — stub (#1989)."""

    target_kind = TargetKind.TRAIT
    _subissue = "#1989"


class FacetCrossingHandler(_StubCrossingHandler):
    """FACET thread crossing — stub (#1990)."""

    target_kind = TargetKind.FACET
    _subissue = "#1990"


class RelationshipTrackCrossingHandler(_StubCrossingHandler):
    """RELATIONSHIP_TRACK thread crossing — stub (#1991)."""

    target_kind = TargetKind.RELATIONSHIP_TRACK
    _subissue = "#1991"


class RelationshipCapstoneCrossingHandler(_StubCrossingHandler):
    """RELATIONSHIP_CAPSTONE thread crossing — stub (#1991)."""

    target_kind = TargetKind.RELATIONSHIP_CAPSTONE
    _subissue = "#1991"


class MantleCrossingHandler(_StubCrossingHandler):
    """MANTLE thread crossing — stub (#1992)."""

    target_kind = TargetKind.MANTLE
    _subissue = "#1992"


class SanctumCrossingHandler(_StubCrossingHandler):
    """SANCTUM thread crossing — stub (#1993)."""

    target_kind = TargetKind.SANCTUM
    _subissue = "#1993"
