"""End-to-end pipeline tests for the magical alteration system.

Test structure:
  AlterationCoreFlowTests       — pending lifecycle: create → resolve → condition + event
  AlterationEscalationTests     — same-scene dedup / escalation vs. separate scenes
  AlterationLibraryTests        — library query and use-as-is resolution path
  AlterationFullPipelineTests   — full chain: use_technique → Soulfray → MAGICAL_SCARS
                                   → PendingAlteration → player resolution → ConditionInstance
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
import pytest

from integration_tests.game_content.characters import CharacterContent
from integration_tests.game_content.magic import MagicContent
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    MagicalAlterationTemplateFactory,
    ResonanceFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.magic.models import MagicalAlterationEvent, MagicalAlterationTemplate, PendingAlteration
from world.magic.services import (
    create_pending_alteration,
    get_library_entries,
    has_pending_alterations,
    resolve_pending_alteration,
    use_technique,
)
from world.magic.types import AlterationGateError, AlterationResolutionResult


def _make_character_with_resonance(name: str) -> tuple:
    """Create a social character and give them a CharacterResonance row.

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
    CharacterResonanceFactory(character_sheet=sheet, resonance=resonance)
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
        assert pending.status == PendingAlterationStatus.RESOLVED


# ---------------------------------------------------------------------------
# Class D: Full pipeline — use_technique → Soulfray → MAGICAL_SCARS → resolution
# ---------------------------------------------------------------------------


class AlterationFullPipelineTests(TestCase):
    """Full pipeline: use_technique → Soulfray accumulation → MAGICAL_SCARS consequence
    → PendingAlteration → player resolution → ConditionInstance applied + gate released.

    This class tests the spec-mandated end-to-end chain (spec line 2452–2453).
    The existing AlterationCoreFlowTests cover the service layer directly;
    this class covers the path from technique use through to resolution.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.models import CharacterSheet
        from world.mechanics.factories import CharacterEngagementFactory

        # --- Character with active resonance ---
        character, _persona = CharacterContent.create_base_social_character(name="Orindra")
        cls.character = character
        cls.sheet = CharacterSheet.objects.get(character=character)

        # Resonance row so _apply_magical_scars can derive origin
        affinity = AffinityFactory(name="Primal (pipeline test)")
        resonance = ResonanceFactory(name="Ember (pipeline test)", affinity=affinity)
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=resonance)
        cls.affinity = affinity
        cls.resonance = resonance

        # --- Alteration content: Soulfray template + consequence pool ---
        cls.alteration_content = MagicContent.create_alteration_content()
        # The soulfray_stage already has consequence_pool wired with MAGICAL_SCARS effect.

        # --- Technique: high anima cost, low control so effective_cost > current_anima ---
        # With SoulfrayConfig threshold=0.30: anima=0/10 = 0.0 < 0.30 → severity > 0.
        cls.technique = TechniqueFactory(
            name="Overburn Blast (pipeline test)",
            intensity=5,
            control=2,
            anima_cost=20,
        )

        # --- SoulfrayConfig: threshold 0.30, severity_scale 10 ---
        from world.checks.factories import CheckTypeFactory

        cls.resilience_check_type = CheckTypeFactory(name="Resilience (pipeline test)")
        from decimal import Decimal

        cls.soulfray_config = SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
            resilience_check_type=cls.resilience_check_type,
            base_check_difficulty=15,
        )

        # Engage the character so the social safety bonus does not inflate control
        CharacterEngagementFactory(character=character)

        # Cache the outcome_tier for the MAGICAL_SCARS consequence so tests don't
        # re-query get_effective_consequences on every call.
        from actions.services import get_effective_consequences

        pool = cls.alteration_content.soulfray_consequence_pool
        consequences = get_effective_consequences(pool)
        cls.soulfray_outcome = consequences[0].outcome_tier if consequences else None

    def _drain_anima(self) -> None:
        """Set the character's anima to 0 so every technique use accumulates Soulfray."""
        from world.magic.models import CharacterAnima

        CharacterAnima.objects.filter(character=self.character).update(current=0)

    def _run_technique_with_mocked_outcome(self, outcome):
        """Run use_technique with the resilience check patched to return outcome."""
        from world.checks.types import CheckResult

        mock_result = CheckResult(
            check_type=self.resilience_check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        with patch("world.checks.services.perform_check", return_value=mock_result):
            return use_technique(
                character=self.character,
                technique=self.technique,
                resolve_fn=lambda: "resolved",
                confirm_soulfray_risk=True,
            )

    def test_use_technique_overburn_creates_pending_alteration(self) -> None:
        """Full pipeline: use_technique overburn → Soulfray → MAGICAL_SCARS → PendingAlteration.

        Two technique uses are required:
        1. First use: Soulfray condition created for character (no consequence pool fired yet).
        2. Second use: Soulfray severity incremented on existing condition → stage reached
           → consequence pool fires → MAGICAL_SCARS handler creates PendingAlteration.
        """
        self._drain_anima()

        # First use: creates the Soulfray condition, returns before firing the pool
        self._run_technique_with_mocked_outcome(self.soulfray_outcome)

        # Verify Soulfray condition exists on character but no pending yet
        from world.conditions.models import ConditionInstance
        from world.magic.audere import SOULFRAY_CONDITION_NAME

        assert ConditionInstance.objects.filter(
            target=self.character,
            condition__name=SOULFRAY_CONDITION_NAME,
        ).exists(), "Soulfray condition should exist after first overburn"

        # No PendingAlteration yet (pool fires only on subsequent accumulation)
        assert not PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).exists(), "No PendingAlteration expected after first overburn"

        # Second use: fires the consequence pool on the existing Soulfray instance
        self._drain_anima()
        result = self._run_technique_with_mocked_outcome(self.soulfray_outcome)

        assert result.confirmed is True
        assert result.soulfray_result is not None

        # MAGICAL_SCARS handler should have created a PendingAlteration
        assert PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).exists(), "PendingAlteration should exist after second overburn fires pool"

        pending = PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).first()
        assert pending is not None
        # Severity 2 → MARKED tier (as set on the ConsequenceEffect.condition_severity)
        assert pending.tier == AlterationTier.MARKED
        assert pending.origin_affinity_id == self.affinity.pk
        assert pending.origin_resonance_id == self.resonance.pk

    def test_resolve_pending_from_pipeline_applies_condition_and_releases_gate(self) -> None:
        """Resolving the PendingAlteration from an overburn chain applies ConditionInstance
        and clears has_pending_alterations."""

        self._drain_anima()

        # Run two overburns to produce a PendingAlteration (same as previous test)
        self._run_technique_with_mocked_outcome(self.soulfray_outcome)
        self._drain_anima()
        self._run_technique_with_mocked_outcome(self.soulfray_outcome)

        assert PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).exists(), "Precondition: PendingAlteration must exist before resolve"

        pending = PendingAlteration.objects.filter(
            character=self.sheet,
            status=PendingAlterationStatus.OPEN,
        ).first()

        # Gate should be active before resolution
        assert has_pending_alterations(self.sheet) is True

        # Player resolves the alteration from scratch
        resolution = resolve_pending_alteration(
            pending=pending,
            name="Ember-Scorched Skin",
            player_description=(
                "A tracery of ember-scorched lines runs across the character's forearm, "
                "a permanent reminder of overburn. The marks are warm to the touch."
            ),
            observer_description=(
                "Faint ember-coloured markings trace the forearm, glowing subtly in low light."
            ),
            weakness_magnitude=0,
            resonance_bonus_magnitude=0,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
            resolved_by=None,
        )

        # ConditionInstance applied to the character
        assert resolution.condition_instance is not None
        assert resolution.condition_instance.target_id == self.character.pk

        # MagicalAlterationEvent created linking the pipeline run
        assert MagicalAlterationEvent.objects.filter(
            character=self.sheet,
            alteration_template=resolution.template,
        ).exists()

        # Gate released
        assert pending.status == PendingAlterationStatus.RESOLVED
        assert has_pending_alterations(self.sheet) is False
