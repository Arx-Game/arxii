"""Tests for the superuser-only 'Load sane defaults' admin button (#651)."""

import os
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.seeds.tests.content_stub import stub_content_root


class TestSeedAdminButton(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_run_requires_superuser(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("admin_seed_run"))
        self.assertEqual(resp.status_code, 403)

    @stub_content_root()
    def test_superuser_can_run_and_is_redirected(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.post(reverse("admin_seed_run"))
        self.assertEqual(resp.status_code, 302)

    def test_run_without_content_repo_flashes_message_and_redirects(self) -> None:
        """No raw 500 when CONTENT_REPO_PATH is unset (#2474 Task 3 follow-on).

        seed_dev_database() now raises ContentError loudly when no content
        repo is configured; the admin view must catch that (mirroring
        content_load_views.content_load_run) and flash the message instead
        of crashing.
        """
        self.client.force_login(self.super)
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            resp = self.client.post(reverse("admin_seed_run"))
        self.assertEqual(resp.status_code, 302)
        redirected = self.client.get(resp.url)
        messages = [str(m) for m in redirected.context["messages"]]
        self.assertTrue(any("CONTENT_REPO_PATH" in m for m in messages))
