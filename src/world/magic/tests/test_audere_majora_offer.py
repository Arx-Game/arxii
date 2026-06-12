"""Tests for Audere Majora offer gates, cast hook, and manifestation broadcast (#543)."""

import importlib

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.classes.models import CharacterClassLevel, PathStage
from world.magic.audere import AUDERE_CONDITION_NAME
from world.magic.audere_majora import (
    AudereMajoraThreshold,
    PendingAudereMajoraOffer,
    check_audere_majora_eligibility,
    maybe_create_audere_majora_offer,
)
from world.magic.tests.majora_fixtures import build_majora_world
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction


def _build_eligible_character():
    """Build a fully-eligible character for Audere Majora offer tests.

    Uses boundary_level=15 to avoid colliding with the model tests (which use 5 and 10).
    Returns (character, sheet, threshold, soulfray_stage, prospect_path, puissant_path).
    """
    # Intensity tier at threshold=10; runtime_intensity=20 passes the gate (20 >= 10).
    # Suffix "_t3" isolates these names from other test modules that use similar levels.
    character, sheet, threshold, prospect_path, puissant_path, soulfray_stage = build_majora_world(
        boundary_level=15,
        suffix="_offer_t3",
    )
    return character, sheet, threshold, soulfray_stage, prospect_path, puissant_path


class AudereMajoraEligibilityGateTests(TestCase):
    """check_audere_majora_eligibility: all gates must pass."""

    def setUp(self) -> None:
        (
            self.character,
            self.sheet,
            self.threshold,
            self.soulfray_stage,
            self.prospect_path,
            self.puissant_path,
        ) = _build_eligible_character()
        # Runtime intensity 20 is above the tier threshold of 10 → gate passes.
        self.passing_intensity = 20

    def test_all_gates_met_returns_threshold(self) -> None:
        result = check_audere_majora_eligibility(self.character, self.passing_intensity)
        assert result is not None
        assert result.pk == self.threshold.pk

    def test_wrong_level_14_returns_none(self) -> None:
        # Delete + recreate to evict the SharedMemoryModel identity-map cache.
        ccl = CharacterClassLevel.objects.get(character=self.character)
        ccl.flush_from_cache()
        CharacterClassLevel.objects.filter(character=self.character).delete()
        CharacterClassLevel.objects.create(
            character=self.character,
            character_class=ccl.character_class,
            level=14,
            is_primary=True,
        )
        self.sheet.invalidate_class_level_cache()
        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None

    def test_wrong_level_16_returns_none(self) -> None:
        # Delete + recreate to evict the SharedMemoryModel identity-map cache.
        ccl = CharacterClassLevel.objects.get(character=self.character)
        ccl.flush_from_cache()
        CharacterClassLevel.objects.filter(character=self.character).delete()
        CharacterClassLevel.objects.create(
            character=self.character,
            character_class=ccl.character_class,
            level=16,
            is_primary=True,
        )
        self.sheet.invalidate_class_level_cache()
        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None

    def test_existing_crossing_returns_none(self) -> None:
        from world.magic.audere_majora import AudereMajoraCrossing

        AudereMajoraCrossing.objects.create(
            character_sheet=self.sheet,
            threshold=self.threshold,
            chosen_path=self.puissant_path,
            level_before=14,
            level_after=15,
        )
        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None

    def test_requires_active_audere_true_without_condition_returns_none(self) -> None:
        from world.conditions.models import ConditionInstance

        ConditionInstance.objects.filter(
            target=self.character,
            condition__name=AUDERE_CONDITION_NAME,
        ).delete()
        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None

    def test_requires_active_audere_false_without_condition_returns_threshold(self) -> None:
        from world.conditions.models import ConditionInstance

        AudereMajoraThreshold.objects.filter(pk=self.threshold.pk).update(
            requires_active_audere=False
        )
        # flush_from_cache evicts the cached instance so the next get() re-reads from DB.
        self.threshold.flush_from_cache()
        self.threshold = AudereMajoraThreshold.objects.get(pk=self.threshold.pk)
        ConditionInstance.objects.filter(
            target=self.character,
            condition__name=AUDERE_CONDITION_NAME,
        ).delete()
        result = check_audere_majora_eligibility(self.character, self.passing_intensity)
        assert result is not None

    def test_no_eligible_child_path_returns_none(self) -> None:
        self.puissant_path.is_active = False
        self.puissant_path.save(update_fields=["is_active"])
        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None

    def test_wrong_stage_child_path_returns_none(self) -> None:
        self.puissant_path.stage = PathStage.TRUE
        self.puissant_path.save(update_fields=["stage"])
        assert check_audere_majora_eligibility(self.character, self.passing_intensity) is None


class AudereMajoraOfferServiceTests(TestCase):
    """maybe_create_audere_majora_offer: idempotency, FK snapshot, broadcast."""

    def setUp(self) -> None:
        (
            self.character,
            self.sheet,
            self.threshold,
            self.soulfray_stage,
            self.prospect_path,
            self.puissant_path,
        ) = _build_eligible_character()
        self.passing_intensity = 20

    def test_creates_offer_on_first_qualifying_call(self) -> None:
        offer = maybe_create_audere_majora_offer(self.character, self.passing_intensity)

        assert offer is not None
        assert offer.threshold == self.threshold
        assert offer.fired_intensity == self.passing_intensity
        assert offer.soulfray_stage_order == self.soulfray_stage.stage_order
        assert offer.character_sheet == self.sheet

    def test_repeat_qualifying_call_keeps_single_row(self) -> None:
        maybe_create_audere_majora_offer(self.character, self.passing_intensity)
        maybe_create_audere_majora_offer(self.character, self.passing_intensity)

        assert PendingAudereMajoraOffer.objects.filter(character_sheet=self.sheet).count() == 1

    def test_ineligible_cast_returns_none(self) -> None:
        # Intensity 1 is below any tier threshold (minimum is 10)
        offer = maybe_create_audere_majora_offer(self.character, 1)
        assert offer is None
        assert not PendingAudereMajoraOffer.objects.filter(character_sheet=self.sheet).exists()

    def test_scene_emit_interaction_created_on_first_call(self) -> None:
        # Create an active scene at the character's location
        room = self.character.location
        scene = SceneFactory(location=room, is_active=True)

        maybe_create_audere_majora_offer(self.character, self.passing_intensity)

        emits = Interaction.objects.filter(scene=scene, mode=InteractionMode.EMIT)
        assert emits.count() == 1
        assert emits.first().content == self.threshold.manifestation_text

    def test_scene_emit_not_repeated_on_refresh(self) -> None:
        room = self.character.location
        scene = SceneFactory(location=room, is_active=True)

        maybe_create_audere_majora_offer(self.character, self.passing_intensity)
        maybe_create_audere_majora_offer(self.character, self.passing_intensity)

        emits = Interaction.objects.filter(scene=scene, mode=InteractionMode.EMIT)
        assert emits.count() == 1

    def test_no_scene_no_interaction_created(self) -> None:
        offer = maybe_create_audere_majora_offer(self.character, self.passing_intensity)
        assert offer is not None
        assert Interaction.objects.filter(mode=InteractionMode.EMIT).count() == 0

    def test_npc_without_sheet_returns_none(self) -> None:
        npc = ObjectDB.objects.create(db_key="majora_npc_no_sheet_t3")
        assert maybe_create_audere_majora_offer(npc, self.passing_intensity) is None

    def test_sheet_without_primary_persona_skips_broadcast(self) -> None:
        """primary_persona raises Persona.DoesNotExist — broadcast must no-op, not blow up."""
        from world.scenes.models import Persona

        room = self.character.location
        SceneFactory(location=room, is_active=True)
        Persona.objects.filter(character_sheet=self.sheet).delete()

        offer = maybe_create_audere_majora_offer(self.character, self.passing_intensity)

        assert offer is not None
        assert Interaction.objects.filter(mode=InteractionMode.EMIT).count() == 0


class CastHookImportSmokeTest(TestCase):
    """Ensure world.magic.services.techniques can be imported without cycle errors."""

    def test_techniques_module_imports_cleanly(self) -> None:
        mod = importlib.import_module("world.magic.services.techniques")
        assert mod is not None
