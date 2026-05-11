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


class AcceptSessionTests(TestCase):
    def _make_pending_formation_session(self):
        """Helper: draft a FORMATION session with one initiator + one invitee."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipationRule
        from world.magic.factories import RitualFactory
        from world.magic.services.sessions import draft_session

        ritual = RitualFactory(participation_rule=ParticipationRule.FORMATION)
        initiator = CharacterSheetFactory()
        invitee = CharacterSheetFactory()
        session = draft_session(
            ritual=ritual,
            initiator=initiator,
            proposed_terms="x",
            session_kwargs={},
            invitee_sheets=[invitee],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        invitee_p = session.participants.get(character_sheet=invitee)
        return session, invitee_p

    def test_accept_transitions_state_and_creates_references(self):
        from world.covenants.factories import CovenantRoleFactory
        from world.magic.constants import ParticipantState, ReferenceKind
        from world.magic.services.sessions import accept_session
        from world.magic.types.sessions import RitualSessionReferenceSpec

        _session, participant = self._make_pending_formation_session()
        role = CovenantRoleFactory()
        accept_session(
            participant=participant,
            participant_kwargs={"chose_intentionally": True},
            references=[
                RitualSessionReferenceSpec(
                    kind=ReferenceKind.COVENANT_ROLE,
                    ref_covenant_role=role,
                ),
            ],
        )
        participant.refresh_from_db()
        self.assertEqual(participant.state, ParticipantState.ACCEPTED)
        self.assertIsNotNone(participant.responded_at)
        self.assertEqual(participant.participant_kwargs, {"chose_intentionally": True})
        self.assertEqual(participant.references.count(), 1)
        self.assertEqual(participant.references.first().ref_covenant_role, role)

    def test_accept_already_accepted_raises_session_not_pending(self):
        from world.magic.exceptions import SessionNotInPendingError
        from world.magic.services.sessions import accept_session

        _session, participant = self._make_pending_formation_session()
        accept_session(participant=participant, participant_kwargs={}, references=[])
        with self.assertRaises(SessionNotInPendingError):
            accept_session(participant=participant, participant_kwargs={}, references=[])

    def test_accept_after_session_deleted_raises(self):
        from django.core.exceptions import ObjectDoesNotExist

        from world.magic.models.sessions import RitualSessionParticipant
        from world.magic.services.sessions import accept_session

        session, participant = self._make_pending_formation_session()
        # Delete the session out from under the participant
        session.delete()
        with self.assertRaises((RitualSessionParticipant.DoesNotExist, ObjectDoesNotExist)):
            accept_session(participant=participant, participant_kwargs={}, references=[])


class DeclineSessionTests(TestCase):
    def _make_pending_formation_session(self, n_invitees: int = 2):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipationRule
        from world.magic.factories import RitualFactory
        from world.magic.services.sessions import draft_session

        ritual = RitualFactory(participation_rule=ParticipationRule.FORMATION)
        initiator = CharacterSheetFactory()
        invitees = [CharacterSheetFactory() for _ in range(n_invitees)]
        session = draft_session(
            ritual=ritual,
            initiator=initiator,
            proposed_terms="x",
            session_kwargs={},
            invitee_sheets=invitees,
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        invitee_ps = list(session.participants.exclude(character_sheet=initiator))
        return session, invitee_ps

    def test_decline_transitions_state_to_declined_for_induction(self):
        """INDUCTION can absorb a single decline if accepts can still reach majority."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipantState, ParticipationRule
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession
        from world.magic.services.sessions import decline_session, draft_session

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        initiator = CharacterSheetFactory()
        invitees = [CharacterSheetFactory() for _ in range(3)]
        session = draft_session(
            ritual=ritual,
            initiator=initiator,
            proposed_terms="x",
            session_kwargs={},
            invitee_sheets=invitees,
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        # Initiator already accepted (1 accept, 0 decline). Decline one invitee.
        # Best-case = 1 + 2 still-invited = 3 accepts vs 1 decline; threshold can
        # still be met. Session survives.
        invitee_ps = list(session.participants.exclude(character_sheet=initiator))
        decline_session(participant=invitee_ps[0])
        invitee_ps[0].refresh_from_db()
        self.assertEqual(invitee_ps[0].state, ParticipantState.DECLINED)
        # Session should still exist:
        self.assertTrue(RitualSession.objects.filter(pk=session.pk).exists())

    def test_decline_kills_formation_session(self):
        """FORMATION: any decline kills the session."""
        from world.magic.models.sessions import RitualSession
        from world.magic.services.sessions import decline_session

        session, invitee_ps = self._make_pending_formation_session(n_invitees=2)
        decline_session(participant=invitee_ps[0])
        # Session should be deleted (CASCADE wipes participants + references):
        self.assertFalse(RitualSession.objects.filter(pk=session.pk).exists())

    def test_decline_already_declined_raises(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipationRule
        from world.magic.exceptions import SessionNotInPendingError
        from world.magic.factories import RitualFactory

        # Use INDUCTION so the first decline doesn't kill the session
        from world.magic.services.sessions import decline_session, draft_session

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        initiator = CharacterSheetFactory()
        invitees = [CharacterSheetFactory() for _ in range(3)]
        session = draft_session(
            ritual=ritual,
            initiator=initiator,
            proposed_terms="x",
            session_kwargs={},
            invitee_sheets=invitees,
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        invitee_ps = list(session.participants.exclude(character_sheet=initiator))
        decline_session(participant=invitee_ps[0])
        with self.assertRaises(SessionNotInPendingError):
            decline_session(participant=invitee_ps[0])

    def test_decline_killing_induction_threshold_deletes_session(self):
        """INDUCTION: enough declines such that majority-of-respondents can't be met → delete."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipationRule
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession
        from world.magic.services.sessions import decline_session, draft_session

        # INDUCTION: 1 initiator + 2 invitees. Initiator counts as 1 accept.
        # If both invitees decline, we have 1 accept + 2 declines + 0 invited;
        # accepts (1) is NOT > declines (2) → threshold cannot be met → delete.
        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        initiator = CharacterSheetFactory()
        invitees = [CharacterSheetFactory() for _ in range(2)]
        session = draft_session(
            ritual=ritual,
            initiator=initiator,
            proposed_terms="x",
            session_kwargs={},
            invitee_sheets=invitees,
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        invitee_ps = list(session.participants.exclude(character_sheet=initiator))
        decline_session(participant=invitee_ps[0])
        # Still alive (1 accept + 1 decline + 1 invited; best-case 2 accepts > 1 decline):
        self.assertTrue(RitualSession.objects.filter(pk=session.pk).exists())
        decline_session(participant=invitee_ps[1])
        # Now dead (1 accept + 2 decline + 0 invited; best-case 1 ≤ 2):
        self.assertFalse(RitualSession.objects.filter(pk=session.pk).exists())
