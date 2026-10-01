"""Schema invariants for ultimates (#4098)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.admin import PathGiftGrantAdminForm
from world.magic.constants import GiftKind
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    KnownUltimateFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    UltimateTechniqueFactory,
)


class KnownUltimateConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.first = UltimateTechniqueFactory()
        cls.second = UltimateTechniqueFactory()

    def test_one_row_per_character_and_ultimate(self) -> None:
        KnownUltimateFactory(character=self.sheet, technique=self.first)
        with self.assertRaises(IntegrityError), transaction.atomic():
            KnownUltimateFactory(character=self.sheet, technique=self.first)

    def test_only_one_readied_per_character(self) -> None:
        KnownUltimateFactory(character=self.sheet, technique=self.first, readied=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            KnownUltimateFactory(character=self.sheet, technique=self.second, readied=True)


class TechniqueUltimateCleanTests(TestCase):
    def test_flagging_known_technique_as_ultimate_refused(self) -> None:
        technique = TechniqueFactory()
        CharacterTechniqueFactory(technique=technique)
        technique.is_ultimate = True
        with self.assertRaises(ValidationError):
            technique.clean()

    def test_flagging_starter_technique_as_ultimate_refused(self) -> None:
        technique = TechniqueFactory()
        grant = PathGiftGrantFactory(gift=technique.gift)
        grant.starter_techniques.add(technique)
        technique.is_ultimate = True
        with self.assertRaises(ValidationError):
            technique.clean()

    def test_fresh_technique_may_be_ultimate(self) -> None:
        technique = UltimateTechniqueFactory()
        technique.clean()
        technique.save()
        technique.refresh_from_db()
        self.assertTrue(technique.is_ultimate)


class PathGiftGrantAdminFormTests(TestCase):
    def _form(self, grant, ultimates):
        data = {
            "path": grant.path_id,
            "gift": grant.gift_id,
            "starter_techniques": [],
            "ultimate_techniques": [t.pk for t in ultimates],
        }
        return PathGiftGrantAdminForm(data=data, instance=grant)

    def test_ultimate_on_minor_gift_refused(self) -> None:
        gift = GiftFactory(kind=GiftKind.MINOR)
        grant = PathGiftGrantFactory(gift=gift)
        form = self._form(grant, [UltimateTechniqueFactory(gift=gift)])
        self.assertFalse(form.is_valid())
        self.assertIn("ultimate_techniques", form.errors)

    def test_ultimate_from_other_gift_refused(self) -> None:
        grant = PathGiftGrantFactory()
        form = self._form(grant, [UltimateTechniqueFactory()])
        self.assertFalse(form.is_valid())

    def test_ordinary_technique_not_offered_as_ultimate(self) -> None:
        grant = PathGiftGrantFactory()
        form = self._form(grant, [TechniqueFactory(gift=grant.gift)])
        self.assertFalse(form.is_valid())  # limit_choices_to is_ultimate=True

    def test_valid_major_gift_ultimate_accepted(self) -> None:
        grant = PathGiftGrantFactory()
        form = self._form(grant, [UltimateTechniqueFactory(gift=grant.gift)])
        self.assertTrue(form.is_valid(), form.errors)


class AudereCopySeedTests(TestCase):
    def test_copy_fields_seed_with_placeholder_marker(self) -> None:
        threshold = AudereThresholdFactory()
        for field in (
            "reveal_framing_text",
            "deferred_death_text",
            "sword_reveal_label",
            "shield_reveal_label",
            "crown_reveal_label",
        ):
            self.assertIn("PLACEHOLDER", getattr(threshold, field), field)

    def test_label_for_category(self) -> None:
        threshold = AudereThresholdFactory(sword_reveal_label="Edge")
        self.assertEqual(threshold.label_for_category("sword"), "Edge")
