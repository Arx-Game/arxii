"""Tests for the Bind Companion action (#672)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.content import ensure_companion_content
from world.magic.specialization.services import grant_gift_to_character


class HasCompanionCapacityPrerequisiteTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.gift = ensure_companion_content()
        self.resonance = self.gift.resonances.first()
        grant_gift_to_character(self.sheet, self.gift, resonance=self.resonance)
        from world.companions.models import CompanionArchetype

        self.archetype = CompanionArchetype.objects.get(name="Hawk")

    def test_denied_without_gift_or_archetype_kwargs(self) -> None:
        from actions.prerequisites import HasCompanionCapacityPrerequisite

        prereq = HasCompanionCapacityPrerequisite()

        met, _reason = prereq.is_met(self.sheet.character, context={"kwargs": {}})

        self.assertFalse(met)

    def test_denied_when_capacity_is_zero(self) -> None:
        from actions.prerequisites import HasCompanionCapacityPrerequisite

        prereq = HasCompanionCapacityPrerequisite()

        met, _reason = prereq.is_met(
            self.sheet.character,
            context={"kwargs": {"gift_id": self.gift.pk, "archetype_id": self.archetype.pk}},
        )

        self.assertFalse(met)

    def test_met_when_capacity_available(self) -> None:
        from actions.prerequisites import HasCompanionCapacityPrerequisite
        from world.magic.constants import TargetKind
        from world.magic.models.threads import Thread

        thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        thread.level = 10
        thread.save(update_fields=["level"])
        prereq = HasCompanionCapacityPrerequisite()

        met, _reason = prereq.is_met(
            self.sheet.character,
            context={"kwargs": {"gift_id": self.gift.pk, "archetype_id": self.archetype.pk}},
        )

        self.assertTrue(met)


class BindCompanionActionTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Bind Test Room")
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()
        self.gift = ensure_companion_content()
        self.resonance = self.gift.resonances.first()
        grant_gift_to_character(self.sheet, self.gift, resonance=self.resonance)
        from world.companions.models import CompanionArchetype
        from world.magic.constants import TargetKind
        from world.magic.models.threads import Thread

        self.archetype = CompanionArchetype.objects.get(name="Hawk")
        thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        thread.level = 10
        thread.save(update_fields=["level"])

    def test_denied_without_capacity(self) -> None:
        from actions.definitions.companions import BindCompanionAction
        from world.companions.models import CompanionArchetype

        expensive = CompanionArchetype.objects.get(name="Direwolf")

        result = BindCompanionAction().run(
            actor=self.sheet.character,
            gift_id=self.gift.pk,
            archetype_id=expensive.pk,
            name="Fang",
        )

        self.assertFalse(result.success)
        from world.companions.models import Companion

        self.assertFalse(Companion.objects.filter(name="Fang").exists())

    def test_bind_succeeds_with_forced_success_outcome(self) -> None:
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="Forced Bind Success", success_level=5)
        with force_check_outcome(success):
            result = BindCompanionAction().run(
                actor=self.sheet.character,
                gift_id=self.gift.pk,
                archetype_id=self.archetype.pk,
                name="Skree",
            )

        self.assertTrue(result.success, result.message)
        from world.companions.models import Companion

        self.assertTrue(Companion.objects.filter(name="Skree", owner=self.sheet).exists())
