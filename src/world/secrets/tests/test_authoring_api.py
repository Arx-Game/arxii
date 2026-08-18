"""Tests for the staff secret-authoring endpoints (#3266)."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.factories import SecretCategoryFactory, SecretFactory
from world.secrets.models import Secret
from world.secrets.services import author_secret


class AuthoredSecretViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Mirror the account-factory import used by test_secret_tab_api.py
        # (see that file's imports; use the same staff/non-staff account setup).
        from evennia_extensions.factories import AccountFactory

        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.category = SecretCategoryFactory(is_active=True)
        cls.inactive_category = SecretCategoryFactory(is_active=False)
        cls.existing = SecretFactory(subject_sheet=cls.sheet)
        SecretFactory(subject_sheet=cls.other_sheet)

    def setUp(self):
        self.client = APIClient()

    def test_anonymous_and_non_staff_rejected_everywhere(self):
        list_url = reverse("secrets:authored-list")
        for client_setup in (None, self.player):
            if client_setup:
                self.client.force_authenticate(client_setup)
            assert self.client.get(list_url, {"subject": self.sheet.pk}).status_code == 403
            assert self.client.post(list_url, {}, format="json").status_code == 403
            self.client.force_authenticate(None)

    def test_list_requires_subject_and_scopes_to_it(self):
        self.client.force_authenticate(self.staff)
        url = reverse("secrets:authored-list")
        assert self.client.get(url).status_code == 400
        response = self.client.get(url, {"subject": self.sheet.pk})
        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [self.existing.id]

    def test_create_sets_gm_provenance_and_round_trips(self):
        self.client.force_authenticate(self.staff)
        url = reverse("secrets:authored-list")
        body = {
            "subject_sheet": self.sheet.pk,
            "content": "She buried the survey markers herself.",
            "level": SecretLevel.UNCOMMON_KNOWLEDGE,
            "category": self.category.pk,
            "consequences": "The land claim collapses.",
            "subject_aware": False,
        }
        response = self.client.post(url, body, format="json")
        assert response.status_code == 201, response.data
        secret = Secret.objects.get(pk=response.data["id"])
        assert secret.provenance == SecretProvenance.GM_AUTHORED
        assert secret.author_persona is None
        assert secret.subject_aware is False
        assert secret.subject_sheet == self.sheet

    def test_create_translates_secret_error_to_400(self):
        # Force a model-invariant violation through the API. PLAYER_FLAVOR
        # above level 1 violates Secret.clean()'s flavor cap - but provenance
        # is fixed to GM_AUTHORED by the endpoint, so instead use whatever
        # invariant IS reachable: an invalid level value.
        self.client.force_authenticate(self.staff)
        url = reverse("secrets:authored-list")
        response = self.client.post(
            url,
            {"subject_sheet": self.sheet.pk, "content": "x", "level": 99},
            format="json",
        )
        assert response.status_code == 400

    def test_patch_edits_and_revalidates(self):
        self.client.force_authenticate(self.staff)
        url = reverse("secrets:authored-detail", args=[self.existing.pk])
        response = self.client.patch(
            url, {"content": "Sharper phrasing.", "subject_aware": False}, format="json"
        )
        assert response.status_code == 200, response.data
        self.existing.refresh_from_db()
        assert self.existing.content == "Sharper phrasing."
        assert self.existing.subject_aware is False

    def test_categories_lists_active_only(self):
        self.client.force_authenticate(self.staff)
        url = reverse("secrets:authored-categories")
        response = self.client.get(url)
        assert response.status_code == 200
        ids = [row["id"] for row in response.data]
        assert self.category.pk in ids
        assert self.inactive_category.pk not in ids


class AuthorSecretSubjectAwareTests(TestCase):
    def test_author_secret_accepts_subject_aware(self):
        sheet = CharacterSheetFactory()
        secret = author_secret(
            subject_sheet=sheet,
            provenance=SecretProvenance.GM_AUTHORED,
            content="Knows the pass.",
            subject_aware=False,
        )
        assert secret.subject_aware is False
