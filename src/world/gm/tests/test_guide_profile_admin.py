"""The Guide admin page, laid out as the approved demo's staff screen (#4418)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory
from world.gm.models import GuideProfile
from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory, RosterEntryFactory
from world.roster.models import NPCLoan
from world.roster.services.staff_characters import mint_gm_character
from world.scenes.factories import SceneFactory


def _npc_entry(name: str):
    return RosterEntryFactory(character_sheet__character=CharacterFactory(db_key=name))


class GuideProfileAdminTests(TestCase):
    """Staff grant Ilsa the Guide role; Warden Osk lends her NPCs for The Siege."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="admin_staff", is_staff=True, is_superuser=True)
        cls.gm = AccountFactory(username="osk_account")
        GMProfileFactory(account=cls.gm, level=GMLevel.JUNIOR)
        mint_gm_character(cls.gm, "Warden Osk")
        cls.ilsa = AccountFactory(username="ilsa_account")
        cls.guide = GuideProfileFactory(account=cls.ilsa, display_name="Ilsa the Guide")
        cls.scene = SceneFactory(name="The Siege at Low Gate")

    def setUp(self) -> None:
        self.client.force_login(self.staff)
        self.change_url = reverse("admin:arxii_guideprofile_change", args=[self.guide.pk])

    def _loan(self, name: str, **extra) -> NPCLoan:
        values = {
            "roster_entry": _npc_entry(name),
            "borrower": self.ilsa,
            "offered_by": self.gm,
            "scene": self.scene,
            "status": NPCLoanStatus.ACTIVE,
            "started_at": timezone.now(),
        }
        values.update(extra)
        return NPCLoanFactory(**values)

    def test_granted_by_is_the_staff_account_that_saves_the_grant(self) -> None:
        add = self.client.get(reverse("admin:arxii_guideprofile_add"))
        self.assertContains(add, "Set to you on save")
        self.assertNotContains(add, 'name="granted_by"')

        newcomer = AccountFactory(username="bram_account")
        saved = self.client.post(
            reverse("admin:arxii_guideprofile_add"),
            {"account": newcomer.pk, "is_active": "on", "display_name": "Bram the Guide"},
        )
        self.assertEqual(saved.status_code, 302, saved.content[:2000])
        grant = GuideProfile.objects.get(account=newcomer)
        self.assertEqual(grant.granted_by, self.staff)

        # A later edit by another staff account keeps who granted it.
        other = AccountFactory(username="other_staff", is_staff=True, is_superuser=True)
        self.client.force_login(other)
        edited = self.client.post(
            reverse("admin:arxii_guideprofile_change", args=[grant.pk]),
            {"account": newcomer.pk, "display_name": "Bram, Guide"},
        )
        self.assertEqual(edited.status_code, 302, edited.content[:2000])
        grant.refresh_from_db()
        self.assertEqual(grant.granted_by, self.staff)
        self.assertFalse(grant.is_active)

    def test_the_page_has_the_demos_three_sections(self) -> None:
        page = self.client.get(self.change_url)
        for index, heading in enumerate(("Who", "Right now", "Last 30 days")):
            self.assertContains(
                page,
                f'<h2 id="fieldset-0-{index}-heading" class="fieldset-heading">{heading}</h2>',
                html=True,
            )

    def test_right_now_lists_each_active_loan_with_who_lent_it(self) -> None:
        vael = self._loan("Captain Vael")
        self._loan("Sergeant Rook", status=NPCLoanStatus.ENDED, ended_at=timezone.now())

        page = self.client.get(self.change_url)
        self.assertContains(page, "Captain Vael")
        self.assertNotContains(page, "Sergeant Rook")
        self.assertContains(page, "<td>Warden Osk</td>", html=True)
        self.assertContains(page, reverse("admin:arxii_scene_change", args=[self.scene.pk]))
        self.assertContains(
            page, reverse("admin:arxii_rosterentry_change", args=[vael.roster_entry_id])
        )
        self.assertContains(
            page,
            reverse("admin:arxii_guideprofile_return_loan", args=[self.guide.pk, vael.pk]),
        )

    def test_return_to_gm_confirms_then_ends_that_loan(self) -> None:
        vael = self._loan("Captain Vael")
        rook = self._loan("Sergeant Rook")
        url = reverse("admin:arxii_guideprofile_return_loan", args=[self.guide.pk, vael.pk])

        confirm = self.client.get(url)
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "Captain Vael")
        # The page's form rows and submit row are styled only if forms.css reaches it.
        self.assertContains(confirm, "admin/css/forms.css")
        vael.refresh_from_db()
        self.assertEqual(vael.status, NPCLoanStatus.ACTIVE)

        returned = self.client.post(url)
        self.assertRedirects(returned, self.change_url)
        vael.refresh_from_db()
        rook.refresh_from_db()
        self.assertEqual(vael.status, NPCLoanStatus.ENDED)
        self.assertEqual(rook.status, NPCLoanStatus.ACTIVE)

        # An ended loan, or another Guide's, has no Return to GM page.
        self.assertEqual(self.client.get(url).status_code, 404)
        stranger = self._loan("Corporal Brann", borrower=AccountFactory())
        other = reverse("admin:arxii_guideprofile_return_loan", args=[self.guide.pk, stranger.pk])
        self.assertEqual(self.client.post(other).status_code, 404)
        stranger.refresh_from_db()
        self.assertEqual(stranger.status, NPCLoanStatus.ACTIVE)

    def test_last_30_days_counts_the_hand_offs(self) -> None:
        now = timezone.now()
        long_ago = now - timedelta(days=45)
        # Accepted and still active.
        self._loan("Captain Vael")
        # Accepted, then ended with the scene: not taken back early.
        finished = SceneFactory(name="Done", date_finished=now - timedelta(hours=2))
        self._loan(
            "Sergeant Rook",
            scene=finished,
            status=NPCLoanStatus.ENDED,
            started_at=now - timedelta(hours=3),
            ended_at=now - timedelta(hours=2),
        )
        # Accepted, then taken back while the scene was still running.
        self._loan(
            "Corporal Brann",
            status=NPCLoanStatus.ENDED,
            started_at=now - timedelta(hours=3),
            ended_at=now - timedelta(hours=1),
        )
        # Declined.
        self._loan("Gate guards", status=NPCLoanStatus.DECLINED, started_at=None, ended_at=now)
        # Older than the window: counts for nothing.
        self._loan(
            "Old Hob",
            status=NPCLoanStatus.ENDED,
            started_at=long_ago,
            ended_at=long_ago,
        )

        page = self.client.get(self.change_url)
        self.assertContains(page, "3 accepted, 1 declined, 1 taken back early")
