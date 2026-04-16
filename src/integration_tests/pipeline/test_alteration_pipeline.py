"""End-to-end pipeline tests for the magical alteration system.

Test structure:
  AlterationCoreFlowTests       — pending lifecycle: create → resolve → condition + event
  AlterationEscalationTests     — same-scene dedup / escalation vs. separate scenes
  AlterationLibraryTests        — library query and use-as-is resolution path
"""

from __future__ import annotations

from django.test import TestCase
import pytest

from integration_tests.game_content.characters import CharacterContent
from integration_tests.game_content.magic import MagicContent
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import (
    AffinityFactory,
    MagicalAlterationTemplateFactory,
    ResonanceFactory,
)
from world.magic.models import MagicalAlterationEvent, MagicalAlterationTemplate, PendingAlteration
from world.magic.services import (
    create_pending_alteration,
    get_library_entries,
    has_pending_alterations,
    resolve_pending_alteration,
)
from world.magic.types import AlterationGateError, AlterationResolutionResult


def _make_character_with_resonance(name: str) -> tuple:
    """Create a social character and give them an active CharacterResonance.

    Returns (character, sheet, affinity, resonance).
    CharacterResonance is required for create_pending_alteration to work
    without passing explicit affinity/resonance args.
    """
    from world.character_sheets.models import CharacterSheet
    from world.magic.factories import CharacterResonanceFactory

    character, _persona = CharacterContent.create_base_social_character(name=name)
    sheet = CharacterSheet.objects.get(character=character)
    affinity = AffinityFactory(name=f"Primal ({name})")
    resonance = ResonanceFactory(name=f"Ember ({name})", affinity=affinity)
    CharacterResonanceFactory(character=character, resonance=resonance, is_active=True)
    return character, sheet, affinity, resonance


# ---------------------------------------------------------------------------
# Class A: Core alteration lifecycle
# ---------------------------------------------------------------------------


class AlterationCoreFlowTests(TestCase):
    """Core pending alteration lifecycle: create → resolve → condition + event + gate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character, cls.sheet, cls.affinity, cls.resonance = _make_character_with_resonance(
            "Lyra"
        )

    def _make_open_pending(self, tier: int = AlterationTier.MARKED) -> PendingAlteration:
        """Create an open PendingAlteration directly for Lyra at the given tier."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=tier,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )
        return result.pending

    def test_create_pending_alteration_returns_new_pending(self) -> None:
        """create_pending_alteration creates an OPEN PendingAlteration for the character."""
        result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=None,
        )

        assert result.created is True
        assert result.pending.status == PendingAlterationStatus.OPEN
        assert result.pending.character_id == self.sheet.pk
        assert result.pending.tier == AlterationTier.MARKED
        assert result.pending.origin_affinity_id == self.affinity.pk
        assert result.pending.origin_resonance_id == self.resonance.pk

    def test_resolve_creates_condition_and_event(self) -> None:
        """resolve_pending_alteration applies the condition and creates an audit event."""
        pending = self._make_open_pending(tier=AlterationTier.MARKED)

        result: AlterationResolutionResult = resolve_pending_alteration(
            pending=pending,
            name="Seared Brand",
            player_description=(
                "A brand of flame-shaped scar tissue spirals along the left forearm, "
                "permanently etched by overburn."
            ),
            observer_description=(
                "Flame-shaped marks cover the left forearm, glowing faintly in darkness."
            ),
            weakness_magnitude=0,
            resonance_bonus_magnitude=0,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
            resolved_by=None,
        )

        # ConditionInstance created for the character
        assert result.condition_instance is not None
        assert result.condition_instance.target_id == self.character.pk

        # MagicalAlterationEvent created
        assert MagicalAlterationEvent.objects.filter(
            character=self.sheet,
            alteration_template=result.template,
        ).exists()

        # PendingAlteration status is RESOLVED
        pending.refresh_from_db()
        assert pending.status == PendingAlterationStatus.RESOLVED

    def test_pending_blocks_xp_spend(self) -> None:
        """has_pending_alterations True and spend_xp_on_unlock raises AlterationGateError."""
        _pending = self._make_open_pending(tier=AlterationTier.MARKED)

        assert has_pending_alterations(self.sheet) is True

        # Build a minimal ClassLevelUnlock target for the gate check
        from world.classes.factories import CharacterClassFactory
        from world.progression.models import ClassLevelUnlock
        from world.progression.services.spends import spend_xp_on_unlock

        char_class = CharacterClassFactory(name="Test Class (gate test)")
        unlock_target = ClassLevelUnlock.objects.create(
            character_class=char_class,
            target_level=1,
        )

        with pytest.raises(AlterationGateError):
            spend_xp_on_unlock(self.character, unlock_target)

    def test_resolved_pending_releases_gate(self) -> None:
        """After resolving the pending, has_pending_alterations returns False."""
        pending = self._make_open_pending(tier=AlterationTier.MARKED)

        resolve_pending_alteration(
            pending=pending,
            name="Quiet Ember Mark",
            player_description=(
                "A faint ember-shaped discolouration settles into the skin permanently."
                " It catches the light only at certain angles."
            ),
            observer_description=(
                "A subtle mark on the skin that catches light oddly in certain angles."
            ),
            weakness_magnitude=0,
            resonance_bonus_magnitude=0,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
            resolved_by=None,
        )

        # Gate should now be clear
        assert has_pending_alterations(self.sheet) is False


# ---------------------------------------------------------------------------
# Class B: Escalation and scene deduplication
# ---------------------------------------------------------------------------


class AlterationEscalationTests(TestCase):
    """Same-scene dedup escalates tier; different scenes create separate pendings."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character_a, cls.sheet_a, cls.affinity, cls.resonance = _make_character_with_resonance(
            "Fen"
        )
        cls.character_b, cls.sheet_b, cls.affinity_b, cls.resonance_b = (
            _make_character_with_resonance("Oryn")
        )
        from world.scenes.factories import SceneFactory

        cls.scene_1 = SceneFactory()
        cls.scene_2 = SceneFactory()

    def test_two_overburns_same_scene_escalate_tier(self) -> None:
        """Two overburns in one scene produce ONE PendingAlteration at the higher tier."""
        # First overburn at tier 2
        result1 = create_pending_alteration(
            character=self.sheet_a,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=self.scene_1,
        )
        assert result1.created is True

        # Second overburn in the same scene at tier 3 (higher)
        result2 = create_pending_alteration(
            character=self.sheet_a,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=self.scene_1,
        )
        # Not newly created — escalated
        assert result2.created is False
        assert result2.previous_tier == AlterationTier.MARKED
        assert result2.pending.tier == AlterationTier.TOUCHED

        # Only ONE pending for this character+scene
        count = PendingAlteration.objects.filter(
            character=self.sheet_a,
            triggering_scene=self.scene_1,
            status=PendingAlterationStatus.OPEN,
        ).count()
        assert count == 1

    def test_lower_tier_same_scene_does_not_downgrade(self) -> None:
        """A lower-tier overburn in the same scene leaves the existing tier unchanged."""
        create_pending_alteration(
            character=self.sheet_b,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity_b,
            origin_resonance=self.resonance_b,
            scene=self.scene_1,
        )
        result = create_pending_alteration(
            character=self.sheet_b,
            tier=AlterationTier.MARKED,  # lower
            origin_affinity=self.affinity_b,
            origin_resonance=self.resonance_b,
            scene=self.scene_1,
        )
        assert result.created is False
        assert result.previous_tier is None  # no escalation — unchanged
        assert result.pending.tier == AlterationTier.TOUCHED  # still at the higher tier

    def test_two_overburns_different_scenes_create_separate_pendings(self) -> None:
        """Overburns in different scenes each create a new PendingAlteration row."""
        _character_c, sheet_c, affinity_c, resonance_c = _make_character_with_resonance("Kael")

        result1 = create_pending_alteration(
            character=sheet_c,
            tier=AlterationTier.MARKED,
            origin_affinity=affinity_c,
            origin_resonance=resonance_c,
            scene=self.scene_1,
        )
        result2 = create_pending_alteration(
            character=sheet_c,
            tier=AlterationTier.MARKED,
            origin_affinity=affinity_c,
            origin_resonance=resonance_c,
            scene=self.scene_2,
        )

        assert result1.created is True
        assert result2.created is True
        assert result1.pending.pk != result2.pending.pk

        count = PendingAlteration.objects.filter(
            character=sheet_c,
            status=PendingAlterationStatus.OPEN,
        ).count()
        assert count == 2


# ---------------------------------------------------------------------------
# Class C: Library browsing and use-as-is resolution
# ---------------------------------------------------------------------------


class AlterationLibraryTests(TestCase):
    """Library entries: tier-filtered queries and use-as-is resolution path."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character, cls.sheet, cls.affinity, cls.resonance = _make_character_with_resonance(
            "Vesper"
        )
        cls.alteration_content = MagicContent.create_alteration_content()

    def test_library_returns_only_tier_matched_entries(self) -> None:
        """get_library_entries(tier=X) returns only entries at tier X."""
        tier2_entries = list(get_library_entries(tier=AlterationTier.MARKED))
        # cls.alteration_content.tier2_entry is tier MARKED (2)
        returned_pks = {e.pk for e in tier2_entries}
        assert self.alteration_content.tier2_entry.pk in returned_pks
        # The other tiers should NOT appear
        assert self.alteration_content.tier1_entry.pk not in returned_pks
        assert self.alteration_content.tier3_entry.pk not in returned_pks

    def test_library_affinity_sort_puts_match_first(self) -> None:
        """Matching origin_affinity appears before non-matching entries."""
        # The alteration content uses a unique affinity.
        # Create a second MARKED entry with a different affinity to test ordering.
        other_affinity = AffinityFactory(name="Celestial (library sort test)")
        other_resonance = ResonanceFactory(
            name="Starlight (library sort test)", affinity=other_affinity
        )
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionCategoryFactory,
            ConditionTemplateFactory,
        )

        alteration_cat = ConditionCategoryFactory(name="Magical Alteration")
        cond = ConditionTemplateFactory(
            name="Starfall Scar (sort test)",
            category=alteration_cat,
            default_duration_type=DurationType.PERMANENT,
        )
        MagicalAlterationTemplateFactory(
            condition_template=cond,
            tier=AlterationTier.MARKED,
            origin_affinity=other_affinity,
            origin_resonance=other_resonance,
            is_library_entry=True,
        )

        entries = list(
            get_library_entries(
                tier=AlterationTier.MARKED,
                character_affinity_id=self.alteration_content.affinity.pk,
            )
        )
        # The matching-affinity entry should come before the non-matching one
        pks = [e.pk for e in entries]
        assert pks.index(self.alteration_content.tier2_entry.pk) < pks.index(
            cond.magical_alteration.pk
        )

    def test_library_use_as_is_resolves_pending(self) -> None:
        """Using a library entry resolves the pending with the library's ConditionTemplate.

        No new MagicalAlterationTemplate is created — the library entry is used directly.
        """
        # Create a pending at the same tier as the library entry
        pending_result = create_pending_alteration(
            character=self.sheet,
            tier=AlterationTier.TOUCHED,  # matches tier3_entry
            origin_affinity=self.alteration_content.affinity,
            origin_resonance=self.alteration_content.resonance,
            scene=None,
        )
        pending = pending_result.pending
        library_entry = self.alteration_content.tier3_entry
        template_count_before = MagicalAlterationTemplate.objects.count()

        result = resolve_pending_alteration(
            pending=pending,
            name="",  # ignored for library path
            player_description="",
            observer_description="",
            is_visible_at_rest=False,
            resolved_by=None,
            library_template=library_entry,
        )

        # No new MagicalAlterationTemplate created
        assert MagicalAlterationTemplate.objects.count() == template_count_before

        # The resolved template IS the library entry
        assert result.template.pk == library_entry.pk

        # ConditionInstance points to the library entry's condition_template
        assert result.condition_instance.condition_id == library_entry.condition_template_id

        # Event created
        assert MagicalAlterationEvent.objects.filter(
            character=self.sheet,
            alteration_template=library_entry,
        ).exists()

        # Pending is RESOLVED
        pending.refresh_from_db()
        assert pending.status == PendingAlterationStatus.RESOLVED
