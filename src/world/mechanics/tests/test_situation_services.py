"""Tests for instantiate_situation (traps-only scope — see #1625)."""

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.mechanics.factories import SituationTemplateFactory, SituationTrapLinkFactory
from world.mechanics.models import SituationInstance
from world.mechanics.situation_services import instantiate_situation
from world.room_features.models import Trap


class InstantiateSituationTest(TestCase):
    def test_creates_situation_instance(self) -> None:
        template = SituationTemplateFactory()
        room = RoomProfileFactory().objectdb

        instance = instantiate_situation(template, room)

        assert isinstance(instance, SituationInstance)
        assert instance.template == template
        assert instance.location == room
        assert instance.is_active is True

    def test_creates_one_trap_per_link(self) -> None:
        template = SituationTemplateFactory()
        SituationTrapLinkFactory(situation_template=template, name="Spike Pit")
        SituationTrapLinkFactory(situation_template=template, name="Poison Dart")
        room_profile = RoomProfileFactory()

        instantiate_situation(template, room_profile.objectdb)

        traps = Trap.objects.filter(room_profile=room_profile)
        assert traps.count() == 2
        assert {t.name for t in traps} == {"Spike Pit", "Poison Dart"}

    def test_trap_fields_copied_from_link_and_fresh_runtime_state(self) -> None:
        template = SituationTemplateFactory()
        link = SituationTrapLinkFactory(
            situation_template=template,
            name="Spike Pit",
            detect_difficulty=15,
            disarm_difficulty=30,
            is_hidden=False,
        )
        room_profile = RoomProfileFactory()

        instantiate_situation(template, room_profile.objectdb)

        trap = Trap.objects.get(room_profile=room_profile, name="Spike Pit")
        assert trap.consequence_pool == link.consequence_pool
        assert trap.detect_check_type == link.detect_check_type
        assert trap.disarm_check_type == link.disarm_check_type
        assert trap.detect_difficulty == 15
        assert trap.disarm_difficulty == 30
        assert trap.is_hidden is False
        assert trap.is_armed is True
        assert trap.detected_by.count() == 0

    def test_no_trap_links_creates_no_traps(self) -> None:
        template = SituationTemplateFactory()
        room = RoomProfileFactory().objectdb

        instantiate_situation(template, room)

        assert Trap.objects.count() == 0

    def test_location_without_room_profile_raises_when_template_has_traps(self) -> None:
        template = SituationTemplateFactory()
        SituationTrapLinkFactory(situation_template=template)
        bare_object = ObjectDBFactory()

        with self.assertRaises(ObjectDoesNotExist):
            instantiate_situation(template, bare_object)

        assert SituationInstance.objects.count() == 0

    def test_location_without_room_profile_is_fine_when_template_has_no_traps(self) -> None:
        template = SituationTemplateFactory()
        bare_object = ObjectDBFactory()

        instance = instantiate_situation(template, bare_object)

        assert instance.location == bare_object
