"""Court form + fealty ceremony tests (#1589, Task 7).

The fealty step reuses the existing ritual-session induction path
(`induct_member_via_session`): inducting a servant into a COURT covenant must
also swear a CourtPact (with the master-granted pull cap, read from the
candidate participant's kwargs) and emit a servant-centred fealty narration.
"""

from datetime import UTC, datetime, timedelta

from django.test import TestCase


def _set_primary_level(sheet, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at the given level."""
    from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory

    CharacterClassLevelFactory(
        character=sheet,
        character_class=CharacterClassFactory(),
        level=level,
        is_primary=True,
    )


class CourtFealtyCeremonyTests(TestCase):
    """Inducting a servant into a COURT covenant performs the fealty pact."""

    def _build_induction_session(
        self,
        *,
        covenant_type,
        granted_pull_cap=None,
    ):
        """Build a fire-ready INDUCTION session: target covenant ref + one
        ACCEPTED candidate carrying a COVENANT_ROLE ref (the servant).

        ``granted_pull_cap`` — when not None, stamped on the candidate
        participant's ``participant_kwargs`` (mirrors how soul-tether/mentorship
        read ``role`` from participant_kwargs).

        Returns (session, covenant, candidate_sheet, chosen_role).
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.magic.constants import (
            ParticipantState,
            ParticipationRule,
            ReferenceKind,
        )
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        # The master / existing member (initiator) — already in the covenant,
        # vouching, with no new role reference. For a COURT the master is the
        # leader and must sit a power-tier above the servant (gulf check, #1589).
        master = CharacterSheetFactory(character__db_key="Master")
        candidate = CharacterSheetFactory(character__db_key="Servant")
        from world.covenants.constants import CovenantType as _CovenantType

        is_court = covenant_type == _CovenantType.COURT
        if is_court:
            _set_primary_level(master, 6)  # tier 2
            _set_primary_level(candidate, 5)  # tier 1 — one tier below
        covenant = CovenantFactory(
            covenant_type=covenant_type,
            leader=master if is_court else None,
        )
        existing_role = CovenantRoleFactory(covenant_type=covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=master,
            covenant=covenant,
            covenant_role=existing_role,
        )
        chosen_role = CovenantRoleFactory(covenant_type=covenant_type)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=master,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=None,
            kind=ReferenceKind.COVENANT,
            ref_covenant=covenant,
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=master,
            state=ParticipantState.ACCEPTED,
        )
        candidate_kwargs = {}
        if granted_pull_cap is not None:
            candidate_kwargs["granted_pull_cap"] = granted_pull_cap
        candidate_p = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=candidate,
            state=ParticipantState.ACCEPTED,
            participant_kwargs=candidate_kwargs,
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=candidate_p,
            kind=ReferenceKind.COVENANT_ROLE,
            ref_covenant_role=chosen_role,
        )
        return session, covenant, candidate, chosen_role

    def test_court_induction_swears_pact_with_granted_cap(self) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.services import active_court_pact_for, induct_member_via_session

        session, covenant, servant, _role = self._build_induction_session(
            covenant_type=CovenantType.COURT,
            granted_pull_cap=3,
        )
        induct_member_via_session(session=session)

        pact = active_court_pact_for(covenant=covenant, servant_sheet=servant)
        self.assertIsNotNone(pact)
        self.assertEqual(pact.granted_pull_cap, 3)

    def test_court_induction_emits_servant_centred_narration(self) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.services import induct_member_via_session
        from world.narrative.models import NarrativeMessage

        session, _covenant, servant, _role = self._build_induction_session(
            covenant_type=CovenantType.COURT,
            granted_pull_cap=2,
        )
        induct_member_via_session(session=session)

        servant_name = servant.character.db_key
        msg = NarrativeMessage.objects.filter(body__contains=servant_name).order_by("-id").first()
        self.assertIsNotNone(msg)
        # Servant is the focal/grammatical subject: the body opens with the
        # servant's name and their act of swearing.
        self.assertTrue(msg.body.startswith(servant_name))
        self.assertIn("fealty", msg.body.lower())
        # The master is backdrop, not the grammatical subject — the body must
        # not open with the master's name.
        self.assertFalse(msg.body.startswith("Master"))
        self.assertNotEqual(servant_name, "Master")

    def test_court_induction_default_grant_is_zero(self) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.services import active_court_pact_for, induct_member_via_session

        session, covenant, servant, _role = self._build_induction_session(
            covenant_type=CovenantType.COURT,
            granted_pull_cap=None,
        )
        induct_member_via_session(session=session)

        pact = active_court_pact_for(covenant=covenant, servant_sheet=servant)
        self.assertIsNotNone(pact)
        self.assertEqual(pact.granted_pull_cap, 0)

    def test_non_court_induction_creates_no_pact(self) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.models import CharacterCovenantRole, CourtPact
        from world.covenants.services import induct_member_via_session

        session, covenant, servant, role = self._build_induction_session(
            covenant_type=CovenantType.DURANCE,
            granted_pull_cap=5,
        )
        membership = induct_member_via_session(session=session)

        self.assertIsInstance(membership, CharacterCovenantRole)
        self.assertEqual(membership.character_sheet, servant)
        self.assertEqual(membership.covenant_role, role)
        self.assertFalse(
            CourtPact.objects.filter(covenant=covenant, servant_sheet=servant).exists()
        )
