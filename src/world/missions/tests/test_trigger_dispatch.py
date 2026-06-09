"""Trigger-based mission dispatch (#729 Phase 2).

Covers the runtime that hands a character a mission on entering a ROOM_TRIGGER
room or examining an ENVIRONMENTAL_DETAIL object: the happy-path grant, the
eligibility filter, and the three anti-nag guards (non-trigger target, active
trigger mission already held, per-(giver, character) cooldown).
"""

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.missions.constants import GiverKind, MissionStatus, MissionVisibility
from world.missions.factories import (
    MissionGiverFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGiverCooldown, MissionInstance
from world.missions.services.trigger_dispatch import (
    maybe_dispatch_on_enter,
    maybe_dispatch_on_examine,
)


def _template_with_entry(name: str) -> object:
    template = MissionTemplateFactory(name=name)
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class TriggerDispatchTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        cls.template = _template_with_entry("trigger-mission")
        cls.giver = MissionGiverFactory(
            name="notice-board",
            giver_kind=GiverKind.ROOM_TRIGGER,
            target=cls.room,
        )
        cls.giver.templates.add(cls.template)

    def test_enter_trigger_room_grants_mission(self) -> None:
        instance = maybe_dispatch_on_enter(self.character, self.room)
        self.assertIsNotNone(instance)
        self.assertEqual(instance.template_id, self.template.pk)
        # Trigger-sourced runs carry no offer/persona context.
        self.assertIsNone(instance.source_offer)
        self.assertTrue(
            MissionInstance.objects.filter(
                participants__character=self.character, status=MissionStatus.ACTIVE
            ).exists()
        )

    def test_non_trigger_target_no_dispatch(self) -> None:
        bare_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.assertIsNone(maybe_dispatch_on_enter(self.character, bare_room))

    def test_ineligible_template_skipped(self) -> None:
        # RESTRICTED + empty rule = emergent staff-only (#870); the
        # non-staff character is filtered out of the draw pool. Regression
        # guard for the pre-#870 gap where the trigger path ignored the
        # template's audience gate entirely.
        self.template.visibility = MissionVisibility.RESTRICTED
        self.template.save(update_fields=["visibility"])
        self.assertIsNone(maybe_dispatch_on_enter(self.character, self.room))
        self.assertFalse(
            MissionInstance.objects.filter(participants__character=self.character).exists()
        )

    def test_cooldown_blocks_redispatch(self) -> None:
        first = maybe_dispatch_on_enter(self.character, self.room)
        self.assertIsNotNone(first)
        # A cooldown row was written; a second entry is now blocked.
        self.assertTrue(
            MissionGiverCooldown.objects.filter(
                giver=self.giver, character=self.character, available_at__gt=timezone.now()
            ).exists()
        )
        # Clear the active-mission guard so the cooldown is what's tested.
        MissionInstance.objects.filter(participants__character=self.character).update(
            status=MissionStatus.COMPLETE
        )
        self.assertIsNone(maybe_dispatch_on_enter(self.character, self.room))

    def test_active_trigger_mission_blocks(self) -> None:
        instance = MissionInstanceFactory(template=self.template, source_offer=None)
        MissionParticipantFactory(
            instance=instance, character=self.character, is_contract_holder=True
        )
        instance.status = MissionStatus.ACTIVE
        instance.save(update_fields=["status"])
        self.assertIsNone(maybe_dispatch_on_enter(self.character, self.room))

    def test_examine_environmental_detail_grants(self) -> None:
        detail = ObjectDBFactory()  # plain Object typeclass
        giver = MissionGiverFactory(
            name="strange-door",
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            target=detail,
        )
        giver.templates.add(_template_with_entry("examine-mission"))
        instance = maybe_dispatch_on_examine(self.character, detail)
        self.assertIsNotNone(instance)
