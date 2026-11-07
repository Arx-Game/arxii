"""The Import Data hub (#5001): one page listing every way authored content comes in."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB


class ImportHubTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "r@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()
        cls.url = reverse("admin_import_hub")

    def test_the_header_button_opens_the_hub(self) -> None:
        self.client.force_login(self.staff)
        body = self.client.get(reverse("admin:index")).content.decode()
        assert f'href="{self.url}" class="import-btn"' in body

    def test_staff_see_the_fixture_upload_and_no_paste(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        assert resp.status_code == 200
        body = resp.content.decode()
        assert reverse("admin_import_upload") in body
        assert reverse("admin_distinction_paste") not in body
        assert "_import/place_names/" not in body
        assert reverse("admin_content_load") not in body

    def test_a_superuser_sees_every_route(self) -> None:
        self.client.force_login(self.super)
        body = self.client.get(self.url).content.decode()
        for name in ("admin_distinction_paste", "admin_import_upload"):
            assert reverse(name) in body, name
        assert "_import/place_names/" in body
        assert "disaster recovery" in body
        # no CONTENT_REPO_PATH in tests: the content-repo panel says so and offers no link
        assert "CONTENT_REPO_PATH" in body
        assert reverse("admin_content_load") not in body

    def test_game_setup_points_its_import_links_at_the_hub(self) -> None:
        self.client.force_login(self.super)
        body = self.client.get(reverse("admin_game_setup")).content.decode()
        assert self.url in body
        assert reverse("admin_import_upload") not in body
