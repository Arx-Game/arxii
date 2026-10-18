"""Journeys for deleting a row that another row's check constraint needs (#4464).

Each of these used to be a foreign key that said "set me to NULL if the target goes"
beside a check constraint that said "on this kind of row I am never NULL". Postgres
refused the delete with an IntegrityError, so the person who pressed delete got a
server error. Now each delete either works and keeps the record's meaning, or is
refused up front the way Django refuses any protected delete.

- A writer deletes their own pose that resolved a check: the pose goes, the check
  outcome stays, and still says it came from a scene action and when.
- Staff delete a journal entry another player praised: refused while the praise
  stands; a wipe that takes both still works.
- Staff delete a mission assist pattern a helper used: refused; it is retired with
  ``is_active`` instead.
- Staff delete two bonded allies a surge was about: the surges go with them.

Tagged ``postgres``: SQLite does not reproduce the rejected UPDATE the way the
production database does.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import tag
from django.urls import reverse

from actions.factories import ConsequencePoolFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.outcome_models import ConsequenceOutcome
from world.checks.services import record_consequence_outcome
from world.checks.types import ModifierBreakdown
from world.combat.constants import SurgeTriggerKind
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import DramaticSurgeRecord
from world.journals.factories import JournalEntryFactory, PraiseFactory
from world.journals.models import JournalEntry
from world.missions.factories import MissionSupportDeclarationFactory
from world.missions.models import MissionAssistPattern, MissionSupportDeclaration
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.models import Interaction


def _staff_client(case: JourneyCase):
    staff = get_user_model().objects.create_user(
        username="warden", password="pw", is_staff=True, is_superuser=True
    )
    case.client.force_login(staff)
    return case.client


@tag("postgres")
class AWriterDeletesAPoseThatResolvedACheck(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Low Bridge")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        sheet = self.ysmay.sheet_data
        self.pose = InteractionFactory(
            persona=sheet.primary_persona,
            scene=SceneFactory(),
            content="Ysmay vaults the rail and lands badly.",
        )
        self.outcome = record_consequence_outcome(
            character_sheet=sheet,
            check_type=CheckTypeFactory(),
            pool=ConsequencePoolFactory(),
            selected_consequence=ConsequenceFactory(),
            breakdown=ModifierBreakdown(),
            action_interaction=self.pose,
            summary=self.pose.content,
        )

    def test_the_pose_goes_and_the_outcome_keeps_its_source(self) -> None:
        response = self.api(self.account_of(self.ysmay)).delete(
            reverse("interaction-detail", args=[self.pose.pk])
        )

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Interaction.objects.filter(pk=self.pose.pk).exists())
        stored = ConsequenceOutcome.objects.get(pk=self.outcome.pk)
        self.assertIsNone(stored.action_interaction_id)
        self.assertEqual(stored.action_interaction_timestamp, self.pose.timestamp)
        self.assertEqual(stored.summary, "Ysmay vaults the rail and lands badly.")


@tag("postgres")
class StaffDeleteAJournalEntryAnotherPlayerPraised(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.entry = JournalEntryFactory(title="On the Low Bridge")
        self.praise = PraiseFactory(parent=self.entry, title="Well said")

    def test_the_delete_is_refused_while_the_praise_stands(self) -> None:
        client = _staff_client(self)
        url = reverse("admin:arxii_journalentry_delete", args=[self.entry.pk])

        page = client.get(url)
        client.post(url, {"post": "yes"})

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "protected")
        self.assertTrue(JournalEntry.objects.filter(pk=self.entry.pk).exists())
        self.praise.refresh_from_db()
        self.assertEqual(self.praise.parent_id, self.entry.pk)

    def test_a_wipe_that_takes_both_still_works(self) -> None:
        JournalEntry.objects.filter(pk__in=[self.entry.pk, self.praise.pk]).delete()

        self.assertFalse(JournalEntry.objects.filter(pk__in=[self.entry.pk, self.praise.pk]))


@tag("postgres")
class StaffDeleteAnAssistPatternAHelperUsed(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.declaration = MissionSupportDeclarationFactory()
        self.pattern = self.declaration.pattern

    def test_the_delete_is_refused_and_the_pattern_is_retired_instead(self) -> None:
        client = _staff_client(self)
        url = reverse("admin:arxii_missionassistpattern_delete", args=[self.pattern.pk])

        page = client.get(url)
        client.post(url, {"post": "yes"})
        self.pattern.is_active = False
        self.pattern.save(update_fields=["is_active"])

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "protected")
        stored = MissionSupportDeclaration.objects.get(pk=self.declaration.pk)
        self.assertEqual(stored.pattern_id, self.pattern.pk)
        self.assertFalse(MissionAssistPattern.objects.get(pk=self.pattern.pk).is_active)


@tag("postgres")
class StaffDeleteTwoAlliesASurgeWasAbout(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        participant = CombatParticipantFactory(encounter=CombatEncounterFactory())
        self.allies = [CharacterSheetFactory(), CharacterSheetFactory()]
        self.surges = [
            DramaticSurgeRecord.objects.create(
                encounter=participant.encounter,
                participant=participant,
                trigger_kind=SurgeTriggerKind.ALLY_PERIL,
                subject_sheet=ally,
                amount=2,
                round_number=1,
            )
            for ally in self.allies
        ]

    def test_both_deletes_go_through_and_the_surges_go_with_them(self) -> None:
        client = _staff_client(self)

        for ally in self.allies:
            response = client.post(
                reverse("admin:arxii_charactersheet_delete", args=[ally.pk]), {"post": "yes"}
            )
            self.assertEqual(response.status_code, 302, response.content[:2000])

        self.assertFalse(DramaticSurgeRecord.objects.filter(pk__in=[s.pk for s in self.surges]))
