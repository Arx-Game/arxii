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

    def test_bind_fails_with_forced_failure_outcome(self) -> None:
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        failure = CheckOutcomeFactory(name="Forced Bind Failure", success_level=-1)
        with force_check_outcome(failure):
            result = BindCompanionAction().run(
                actor=self.sheet.character,
                gift_id=self.gift.pk,
                archetype_id=self.archetype.pk,
                name="Ghost",
            )

        self.assertFalse(result.success)
        self.assertIn("resists your attempt to bind it", result.message)
        from world.companions.models import Companion

        self.assertFalse(Companion.objects.filter(name="Ghost").exists())


class ReleaseCompanionActionTests(TestCase):
    """Tests for ReleaseCompanionAction (#1918) — the release-via-Action seam."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Release Test Room")
        self.sheet = CharacterSheetFactory()
        self.owner = self.sheet.character
        self.owner.location = self.room
        self.owner.save()
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

    def _bind_companion(self, name: str = "Skree"):
        """Bind a companion via the Action with a forced-success check roll."""
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name=f"Forced Release Success {name}", success_level=5)
        with force_check_outcome(success):
            result = BindCompanionAction().run(
                actor=self.owner,
                gift_id=self.gift.pk,
                archetype_id=self.archetype.pk,
                name=name,
            )
        self.assertTrue(result.success, result.message)
        return result.data["companion_id"]

    def test_release_succeeds(self) -> None:
        from evennia.objects.models import ObjectDB

        from actions.definitions.companions import ReleaseCompanionAction
        from world.companions.models import Companion

        companion_id = self._bind_companion()
        companion = Companion.objects.get(pk=companion_id)
        object_id = companion.objectdb_id

        result = ReleaseCompanionAction().run(actor=self.owner, companion_id=companion_id)

        self.assertTrue(result.success, result.message)
        self.assertIn("released from your bond", result.message)
        companion.refresh_from_db()
        self.assertIsNotNone(companion.released_at)
        self.assertFalse(companion.is_active)
        self.assertFalse(ObjectDB.objects.filter(pk=object_id).exists())

    def test_release_rejected_for_foreign_companion(self) -> None:
        from actions.definitions.companions import ReleaseCompanionAction
        from world.companions.models import Companion

        companion_id = self._bind_companion()
        # A second character who does NOT own this companion.
        other_sheet = CharacterSheetFactory()

        result = ReleaseCompanionAction().run(
            actor=other_sheet.character, companion_id=companion_id
        )

        self.assertFalse(result.success)
        self.assertIn("not your companion", result.message)
        # The companion is untouched.
        companion = Companion.objects.get(pk=companion_id)
        self.assertTrue(companion.is_active)

    def test_release_rejected_for_already_released(self) -> None:
        from actions.definitions.companions import ReleaseCompanionAction

        companion_id = self._bind_companion()
        # Release once via the Action, then attempt to release again.
        first = ReleaseCompanionAction().run(actor=self.owner, companion_id=companion_id)
        self.assertTrue(first.success)

        second = ReleaseCompanionAction().run(actor=self.owner, companion_id=companion_id)

        self.assertFalse(second.success)
        self.assertIn("no longer active", second.message)

    def test_release_without_companion_id_fails(self) -> None:
        from actions.definitions.companions import ReleaseCompanionAction

        result = ReleaseCompanionAction().run(actor=self.owner)

        self.assertFalse(result.success)
        self.assertIn("Pick a companion", result.message)
