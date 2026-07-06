from datetime import UTC

from django.test import TestCase

from world.magic.constants import ParticipationRule
from world.magic.factories import RitualFactory


class RitualParticipationRuleTests(TestCase):
    def test_default_rule_is_single_actor(self):
        ritual = RitualFactory()
        self.assertEqual(ritual.participation_rule, ParticipationRule.SINGLE_ACTOR)

    def test_min_max_participants_default_null(self):
        ritual = RitualFactory()
        self.assertIsNone(ritual.min_participants)
        self.assertIsNone(ritual.max_participants)


class RitualSessionModelTests(TestCase):
    def test_create_minimal_session(self):
        from datetime import datetime, timedelta

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession

        ritual = RitualFactory()
        sheet = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=sheet,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.assertEqual(session.session_kwargs, {})
        self.assertEqual(session.proposed_terms, "")


class RitualSessionParticipantConstraintTests(TestCase):
    def test_unique_session_character_sheet(self):
        from datetime import datetime, timedelta

        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession, RitualSessionParticipant

        ritual = RitualFactory()
        sheet = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=sheet,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionParticipant.objects.create(session=session, character_sheet=sheet)
        with self.assertRaises(IntegrityError):
            RitualSessionParticipant.objects.create(session=session, character_sheet=sheet)


class RitualSessionReferenceCheckConstraintTests(TestCase):
    def test_exactly_one_ref_required(self):
        from datetime import datetime, timedelta

        from django.db import IntegrityError, transaction

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ReferenceKind
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession, RitualSessionReference

        ritual = RitualFactory()
        sheet = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=sheet,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        # Both refs null violates the CheckConstraint:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RitualSessionReference.objects.create(
                    session=session,
                    kind=ReferenceKind.COVENANT,
                )

    def test_organization_kind_requires_ref_organization(self):
        from datetime import datetime, timedelta

        from django.db import IntegrityError, transaction

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ReferenceKind
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession, RitualSessionReference
        from world.societies.factories import OrganizationFactory

        ritual = RitualFactory()
        sheet = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=sheet,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        org = OrganizationFactory()
        # Valid: kind=ORGANIZATION with ref_organization set.
        ref = RitualSessionReference.objects.create(
            session=session,
            kind=ReferenceKind.ORGANIZATION,
            ref_organization=org,
        )
        self.assertEqual(ref.ref_organization, org)
        # Invalid: kind=ORGANIZATION with ref_organization null.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RitualSessionReference.objects.create(
                    session=session,
                    kind=ReferenceKind.ORGANIZATION,
                )


class OrganizationInductionRitualFactoryTests(TestCase):
    def test_factory_produces_valid_bilateral_ritual(self):
        from world.magic.constants import ParticipationRule, RitualExecutionKind
        from world.magic.factories import OrganizationInductionRitualFactory

        ritual = OrganizationInductionRitualFactory()
        self.assertEqual(ritual.execution_kind, RitualExecutionKind.SERVICE)
        self.assertEqual(ritual.participation_rule, ParticipationRule.BILATERAL)
        self.assertEqual(ritual.min_participants, 2)
        self.assertEqual(ritual.max_participants, 2)
        self.assertEqual(
            ritual.service_function_path,
            "world.societies.membership_services.induct_organization_member_via_session",
        )
        self.assertEqual(
            ritual.draft_validator_path,
            "world.societies.membership_services.assert_initiator_can_lead_org_ritual",
        )
