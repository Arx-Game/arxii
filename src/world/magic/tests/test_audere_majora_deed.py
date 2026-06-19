"""Tests for _mint_crossing_deed wired into cross_threshold and
resolve_audere_majora_offer (#953).

Four cases:
  1. Happy path: mint + attribution + witnesses.
  2. No primary persona → no-op (legend_entry stays None).
  3. scene=None → deed minted, zero PersonaDeedKnowledge rows.
  4. End-to-end: resolve_audere_majora_offer accept mints deed via the real entry point.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.audere_majora import (
    AudereMajoraCrossing,
    cross_threshold,
    resolve_audere_majora_offer,
)
from world.magic.factories import wire_audere_power_multipliers
from world.magic.tests.majora_fixtures import build_crossing_world
from world.scenes.constants import PersonaType
from world.scenes.factories import SceneFactory
from world.scenes.models import Persona
from world.societies.constants import DeedKnowledgeSource, RenownMagnitude, RenownReach, RenownRisk
from world.societies.models import PersonaDeedKnowledge


def _set_deed_risk(threshold) -> None:
    """Stamp non-NONE renown fields on a threshold so a crossing mints a legend deed."""
    threshold.risk = RenownRisk.HIGH
    threshold.magnitude = RenownMagnitude.HIGH
    threshold.reach = RenownReach.REGIONAL
    threshold.save(update_fields=["risk", "magnitude", "reach"])


class MintCrossingDeedWithWitnessesTests(TestCase):
    """Crossing mints a deed attributed to the crosser's primary persona."""

    @classmethod
    def setUpTestData(cls):
        wire_audere_power_multipliers()

        (
            cls.character,
            cls.sheet,
            cls.threshold,
            cls.prospect_path,
            cls.puissant_path,
            cls.offer,
        ) = build_crossing_world(boundary_level=30, suffix="_deed_mint")
        _set_deed_risk(cls.threshold)

        # Active scene at the crosser's location.
        cls.scene = SceneFactory(location=cls.character.location, is_active=True)

    def setUp(self):
        cross_threshold(
            self.sheet,
            self.threshold,
            self.puissant_path,
            declaration_text="I cross the threshold.",
        )
        self.receipt = AudereMajoraCrossing.objects.get(
            character_sheet=self.sheet, threshold=self.threshold
        )

    def test_legend_entry_is_set(self):
        self.assertIsNotNone(self.receipt.legend_entry)

    def test_legend_entry_attributed_to_primary_persona(self):
        entry = self.receipt.legend_entry
        self.assertIsNotNone(entry)
        self.assertEqual(entry.persona, self.sheet.primary_persona)

    def test_no_spoiler_text_in_title(self):
        entry = self.receipt.legend_entry
        self.assertIsNotNone(entry)
        self.assertNotIn(self.threshold.vision_text, entry.title)
        self.assertNotIn(self.threshold.manifestation_text, entry.title)

    def test_no_spoiler_text_in_description(self):
        entry = self.receipt.legend_entry
        self.assertIsNotNone(entry)
        self.assertNotIn(self.threshold.manifestation_text, entry.description or "")


class MintCrossingDeedWitnessesRecordedTests(TestCase):
    """Witnesses (other personas on-scene) are granted deed knowledge."""

    @classmethod
    def setUpTestData(cls):
        wire_audere_power_multipliers()

        (
            cls.character,
            cls.sheet,
            cls.threshold,
            cls.prospect_path,
            cls.puissant_path,
            cls.offer,
        ) = build_crossing_world(boundary_level=31, suffix="_deed_wit")
        _set_deed_risk(cls.threshold)

        # Scene at the crosser's location.
        cls.scene = SceneFactory(location=cls.character.location, is_active=True)

        # A witness: separate sheet with a primary persona.
        cls.witness_sheet = CharacterSheetFactory()
        cls.witness_persona = cls.witness_sheet.primary_persona

    def setUp(self):
        from world.scenes.constants import InteractionMode
        from world.scenes.interaction_services import create_interaction

        # Post a witness interaction so scene_witness_personas picks them up.
        create_interaction(
            persona=self.witness_persona,
            content="I witness this.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )

        cross_threshold(
            self.sheet,
            self.threshold,
            self.puissant_path,
            declaration_text="I cross.",
        )
        self.receipt = AudereMajoraCrossing.objects.get(
            character_sheet=self.sheet, threshold=self.threshold
        )

    def test_witness_has_deed_knowledge(self):
        entry = self.receipt.legend_entry
        self.assertIsNotNone(entry)
        self.assertTrue(
            PersonaDeedKnowledge.objects.filter(
                deed=entry,
                persona=self.witness_persona,
                source=DeedKnowledgeSource.WITNESSED,
            ).exists()
        )

    def test_crosser_has_no_deed_knowledge_row(self):
        """Doer has no PersonaDeedKnowledge row (implicit knowledge via LegendEntry.persona)."""
        entry = self.receipt.legend_entry
        self.assertIsNotNone(entry)
        self.assertFalse(
            PersonaDeedKnowledge.objects.filter(
                deed=entry,
                persona=self.sheet.primary_persona,
            ).exists()
        )


class MintCrossingDeedNoPrimaryPersonaTests(TestCase):
    """When the sheet has no PRIMARY persona, crossing no-ops on the deed."""

    @classmethod
    def setUpTestData(cls):
        wire_audere_power_multipliers()

        (
            cls.character,
            cls.sheet,
            cls.threshold,
            cls.prospect_path,
            cls.puissant_path,
            cls.offer,
        ) = build_crossing_world(boundary_level=32, suffix="_deed_nopersona")
        _set_deed_risk(cls.threshold)

        # Remove the PRIMARY persona so _mint_crossing_deed hits the no-op branch.
        Persona.objects.filter(character_sheet=cls.sheet, persona_type=PersonaType.PRIMARY).delete()
        # Bust the cached_property.
        cls.sheet.__dict__.pop("primary_persona", None)

    def test_no_legend_entry_when_no_primary_persona(self):
        cross_threshold(
            self.sheet,
            self.threshold,
            self.puissant_path,
            declaration_text="I cross without a persona.",
        )
        receipt = AudereMajoraCrossing.objects.get(
            character_sheet=self.sheet, threshold=self.threshold
        )
        self.assertIsNone(receipt.legend_entry)


class MintCrossingDeedNoSceneTests(TestCase):
    """When there is no active scene, deed is still minted but zero witnesses recorded."""

    @classmethod
    def setUpTestData(cls):
        wire_audere_power_multipliers()

        (
            cls.character,
            cls.sheet,
            cls.threshold,
            cls.prospect_path,
            cls.puissant_path,
            cls.offer,
        ) = build_crossing_world(boundary_level=33, suffix="_deed_noscene")
        _set_deed_risk(cls.threshold)
        # Deliberately no active scene at cls.character.location.

    def test_deed_minted_with_zero_witnesses(self):
        cross_threshold(
            self.sheet,
            self.threshold,
            self.puissant_path,
            declaration_text="Alone in the dark.",
        )
        receipt = AudereMajoraCrossing.objects.get(
            character_sheet=self.sheet, threshold=self.threshold
        )
        self.assertIsNotNone(receipt.legend_entry)
        entry = receipt.legend_entry
        witness_count = PersonaDeedKnowledge.objects.filter(deed=entry).count()
        self.assertEqual(witness_count, 0)


class ResolveOfferAcceptMintsDeedE2ETests(TestCase):
    """resolve_audere_majora_offer accept end-to-end: deed minted and attributed to crosser."""

    @classmethod
    def setUpTestData(cls):
        wire_audere_power_multipliers()

        (
            cls.character,
            cls.sheet,
            cls.threshold,
            cls.prospect_path,
            cls.chosen_path,
            cls.offer,
        ) = build_crossing_world(boundary_level=34, suffix="_deed_e2e")
        _set_deed_risk(cls.threshold)

    def test_resolve_accept_mints_deed_end_to_end(self):
        result = resolve_audere_majora_offer(
            self.offer.pk,
            accept=True,
            path_id=self.chosen_path.pk,
            declaration_text="I cross the threshold.",
        )
        self.assertTrue(result.accepted)
        receipt = AudereMajoraCrossing.objects.get(character_sheet=self.sheet)
        self.assertIsNotNone(receipt.legend_entry)
        self.assertEqual(receipt.legend_entry.persona, self.sheet.primary_persona)
