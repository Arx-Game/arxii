"""Trigger-based mission dispatch (#729 Phase 2).

Covers the runtime that hands a character a mission on entering a ROOM_TRIGGER
room or examining an ENVIRONMENTAL_DETAIL object: the happy-path grant, the
eligibility filter, and the three anti-nag guards (non-trigger target, active
trigger mission already held, per-(giver, character) cooldown).
"""

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
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
from world.missions.services.visibility import template_visible_to


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
        # Trigger-sourced runs carry no offer context (not NPC-mediated); this
        # character has no CharacterSheet/persona in this test, so
        # accepted_as_persona is None too — see
        # test_grant_sets_accepted_as_persona_when_character_has_one below
        # for the case where a persona IS resolved.
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

    def test_grant_sets_accepted_as_persona_when_character_has_one(self) -> None:
        """Review fix (#1035): the persona already resolved for the
        visibility gate (#870) is threaded into ``accepted_as_persona`` —
        previously dropped, leaving ``has_completed_mission`` unable to find
        trigger-granted runs."""
        sheet = CharacterSheetFactory(character=self.character)
        instance = maybe_dispatch_on_enter(self.character, self.room)
        self.assertIsNotNone(instance)
        self.assertEqual(instance.accepted_as_persona_id, sheet.primary_persona.pk)


class ChainGateOpensAfterFixedGrantTests(TestCase):
    """Regression for the review finding: a trigger-dispatched grant must
    thread the presenting persona so a chained ``has_completed_mission`` gate
    actually opens in live play, not just via staff/NPC-offer grants (#1035).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.sheet.primary_persona
        cls.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        cls.t1 = _template_with_entry("chain-gate-t1")
        cls.giver = MissionGiverFactory(
            name="chain-gate-t1-trigger",
            giver_kind=GiverKind.ROOM_TRIGGER,
            target=cls.room,
        )
        cls.giver.templates.add(cls.t1)
        cls.t2 = MissionTemplateFactory(
            name="chain-gate-t2",
            visibility=MissionVisibility.RESTRICTED,
            availability_rule={
                "leaf": "has_completed_mission",
                "params": {"template_id": cls.t1.pk},
            },
        )

    def test_gate_closed_before_t1_completion(self) -> None:
        self.assertFalse(template_visible_to(self.t2, self.character, persona=self.persona))

    def test_gate_opens_after_trigger_granted_t1_completes(self) -> None:
        instance = maybe_dispatch_on_enter(self.character, self.room)
        self.assertIsNotNone(instance)
        instance.status = MissionStatus.COMPLETE
        instance.save(update_fields=["status"])
        self.assertTrue(template_visible_to(self.t2, self.character, persona=self.persona))
