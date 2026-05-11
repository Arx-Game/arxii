from datetime import UTC, datetime, timedelta

from django.test import TestCase


class DraftSessionTests(TestCase):
    def test_draft_creates_session_with_initiator_as_accepted(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipantState, ParticipationRule
        from world.magic.factories import RitualFactory
        from world.magic.services.sessions import draft_session

        ritual = RitualFactory(participation_rule=ParticipationRule.FORMATION)
        initiator = CharacterSheetFactory()
        invitee = CharacterSheetFactory()

        session = draft_session(
            ritual=ritual,
            initiator=initiator,
            proposed_terms="Form a covenant",
            session_kwargs={"name": "Test"},
            invitee_sheets=[invitee],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        self.assertEqual(session.ritual, ritual)
        self.assertEqual(session.participants.count(), 2)
        # Initiator is auto-accepted:
        initiator_p = session.participants.get(character_sheet=initiator)
        self.assertEqual(initiator_p.state, ParticipantState.ACCEPTED)
        # Invitee is INVITED:
        invitee_p = session.participants.get(character_sheet=invitee)
        self.assertEqual(invitee_p.state, ParticipantState.INVITED)

    def test_draft_attaches_session_references(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import CovenantFactory
        from world.magic.constants import ParticipationRule, ReferenceKind
        from world.magic.factories import RitualFactory
        from world.magic.services.sessions import draft_session
        from world.magic.types.sessions import RitualSessionReferenceSpec

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        initiator = CharacterSheetFactory()
        candidate = CharacterSheetFactory()
        target = CovenantFactory()

        session = draft_session(
            ritual=ritual,
            initiator=initiator,
            proposed_terms="Induct member",
            session_kwargs={},
            invitee_sheets=[candidate],
            session_references=[
                RitualSessionReferenceSpec(kind=ReferenceKind.COVENANT, ref_covenant=target),
            ],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        self.assertEqual(session.references.filter(participant__isnull=True).count(), 1)
        self.assertEqual(session.references.first().ref_covenant, target)

    def test_draft_rejects_bilateral_with_wrong_participant_count(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipationRule
        from world.magic.exceptions import ParticipantCountError
        from world.magic.factories import RitualFactory
        from world.magic.services.sessions import draft_session

        ritual = RitualFactory(
            participation_rule=ParticipationRule.BILATERAL,
            min_participants=2,
            max_participants=2,
        )
        initiator = CharacterSheetFactory()
        # Inviting two extras would make 3 total — too many for BILATERAL:
        with self.assertRaises(ParticipantCountError):
            draft_session(
                ritual=ritual,
                initiator=initiator,
                proposed_terms="",
                session_kwargs={},
                invitee_sheets=[CharacterSheetFactory(), CharacterSheetFactory()],
                session_references=[],
                initiator_participant_kwargs={},
                initiator_references=[],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

    def test_draft_rejects_formation_with_one_total_participant(self):
        """FORMATION minimum 2 enforced even without explicit bounds."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipationRule
        from world.magic.exceptions import ParticipantCountError
        from world.magic.factories import RitualFactory
        from world.magic.services.sessions import draft_session

        ritual = RitualFactory(participation_rule=ParticipationRule.FORMATION)
        initiator = CharacterSheetFactory()
        with self.assertRaises(ParticipantCountError):
            draft_session(
                ritual=ritual,
                initiator=initiator,
                proposed_terms="",
                session_kwargs={},
                invitee_sheets=[],  # only initiator → 1 total
                session_references=[],
                initiator_participant_kwargs={},
                initiator_references=[],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
