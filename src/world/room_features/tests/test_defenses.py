"""Tests for the #2177 defense models (bars/ward/alarm)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from evennia_extensions.models import ExitProfile, RoomProfile
from world.room_features.constants import (
    EXIT_BARS_MAX_LEVEL,
    ROOM_ALARM_MAX_LEVEL,
    ROOM_WARD_MAX_LEVEL,
    DefenseKind,
)
from world.room_features.models import ExitBarsDetails, RoomAlarmDetails, RoomWardDetails


class ExitBarsDetailsTests(TestCase):
    def test_one_bars_row_per_exit_independent_of_room_features(self):
        room = ObjectDBFactory(db_key="BarsRoom", db_typeclass_path="typeclasses.rooms.Room")
        dest = ObjectDBFactory(db_key="BarsDest", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="north", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        bars = ExitBarsDetails.objects.create(exit_profile=exit_profile, level=2)
        assert bars.level == 2
        assert ExitBarsDetails.objects.filter(exit_profile=exit_profile).active().count() == 1

    def test_dissolved_bars_excluded_from_active(self):
        from django.utils import timezone

        room = ObjectDBFactory(db_key="BarsRoom2", db_typeclass_path="typeclasses.rooms.Room")
        dest = ObjectDBFactory(db_key="BarsDest2", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="south", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        bars = ExitBarsDetails.objects.create(
            exit_profile=exit_profile, dissolved_at=timezone.now()
        )
        assert not ExitBarsDetails.objects.filter(exit_profile=exit_profile).active().exists()
        assert ExitBarsDetails.objects.filter(pk=bars.pk).exists()


class RoomWardAlarmCoexistenceTests(TestCase):
    def test_ward_and_alarm_and_room_feature_coexist(self):
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

        room_profile = RoomProfileFactory()
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        RoomFeatureInstanceFactory(room_profile=room_profile, feature_kind=kind)

        from world.magic.factories import ResonanceFactory

        resonance = ResonanceFactory()
        ward = RoomWardDetails.objects.create(room_profile=room_profile, resonance=resonance)
        alarm = RoomAlarmDetails.objects.create(room_profile=room_profile)

        assert ward.room_profile_id == room_profile.pk
        assert alarm.room_profile_id == room_profile.pk
        # RoomFeatureInstance still active -- the three models don't collide.
        assert room_profile.feature_instance.feature_kind_id == kind.pk


class DefenseConstantsTests(TestCase):
    def test_max_levels_are_five(self):
        assert EXIT_BARS_MAX_LEVEL == 5
        assert ROOM_WARD_MAX_LEVEL == 5
        assert ROOM_ALARM_MAX_LEVEL == 5

    def test_defense_kind_choices(self):
        assert set(DefenseKind.values) == {"EXIT_BARS", "ROOM_WARD", "ROOM_ALARM"}


class DefenseProgressionDetailsTests(TestCase):
    def _project(self):
        from datetime import timedelta

        from django.utils import timezone

        from world.character_sheets.factories import CharacterSheetFactory
        from world.projects.constants import CompletionMode, ProjectKind
        from world.projects.models import Project
        from world.scenes.factories import PersonaFactory

        sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=sheet)
        return Project.objects.create(
            kind=ProjectKind.ROOM_DEFENSE_INSTALLATION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            threshold_target=500,
            started_at=timezone.now(),
            time_limit=timezone.now() + timedelta(days=7),
        )

    def test_bars_progression_targets_exit_profile_only(self):
        from world.room_features.models import DefenseProgressionDetails

        room = ObjectDBFactory(db_key="ProgRoom", db_typeclass_path="typeclasses.rooms.Room")
        dest = ObjectDBFactory(db_key="ProgDest", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="up", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        project = self._project()
        details = DefenseProgressionDetails.objects.create(
            project=project,
            defense_kind=DefenseKind.EXIT_BARS,
            target_exit_profile=exit_profile,
            target_level=1,
        )
        assert details.target_room_profile is None

    def test_ward_progression_targets_room_profile_and_resonance(self):
        from world.magic.factories import ResonanceFactory
        from world.room_features.models import DefenseProgressionDetails

        room_profile = RoomProfileFactory()
        resonance = ResonanceFactory()
        project = self._project()
        details = DefenseProgressionDetails.objects.create(
            project=project,
            defense_kind=DefenseKind.ROOM_WARD,
            target_room_profile=room_profile,
            target_level=1,
            resonance=resonance,
        )
        assert details.target_exit_profile is None
        assert details.resonance_id == resonance.pk


class CompleteDefenseInstallationTests(TestCase):
    def _project(self, threshold=500):
        from datetime import timedelta

        from django.utils import timezone

        from world.character_sheets.factories import CharacterSheetFactory
        from world.projects.constants import CompletionMode, ProjectKind
        from world.projects.models import Project
        from world.scenes.factories import PersonaFactory

        sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=sheet)
        return Project.objects.create(
            kind=ProjectKind.ROOM_DEFENSE_INSTALLATION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            threshold_target=threshold,
            started_at=timezone.now(),
            time_limit=timezone.now() + timedelta(days=7),
        )

    def test_completes_bars_install(self):
        from world.room_features.models import DefenseProgressionDetails, ExitBarsDetails
        from world.room_features.services import complete_defense_installation

        room = ObjectDBFactory(db_key="CDIRoom", db_typeclass_path="typeclasses.rooms.Room")
        dest = ObjectDBFactory(db_key="CDIDest", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="down", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        project = self._project()
        DefenseProgressionDetails.objects.create(
            project=project,
            defense_kind=DefenseKind.EXIT_BARS,
            target_exit_profile=exit_profile,
            target_level=1,
        )
        complete_defense_installation(project)
        assert ExitBarsDetails.objects.filter(exit_profile=exit_profile).active().exists()

    def test_completes_ward_install_with_resonance(self):
        from world.magic.factories import ResonanceFactory
        from world.room_features.models import DefenseProgressionDetails, RoomWardDetails
        from world.room_features.services import complete_defense_installation

        room_profile = RoomProfileFactory()
        resonance = ResonanceFactory()
        project = self._project()
        DefenseProgressionDetails.objects.create(
            project=project,
            defense_kind=DefenseKind.ROOM_WARD,
            target_room_profile=room_profile,
            target_level=1,
            resonance=resonance,
        )
        complete_defense_installation(project)
        ward = RoomWardDetails.objects.filter(room_profile=room_profile).active().first()
        assert ward is not None
        assert ward.resonance_id == resonance.pk

    def test_upgrade_bumps_level_not_downgrade(self):
        from world.room_features.models import DefenseProgressionDetails, RoomAlarmDetails
        from world.room_features.services import complete_defense_installation

        room_profile = RoomProfileFactory()
        RoomAlarmDetails.objects.create(room_profile=room_profile, level=2)
        project = self._project()
        DefenseProgressionDetails.objects.create(
            project=project,
            defense_kind=DefenseKind.ROOM_ALARM,
            target_room_profile=room_profile,
            target_level=1,
        )
        complete_defense_installation(project)
        alarm = RoomAlarmDetails.objects.get(room_profile=room_profile)
        assert alarm.level == 2  # unchanged -- target_level (1) is not an upgrade


class ReactToUnauthorizedEntryTests(TestCase):
    def _room_ward_and_intruder(self, *, condition=None, damage=0):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.room_features.models import RoomWardDetails
        from world.scenes.factories import PersonaFactory

        room = ObjectDBFactory(db_key="ReactRoom", db_typeclass_path="typeclasses.rooms.Room")
        room_profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        resonance = ResonanceFactory()
        ward = RoomWardDetails.objects.create(
            room_profile=room_profile,
            resonance=resonance,
            reaction_condition=condition,
            reaction_damage_amount=damage,
        )
        intruder = ObjectDBFactory(
            db_key="ReactMallory", db_typeclass_path="typeclasses.characters.Character"
        )
        intruder.location = room
        intruder.save()
        sheet = CharacterSheetFactory(character=intruder)
        PersonaFactory(character_sheet=sheet)
        return room, ward, intruder

    def test_ward_applies_condition_to_unauthorized_entrant(self):
        from world.conditions.factories import ConditionTemplateFactory
        from world.room_features.services import react_to_unauthorized_entry

        condition = ConditionTemplateFactory()
        room, _ward, intruder = self._room_ward_and_intruder(condition=condition)
        react_to_unauthorized_entry(intruder, room)
        assert intruder.condition_instances.filter(condition=condition).exists()

    def test_ward_lapsed_does_not_react(self):
        from django.utils import timezone

        from world.conditions.factories import ConditionTemplateFactory
        from world.room_features.services import react_to_unauthorized_entry

        condition = ConditionTemplateFactory()
        room, ward, intruder = self._room_ward_and_intruder(condition=condition)
        ward.lapsed_at = timezone.now()
        ward.save(update_fields=["lapsed_at"])
        react_to_unauthorized_entry(intruder, room)
        assert not intruder.condition_instances.filter(condition=condition).exists()

    def test_owner_entering_does_not_trigger_ward(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionTemplateFactory
        from world.locations.services import transfer_ownership
        from world.room_features.services import react_to_unauthorized_entry
        from world.scenes.factories import PersonaFactory

        condition = ConditionTemplateFactory()
        room, _ward, _intruder = self._room_ward_and_intruder(condition=condition)
        room_profile = RoomProfile.objects.get(objectdb=room)
        owner = ObjectDBFactory(
            db_key="ReactOwner", db_typeclass_path="typeclasses.characters.Character"
        )
        owner.location = room
        owner.save()
        owner_sheet = CharacterSheetFactory(character=owner)
        owner_persona = PersonaFactory(character_sheet=owner_sheet)
        owner_sheet.active_persona = owner_persona
        owner_sheet.save(update_fields=["active_persona"])
        transfer_ownership(room_profile=room_profile, to_persona=owner_persona)

        react_to_unauthorized_entry(owner, room)
        assert not owner.condition_instances.filter(condition=condition).exists()

    def test_alarm_notifies_owner(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.locations.services import transfer_ownership
        from world.narrative.models import NarrativeMessageDelivery
        from world.room_features.models import RoomAlarmDetails
        from world.room_features.services import react_to_unauthorized_entry
        from world.scenes.factories import PersonaFactory

        room = ObjectDBFactory(db_key="AlarmRoom", db_typeclass_path="typeclasses.rooms.Room")
        room_profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        owner_sheet = CharacterSheetFactory()
        owner_persona = PersonaFactory(character_sheet=owner_sheet)
        transfer_ownership(room_profile=room_profile, to_persona=owner_persona)
        RoomAlarmDetails.objects.create(room_profile=room_profile)

        intruder = ObjectDBFactory(
            db_key="AlarmMallory", db_typeclass_path="typeclasses.characters.Character"
        )
        intruder.location = room
        intruder.save()
        intruder_sheet = CharacterSheetFactory(character=intruder)
        PersonaFactory(character_sheet=intruder_sheet)

        react_to_unauthorized_entry(intruder, room)
        assert NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=owner_sheet
        ).exists()

    def test_ward_damage_debits_intruder_health(self):
        """``reaction_damage_amount`` genuinely debits health via ``arm_or_apply_sudden_harm``.

        Regression guard for #1228/PR #1285: a prior damage path silently no-op'd
        because it never wrote the debit through to ``vitals.health`` before running
        consequences. Asserting only "no exception raised" would not have caught
        that -- assert the actual health drop.
        """
        from world.room_features.services import react_to_unauthorized_entry
        from world.vitals.factories import CharacterVitalsFactory

        room, _ward, intruder = self._room_ward_and_intruder(damage=15)
        vitals = CharacterVitalsFactory(
            character_sheet=intruder.sheet_data, health=100, max_health=100
        )

        react_to_unauthorized_entry(intruder, room)

        vitals.refresh_from_db()
        assert vitals.health == 85

    def test_alarm_message_is_identity_transparent(self):
        """``RoomAlarmDetails`` is identity-transparent (ADR-0083): the owner
        notification body must never contain the intruder's name/key.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.locations.services import transfer_ownership
        from world.narrative.models import NarrativeMessageDelivery
        from world.room_features.models import RoomAlarmDetails
        from world.room_features.services import react_to_unauthorized_entry
        from world.scenes.factories import PersonaFactory

        room = ObjectDBFactory(
            db_key="AlarmIdentityRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        room_profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        owner_sheet = CharacterSheetFactory()
        owner_persona = PersonaFactory(character_sheet=owner_sheet)
        transfer_ownership(room_profile=room_profile, to_persona=owner_persona)
        RoomAlarmDetails.objects.create(room_profile=room_profile)

        intruder = ObjectDBFactory(
            db_key="IdentityMallory", db_typeclass_path="typeclasses.characters.Character"
        )
        intruder.location = room
        intruder.save()
        intruder_sheet = CharacterSheetFactory(character=intruder)
        PersonaFactory(character_sheet=intruder_sheet)

        react_to_unauthorized_entry(intruder, room)

        delivery = NarrativeMessageDelivery.objects.get(recipient_character_sheet=owner_sheet)
        assert intruder.db_key not in delivery.message.body

    def test_alarm_org_holder_does_not_crash_or_notify(self):
        """``_trigger_alarm`` no-ops (does not crash) when the room's owner is an
        Organization -- only a Persona holder gets notified (#2177 Task 8 fix).
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.locations.services import transfer_ownership
        from world.narrative.models import NarrativeMessageDelivery
        from world.room_features.models import RoomAlarmDetails
        from world.room_features.services import react_to_unauthorized_entry
        from world.scenes.factories import PersonaFactory
        from world.societies.factories import OrganizationFactory

        room = ObjectDBFactory(db_key="AlarmOrgRoom", db_typeclass_path="typeclasses.rooms.Room")
        room_profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        org = OrganizationFactory()
        transfer_ownership(room_profile=room_profile, to_organization=org)
        RoomAlarmDetails.objects.create(room_profile=room_profile)

        intruder = ObjectDBFactory(
            db_key="OrgMallory", db_typeclass_path="typeclasses.characters.Character"
        )
        intruder.location = room
        intruder.save()
        intruder_sheet = CharacterSheetFactory(character=intruder)
        PersonaFactory(character_sheet=intruder_sheet)

        react_to_unauthorized_entry(intruder, room)  # must not raise

        assert not NarrativeMessageDelivery.objects.exists()
