"""Concrete crossing-ceremony handlers (ADR-0094, #1987).

Each handler is registered against a ``TargetKind`` in ``MagicConfig.ready()``.

- ``GiftCrossingHandler`` (GIFT) and ``CovenantRoleCrossingHandler``
  (COVENANT_ROLE) wrap the existing variant-discovery logic verbatim — no
  behavior change. They use ``AbstractSpecializedVariant`` (ADR-0055).
- ``TechniqueCrossingHandler`` (TECHNIQUE) executes a ceremony beat at
  crossings. The signature-bonus gating itself is subissue #1988; this
  handler just ensures the crossing isn't silent.
- ``RelationshipTrackCrossingHandler`` (RELATIONSHIP_TRACK) and
  ``RelationshipCapstoneCrossingHandler`` (RELATIONSHIP_CAPSTONE) use the
  ``_CrossingChoiceHandler`` base — the same player-choice pattern as TRAIT
  and FACET (#1991).
- ``MantleCrossingHandler`` (MANTLE) uses the ``_CrossingChoiceHandler`` base
  — the same player-choice pattern as TRAIT and FACET (#1992).
- The remaining kind (SANCTUM) is a stub that logs a debug no-op. It is
  replaced with real logic in its subissue (#1993).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.classes.services import is_crossing_level
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


def _parents_for(thread: Thread) -> Iterable:  # noqa: PLR0911
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
    if thread.target_kind == TargetKind.ORGANIZATION:
        if thread.target_organization_id is not None:
            org = thread.target_organization
            handler = org.gift_grants_handler
            # Only gifts whose supported-resonance set contains the thread's
            # resonance contribute techniques (so variants are only discovered
            # for techniques the member actually received).
            return handler.acquired_techniques_for(thread.resonance)
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
    if target_kind == TargetKind.ORGANIZATION:
        from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

        return TechniqueVariant
    return None


class _VariantDiscoveryHandler:
    """Shared base for handlers that discover ``AbstractSpecializedVariant`` rows.

    GIFT, ORGANIZATION, and COVENANT_ROLE all use the same execute logic —
    they differ only in ``target_kind`` (which drives ``_parents_for`` and
    ``_variant_model_for``).
    """

    target_kind: str = ""

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


class GiftCrossingHandler(_VariantDiscoveryHandler):
    """GIFT thread crossing handler — discovers technique variants.

    Wraps the existing variant-discovery logic for GIFT threads (ADR-0055,
    #1578). No behavior change from the original ``fire_variant_discoveries``.
    """

    target_kind = TargetKind.GIFT


class OrganizationCrossingHandler(_VariantDiscoveryHandler):
    """ORGANIZATION thread crossing handler — discovers technique variants.

    Mirrors ``GiftCrossingHandler``: the org's acquired gifts carry techniques,
    and ``TechniqueVariant`` rows specialize them by resonance at crossings.
    """

    target_kind = TargetKind.ORGANIZATION


class CovenantRoleCrossingHandler(_VariantDiscoveryHandler):
    """COVENANT_ROLE thread crossing handler — discovers sub-role variants.

    Wraps the existing variant-discovery logic for COVENANT_ROLE threads
    (#1277, #1578). No behavior change.
    """

    target_kind = TargetKind.COVENANT_ROLE


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

    Fires a narrative-only beat at the first crossing (level 3) so the player
    knows they can now sign their technique. The real ceremony (discovery) fires
    at selection time, not at the crossing — driven by the bonus's
    ``discovery_achievement`` FK via ``execute_ceremony_beat``. Higher crossings
    produce no beat; the player discovers new options by seeing new bonuses appear
    in ``signature list`` as their thread deepens.

    ADR-0072 establishes that TECHNIQUE signatures are additive flourishes, not
    discovered variants — so this handler does NOT use
    ``AbstractSpecializedVariant``.
    """

    target_kind = TargetKind.TECHNIQUE

    def execute(self, *, thread: Thread, starting_level: int, new_level: int) -> None:
        if new_level <= starting_level:
            return

        # Only fire at the first crossing (level 3) — the "you may now sign" moment.
        # Higher crossings don't need a beat; the discovery fires on selection.
        if not is_crossing_level(new_level) or new_level != 3:  # noqa: PLR2004 — first crossing
            return

        sheet: CharacterSheet = thread.owner
        execute_ceremony_beat(
            sheet=sheet,
            narrative=CeremonyNarrative(
                personal_body=(
                    "Your technique thread has crossed the first threshold. "
                    "You may now sign it with a signature bonus (use 'signature set')."
                ),
            ),
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


class _CrossingChoiceHandler:
    """Shared base for handlers that create player-choice crossing offers.

    Both TRAIT and FACET (and future kinds) use the same flow: auto-resolve
    skipped lower crossings, create a pending offer for the highest crossing,
    fire ceremony beat #1. Differ only in target_kind.
    """

    target_kind: str = ""

    def execute(self, *, thread: Thread, starting_level: int, new_level: int) -> None:
        if new_level <= starting_level:
            return

        # Find crossing levels in (starting_level, new_level]
        crossing_levels = [
            level for level in (3, 6, 11, 16, 21) if starting_level < level <= new_level
        ]
        if not crossing_levels:
            return

        highest = max(crossing_levels)

        # Auto-resolve skipped lower crossings with the is_default option
        for level in crossing_levels:
            if level == highest:
                continue
            _auto_resolve_crossing(thread, level)

        # Create pending offer for the highest crossing (if not already chosen)
        from world.magic.models.crossing import (  # noqa: PLC0415
            CrossingChoice,
            PendingCrossingOffer,
        )

        if not CrossingChoice.objects.filter(thread=thread, crossing_level=highest).exists():
            PendingCrossingOffer.objects.update_or_create(
                thread=thread,
                defaults={"crossing_level": highest},
            )

        # Fire ceremony beat #1 — narrative-only announcement
        execute_ceremony_beat(
            sheet=thread.owner,
            narrative=CeremonyNarrative(
                personal_body=_compose_crossing_message(thread, highest),
            ),
        )


class TraitCrossingHandler(_CrossingChoiceHandler):
    """TRAIT thread crossing handler — player-chosen resonance expression.

    At each crossing level (3, 6, 11, 16, 21), creates a PendingCrossingOffer
    for the player to choose a resonance-flavored expression of their stat.
    Skipped lower crossings (multi-crossing imbue) are auto-resolved with the
    is_default option. Fires ceremony beat #1 (narrative-only) at crossing time;
    beat #2 (achievement/codex) fires at resolution time.
    """

    target_kind = TargetKind.TRAIT


def _anchor_label_for(thread: Thread) -> str:
    """Return a human-readable label for the thread's anchor entity.

    Used by ``_compose_crossing_message`` and ``CmdCrossing._list_offers`` so
    the crossing announcement references the right anchor (partner name for
    relationship threads, trait/facet name for those kinds) instead of a
    generic placeholder.
    """
    kind = thread.target_kind
    fallback = {
        TargetKind.TRAIT: "trait",  # noqa: STRING_LITERAL
        TargetKind.FACET: "facet",  # noqa: STRING_LITERAL
        TargetKind.RELATIONSHIP_TRACK: "relationship",  # noqa: STRING_LITERAL
        TargetKind.RELATIONSHIP_CAPSTONE: "capstone",  # noqa: STRING_LITERAL
    }.get(kind, "thread")  # noqa: STRING_LITERAL
    if kind == TargetKind.TRAIT and thread.target_trait is not None:
        return thread.target_trait.name
    if kind == TargetKind.FACET and thread.target_facet is not None:
        return thread.target_facet.name
    if kind == TargetKind.RELATIONSHIP_TRACK:
        track = thread.target_relationship_track
        if track is not None:
            partner_name = track.relationship.target.character.db_key
            return f"bond with {partner_name} ({track.track.name})"
    if kind == TargetKind.RELATIONSHIP_CAPSTONE:
        cap = thread.target_capstone
        if cap is not None:
            partner_name = cap.relationship.target.character.db_key
            return f"capstone '{cap.title}' with {partner_name}"
    if kind == TargetKind.MANTLE and thread.target_mantle is not None:
        return thread.target_mantle.name
    return fallback


def _compose_crossing_message(thread: Thread, crossing_level: int) -> str:
    """Build a resonance-flavored crossing announcement."""
    resonance_name = thread.resonance.name if thread.resonance else "your resonance"
    anchor_label = _anchor_label_for(thread)
    return (
        f"Your {resonance_name}-resonant {anchor_label} thread "
        f"has crossed a threshold (level {crossing_level}). "
        f"Use 'crossing list' to choose how it manifests."
    )


def _auto_resolve_crossing(thread: Thread, crossing_level: int) -> None:
    """Auto-resolve a skipped crossing with the is_default option.

    Fail-open: if no is_default option exists for (target_kind, resonance,
    level), the crossing is silently skipped (staff haven't authored content
    yet).
    """
    from world.magic.models.crossing import (  # noqa: PLC0415
        CrossingChoice,
        CrossingOption,
    )

    if CrossingChoice.objects.filter(thread=thread, crossing_level=crossing_level).exists():
        return  # already chosen

    default_option = CrossingOption.objects.filter(
        target_kind=thread.target_kind,
        resonance=thread.resonance,
        crossing_level=crossing_level,
        is_default=True,
    ).first()

    if default_option is None:
        return  # fail-open: no content authored

    CrossingChoice.objects.create(
        thread=thread,
        crossing_level=crossing_level,
        option=default_option,
    )


class FacetCrossingHandler(_CrossingChoiceHandler):
    """FACET thread crossing handler — player-chosen aura enhancement.

    At each crossing level, creates a PendingCrossingOffer for the player
    to choose a resonance-matched aura enhancement. The chosen buff is
    active while wearing an item with the anchor facet (enforced by the
    read path, not the handler).
    """

    target_kind = TargetKind.FACET


class RelationshipTrackCrossingHandler(_CrossingChoiceHandler):
    """RELATIONSHIP_TRACK thread crossing — player-chosen bond expression (#1991).

    At each crossing level, creates a PendingCrossingOffer for the player to
    choose a resonance-matched bond expression. The buff is always-on (a
    relationship bond is intrinsic — not wear-gated like FACET).
    """

    target_kind = TargetKind.RELATIONSHIP_TRACK


class RelationshipCapstoneCrossingHandler(_CrossingChoiceHandler):
    """RELATIONSHIP_CAPSTONE thread crossing — player-chosen bond expression (#1991).

    Coordinates with Soul Tether (Spec B): the ceremony is a personalization
    layer only. It does not touch ``hollow_current``, ``hollow_max``, or any
    Soul Tether service. The Hollow continues to function normally — deepening
    the Hollow at crossings is a separate Spec B follow-up.
    """

    target_kind = TargetKind.RELATIONSHIP_CAPSTONE


class MantleCrossingHandler(_CrossingChoiceHandler):
    """MANTLE thread crossing — player-chosen mantle personalization.

    At each crossing level (3, 6, 11, 16, 21), creates a PendingCrossingOffer
    for the player to choose how the mantle's power reshapes to match their
    resonance. The chosen buff is always-on (the thread IS the attunement bond
    — not wear-gated like FACET). Skipped lower crossings are auto-resolved
    with the is_default option.
    """

    target_kind = TargetKind.MANTLE


class SanctumCrossingHandler(_StubCrossingHandler):
    """SANCTUM thread crossing — stub (#1993)."""

    target_kind = TargetKind.SANCTUM
    _subissue = "#1993"
