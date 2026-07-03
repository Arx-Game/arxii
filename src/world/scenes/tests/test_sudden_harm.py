"""Tests for world.scenes.sudden_harm (#1316).

Deviates from the plan's literal pytest-style sketch: this repo's test runner is
Django's own ``arx test`` (``DiscoverRunner``), which only collects
``unittest.TestCase`` subclasses — a bare ``@pytest.mark.django_db`` class is
silently never run. Rewritten as ``django.test.TestCase``, mirroring
``world.areas.positioning.tests.test_plummet_begin``'s setUp shape (an explicit
``Room`` + ``db_location`` assignment), since presence (``room.contents``) needs a
real room rather than the factory's default (locationless) placement.

Built in ``setUp`` (not ``setUpTestData``): factories create Evennia ObjectDB
instances (DbHolder — not deepcopyable), which would break ``setUpTestData``'s
deepcopy (same rationale as the plummet tests).

Also deviates on one import: ``get_scene_round_defaults_config`` actually lives on
``world.scenes.models`` (not ``world.scenes.round_services``, which merely imports
and re-uses it internally) — imported from its real home here.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.interpose_content import ensure_interpose_content
from world.conditions.factories import DamageTypeFactory
from world.scenes.models import PendingSuddenHarm, get_scene_round_defaults_config
from world.scenes.sudden_harm import arm_or_apply_sudden_harm
from world.vitals.factories import CharacterVitalsFactory


class ArmOrApplySuddenHarmTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="SuddenHarmRoom", nohome=True)

        sheet = CharacterSheetFactory()
        self.char = sheet.character
        self.char.db_location = self.room
        self.char.save(update_fields=["db_location"])
        self.sheet = sheet
        CharacterVitalsFactory(character_sheet=sheet)

    def _place_bystander(self) -> None:
        bystander_sheet = CharacterSheetFactory()
        bystander = bystander_sheet.character
        bystander.db_location = self.room
        bystander.save(update_fields=["db_location"])
        self.bystander_sheet = bystander_sheet

    def test_solo_target_resolves_immediately(self) -> None:
        starting_health = self.sheet.vitals.health
        damage_type = DamageTypeFactory()

        arm_or_apply_sudden_harm(self.char, 15, damage_type)

        self.sheet.vitals.refresh_from_db()
        self.assertLess(self.sheet.vitals.health, starting_health)
        self.assertFalse(PendingSuddenHarm.objects.filter(target_sheet=self.sheet).exists())

    def test_below_threshold_resolves_immediately_even_with_bystander(self) -> None:
        self._place_bystander()
        starting_health = self.sheet.vitals.health
        config = get_scene_round_defaults_config()
        below = config.sudden_harm_interpose_threshold - 1

        arm_or_apply_sudden_harm(self.char, below, None)

        self.sheet.vitals.refresh_from_db()
        self.assertLess(self.sheet.vitals.health, starting_health)
        self.assertFalse(PendingSuddenHarm.objects.filter(target_sheet=self.sheet).exists())

    def test_bystander_present_and_above_threshold_defers(self) -> None:
        ensure_interpose_content()
        self._place_bystander()
        starting_health = self.sheet.vitals.health
        config = get_scene_round_defaults_config()
        above = config.sudden_harm_interpose_threshold + 5

        arm_or_apply_sudden_harm(self.char, above, None, source_description="a hidden blade")

        self.sheet.vitals.refresh_from_db()
        self.assertEqual(self.sheet.vitals.health, starting_health)
        pending = PendingSuddenHarm.objects.get(target_sheet=self.sheet)
        self.assertEqual(pending.amount, above)
        self.assertEqual(pending.source_description, "a hidden blade")

    def test_no_potential_interposer_present_resolves_immediately(self) -> None:
        """Above threshold, but truly alone — no bystander to hold the harm for."""
        starting_health = self.sheet.vitals.health
        config = get_scene_round_defaults_config()
        above = config.sudden_harm_interpose_threshold + 5

        arm_or_apply_sudden_harm(self.char, above, None)

        self.sheet.vitals.refresh_from_db()
        self.assertLess(self.sheet.vitals.health, starting_health)
        self.assertFalse(PendingSuddenHarm.objects.filter(target_sheet=self.sheet).exists())

    def test_interpose_template_not_seeded_falls_back_to_immediate_resolution(self) -> None:
        """Bystander present, above threshold, but the Interpose seed content is missing.

        Deliberately does NOT call ensure_interpose_content() (unlike
        test_bystander_present_and_above_threshold_defers) so
        ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME) raises
        DoesNotExist, exercising _bind_interpose_challenge's guard. Must degrade to
        the same immediate-resolution path as the below-threshold/no-bystander
        branches — no PendingSuddenHarm row, no propagated exception.
        """
        self._place_bystander()
        starting_health = self.sheet.vitals.health
        config = get_scene_round_defaults_config()
        above = config.sudden_harm_interpose_threshold + 5

        arm_or_apply_sudden_harm(self.char, above, None, source_description="a hidden blade")

        self.sheet.vitals.refresh_from_db()
        self.assertLess(self.sheet.vitals.health, starting_health)
        self.assertFalse(PendingSuddenHarm.objects.filter(target_sheet=self.sheet).exists())
