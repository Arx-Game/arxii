"""End-to-end tests for the Mentor's Vow ritual session lifecycle (#1165).

Drives the real draft_session → accept_session → fire_session pipeline using
the MentorsVowRitualFactory, verifying that establish_mentor_bond_via_session
creates the correct MentorBond and that the session row is deleted on fire.
"""

from datetime import UTC, datetime, timedelta

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.covenants.factories import (
    CovenantFactory,
    seed_mentor_bond_defaults,
)
from world.covenants.models import MentorBond
from world.magic.constants import ReferenceKind
from world.magic.factories import MentorsVowRitualFactory
from world.magic.models.sessions import RitualSession
from world.magic.services.sessions import accept_session, draft_session, fire_session
from world.magic.types.sessions import RitualSessionReferenceSpec


def _set_primary_level(sheet, level: int) -> None:
    """Helper: give sheet.character a primary CharacterClassLevel at the given level."""
    char_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=sheet,
        character_class=char_class,
        level=level,
        is_primary=True,
    )


class MentorsVowRitualLifecycleTests(TestCase):
    """Full lifecycle: draft → accept → fire → MentorBond created."""

    def setUp(self):
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)  # band [2, 6] with default band_width=2
        self.mentor_sheet = CharacterSheetFactory()
        self.sidekick_sheet = CharacterSheetFactory()
        # mentor in band (level 4), sidekick out of band (level 1) → adjusted_party=SIDEKICK
        _set_primary_level(self.mentor_sheet, 4)
        _set_primary_level(self.sidekick_sheet, 1)

    def test_fire_creates_mentor_bond_and_deletes_session(self):
        """Full lifecycle produces a MentorBond with correct parties; session is gone."""
        from world.covenants.constants import MentorBondAdjusted

        vow_ritual = MentorsVowRitualFactory()

        session = draft_session(
            ritual=vow_ritual,
            initiator=self.mentor_sheet,
            proposed_terms="Mentor's Vow between mentor and sidekick.",
            session_kwargs={},
            invitee_sheets=[self.sidekick_sheet],
            session_references=[
                RitualSessionReferenceSpec(
                    kind=ReferenceKind.COVENANT,
                    ref_covenant=self.covenant,
                ),
            ],
            initiator_participant_kwargs={"role": "mentor"},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session_pk = session.pk

        sidekick_participant = session.participants.get(character_sheet=self.sidekick_sheet)
        accept_session(
            participant=sidekick_participant,
            participant_kwargs={"role": "sidekick"},
            references=[],
        )

        bond = fire_session(session=session)

        # Bond row was created with correct parties and adjusted_party.
        self.assertIsInstance(bond, MentorBond)
        self.assertEqual(bond.covenant, self.covenant)
        self.assertEqual(bond.mentor_sheet, self.mentor_sheet)
        self.assertEqual(bond.sidekick_sheet, self.sidekick_sheet)
        self.assertEqual(bond.adjusted_party, MentorBondAdjusted.SIDEKICK)
        self.assertIsNone(bond.dissolved_at)

        # Session row was deleted after fire.
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())

    def test_fire_mentor_adjusted_when_mentor_out_of_band(self):
        """When mentor is out-of-band and sidekick is in-band, adjusted_party=MENTOR."""
        from world.covenants.constants import MentorBondAdjusted

        # Swap levels: mentor out of band (8), sidekick in band (4)
        out_mentor = CharacterSheetFactory()
        in_sidekick = CharacterSheetFactory()
        _set_primary_level(out_mentor, 8)  # out of band
        _set_primary_level(in_sidekick, 4)  # in band

        vow_ritual = MentorsVowRitualFactory()

        session = draft_session(
            ritual=vow_ritual,
            initiator=out_mentor,
            proposed_terms="Mentor's Vow — mentor is the outlier.",
            session_kwargs={},
            invitee_sheets=[in_sidekick],
            session_references=[
                RitualSessionReferenceSpec(
                    kind=ReferenceKind.COVENANT,
                    ref_covenant=self.covenant,
                ),
            ],
            initiator_participant_kwargs={"role": "mentor"},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        sidekick_participant = session.participants.get(character_sheet=in_sidekick)
        accept_session(
            participant=sidekick_participant,
            participant_kwargs={"role": "sidekick"},
            references=[],
        )

        bond = fire_session(session=session)

        self.assertIsInstance(bond, MentorBond)
        self.assertEqual(bond.mentor_sheet, out_mentor)
        self.assertEqual(bond.sidekick_sheet, in_sidekick)
        self.assertEqual(bond.adjusted_party, MentorBondAdjusted.MENTOR)

    def test_fire_missing_covenant_reference_raises(self):
        """fire_session raises if no COVENANT session reference is provided."""
        from world.magic.exceptions import SessionTargetMissingError

        vow_ritual = MentorsVowRitualFactory()

        session = draft_session(
            ritual=vow_ritual,
            initiator=self.mentor_sheet,
            proposed_terms="Missing covenant ref.",
            session_kwargs={},
            invitee_sheets=[self.sidekick_sheet],
            session_references=[],  # no COVENANT ref
            initiator_participant_kwargs={"role": "mentor"},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        sidekick_participant = session.participants.get(character_sheet=self.sidekick_sheet)
        accept_session(
            participant=sidekick_participant,
            participant_kwargs={"role": "sidekick"},
            references=[],
        )

        with self.assertRaises(SessionTargetMissingError):
            fire_session(session=session)

    def test_fire_missing_role_kwargs_raises(self):
        """fire_session raises if participants are missing role kwargs."""
        from world.magic.exceptions import RequiredReferenceMissingError

        vow_ritual = MentorsVowRitualFactory()

        session = draft_session(
            ritual=vow_ritual,
            initiator=self.mentor_sheet,
            proposed_terms="Missing role kwargs.",
            session_kwargs={},
            invitee_sheets=[self.sidekick_sheet],
            session_references=[
                RitualSessionReferenceSpec(
                    kind=ReferenceKind.COVENANT,
                    ref_covenant=self.covenant,
                ),
            ],
            initiator_participant_kwargs={},  # no "role"
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        sidekick_participant = session.participants.get(character_sheet=self.sidekick_sheet)
        accept_session(
            participant=sidekick_participant,
            participant_kwargs={},  # no "role"
            references=[],
        )

        with self.assertRaises(RequiredReferenceMissingError):
            fire_session(session=session)
