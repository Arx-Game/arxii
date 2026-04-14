"""Tests for GM table services."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from world.gm.constants import GMTableStatus
from world.gm.factories import (
    GMProfileFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.gm.services import (
    archive_table,
    create_table,
    join_table,
    leave_table,
    soft_leave_memberships_for_retired_persona,
    transfer_ownership,
)
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


class CreateTableTest(TestCase):
    def test_creates_table_with_gm(self) -> None:
        gm = GMProfileFactory()
        table = create_table(gm, "First Table")
        assert table.gm == gm
        assert table.name == "First Table"
        assert table.status == GMTableStatus.ACTIVE


class ArchiveTableTest(TestCase):
    def test_sets_status_and_timestamp(self) -> None:
        table = GMTableFactory()
        archive_table(table)
        table.refresh_from_db()
        assert table.status == GMTableStatus.ARCHIVED
        assert table.archived_at is not None

    def test_idempotent_when_already_archived(self) -> None:
        table = GMTableFactory()
        archive_table(table)
        first_archived_at = table.archived_at
        archive_table(table)
        table.refresh_from_db()
        assert table.archived_at == first_archived_at


class TransferOwnershipTest(TestCase):
    def test_reassigns_gm(self) -> None:
        table = GMTableFactory()
        new_gm = GMProfileFactory()
        transfer_ownership(table, new_gm)
        table.refresh_from_db()
        assert table.gm == new_gm


class JoinTableTest(TestCase):
    def test_creates_membership(self) -> None:
        table = GMTableFactory()
        persona = PersonaFactory()
        m = join_table(table, persona)
        assert m.pk is not None
        assert m.table == table
        assert m.persona == persona

    def test_rejects_temporary_persona(self) -> None:
        table = GMTableFactory()
        temp = PersonaFactory(persona_type=PersonaType.TEMPORARY)
        with self.assertRaises(ValidationError):
            join_table(table, temp)

    def test_idempotent_for_active_membership(self) -> None:
        table = GMTableFactory()
        persona = PersonaFactory()
        m1 = join_table(table, persona)
        m2 = join_table(table, persona)
        assert m1.pk == m2.pk

    def test_allows_rejoin_after_leaving(self) -> None:
        m1 = GMTableMembershipFactory()
        m1.left_at = timezone.now()
        m1.save()
        m2 = join_table(m1.table, m1.persona)
        assert m2.pk != m1.pk


class LeaveTableTest(TestCase):
    def test_sets_left_at(self) -> None:
        m = GMTableMembershipFactory()
        leave_table(m)
        m.refresh_from_db()
        assert m.left_at is not None

    def test_noop_when_already_left(self) -> None:
        m = GMTableMembershipFactory()
        leave_table(m)
        m.refresh_from_db()
        first = m.left_at
        leave_table(m)
        m.refresh_from_db()
        assert m.left_at == first


class SoftLeaveForRetiredPersonaTest(TestCase):
    def test_closes_active_memberships_only(self) -> None:
        persona = PersonaFactory()
        # Two active memberships across different tables
        m1 = GMTableMembershipFactory(persona=persona)
        m2 = GMTableMembershipFactory(persona=persona)
        # One already-closed
        closed = GMTableMembershipFactory(persona=persona)
        closed.left_at = timezone.now()
        closed.save()
        # Membership for a different persona
        other = GMTableMembershipFactory()

        count = soft_leave_memberships_for_retired_persona(persona)
        assert count == 2
        m1.refresh_from_db()
        m2.refresh_from_db()
        assert m1.left_at is not None
        assert m2.left_at is not None
        other.refresh_from_db()
        assert other.left_at is None


class GMApplicationQueueTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.gm.factories import GMProfileFactory, GMTableFactory
        from world.roster.factories import (
            RosterApplicationFactory,
            RosterEntryFactory,
        )
        from world.stories.factories import StoryFactory
        from world.stories.models import StoryParticipation

        cls.gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.gm)
        cls.other_gm = GMProfileFactory()
        cls.other_table = GMTableFactory(gm=cls.other_gm)

        # Entry whose story is at our GM's table
        cls.entry_at_table = RosterEntryFactory()
        story = StoryFactory(primary_table=cls.table)
        StoryParticipation.objects.create(
            story=story,
            character=cls.entry_at_table.character_sheet.character,
            is_active=True,
        )
        cls.app_at_table = RosterApplicationFactory(
            character=cls.entry_at_table.character_sheet.character,
        )

        # Entry at another GM's table
        cls.entry_at_other = RosterEntryFactory()
        other_story = StoryFactory(primary_table=cls.other_table)
        StoryParticipation.objects.create(
            story=other_story,
            character=cls.entry_at_other.character_sheet.character,
            is_active=True,
        )
        cls.app_at_other = RosterApplicationFactory(
            character=cls.entry_at_other.character_sheet.character,
        )

    def test_queue_includes_own_table_applications(self) -> None:
        from world.gm.services import gm_application_queue

        queue = gm_application_queue(self.gm)
        assert self.app_at_table in queue

    def test_queue_excludes_other_gm_applications(self) -> None:
        from world.gm.services import gm_application_queue

        queue = gm_application_queue(self.gm)
        assert self.app_at_other not in queue

    def test_queue_excludes_non_pending_applications(self) -> None:
        from world.gm.services import gm_application_queue
        from world.roster.models.choices import ApplicationStatus

        self.app_at_table.status = ApplicationStatus.APPROVED
        self.app_at_table.save()
        queue = gm_application_queue(self.gm)
        assert self.app_at_table not in queue

    def test_queue_empty_for_gm_with_no_tables(self) -> None:
        from world.gm.factories import GMProfileFactory
        from world.gm.services import gm_application_queue

        lonely_gm = GMProfileFactory()
        queue = gm_application_queue(lonely_gm)
        assert queue.count() == 0
