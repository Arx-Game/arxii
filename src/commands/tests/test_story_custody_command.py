"""Tests for the ``story protect``/``story clearance`` telnet subverbs (#2001 Task 7).

Mirrors ``test_story_command.py``'s structure. Covers: the permission matrix
(custodian/requester/staff/outsider) per subverb, identity-based clearance-request
fan-out, required-field errors, and one E2E: protect via telnet -> outsider
blocked (via ``check_subject_custody``, the same seam stake authoring gates
through) -> clearance request via telnet -> grant via telnet ->
``check_subject_custody`` now allows.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.story import CmdStory
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.items.factories import ItemInstanceFactory
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.stories.constants import (
    CustodyClearanceStatus,
    CustodyScope,
    StakeSubjectKind,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    CustodyClearanceFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.models import CustodyClearance, StoryProtectedSubject
from world.stories.services.boundaries import _subject_identity
from world.stories.services.custody import check_subject_custody


def _make_cmd(caller, args: str) -> CmdStory:
    """Build a CmdStory with the given caller and args."""
    cmd = CmdStory()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"story {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    """Return all positional string messages sent to *caller*.msg."""
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


def _caller(account, *, search_matches: list | None = None) -> MagicMock:
    caller = MagicMock()
    caller.msg = MagicMock()
    caller.account = account
    caller.search = MagicMock(return_value=search_matches if search_matches is not None else [])
    return caller


def _run(account, args: str, *, search_matches: list | None = None) -> list[str]:
    caller = _caller(account, search_matches=search_matches)
    cmd = _make_cmd(caller, args)
    cmd.func()
    return _messages(caller)


class CmdStoryProtectPermissionTests(TestCase):
    """`story protect <story-id> add|remove|list` permission matrix."""

    def setUp(self) -> None:
        self.lead_account = AccountFactory()
        self.lead_gm = GMProfileFactory(account=self.lead_account)
        self.table = GMTableFactory(gm=self.lead_gm)
        self.owner_account = AccountFactory()
        self.story = StoryFactory(owners=[self.owner_account], primary_table=self.table)

        self.staff_account = AccountFactory(is_staff=True)
        self.outsider_account = AccountFactory()

        self.npc_char = CharacterFactory(db_key="Protected NPC")
        self.sheet = CharacterSheetFactory(character=self.npc_char)

    def test_lead_gm_can_add(self) -> None:
        messages = _run(
            self.lead_account,
            f"protect {self.story.pk} add npc_fate=Protected NPC",
            search_matches=[self.npc_char],
        )
        self.assertTrue(any("Protected #" in m for m in messages), messages)

    def test_story_owner_can_add(self) -> None:
        messages = _run(
            self.owner_account,
            f"protect {self.story.pk} add npc_fate=Protected NPC",
            search_matches=[self.npc_char],
        )
        self.assertTrue(any("Protected #" in m for m in messages), messages)

    def test_staff_can_add(self) -> None:
        messages = _run(
            self.staff_account,
            f"protect {self.story.pk} add npc_fate=Protected NPC",
            search_matches=[self.npc_char],
        )
        self.assertTrue(any("Protected #" in m for m in messages), messages)

    def test_outsider_cannot_add(self) -> None:
        messages = _run(
            self.outsider_account,
            f"protect {self.story.pk} add npc_fate=Protected NPC",
            search_matches=[self.npc_char],
        )
        joined = " ".join(messages)
        self.assertIn("do not own or lead", joined.lower())
        self.assertFalse(StoryProtectedSubject.objects.filter(story=self.story).exists())

    def test_outsider_cannot_list(self) -> None:
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.sheet)
        messages = _run(self.outsider_account, f"protect {self.story.pk} list")
        joined = " ".join(messages)
        self.assertIn("do not own or lead", joined.lower())

    def test_outsider_cannot_remove(self) -> None:
        protected = StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.sheet)
        messages = _run(self.outsider_account, f"protect {self.story.pk} remove {protected.pk}")
        joined = " ".join(messages)
        self.assertIn("do not own or lead", joined.lower())
        protected.refresh_from_db()
        self.assertTrue(protected.is_active)


class CmdStoryProtectAddTests(TestCase):
    """Subject-ref resolution for `protect ... add` across each kind."""

    def setUp(self) -> None:
        self.lead_account = AccountFactory()
        self.lead_gm = GMProfileFactory(account=self.lead_account)
        self.table = GMTableFactory(gm=self.lead_gm)
        self.story = StoryFactory(owners=[], primary_table=self.table)

    def _add(self, args: str, *, search_matches: list | None = None) -> list[str]:
        return _run(
            self.lead_account, f"protect {self.story.pk} add {args}", search_matches=search_matches
        )

    def test_npc_fate_resolves_character_by_name(self) -> None:
        npc = CharacterFactory(db_key="Elenna Vale")
        sheet = CharacterSheetFactory(character=npc)
        messages = self._add("npc_fate=Elenna Vale", search_matches=[npc])
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.NPC_FATE)
        self.assertEqual(protected.subject_sheet_id, sheet.pk)

    def test_personal_jeopardy_resolves_character_by_name(self) -> None:
        pc = CharacterFactory(db_key="Some PC")
        sheet = CharacterSheetFactory(character=pc)
        messages = self._add("personal_jeopardy=Some PC", search_matches=[pc])
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.PERSONAL_JEOPARDY)
        self.assertEqual(protected.subject_sheet_id, sheet.pk)

    def test_unresolvable_character_name_errors(self) -> None:
        messages = self._add("npc_fate=Nobody Here", search_matches=[])
        joined = " ".join(messages)
        self.assertIn("no character found", joined.lower())
        self.assertFalse(StoryProtectedSubject.objects.filter(story=self.story).exists())

    def test_item_resolves_by_id(self) -> None:
        item = ItemInstanceFactory()
        messages = self._add(f"item={item.pk}")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.ITEM)
        self.assertEqual(protected.subject_item_id, item.pk)

    def test_item_unknown_id_errors(self) -> None:
        messages = self._add("item=999999")
        joined = " ".join(messages)
        self.assertIn("no item instance", joined.lower())

    def test_faction_resolves_organization_by_name(self) -> None:
        org = OrganizationFactory(name="The Silver Rose")
        messages = self._add("faction=The Silver Rose")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.FACTION)
        self.assertEqual(protected.subject_organization_id, org.pk)

    def test_faction_resolves_society_by_name_when_no_org_matches(self) -> None:
        society = SocietyFactory(name="The Undersea Court")
        messages = self._add("faction=The Undersea Court")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.FACTION)
        self.assertEqual(protected.subject_society_id, society.pk)

    def test_faction_unknown_name_errors(self) -> None:
        messages = self._add("faction=Nonexistent Group")
        joined = " ".join(messages)
        self.assertIn("no organization or society", joined.lower())

    def test_faction_name_collision_between_org_and_society_errors(self) -> None:
        # #2001 Task 7 review Fix 2: an ambiguous name matching both an Organization
        # and a Society must not silently pick the Organization — it asks the GM to
        # disambiguate via org=/society=.
        OrganizationFactory(name="The Ashfall Concord")
        SocietyFactory(name="The Ashfall Concord")
        messages = self._add("faction=The Ashfall Concord")
        joined = " ".join(messages)
        self.assertIn("matches both an organization and a society", joined.lower())
        self.assertIn("org=<name>", joined)
        self.assertIn("society=<name>", joined)
        self.assertFalse(StoryProtectedSubject.objects.filter(story=self.story).exists())

    def test_faction_name_collision_resolves_via_org_key(self) -> None:
        org = OrganizationFactory(name="The Ashfall Concord")
        SocietyFactory(name="The Ashfall Concord")
        messages = self._add("org=The Ashfall Concord")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.FACTION)
        self.assertEqual(protected.subject_organization_id, org.pk)

    def test_faction_name_collision_resolves_via_society_key(self) -> None:
        OrganizationFactory(name="The Ashfall Concord")
        society = SocietyFactory(name="The Ashfall Concord")
        messages = self._add("society=The Ashfall Concord")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.FACTION)
        self.assertEqual(protected.subject_society_id, society.pk)

    def test_location_uses_freeform_label(self) -> None:
        messages = self._add("location=The Old Well")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.LOCATION)
        self.assertEqual(protected.subject_label, "The Old Well")

    def test_custom_uses_freeform_label(self) -> None:
        messages = self._add("custom=The Signet Ring")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.CUSTOM)
        self.assertEqual(protected.subject_label, "The Signet Ring")

    def test_notes_and_beat_are_recorded(self) -> None:
        chapter = ChapterFactory(story=self.story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode)
        messages = self._add(f"custom=A Ring beat={beat.pk} notes=Load-bearing for the finale")
        self.assertTrue(any("Protected #" in m for m in messages), messages)
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.beat_id, beat.pk)
        self.assertEqual(protected.notes, "Load-bearing for the finale")

    def test_beat_from_another_story_rejected(self) -> None:
        other_story = StoryFactory()
        other_chapter = ChapterFactory(story=other_story)
        other_episode = EpisodeFactory(chapter=other_chapter)
        other_beat = BeatFactory(episode=other_episode)
        messages = self._add(f"custom=A Ring beat={other_beat.pk}")
        joined = " ".join(messages)
        self.assertIn("does not belong to this story", joined.lower())
        self.assertFalse(StoryProtectedSubject.objects.filter(story=self.story).exists())

    def test_missing_kind_key_errors(self) -> None:
        messages = self._add("beat=1 notes=oops")
        joined = " ".join(messages)
        self.assertIn("provide exactly one subject kind", joined.lower())

    def test_two_kind_keys_errors(self) -> None:
        messages = self._add("custom=Ring location=Well")
        joined = " ".join(messages)
        self.assertIn("provide exactly one subject kind", joined.lower())


class CmdStoryProtectRemoveListTests(TestCase):
    def setUp(self) -> None:
        self.lead_account = AccountFactory()
        self.lead_gm = GMProfileFactory(account=self.lead_account)
        self.table = GMTableFactory(gm=self.lead_gm)
        self.story = StoryFactory(owners=[], primary_table=self.table)

    def test_remove_deactivates_rather_than_deletes(self) -> None:
        protected = StoryProtectedSubjectFactory(
            story=self.story,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_sheet=None,
            subject_label="A Ring",
        )
        messages = _run(self.lead_account, f"protect {self.story.pk} remove {protected.pk}")
        self.assertTrue(any("Deactivated protection" in m for m in messages), messages)
        protected.refresh_from_db()
        self.assertFalse(protected.is_active)
        self.assertTrue(StoryProtectedSubject.objects.filter(pk=protected.pk).exists())

    def test_remove_unknown_id_errors(self) -> None:
        messages = _run(self.lead_account, f"protect {self.story.pk} remove 999999")
        joined = " ".join(messages)
        self.assertIn("no protected subject", joined.lower())

    def test_list_shows_active_and_inactive(self) -> None:
        active = StoryProtectedSubjectFactory(
            story=self.story,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_sheet=None,
            subject_label="Active Thing",
        )
        inactive = StoryProtectedSubjectFactory(
            story=self.story,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_sheet=None,
            subject_label="Inactive Thing",
            is_active=False,
        )
        messages = _run(self.lead_account, f"protect {self.story.pk} list")
        joined = " ".join(messages)
        self.assertIn(f"[{active.pk}]", joined)
        self.assertIn("Active Thing", joined)
        self.assertIn(f"[{inactive.pk}]", joined)
        self.assertIn("Inactive Thing", joined)
        self.assertIn("(inactive)", joined)

    def test_list_empty_says_so(self) -> None:
        messages = _run(self.lead_account, f"protect {self.story.pk} list")
        joined = " ".join(messages)
        self.assertIn("no protected subjects", joined.lower())


class CmdStoryClearanceRequestTests(TestCase):
    """`story clearance request ...` — pk path, identity-path fan-out, dupes."""

    def setUp(self) -> None:
        self.custodian_account = AccountFactory()
        self.custodian_gm = GMProfileFactory(account=self.custodian_account)
        self.table = GMTableFactory(gm=self.custodian_gm)
        self.protecting_story = StoryFactory(owners=[], primary_table=self.table)

        self.other_custodian_account = AccountFactory()
        self.other_custodian_gm = GMProfileFactory(account=self.other_custodian_account)
        self.other_table = GMTableFactory(gm=self.other_custodian_gm)
        self.other_protecting_story = StoryFactory(owners=[], primary_table=self.other_table)

        self.sheet = CharacterSheetFactory()
        self.subject = StoryProtectedSubjectFactory(
            story=self.protecting_story, subject_sheet=self.sheet
        )

        self.requester_account = AccountFactory()
        self.requester_gm = GMProfileFactory(account=self.requester_account)

        self.npc_char = self.sheet.character

    def test_requires_gm_profile(self) -> None:
        no_gm_account = AccountFactory()
        messages = _run(
            no_gm_account, f"clearance request protected={self.subject.pk} scope=appear"
        )
        joined = " ".join(messages)
        self.assertIn("gm profile", joined.lower())

    def test_missing_scope_errors(self) -> None:
        messages = _run(self.requester_account, f"clearance request protected={self.subject.pk}")
        joined = " ".join(messages)
        self.assertIn("scope is required", joined.lower())

    def test_pk_path_creates_pending_clearance(self) -> None:
        messages = _run(
            self.requester_account,
            f"clearance request protected={self.subject.pk} scope=appear message=please",
        )
        self.assertTrue(any("Requested appear clearance" in m for m in messages), messages)
        clearance = CustodyClearance.objects.get(
            protected_subject=self.subject, requested_by=self.requester_gm
        )
        self.assertEqual(clearance.status, CustodyClearanceStatus.PENDING)
        self.assertEqual(clearance.scope, CustodyScope.APPEAR)
        self.assertEqual(clearance.message, "please")

    def test_pk_path_duplicate_is_a_hard_error(self) -> None:
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        messages = _run(
            self.requester_account,
            f"clearance request protected={self.subject.pk} scope=appear",
        )
        joined = " ".join(messages)
        self.assertIn("already have a live clearance request", joined.lower())
        self.assertEqual(
            CustodyClearance.objects.filter(
                protected_subject=self.subject, requested_by=self.requester_gm
            ).count(),
            1,
        )

    def test_identity_path_fans_out_across_stories(self) -> None:
        """Two independent stories protect the same NPC identity — one request each."""
        other_subject = StoryProtectedSubjectFactory(
            story=self.other_protecting_story, subject_sheet=self.sheet
        )
        messages = _run(
            self.requester_account,
            "clearance request npc_fate=Whoever scope=appear",
            search_matches=[self.npc_char],
        )
        joined = " ".join(messages)
        self.assertIn("Requested appear clearance (2 new)", joined)
        self.assertTrue(
            CustodyClearance.objects.filter(
                protected_subject=self.subject, requested_by=self.requester_gm
            ).exists()
        )
        self.assertTrue(
            CustodyClearance.objects.filter(
                protected_subject=other_subject, requested_by=self.requester_gm
            ).exists()
        )

    def test_identity_path_skips_already_pending_and_reports_it(self) -> None:
        # A second, independent protection shares the NPC's identity (mirrors
        # test_identity_path_fans_out_across_stories) — the first already has a
        # live request from this requester at this scope; only the second is new.
        other_subject = StoryProtectedSubjectFactory(
            story=self.other_protecting_story, subject_sheet=self.sheet
        )
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        messages = _run(
            self.requester_account,
            "clearance request npc_fate=Whoever scope=appear",
            search_matches=[self.npc_char],
        )
        joined = " ".join(messages)
        self.assertIn("Requested appear clearance (1 new)", joined)
        self.assertIn("already had a live request", joined.lower())
        self.assertTrue(
            CustodyClearance.objects.filter(
                protected_subject=other_subject, requested_by=self.requester_gm
            ).exists()
        )
        # Still only the one pre-existing clearance for the first subject — no dupe.
        self.assertEqual(
            CustodyClearance.objects.filter(
                protected_subject=self.subject, requested_by=self.requester_gm
            ).count(),
            1,
        )

    def test_no_matching_identity_errors(self) -> None:
        unrelated_char = CharacterFactory(db_key="Unrelated")
        CharacterSheetFactory(character=unrelated_char)
        messages = _run(
            self.requester_account,
            "clearance request npc_fate=Unrelated scope=appear",
            search_matches=[unrelated_char],
        )
        joined = " ".join(messages)
        self.assertIn("no active protected subject matches", joined.lower())

    def test_both_protected_and_kind_given_errors(self) -> None:
        messages = _run(
            self.requester_account,
            f"clearance request protected={self.subject.pk} npc_fate=Whoever scope=appear",
            search_matches=[self.npc_char],
        )
        joined = " ".join(messages)
        self.assertIn("provide exactly one of protected", joined.lower())


class CmdStoryClearanceGrantDenyPermissionTests(TestCase):
    """`story clearance grant|deny <id>` — custodian Lead GM only, no staff bypass."""

    def setUp(self) -> None:
        self.custodian_account = AccountFactory()
        self.custodian_gm = GMProfileFactory(account=self.custodian_account)
        self.table = GMTableFactory(gm=self.custodian_gm)
        self.protecting_story = StoryFactory(owners=[], primary_table=self.table)
        self.subject = StoryProtectedSubjectFactory(story=self.protecting_story)

        self.requester_account = AccountFactory()
        self.requester_gm = GMProfileFactory(account=self.requester_account)

        self.staff_account = AccountFactory(is_staff=True)
        self.outsider_account = AccountFactory()
        self.outsider_gm = GMProfileFactory(account=self.outsider_account)

    def _pending(self) -> CustodyClearance:
        return CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )

    def test_custodian_can_grant(self) -> None:
        clearance = self._pending()
        messages = _run(self.custodian_account, f"clearance grant {clearance.pk}")
        self.assertTrue(any("Granted clearance" in m for m in messages), messages)
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.GRANTED)

    def test_custodian_can_deny(self) -> None:
        clearance = self._pending()
        messages = _run(self.custodian_account, f"clearance deny {clearance.pk}")
        self.assertTrue(any("Denied clearance" in m for m in messages), messages)
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.DENIED)

    def test_staff_without_matching_gm_profile_cannot_grant(self) -> None:
        clearance = self._pending()
        messages = _run(self.staff_account, f"clearance grant {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("gm profile", joined.lower())
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.PENDING)

    def test_requester_cannot_grant_own_request(self) -> None:
        clearance = self._pending()
        messages = _run(self.requester_account, f"clearance grant {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("only the protecting story's lead gm", joined.lower())
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.PENDING)

    def test_outsider_gm_cannot_grant(self) -> None:
        clearance = self._pending()
        messages = _run(self.outsider_account, f"clearance grant {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("only the protecting story's lead gm", joined.lower())
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.PENDING)

    def test_grant_requires_id(self) -> None:
        messages = _run(self.custodian_account, "clearance grant")
        joined = " ".join(messages)
        self.assertIn("usage", joined.lower())

    def test_note_is_recorded(self) -> None:
        clearance = self._pending()
        _run(self.custodian_account, f"clearance grant {clearance.pk} note=looks fine")
        clearance.refresh_from_db()
        self.assertEqual(clearance.response_note, "looks fine")


class CmdStoryClearanceEscalateTests(TestCase):
    def setUp(self) -> None:
        self.custodian_account = AccountFactory()
        self.custodian_gm = GMProfileFactory(account=self.custodian_account)
        self.table = GMTableFactory(gm=self.custodian_gm)
        self.protecting_story = StoryFactory(owners=[], primary_table=self.table)
        self.subject = StoryProtectedSubjectFactory(story=self.protecting_story)

        self.requester_account = AccountFactory()
        self.requester_gm = GMProfileFactory(account=self.requester_account)
        self.outsider_account = AccountFactory()
        self.outsider_gm = GMProfileFactory(account=self.outsider_account)

    def test_requester_can_escalate_a_denied_request(self) -> None:
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            status=CustodyClearanceStatus.DENIED,
        )
        messages = _run(self.requester_account, f"clearance escalate {clearance.pk}")
        self.assertTrue(any("Escalated clearance" in m for m in messages), messages)
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.ESCALATED)

    def test_non_requester_cannot_escalate(self) -> None:
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            status=CustodyClearanceStatus.DENIED,
        )
        messages = _run(self.outsider_account, f"clearance escalate {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("only the requesting gm", joined.lower())
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.DENIED)

    def test_pending_and_not_stale_cannot_escalate(self) -> None:
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            status=CustodyClearanceStatus.PENDING,
        )
        messages = _run(self.requester_account, f"clearance escalate {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("not in a state that allows", joined.lower())
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.PENDING)


class CmdStoryClearanceResolveTests(TestCase):
    def setUp(self) -> None:
        self.custodian_account = AccountFactory()
        self.custodian_gm = GMProfileFactory(account=self.custodian_account)
        self.table = GMTableFactory(gm=self.custodian_gm)
        self.protecting_story = StoryFactory(owners=[], primary_table=self.table)
        self.subject = StoryProtectedSubjectFactory(story=self.protecting_story)

        self.requester_account = AccountFactory()
        self.requester_gm = GMProfileFactory(account=self.requester_account)
        self.staff_account = AccountFactory(is_staff=True)

    def _escalated(self) -> CustodyClearance:
        return CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            status=CustodyClearanceStatus.ESCALATED,
        )

    def test_staff_can_resolve_grant(self) -> None:
        clearance = self._escalated()
        messages = _run(self.staff_account, f"clearance resolve {clearance.pk} grant")
        self.assertTrue(any("Granted (staff) clearance" in m for m in messages), messages)
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.GRANTED)
        self.assertEqual(clearance.staff_resolver_id, self.staff_account.pk)

    def test_staff_can_resolve_deny(self) -> None:
        clearance = self._escalated()
        messages = _run(self.staff_account, f"clearance resolve {clearance.pk} deny")
        self.assertTrue(any("Denied (staff) clearance" in m for m in messages), messages)
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.DENIED)

    def test_custodian_gm_cannot_resolve(self) -> None:
        clearance = self._escalated()
        messages = _run(self.custodian_account, f"clearance resolve {clearance.pk} grant")
        joined = " ".join(messages)
        self.assertIn("only staff", joined.lower())
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.ESCALATED)

    def test_requester_cannot_resolve(self) -> None:
        clearance = self._escalated()
        messages = _run(self.requester_account, f"clearance resolve {clearance.pk} grant")
        joined = " ".join(messages)
        self.assertIn("only staff", joined.lower())

    def test_resolve_requires_grant_or_deny_token(self) -> None:
        clearance = self._escalated()
        messages = _run(self.staff_account, f"clearance resolve {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("usage", joined.lower())


class CmdStoryClearanceRevokeTests(TestCase):
    def setUp(self) -> None:
        self.custodian_account = AccountFactory()
        self.custodian_gm = GMProfileFactory(account=self.custodian_account)
        self.table = GMTableFactory(gm=self.custodian_gm)
        self.protecting_story = StoryFactory(owners=[], primary_table=self.table)
        self.subject = StoryProtectedSubjectFactory(story=self.protecting_story)

        self.requester_account = AccountFactory()
        self.requester_gm = GMProfileFactory(account=self.requester_account)
        self.staff_account = AccountFactory(is_staff=True)
        self.outsider_account = AccountFactory()

    def _granted(self) -> CustodyClearance:
        return CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            status=CustodyClearanceStatus.GRANTED,
        )

    def test_custodian_can_revoke(self) -> None:
        clearance = self._granted()
        messages = _run(self.custodian_account, f"clearance revoke {clearance.pk}")
        self.assertTrue(any("Revoked clearance" in m for m in messages), messages)
        clearance.refresh_from_db()
        self.assertIsNotNone(clearance.revoked_at)

    def test_staff_can_revoke(self) -> None:
        clearance = self._granted()
        messages = _run(self.staff_account, f"clearance revoke {clearance.pk}")
        self.assertTrue(any("Revoked clearance" in m for m in messages), messages)
        clearance.refresh_from_db()
        self.assertIsNotNone(clearance.revoked_at)

    def test_outsider_cannot_revoke(self) -> None:
        clearance = self._granted()
        messages = _run(self.outsider_account, f"clearance revoke {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("lead gm or staff may revoke", joined.lower())
        clearance.refresh_from_db()
        self.assertIsNone(clearance.revoked_at)

    def test_requester_cannot_revoke_their_own_grant(self) -> None:
        clearance = self._granted()
        messages = _run(self.requester_account, f"clearance revoke {clearance.pk}")
        joined = " ".join(messages)
        self.assertIn("lead gm or staff may revoke", joined.lower())
        clearance.refresh_from_db()
        self.assertIsNone(clearance.revoked_at)


class CmdStoryClearanceListTests(TestCase):
    def setUp(self) -> None:
        self.custodian_account = AccountFactory()
        self.custodian_gm = GMProfileFactory(account=self.custodian_account)
        self.table = GMTableFactory(gm=self.custodian_gm)
        self.protecting_story = StoryFactory(owners=[], primary_table=self.table)
        self.subject = StoryProtectedSubjectFactory(story=self.protecting_story)

        self.requester_account = AccountFactory()
        self.requester_gm = GMProfileFactory(account=self.requester_account)

        self.outsider_account = AccountFactory()
        self.outsider_gm = GMProfileFactory(account=self.outsider_account)

        self.staff_account = AccountFactory(is_staff=True)

    def test_requester_sees_own_request(self) -> None:
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject, requested_by=self.requester_gm
        )
        messages = _run(self.requester_account, "clearance list")
        joined = " ".join(messages)
        self.assertIn(f"[{clearance.pk}]", joined)

    def test_custodian_sees_requests_against_their_story(self) -> None:
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject, requested_by=self.requester_gm
        )
        messages = _run(self.custodian_account, "clearance list")
        joined = " ".join(messages)
        self.assertIn(f"[{clearance.pk}]", joined)

    def test_outsider_does_not_see_unrelated_clearance(self) -> None:
        CustodyClearanceFactory(protected_subject=self.subject, requested_by=self.requester_gm)
        messages = _run(self.outsider_account, "clearance list")
        joined = " ".join(messages)
        self.assertIn("no custody clearances", joined.lower())

    def test_staff_sees_everything(self) -> None:
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject, requested_by=self.requester_gm
        )
        messages = _run(self.staff_account, "clearance list")
        joined = " ".join(messages)
        self.assertIn(f"[{clearance.pk}]", joined)

    def test_pending_filter_excludes_resolved(self) -> None:
        pending = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            status=CustodyClearanceStatus.PENDING,
        )
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            status=CustodyClearanceStatus.GRANTED,
        )
        messages = _run(self.requester_account, "clearance list pending")
        joined = " ".join(messages)
        self.assertIn(f"[{pending.pk}]", joined)


class CmdStoryCustodyE2ETests(TestCase):
    """protect via telnet -> outsider blocked -> clearance request via telnet ->
    grant via telnet -> ``check_subject_custody`` allows (#2001 Task 7).

    "Stake authoring" is exercised via ``check_subject_custody`` directly — the
    same seam ``StakeSerializer._check_custody`` gates through (mirrors
    ``CustodyClearanceE2ETests`` in ``test_custody_api.py``, which does the
    same rather than constructing a full Beat/Episode/Stake hierarchy).
    """

    def setUp(self) -> None:
        self.custodian_account = AccountFactory()
        self.custodian_gm = GMProfileFactory(account=self.custodian_account)
        self.table = GMTableFactory(gm=self.custodian_gm)
        self.protecting_story = StoryFactory(
            owners=[self.custodian_account], primary_table=self.table
        )

        self.npc_char = CharacterFactory(db_key="Elenna Vale")
        self.sheet = CharacterSheetFactory(character=self.npc_char)

        self.requester_account = AccountFactory()
        self.requester_gm = GMProfileFactory(account=self.requester_account)

    def test_protect_request_grant_unlocks_custody(self) -> None:
        # 1. Protect via telnet, as the custodian GM.
        protect_messages = _run(
            self.custodian_account,
            f"protect {self.protecting_story.pk} add npc_fate=Elenna Vale",
            search_matches=[self.npc_char],
        )
        self.assertTrue(any("Protected #" in m for m in protect_messages), protect_messages)
        protected = StoryProtectedSubject.objects.get(
            story=self.protecting_story, subject_sheet=self.sheet
        )

        identity = _subject_identity(StakeSubjectKind.NPC_FATE, self.sheet.pk, None, None, None, "")

        # 2. The outsider (requester) is blocked at the custody-check seam stake
        # authoring gates through.
        before = check_subject_custody(
            subject_identity=identity,
            actor_account=self.requester_account,
            scope=CustodyScope.APPEAR,
        )
        self.assertFalse(before.allowed)

        # 3. Clearance request via telnet.
        request_messages = _run(
            self.requester_account,
            f"clearance request protected={protected.pk} scope=appear",
        )
        self.assertTrue(
            any("Requested appear clearance" in m for m in request_messages), request_messages
        )
        clearance = CustodyClearance.objects.get(
            protected_subject=protected, requested_by=self.requester_gm
        )
        self.assertEqual(clearance.status, CustodyClearanceStatus.PENDING)

        # 4. Grant via telnet, as the custodian.
        grant_messages = _run(self.custodian_account, f"clearance grant {clearance.pk}")
        self.assertTrue(any("Granted clearance" in m for m in grant_messages), grant_messages)
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.GRANTED)

        # 5. check_subject_custody now allows the requester.
        after = check_subject_custody(
            subject_identity=identity,
            actor_account=self.requester_account,
            scope=CustodyScope.APPEAR,
        )
        self.assertTrue(after.allowed)
