"""Tests for the Durance intake registration fire handler and services (#2479)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import ParticipantState, ParticipationRule
from world.magic.factories import (
    RitualFactory,
    RitualSessionFactory,
    RitualSessionParticipantFactory,
)
from world.magic.services.sessions import fire_session
from world.progression.models import DuranceTrainingSite
from world.progression.models.durance_cohort import CohortEnrollment, DuranceCohort
from world.progression.services.advancement import (
    _DURANCE_REGISTRATION_SERVICE_PATH,
    convene_durance_registration_at_site,
)
from world.progression.services.durance_registration import (
    enroll_in_durance_cohort,
    get_or_create_open_academy_cohort,
    register_durance_via_session,
)
from world.scenes.factories import SceneFactory
from world.societies.factories import OrganizationFactory


def _place_in_room(sheet, room) -> None:
    """Move a character into *room* (ObjectDB) and persist the change."""
    sheet.character.location = room
    sheet.character.save()


class TestDuranceRegistrationServices(TestCase):
    def test_get_or_create_open_academy_cohort_creates_new(self):
        academy = OrganizationFactory(name="Shroudwatch Academy")
        cohort = get_or_create_open_academy_cohort(academy)
        self.assertIsNotNone(cohort.pk)
        self.assertEqual(cohort.organization, academy)
        self.assertEqual(DuranceCohort.objects.count(), 1)

    def test_get_or_create_open_academy_cohort_reuses_open(self):
        academy = OrganizationFactory(name="Shroudwatch Academy")
        first = get_or_create_open_academy_cohort(academy)
        second = get_or_create_open_academy_cohort(academy)
        self.assertEqual(first.pk, second.pk)

    def test_enroll_idempotent(self):
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        academy = OrganizationFactory(name="Shroudwatch Academy")
        cohort = DuranceCohort.objects.create(organization=academy)

        first = enroll_in_durance_cohort(persona=persona, cohort=cohort)
        second = enroll_in_durance_cohort(persona=persona, cohort=cohort)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CohortEnrollment.objects.count(), 1)
        sheet.refresh_from_db()
        self.assertEqual(sheet.durance_cohort, cohort)

    def _create_registration_session(self, inductee, officiant):
        if inductee.character.location is None:
            room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
            _place_in_room(inductee, room)
        if officiant.character.location is None:
            _place_in_room(officiant, inductee.character.location)
        ritual = RitualFactory(
            name="Ritual of the Durance: Registration",
            service_function_path=_DURANCE_REGISTRATION_SERVICE_PATH,
            participation_rule=ParticipationRule.INDUCTION,
            min_participants=2,
        )
        scene = SceneFactory(location=inductee.character.location, is_active=True)
        session = RitualSessionFactory(
            ritual=ritual,
            initiator=officiant,
            scene=scene,
            session_kwargs={"site_convened": "1", "registration": "1"},
        )
        # The factory may have auto-created an invitee; clear and rebuild.
        session.participants.all().delete()
        RitualSessionParticipantFactory(
            session=session,
            character_sheet=officiant,
            state=ParticipantState.ACCEPTED,
        )
        RitualSessionParticipantFactory(
            session=session,
            character_sheet=inductee,
            state=ParticipantState.ACCEPTED,
            participant_kwargs={"testament": "I am here to begin my Durance."},
        )
        return session

    def test_register_via_session_enrolls_and_sets_flag(self):
        officiant = CharacterSheetFactory()
        inductee = CharacterSheetFactory()
        OrganizationFactory(name="Shroudwatch Academy")
        session = self._create_registration_session(inductee, officiant)
        persona = inductee.primary_persona

        with patch("world.progression.services.durance_registration._fire_enrollment_antiphon"):
            result = register_durance_via_session(session=session)

        self.assertIn(persona, result["enrolled"])
        inductee.refresh_from_db()
        self.assertIsNotNone(inductee.durance_entered_at)
        self.assertIsNotNone(inductee.durance_cohort)
        self.assertTrue(CohortEnrollment.objects.filter(persona=persona).exists())

    def test_register_via_session_is_idempotent(self):
        officiant = CharacterSheetFactory()
        inductee = CharacterSheetFactory()
        OrganizationFactory(name="Shroudwatch Academy")
        session = self._create_registration_session(inductee, officiant)

        with patch("world.progression.services.durance_registration._fire_enrollment_antiphon"):
            register_durance_via_session(session=session)

        session2 = self._create_registration_session(inductee, officiant)
        with patch("world.progression.services.durance_registration._fire_enrollment_antiphon"):
            result = register_durance_via_session(session=session2)

        self.assertIn(inductee.primary_persona, result["already_registered"])
        self.assertEqual(
            CohortEnrollment.objects.filter(persona=inductee.primary_persona).count(),
            1,
        )

    def test_fire_session_dispatches_registration(self):
        officiant = CharacterSheetFactory()
        inductee = CharacterSheetFactory()
        OrganizationFactory(name="Shroudwatch Academy")
        session = self._create_registration_session(inductee, officiant)

        with patch("world.progression.services.durance_registration._fire_enrollment_antiphon"):
            fire_session(session=session)

        inductee.refresh_from_db()
        self.assertIsNotNone(inductee.durance_entered_at)

    def test_convene_registration_at_site(self):
        officiant = CharacterSheetFactory()
        inductee = CharacterSheetFactory()
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(officiant, room)
        _place_in_room(inductee, room)
        OrganizationFactory(name="Shroudwatch Academy")
        RitualFactory(
            name="Ritual of the Durance: Registration",
            service_function_path=_DURANCE_REGISTRATION_SERVICE_PATH,
        )
        DuranceTrainingSite.objects.create(
            room_profile=room.room_profile,
            officiant=officiant,
            training_path=None,
            is_active=True,
        )
        session = convene_durance_registration_at_site(
            inductee_sheet=inductee,
            room=room,
        )
        self.assertEqual(
            session.ritual.service_function_path,
            _DURANCE_REGISTRATION_SERVICE_PATH,
        )
        self.assertEqual(session.session_kwargs.get("registration"), "1")
