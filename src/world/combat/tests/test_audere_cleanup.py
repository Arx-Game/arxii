"""Encounter cleanup ends Audere (reverting modifiers) and deletes pending offers (#873, #543)."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterOutcome
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import cleanup_completed_encounter
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import ConditionInstance
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    AUDERE_MAJORA_CONDITION_NAME,
    PendingAudereOffer,
    offer_audere,
)
from world.magic.audere_majora import PendingAudereMajoraOffer
from world.magic.factories import (
    CharacterAnimaFactory,
    IntensityTierFactory,
    PendingAudereOfferFactory,
    wire_audere_power_multipliers,
)
from world.magic.tests.audere_test_helpers import build_audere_gate_fixture
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import CharacterVitals
from world.vitals.services import defer_or_apply_certain_death


class CleanupAudereTeardownTests(TestCase):
    """cleanup_completed_encounter must end Audere via end_audere (reverting the
    engagement intensity modifier and anima-pool expansion) BEFORE the generic
    end-of-combat condition sweep strips the condition, and must delete any
    unanswered PendingAudereOffer rows for participants."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gate = build_audere_gate_fixture(tier_suffix="cleanup")
        cls.obj_ct = ContentType.objects.get_for_model(ObjectDB)

    def setUp(self) -> None:
        # A real typeclassed object — bare ObjectDB rows lack the ObjectParent
        # mixin (no trigger_handler) and can't exist in production.
        self.character = ObjectDBFactory(db_key="audere_cleanup_char")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.anima = CharacterAnimaFactory(
            character=self.character.sheet_data, current=10, maximum=50
        )
        self.engagement = CharacterEngagement.objects.create(
            character=self.character.sheet_data,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.obj_ct,
            source_id=self.character.pk,
        )
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )

    def test_cleanup_ends_audere_and_reverts_modifiers(self) -> None:
        original_maximum = self.anima.maximum
        result = offer_audere(self.character, accept=True)
        assert result.accepted is True

        cleanup_completed_encounter(self.encounter)

        self.engagement.refresh_from_db()
        self.anima.refresh_from_db()
        assert self.engagement.intensity_modifier == 0
        assert self.anima.maximum == original_maximum
        assert self.anima.pre_audere_maximum is None
        assert not ConditionInstance.objects.filter(
            target=self.character, condition__name=AUDERE_CONDITION_NAME
        ).exists()

    def test_cleanup_deletes_pending_offers(self) -> None:
        PendingAudereOfferFactory(character_sheet=self.sheet)

        cleanup_completed_encounter(self.encounter)

        assert not PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists()


class CleanupAuderaMajoraTeardownTests(TestCase):
    """cleanup_completed_encounter must end Audere Majora via end_audere_majora (removing
    the condition) and delete any unanswered PendingAudereMajoraOffer rows for participants
    (#543)."""

    def setUp(self) -> None:
        _audere, self.majora_template = wire_audere_power_multipliers()
        self.character = ObjectDBFactory(db_key="majora_cleanup_char")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )

    def test_cleanup_ends_audere_majora(self) -> None:
        ConditionInstanceFactory(
            target=self.character,
            condition=self.majora_template,
            current_stage=None,
        )

        cleanup_completed_encounter(self.encounter)

        assert not ConditionInstance.objects.filter(
            target=self.character, condition__name=AUDERE_MAJORA_CONDITION_NAME
        ).exists()

    def test_cleanup_deletes_pending_majora_offers(self) -> None:
        from world.classes.models import PathStage
        from world.conditions.factories import (
            ConditionStageFactory,
            ConditionTemplateFactory,
        )
        from world.magic.audere import SOULFRAY_CONDITION_NAME
        from world.magic.audere_majora import AudereMajoraThreshold

        tier = IntensityTierFactory(
            name="Major_majora_cleanup_tier", threshold=10, control_modifier=0
        )
        soulfray_t = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        warp_stage = ConditionStageFactory(condition=soulfray_t, stage_order=3, name="Ripping_mcu")
        threshold = AudereMajoraThreshold.objects.create(
            boundary_level=50,
            target_stage=PathStage.PUISSANT,
            minimum_intensity_tier=tier,
            minimum_warp_stage=warp_stage,
            requires_active_audere=False,
            vision_text="[PLACEHOLDER VISION]",
            manifestation_text="[PLACEHOLDER MANIFESTATION]",
        )
        PendingAudereMajoraOffer.objects.create(
            character_sheet=self.sheet,
            threshold=threshold,
            fired_intensity=20,
            soulfray_stage_order=3,
        )

        cleanup_completed_encounter(self.encounter)

        assert not PendingAudereMajoraOffer.objects.filter(character_sheet=self.sheet).exists()


class CleanupCertainDeathBackstopTests(TestCase):
    """cleanup_completed_encounter is a backstop for a deferred certain death whose
    death_deferred condition left the character without the ordinary
    conditions.services._resolve_deferred_death_on_expiry seam ever running
    (#4098 fix round 1) — e.g. a raw ConditionInstance delete bypassing
    remove_condition entirely, which the round-duration countdown and some
    interaction-removal/damage paths effectively do."""

    def setUp(self) -> None:
        self.audere, _majora = wire_audere_power_multipliers()
        self.character = ObjectDBFactory(db_key="certain_death_backstop_char")
        self.sheet = CharacterSheetFactory(character=self.character)
        CharacterVitalsFactory(character_sheet=self.sheet)
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )

    def _state(self) -> CharacterVitals:
        return CharacterVitals.objects.get(character_sheet=self.sheet)

    def test_backstop_applies_death_when_condition_left_without_the_expiry_seam(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        self.assertTrue(defer_or_apply_certain_death(self.sheet))
        self.assertTrue(self._state().death_certain_pending)

        # Raw delete — bypasses remove_condition, so
        # _resolve_deferred_death_on_expiry never runs.
        ConditionInstance.objects.filter(target=self.character, condition=self.audere).delete()

        cleanup_completed_encounter(self.encounter)

        state = self._state()
        self.assertEqual(state.life_state, CharacterLifeState.DEAD)
        self.assertFalse(state.death_certain_pending)


class CleanupAbandonedCertainDeathTests(TestCase):
    """An ABANDONED encounter cancels a pending certain death instead of applying
    it (#4098 owner ruling) — a GM closing a broken fight shouldn't kill anyone.
    The cancellation must beat the ordinary end_audere -> remove_condition ->
    _resolve_deferred_death_on_expiry seam, which would otherwise apply the death
    the moment cleanup removes the deferring Audere condition."""

    def setUp(self) -> None:
        self.audere, _majora = wire_audere_power_multipliers()
        self.character = ObjectDBFactory(db_key="abandoned_certain_death_char")
        self.sheet = CharacterSheetFactory(character=self.character)
        CharacterVitalsFactory(character_sheet=self.sheet)
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )

    def _state(self) -> CharacterVitals:
        return CharacterVitals.objects.get(character_sheet=self.sheet)

    def test_abandoned_outcome_clears_pending_death_and_leaves_character_alive(self) -> None:
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        self.assertTrue(defer_or_apply_certain_death(self.sheet))
        self.assertTrue(self._state().death_certain_pending)

        self.encounter.outcome = EncounterOutcome.ABANDONED
        self.encounter.save(update_fields=["outcome"])

        cleanup_completed_encounter(self.encounter)

        state = self._state()
        self.assertEqual(state.life_state, CharacterLifeState.ALIVE)
        self.assertFalse(state.death_certain_pending)
        # The Audere condition is still torn down as part of ordinary cleanup —
        # only the death itself is cancelled, not the condition teardown.
        self.assertFalse(
            ConditionInstance.objects.filter(target=self.character, condition=self.audere).exists()
        )

    def test_non_abandoned_outcome_still_applies_the_death(self) -> None:
        """A normally completed encounter (VICTORY, DEFEAT, FLED) is unaffected —
        the deferred death still applies through the ordinary end_audere ->
        remove_condition -> _resolve_deferred_death_on_expiry seam."""
        ConditionInstanceFactory(target=self.character, condition=self.audere)
        self.assertTrue(defer_or_apply_certain_death(self.sheet))
        self.assertTrue(self._state().death_certain_pending)

        self.encounter.outcome = EncounterOutcome.VICTORY
        self.encounter.save(update_fields=["outcome"])

        cleanup_completed_encounter(self.encounter)

        state = self._state()
        self.assertEqual(state.life_state, CharacterLifeState.DEAD)
        self.assertFalse(state.death_certain_pending)
