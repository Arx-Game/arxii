"""Tests for magical_profile predicate and resonance_environment_for_cast service.

Tests:
- CharacterSheet with a related CharacterAura → magical_profile returns the aura.
- CharacterSheet with no CharacterAura → magical_profile returns None.
- resonance_environment_for_cast:
  (1) no aura → inert, no ConditionInstance created
  (2) magnitude 0 → inert
  (3) kind == CORRUPT → inert (asserts no condition; direction still computed)
  (4) OPPOSED with seeded pool → authored condition applied, result reports it
  (5) OPPOSED with consequence_pool=None → inert
  (6) ALIGNED → inert (T7 handles presence-tied ALIGNED)
- _get_endure_hallowed_ground_check_type (name-contract regression guard):
  (7) returns the row when a CheckType named "endure_hallowed_ground" exists
  (8) raises CheckType.DoesNotExist when the row is absent (never silently creates)
- OPPOSED backfire tests assert the CheckType lookup uses the seeded name "endure_hallowed_ground"
- refresh_resonance_alignment / clear_resonance_alignment (T7):
  (9)  enter aligned room (low magnitude) → low-band buff applied
  (10) refresh in higher-magnitude aligned room → high-band buff, exactly one resonance-alignment
       ConditionInstance remains
  (11) refresh when room is non-aligned → buff removed, none applied
  (12) no aura → no buff, no error
  (13) room has no RoomProfile → no buff; any prior buff cleared
  (14) idempotent: two refreshes in same aligned room → still exactly one buff instance
  (15) clear_resonance_alignment removes existing buff and is a no-op when none present
- T8 orchestrator integration (use_technique wires Step 10):
  (16) OPPOSED cast in cascade room → ConditionInstance applied via use_technique (not direct call)
  (17) cast in room with no RoomProfile → no error, no ConditionInstance
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.constants import (
    ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME,
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)
from world.magic.factories import (
    AffinityFactory,
    AffinityInteractionFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models.aura import CharacterAura
from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier
from world.magic.services import use_technique
from world.magic.services.gain import tag_room_resonance
from world.magic.services.resonance_environment import (
    clear_resonance_alignment,
    magical_profile,
    refresh_resonance_alignment,
    resonance_environment_for_cast,
)
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory


def _set_room_resonance_value(room_profile, resonance, value: int) -> None:
    """Tag the room with resonance and set the modifier value."""
    mod = tag_room_resonance(room_profile, resonance)
    mod.value = value
    mod.save(update_fields=["value"])


def _make_check_result(outcome) -> CheckResult:
    """Build a minimal CheckResult for mocking perform_check."""
    mock_check_type = MagicMock()
    return CheckResult(
        check_type=mock_check_type,
        outcome=outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


class MagicalProfileTest(ResonanceCacheIsolationMixin, TestCase):
    """Tests for the magical_profile(character_sheet) predicate."""

    def setUp(self) -> None:
        super().setUp()
        # Create sheets AFTER super().setUp() per mixin docstring.
        self.sheet_with_aura = CharacterSheetFactory()
        self.aura = CharacterAuraFactory(character=self.sheet_with_aura.character)

        self.sheet_without_aura = CharacterSheetFactory()
        # Explicitly ensure no CharacterAura exists for sheet_without_aura.
        CharacterAura.objects.filter(character=self.sheet_without_aura.character).delete()

    def test_returns_aura_when_character_has_one(self) -> None:
        """A sheet whose character has a CharacterAura → returns that exact instance."""
        result = magical_profile(self.sheet_with_aura)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.aura.pk)

    def test_returns_none_when_character_has_no_aura(self) -> None:
        """A sheet whose character has no CharacterAura → returns None (Quiescent)."""
        result = magical_profile(self.sheet_without_aura)
        self.assertIsNone(result)


class ResonanceCastResultInertTest(ResonanceCacheIsolationMixin, TestCase):
    """Branch tests for resonance_environment_for_cast that return inert results."""

    def setUp(self) -> None:
        super().setUp()
        # Common setup: a room with resonance, and an OPPOSED interaction.
        self.celestial = AffinityFactory(name="Celestial")
        self.abyssal = AffinityFactory(name="Abyssal")
        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)
        self.abyssal_resonance = ResonanceFactory(affinity=self.abyssal)

        self.room_profile = RoomProfileFactory()
        _set_room_resonance_value(self.room_profile, self.celestial_resonance, 50)

        # Technique: abyssal gift cast into celestial room (OPPOSED pair)
        self.gift = GiftFactory()
        self.gift.resonances.add(self.abyssal_resonance)
        self.technique = TechniqueFactory(gift=self.gift)

        # Sheet with aura for the "normal" case
        self.sheet = CharacterSheetFactory()
        CharacterAuraFactory(
            character=self.sheet.character,
            celestial=Decimal("10.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("70.00"),
        )

    def test_no_aura_returns_inert(self) -> None:
        """Sheet with no CharacterAura → inert result, no ConditionInstance created."""
        sheet_no_aura = CharacterSheetFactory()
        CharacterAura.objects.filter(character=sheet_no_aura.character).delete()

        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        result = resonance_environment_for_cast(
            caster_sheet=sheet_no_aura,
            room_profile=self.room_profile,
            technique=self.technique,
        )

        self.assertEqual(result.valence, "")
        self.assertEqual(result.applied, ())
        count = ConditionInstance.objects.filter(target=sheet_no_aura.character).count()
        self.assertEqual(count, 0)

    def test_magnitude_zero_returns_inert(self) -> None:
        """Magnitude 0 → inert result, no condition applied."""
        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("0.00"),  # multiplier=0 → magnitude=0
        )

        result = resonance_environment_for_cast(
            caster_sheet=self.sheet,
            room_profile=self.room_profile,
            technique=self.technique,
        )

        self.assertEqual(result.valence, "")
        self.assertEqual(result.applied, ())
        self.assertEqual(ConditionInstance.objects.filter(target=self.sheet.character).count(), 0)

    def test_corrupt_kind_returns_inert_no_condition(self) -> None:
        """CORRUPT kind → inert (deferred), no condition applied, direction still computed."""
        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.CORRUPT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        result = resonance_environment_for_cast(
            caster_sheet=self.sheet,
            room_profile=self.room_profile,
            technique=self.technique,
        )

        # Inert: no condition applied
        self.assertEqual(result.applied, ())
        self.assertEqual(ConditionInstance.objects.filter(target=self.sheet.character).count(), 0)
        # The primitive still computed a direction (it's in the effect, not the result, but
        # the service returned inert so we check result.valence is empty)
        self.assertEqual(result.valence, "")

    def test_opposed_with_null_pool_returns_inert(self) -> None:
        """OPPOSED + consequence_pool=None → inert, no condition."""
        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
            consequence_pool=None,
        )

        result = resonance_environment_for_cast(
            caster_sheet=self.sheet,
            room_profile=self.room_profile,
            technique=self.technique,
        )

        self.assertEqual(result.valence, "")
        self.assertEqual(result.applied, ())
        self.assertEqual(ConditionInstance.objects.filter(target=self.sheet.character).count(), 0)

    def test_aligned_returns_inert(self) -> None:
        """ALIGNED pair → inert from this service (T7 handles presence-tied ALIGNED)."""
        # Celestial-caster in celestial room = ALIGNED
        sheet_aligned = CharacterSheetFactory()
        CharacterAuraFactory(
            character=sheet_aligned.character,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )
        celestial_resonance2 = ResonanceFactory(affinity=self.celestial)
        gift2 = GiftFactory()
        gift2.resonances.add(celestial_resonance2)
        technique2 = TechniqueFactory(gift=gift2)

        AffinityInteractionFactory(
            source_affinity=self.celestial,
            environment_affinity=self.celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        result = resonance_environment_for_cast(
            caster_sheet=sheet_aligned,
            room_profile=self.room_profile,
            technique=technique2,
        )

        # ALIGNED → cast service returns inert (presence-tied boon is T7)
        self.assertEqual(result.valence, "")
        self.assertEqual(result.applied, ())
        self.assertEqual(
            ConditionInstance.objects.filter(target=sheet_aligned.character).count(), 0
        )


class ResonanceCastOpposedBackfireTest(ResonanceCacheIsolationMixin, TestCase):
    """OPPOSED with a seeded pool → correct authored condition applied per check outcome."""

    def setUp(self) -> None:
        super().setUp()
        # Affinities and resonances
        self.abyssal = AffinityFactory(name="Abyssal")
        self.celestial = AffinityFactory(name="Celestial")
        self.abyssal_resonance = ResonanceFactory(affinity=self.abyssal)
        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)

        # Room seeded with celestial resonance (high magnitude)
        self.room_profile = RoomProfileFactory()
        _set_room_resonance_value(self.room_profile, self.celestial_resonance, 50)

        # Technique: abyssal gift
        self.gift = GiftFactory()
        self.gift.resonances.add(self.abyssal_resonance)
        self.technique = TechniqueFactory(gift=self.gift)

        # Caster sheet with Abyssal-dominant aura
        self.sheet = CharacterSheetFactory()
        CharacterAuraFactory(
            character=self.sheet.character,
            celestial=Decimal("10.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("70.00"),
        )

        # Authored ConditionTemplates per outcome tier
        self.outcome_failure = CheckOutcomeFactory(name="Failure_t6", success_level=-1)
        self.outcome_success = CheckOutcomeFactory(name="Success_t6", success_level=1)
        self.condition_on_failure = ConditionTemplateFactory(name="Singed_t6")
        self.condition_on_success = ConditionTemplateFactory(name="Tempered_t6")

        # Build ConsequencePool with two consequences (one per outcome tier)
        self.pool = ConsequencePoolFactory(name="OpposedBackfire_t6")
        self.consequence_failure = ConsequenceFactory(
            outcome_tier=self.outcome_failure, label="Singed by the holy ground"
        )
        ConsequenceEffectFactory(
            consequence=self.consequence_failure,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=self.condition_on_failure,
        )
        self.pool_entry_failure = ConsequencePoolEntryFactory(
            pool=self.pool, consequence=self.consequence_failure
        )

        self.consequence_success = ConsequenceFactory(
            outcome_tier=self.outcome_success, label="Tempered by the light"
        )
        ConsequenceEffectFactory(
            consequence=self.consequence_success,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=self.condition_on_success,
        )
        self.pool_entry_success = ConsequencePoolEntryFactory(
            pool=self.pool, consequence=self.consequence_success
        )

        # OPPOSED REJECT interaction with the seeded pool
        self.interaction = AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
            consequence_pool=self.pool,
        )

        # The service looks up the seeded CheckType by name — create it so the
        # lookup hits a real row (name-contract tested separately in
        # EndureHallowedGroundCheckTypeNameContractTest).
        self.endure_check_type = CheckTypeFactory(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME)

    def test_opposed_failure_applies_failure_condition(self) -> None:
        """OPPOSED + failure outcome → failure consequence's condition applied to caster."""
        # Force perform_check to return the failure outcome
        check_result = _make_check_result(self.outcome_failure)
        with patch(
            "world.magic.services.resonance_environment.perform_check",
            return_value=check_result,
        ):
            result = resonance_environment_for_cast(
                caster_sheet=self.sheet,
                room_profile=self.room_profile,
                technique=self.technique,
            )

        # Result should report the applied condition name
        self.assertEqual(result.valence, ResonanceValence.OPPOSED)
        self.assertIn(self.condition_on_failure.name, result.applied)

        # A real ConditionInstance must exist on the caster's ObjectDB
        instances = ConditionInstance.objects.filter(
            target=self.sheet.character,
            condition=self.condition_on_failure,
        )
        self.assertTrue(instances.exists(), "Expected ConditionInstance for failure outcome")

    def test_opposed_success_applies_success_condition(self) -> None:
        """OPPOSED + success outcome → success consequence's condition applied to caster."""
        check_result = _make_check_result(self.outcome_success)
        with patch(
            "world.magic.services.resonance_environment.perform_check",
            return_value=check_result,
        ):
            result = resonance_environment_for_cast(
                caster_sheet=self.sheet,
                room_profile=self.room_profile,
                technique=self.technique,
            )

        self.assertEqual(result.valence, ResonanceValence.OPPOSED)
        self.assertIn(self.condition_on_success.name, result.applied)

        instances = ConditionInstance.objects.filter(
            target=self.sheet.character,
            condition=self.condition_on_success,
        )
        self.assertTrue(instances.exists(), "Expected ConditionInstance for success outcome")

    def test_opposed_repel_also_triggers_backfire(self) -> None:
        """OPPOSED REPEL (not just REJECT) also runs the backfire pipeline."""
        # Create a REPEL interaction using different affinities to avoid uniqueness collision
        primal = AffinityFactory(name="Primal")
        primal_resonance = ResonanceFactory(affinity=primal)
        room_profile2 = RoomProfileFactory()
        _set_room_resonance_value(room_profile2, self.celestial_resonance, 50)

        sheet2 = CharacterSheetFactory()
        CharacterAuraFactory(
            character=sheet2.character,
            celestial=Decimal("10.00"),
            primal=Decimal("70.00"),
            abyssal=Decimal("20.00"),
        )
        gift2 = GiftFactory()
        gift2.resonances.add(primal_resonance)
        technique2 = TechniqueFactory(gift=gift2)

        repel_pool = ConsequencePoolFactory(name="RepelPool_t6")
        repel_consequence = ConsequenceFactory(
            outcome_tier=self.outcome_failure, label="Repelled by celestial"
        )
        ConsequenceEffectFactory(
            consequence=repel_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=self.condition_on_failure,
        )
        ConsequencePoolEntryFactory(pool=repel_pool, consequence=repel_consequence)

        AffinityInteractionFactory(
            source_affinity=primal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REPEL,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
            consequence_pool=repel_pool,
        )

        check_result = _make_check_result(self.outcome_failure)
        with patch(
            "world.magic.services.resonance_environment.perform_check",
            return_value=check_result,
        ):
            result = resonance_environment_for_cast(
                caster_sheet=sheet2,
                room_profile=room_profile2,
                technique=technique2,
            )

        self.assertEqual(result.valence, ResonanceValence.OPPOSED)
        self.assertIn(self.condition_on_failure.name, result.applied)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=sheet2.character,
                condition=self.condition_on_failure,
            ).exists()
        )


class EndureHallowedGroundCheckTypeNameContractTest(TestCase):
    """Regression guard for the endure_hallowed_ground CheckType name contract.

    Ensures _get_endure_hallowed_ground_check_type() uses CheckType.objects.get()
    against the seeded name "endure_hallowed_ground" — NOT get_or_create and NOT
    the human-readable "Endure Hallowed Ground". If either the constant value or the
    lookup strategy drifts, these tests catch it before the pipeline integration test.
    """

    def test_returns_check_type_when_seeded_name_exists(self) -> None:
        """Returns the row when a CheckType named 'endure_hallowed_ground' exists."""
        from world.checks.models import CheckType
        from world.magic.services.resonance_environment import (
            _get_endure_hallowed_ground_check_type,
        )

        # Create a CheckType with EXACTLY the seeded name.
        seeded = CheckTypeFactory(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME)

        result = _get_endure_hallowed_ground_check_type()

        self.assertEqual(result.pk, seeded.pk)
        self.assertEqual(result.name, "endure_hallowed_ground")

        # Verify no extra CheckType rows were silently created (get, not get_or_create).
        count = CheckType.objects.filter(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME).count()
        self.assertEqual(count, 1, "get() must not create a second row")

    def test_raises_does_not_exist_when_row_absent(self) -> None:
        """Raises CheckType.DoesNotExist when the seeded row is missing.

        The service must never silently fabricate a chartless CheckType.
        A missing seed is a real misconfiguration — it should propagate loudly.
        """
        from world.checks.models import CheckType
        from world.magic.services.resonance_environment import (
            _get_endure_hallowed_ground_check_type,
        )

        # Guarantee no row exists.
        CheckType.objects.filter(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME).delete()

        with self.assertRaises(CheckType.DoesNotExist):
            _get_endure_hallowed_ground_check_type()


class AppliedNameParenthesisRegressionTest(ResonanceCacheIsolationMixin, TestCase):
    """Regression guard: condition names containing ' (' must survive round-trip intact.

    The old implementation parsed AppliedEffect.description with .split(" (")[0] and
    .replace("Applied ", ""), which silently truncates any name containing ' (' (e.g.
    'Singed (light)'). The fix reads condition names directly from the selected
    consequence's APPLY_CONDITION effects before calling apply_resolution, giving a
    deterministic source that is immune to prose formatting.

    This test is RED against the old string-parse and GREEN after the fix.
    """

    def setUp(self) -> None:
        super().setUp()
        self.abyssal = AffinityFactory(name="Abyssal")
        self.celestial = AffinityFactory(name="Celestial")
        self.abyssal_resonance = ResonanceFactory(affinity=self.abyssal)
        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)

        self.room_profile = RoomProfileFactory()
        _set_room_resonance_value(self.room_profile, self.celestial_resonance, 50)

        self.gift = GiftFactory()
        self.gift.resonances.add(self.abyssal_resonance)
        self.technique = TechniqueFactory(gift=self.gift)

        self.sheet = CharacterSheetFactory()
        CharacterAuraFactory(
            character=self.sheet.character,
            celestial=Decimal("10.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("70.00"),
        )

        self.outcome_failure = CheckOutcomeFactory(name="Failure_paren", success_level=-1)
        # Condition whose name contains ' (' — this is what triggers the regression.
        self.condition_with_paren = ConditionTemplateFactory(name="Singed (light)")

        self.pool = ConsequencePoolFactory(name="ParenPool")
        self.consequence = ConsequenceFactory(
            outcome_tier=self.outcome_failure,
            label="Singed by hallowed light",
        )
        ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=self.condition_with_paren,
        )
        ConsequencePoolEntryFactory(pool=self.pool, consequence=self.consequence)

        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
            consequence_pool=self.pool,
        )
        self.endure_check_type = CheckTypeFactory(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME)

    def test_applied_contains_exact_name_with_parenthesis(self) -> None:
        """result.applied must contain the EXACT full name 'Singed (light)', not truncated."""
        check_result = _make_check_result(self.outcome_failure)
        with patch(
            "world.magic.services.resonance_environment.perform_check",
            return_value=check_result,
        ):
            result = resonance_environment_for_cast(
                caster_sheet=self.sheet,
                room_profile=self.room_profile,
                technique=self.technique,
            )

        self.assertIn(
            "Singed (light)",
            result.applied,
            f"Expected exact name 'Singed (light)' in result.applied, got {result.applied!r}",
        )


# =============================================================================
# T7 — refresh_resonance_alignment / clear_resonance_alignment
# =============================================================================


class RefreshResonanceAlignmentTest(ResonanceCacheIsolationMixin, TestCase):
    """Tests for refresh_resonance_alignment and clear_resonance_alignment.

    Seed two ALIGNED boon tiers (low + high min_magnitude) on a diagonal
    Celestial→Celestial interaction. Two room profiles — one that evaluates
    to LOW magnitude, one to HIGH magnitude — are used to verify band-selection
    and idempotent clearing.

    Cache-sensitive rows (AffinityInteraction, ResonanceAlignmentBoonTier) are
    created in setUp AFTER super().setUp() per ResonanceCacheIsolationMixin docs.
    """

    def _boon_condition_template_pks(self) -> set[int]:
        """Return the set of PKs of all boon ConditionTemplates (from the manager cache)."""
        return {t.pk for t in ResonanceAlignmentBoonTier.objects.boon_condition_templates()}

    def _boon_instances_on(self, character: ObjectDB) -> list:
        """Return ConditionInstance rows on character whose template is a boon template."""
        boon_pks = self._boon_condition_template_pks()
        return list(
            ConditionInstance.objects.filter(
                target=character,
                condition__pk__in=boon_pks,
            )
        )

    def setUp(self) -> None:
        super().setUp()  # clears manager caches — create cache-sensitive data AFTER this

        # --- Affinities and resonances ---
        self.celestial = AffinityFactory(name="Celestial")
        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)

        # --- ALIGNED diagonal interaction: Celestial caster in Celestial room ---
        self.aligned_interaction = AffinityInteractionFactory(
            source_affinity=self.celestial,
            environment_affinity=self.celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # --- Two boon tiers: low threshold (min=1) and high threshold (min=5) ---
        self.low_buff = ConditionTemplateFactory(name="Celestial Warmth")
        self.high_buff = ConditionTemplateFactory(name="Celestial Radiance")

        low_tier = ResonanceAlignmentBoonTier(
            affinity_interaction=self.aligned_interaction,
            min_magnitude=1,
            condition_template=self.low_buff,
        )
        low_tier.full_clean()
        low_tier.save()
        self.low_tier = low_tier

        high_tier = ResonanceAlignmentBoonTier(
            affinity_interaction=self.aligned_interaction,
            min_magnitude=5,
            condition_template=self.high_buff,
        )
        high_tier.full_clean()
        high_tier.save()
        self.high_tier = high_tier

        # --- Room A: LOW resonance magnitude (value=1 → magnitude stays low) ---
        self.low_room_profile = RoomProfileFactory()
        _set_room_resonance_value(self.low_room_profile, self.celestial_resonance, 1)

        # --- Room B: HIGH resonance magnitude (value=10 → magnitude > 5) ---
        self.high_room_profile = RoomProfileFactory()
        _set_room_resonance_value(self.high_room_profile, self.celestial_resonance, 10)

        # --- Character sheet with Celestial-dominant aura (dominant = "celestial") ---
        self.sheet = CharacterSheetFactory()
        CharacterAuraFactory(
            character=self.sheet.character,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )

    def _place_character_in_room(self, character: ObjectDB, room_profile: RoomProfile) -> None:
        """Set character.location to the room backing the given RoomProfile."""
        character.db_location = room_profile.objectdb
        character.save(update_fields=["db_location"])

    def test_aligned_low_magnitude_applies_low_band_buff(self) -> None:
        """Character in low-magnitude aligned room → low-band buff applied."""
        self._place_character_in_room(self.sheet.character, self.low_room_profile)

        refresh_resonance_alignment(character_sheet=self.sheet)

        instances = self._boon_instances_on(self.sheet.character)
        self.assertEqual(len(instances), 1, "Expected exactly one boon ConditionInstance")
        self.assertEqual(instances[0].condition_id, self.low_buff.pk)

    def test_refresh_in_higher_magnitude_room_replaces_buff(self) -> None:
        """Moving to a higher-magnitude aligned room replaces old buff with high-band buff,
        leaving exactly one resonance-alignment ConditionInstance."""
        # First: place in low room → get low buff
        self._place_character_in_room(self.sheet.character, self.low_room_profile)
        refresh_resonance_alignment(character_sheet=self.sheet)

        low_instances = self._boon_instances_on(self.sheet.character)
        self.assertEqual(len(low_instances), 1)
        self.assertEqual(low_instances[0].condition_id, self.low_buff.pk)

        # Now move to high room → low buff cleared, high buff applied
        self._place_character_in_room(self.sheet.character, self.high_room_profile)
        refresh_resonance_alignment(character_sheet=self.sheet)

        instances = self._boon_instances_on(self.sheet.character)
        self.assertEqual(
            len(instances), 1, "Expected exactly one boon ConditionInstance after upgrade"
        )
        self.assertEqual(instances[0].condition_id, self.high_buff.pk)

    def test_non_aligned_room_removes_buff(self) -> None:
        """Refresh when character is in a non-aligned room removes any buff, applies none."""
        # Plant a buff first
        self._place_character_in_room(self.sheet.character, self.low_room_profile)
        refresh_resonance_alignment(character_sheet=self.sheet)
        self.assertEqual(len(self._boon_instances_on(self.sheet.character)), 1)

        # Create a room with NO resonance (evaluate_resonance_environment → inert)
        empty_room_profile = RoomProfileFactory()
        # No resonance tagged → inert → buff should clear
        self._place_character_in_room(self.sheet.character, empty_room_profile)

        refresh_resonance_alignment(character_sheet=self.sheet)

        self.assertEqual(len(self._boon_instances_on(self.sheet.character)), 0)

    def test_no_aura_no_buff_no_error(self) -> None:
        """Character with no CharacterAura → no buff applied, no exception."""
        sheet_no_aura = CharacterSheetFactory()
        CharacterAura.objects.filter(character=sheet_no_aura.character).delete()
        self._place_character_in_room(sheet_no_aura.character, self.low_room_profile)

        refresh_resonance_alignment(character_sheet=sheet_no_aura)

        self.assertEqual(len(self._boon_instances_on(sheet_no_aura.character)), 0)

    def test_room_with_no_profile_clears_existing_buff(self) -> None:
        """Room with no RoomProfile → no buff; any prior buff is cleared first."""
        # Apply a buff in an aligned room first
        self._place_character_in_room(self.sheet.character, self.low_room_profile)
        refresh_resonance_alignment(character_sheet=self.sheet)
        self.assertEqual(len(self._boon_instances_on(self.sheet.character)), 1)

        # Now move character to an ObjectDB room that has no RoomProfile
        bare_room = ObjectDB.objects.create(
            db_key="BareRoom",
            db_typeclass_path="typeclasses.objects.Object",
        )
        self.sheet.character.db_location = bare_room
        self.sheet.character.save(update_fields=["db_location"])

        refresh_resonance_alignment(character_sheet=self.sheet)

        # Buff must be gone
        self.assertEqual(len(self._boon_instances_on(self.sheet.character)), 0)

    def test_idempotent_two_refreshes_same_room_one_buff(self) -> None:
        """Two refreshes in the same aligned room → still exactly one buff instance."""
        self._place_character_in_room(self.sheet.character, self.low_room_profile)

        refresh_resonance_alignment(character_sheet=self.sheet)
        refresh_resonance_alignment(character_sheet=self.sheet)

        instances = self._boon_instances_on(self.sheet.character)
        self.assertEqual(len(instances), 1, "Expected exactly one buff after two refreshes")

    def test_clear_resonance_alignment_removes_buff(self) -> None:
        """clear_resonance_alignment removes an existing buff."""
        self._place_character_in_room(self.sheet.character, self.low_room_profile)
        refresh_resonance_alignment(character_sheet=self.sheet)
        self.assertEqual(len(self._boon_instances_on(self.sheet.character)), 1)

        clear_resonance_alignment(character_sheet=self.sheet)

        self.assertEqual(len(self._boon_instances_on(self.sheet.character)), 0)

    def test_clear_resonance_alignment_noop_when_none_present(self) -> None:
        """clear_resonance_alignment is a no-op when no buff is present (no exception)."""
        self.assertEqual(len(self._boon_instances_on(self.sheet.character)), 0)

        # Should not raise
        clear_resonance_alignment(character_sheet=self.sheet)


# =============================================================================
# T8 — use_technique orchestrator wires resonance_environment_for_cast (Step 10)
# =============================================================================


class UseTechniqueResonanceEnvironmentIntegrationTest(ResonanceCacheIsolationMixin, TestCase):
    """Integration tests: Step 10 fires through use_technique, not by direct service call.

    (16) OPPOSED cast in cascade room with seeded pool → ConditionInstance applied
         on the caster via use_technique. Proves Step 10 is wired in the orchestrator.
    (17) Cast in room with no RoomProfile → no error, no ConditionInstance applied.
    """

    def setUp(self) -> None:
        super().setUp()  # clears manager caches — create cache-sensitive data AFTER

        # --- Affinities and resonances ---
        self.abyssal = AffinityFactory(name="Abyssal")
        self.celestial = AffinityFactory(name="Celestial")
        self.abyssal_resonance = ResonanceFactory(affinity=self.abyssal)
        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)

        # --- Room with celestial cascade resonance (high value → non-zero magnitude) ---
        self.room_profile = RoomProfileFactory()
        room_mod = tag_room_resonance(self.room_profile, self.celestial_resonance)
        room_mod.value = 50
        room_mod.save(update_fields=["value"])
        self.room_obj = self.room_profile.objectdb

        # --- Technique: abyssal gift cast into celestial room (OPPOSED pair) ---
        self.gift = GiftFactory()
        self.gift.resonances.add(self.abyssal_resonance)
        self.technique = TechniqueFactory(
            gift=self.gift,
            intensity=5,
            control=10,
            anima_cost=3,
        )

        # --- Caster: CharacterSheet + CharacterAura + CharacterAnima ---
        self.anima = CharacterAnimaFactory(current=20, maximum=20)
        self.character = self.anima.character
        CharacterEngagementFactory(character=self.character)
        # Place character in the room
        self.character.db_location = self.room_obj
        self.character.save(update_fields=["db_location"])

        # CharacterSheet linked to this character
        self.sheet = CharacterSheetFactory(character=self.character)
        CharacterAuraFactory(
            character=self.character,
            celestial=Decimal("10.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("70.00"),
        )

        # --- Authored consequence pool for backfire ---
        self.outcome_failure = CheckOutcomeFactory(name="Failure_t8", success_level=-1)
        self.backfire_condition = ConditionTemplateFactory(name="HallowedBurn_t8")

        self.pool = ConsequencePoolFactory(name="OpposedBackfire_t8")
        self.consequence = ConsequenceFactory(
            outcome_tier=self.outcome_failure,
            label="Burned by hallowed ground",
        )
        ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=self.backfire_condition,
        )
        ConsequencePoolEntryFactory(pool=self.pool, consequence=self.consequence)

        # --- OPPOSED REJECT interaction with seeded pool ---
        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
            consequence_pool=self.pool,
        )

        # The endure_hallowed_ground CheckType must exist (service uses get(), not get_or_create)
        self.endure_check_type = CheckTypeFactory(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME)

    def test_opposed_cast_via_orchestrator_applies_backfire_condition(self) -> None:
        """OPPOSED cast through use_technique → ConditionInstance applied on caster.

        Drives use_technique (not resonance_environment_for_cast directly) so that
        Step 10 integration is what is being exercised. Forces the backfire check to
        return the failure outcome deterministically via perform_check patch.
        """
        check_result = _make_check_result(self.outcome_failure)
        with patch(
            "world.magic.services.resonance_environment.perform_check",
            return_value=check_result,
        ):
            result = use_technique(
                character=self.character,
                technique=self.technique,
                resolve_fn=lambda: "resolved",
            )

        # use_technique should complete successfully
        self.assertTrue(result.confirmed)

        # The backfire ConditionInstance must be on the caster — wired by Step 10
        instances = ConditionInstance.objects.filter(
            target=self.character,
            condition=self.backfire_condition,
        )
        self.assertTrue(
            instances.exists(),
            "Expected backfire ConditionInstance from resonance_environment_for_cast "
            "wired through use_technique Step 10",
        )

    def test_cast_in_room_without_room_profile_no_error_no_condition(self) -> None:
        """Cast in a room with no RoomProfile → no error; Step 10 silently skips.

        No ConditionInstance should be created. This is the "bare room" guard: the
        orchestrator must handle RoomProfile.DoesNotExist without propagating it.
        """
        from evennia.objects.models import ObjectDB

        # Create a bare room ObjectDB with no RoomProfile attached
        bare_room = ObjectDB.objects.create(
            db_key="BareRoomT8",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.db_location = bare_room
        self.character.save(update_fields=["db_location"])

        # Should not raise; Step 10 must guard against missing RoomProfile
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda: "resolved",
        )

        self.assertTrue(result.confirmed)
        self.assertEqual(
            ConditionInstance.objects.filter(target=self.character).count(),
            0,
            "No ConditionInstance should be created when room has no RoomProfile",
        )


class ClearResonanceAlignmentQueryCountTest(ResonanceCacheIsolationMixin, TestCase):
    """Query-count regression guard for clear_resonance_alignment hot-path.

    Proves that clear_resonance_alignment costs ZERO repeated queries on the warm
    handler path — the realistic per-move state after at_post_move has been invoked
    at least once.  The old ``get_active_conditions``-per-call implementation issued
    one SELECT every time regardless; the new handler-based path issues zero after the
    first load.

    RED against the old implementation (get_active_conditions fires on every call →
    assertNumQueries(0) fails).  GREEN after the handler rework (Python filter over
    cached list → zero queries).
    """

    def setUp(self) -> None:
        super().setUp()  # clears manager caches — create cache-sensitive data AFTER this

        # Seed affinities and a Celestial→Celestial ALIGNED interaction
        self.celestial = AffinityFactory(name="Celestial")
        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)

        self.aligned_interaction = AffinityInteractionFactory(
            source_affinity=self.celestial,
            environment_affinity=self.celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # Seed FOUR boon tiers so N is clearly > 1 — old per-template code would scale here.
        self.boon_templates = []
        for i in range(4):
            tmpl = ConditionTemplateFactory(name=f"QueryCountBoonTier{i}")
            tier = ResonanceAlignmentBoonTier(
                affinity_interaction=self.aligned_interaction,
                min_magnitude=i + 1,
                condition_template=tmpl,
            )
            tier.full_clean()
            tier.save()
            self.boon_templates.append(tmpl)

        # Character with Celestial-dominant aura — NOT in any aligned room
        self.sheet = CharacterSheetFactory()
        CharacterAuraFactory(
            character=self.sheet.character,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )
        # Guarantee no buff is currently on this character
        ConditionInstance.objects.filter(target=self.sheet.character).delete()

    def test_no_buff_warm_handler_zero_queries(self) -> None:
        """clear_resonance_alignment with a warm handler and no buff → ZERO queries.

        Simulates the realistic per-move state: both caches have been warmed — the
        boon_condition_templates manager cache (warmed by first call) and the
        character.conditions handler cache (warmed by first active() access).  The
        common no-buff case (non-aligned room / non-magical character) must not hit the DB.

        RED against the old get_active_conditions-per-call implementation (always 1+
        query per call regardless of handler state).
        GREEN after the handler rework (Python filter over cached list → 0 queries).
        """
        # Warm the boon_condition_templates manager cache (fires 1 query, then cached).
        boon_tmpl_set = ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        self.assertEqual(len(boon_tmpl_set), 4, "Expected 4 seeded boon templates")

        # Warm the conditions handler — simulates any prior access in the same move cycle.
        _ = self.sheet.character.conditions.active()

        # After both warm-ups, clear must cost ZERO queries (Python filter only).
        with self.assertNumQueries(0):
            clear_resonance_alignment(character_sheet=self.sheet)

    def test_query_count_does_not_scale_with_template_count(self) -> None:
        """Adding more boon templates must not increase the (already zero) query count.

        Adds a fifth template, re-warms the handler, repeats assertNumQueries(0).
        Proves the count is O(1) [actually O(0)] not O(N).
        """
        # Add a fifth boon tier
        extra_tmpl = ConditionTemplateFactory(name="QueryCountBoonTier4")
        extra_tier = ResonanceAlignmentBoonTier(
            affinity_interaction=self.aligned_interaction,
            min_magnitude=5,
            condition_template=extra_tmpl,
        )
        extra_tier.full_clean()
        extra_tier.save()

        # Invalidate the cached frozenset so it picks up the new tier
        ResonanceAlignmentBoonTier.objects.clear_cache()

        # Re-warm both caches: boon_templates (fires 1 query) + conditions handler.
        boon_tmpl_set = ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        self.assertEqual(len(boon_tmpl_set), 5, "Expected 5 boon templates after addition")
        _ = self.sheet.character.conditions.active()

        with self.assertNumQueries(0):
            clear_resonance_alignment(character_sheet=self.sheet)

    def test_handler_invalidation_correctness(self) -> None:
        """Handler invalidation ensures clear sees the buff applied by a prior refresh.

        Sequence:
          1. Warm handler (empty active list — no buff).
          2. refresh_resonance_alignment applies a buff → apply_condition invalidates handler.
          3. A second clear_resonance_alignment re-loads the handler (now sees the buff) and
             removes it.

        If the clear read a stale (pre-apply) handler cache the buff would be invisible and
        the second clear would be a no-op — leaving the buff in place.  This proves T7a
        invalidation is wired correctly end-to-end.
        """
        # Create a room + aura so refresh can apply a buff
        room_profile = RoomProfileFactory()
        _set_room_resonance_value(room_profile, self.celestial_resonance, 10)
        self.sheet.character.db_location = room_profile.objectdb
        self.sheet.character.save(update_fields=["db_location"])

        # Step 1: Warm the handler — sees empty active list.
        initial_active = self.sheet.character.conditions.active()
        self.assertEqual(len(initial_active), 0, "Handler should be empty before any buff")

        # Step 2: refresh_resonance_alignment applies a buff.  apply_condition inside
        # refresh must call _invalidate_condition_handler, which drops the stale cache.
        refresh_resonance_alignment(character_sheet=self.sheet)

        boon_tmpl_pks = {t.pk for t in self.boon_templates}
        db_instances = list(
            ConditionInstance.objects.filter(
                target=self.sheet.character, condition__pk__in=boon_tmpl_pks
            )
        )
        self.assertEqual(len(db_instances), 1, "Expected buff in DB after refresh")

        # Step 3: clear_resonance_alignment must see the buff (not the stale empty cache)
        # and remove it.
        clear_resonance_alignment(character_sheet=self.sheet)

        db_instances_after = list(
            ConditionInstance.objects.filter(
                target=self.sheet.character, condition__pk__in=boon_tmpl_pks
            )
        )
        self.assertEqual(
            len(db_instances_after),
            0,
            "clear_resonance_alignment must see and remove the buff applied by refresh "
            "(proves handler invalidation is wired correctly, not reading stale cache)",
        )
