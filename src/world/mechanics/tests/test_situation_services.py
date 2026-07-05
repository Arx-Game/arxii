"""Tests for instantiate_situation (traps + challenges — see #1625, #1895)."""

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.mechanics.factories import (
    SituationChallengeLinkFactory,
    SituationTemplateFactory,
    SituationTrapLinkFactory,
)
from world.mechanics.models import ChallengeInstance, SituationInstance
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

    def test_creates_one_challenge_instance_per_link(self) -> None:
        template = SituationTemplateFactory()
        SituationChallengeLinkFactory(
            situation_template=template,
            target_object_name="the locked door",
        )
        SituationChallengeLinkFactory(
            situation_template=template,
            target_object_name="the guttering torch",
        )
        room = RoomProfileFactory().objectdb

        instantiate_situation(template, room)

        instances = ChallengeInstance.objects.filter(location=room)
        assert instances.count() == 2
        assert {ci.target_object.db_key for ci in instances} == {
            "the locked door",
            "the guttering torch",
        }

    def test_challenge_instance_links_correct_template(self) -> None:
        template = SituationTemplateFactory()
        link = SituationChallengeLinkFactory(
            situation_template=template,
            target_object_name="the locked door",
        )
        room = RoomProfileFactory().objectdb

        instantiate_situation(template, room)

        instance = ChallengeInstance.objects.get(location=room)
        assert instance.template == link.challenge_template
        assert instance.is_active is True
        assert instance.is_revealed is True

    def test_traps_and_challenges_both_created_in_one_call(self) -> None:
        template = SituationTemplateFactory()
        SituationTrapLinkFactory(situation_template=template, name="Spike Pit")
        SituationChallengeLinkFactory(
            situation_template=template,
            target_object_name="the locked door",
        )
        room_profile = RoomProfileFactory()

        instantiate_situation(template, room_profile.objectdb)

        assert Trap.objects.filter(room_profile=room_profile).count() == 1
        assert ChallengeInstance.objects.filter(location=room_profile.objectdb).count() == 1

    def test_no_challenge_links_creates_no_challenge_instances(self) -> None:
        template = SituationTemplateFactory()
        room = RoomProfileFactory().objectdb

        instantiate_situation(template, room)

        assert ChallengeInstance.objects.count() == 0

    def test_location_without_room_profile_is_fine_when_only_challenges(self) -> None:
        template = SituationTemplateFactory()
        SituationChallengeLinkFactory(
            situation_template=template,
            target_object_name="the locked door",
        )
        bare_object = ObjectDBFactory()

        instance = instantiate_situation(template, bare_object)

        assert instance.location == bare_object
        assert ChallengeInstance.objects.filter(location=bare_object).count() == 1
