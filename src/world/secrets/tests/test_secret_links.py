"""A secret's persona and story links (#4528): staff-set, read by the staff shape only."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.scenes.factories import PersonaFactory
from world.secrets.factories import SecretFactory
from world.secrets.models import Secret
from world.stories.factories import StoryFactory


class SecretLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.sheet = CharacterSheetFactory()
        cls.secret = SecretFactory(subject_sheet=cls.sheet)
        cls.persona = PersonaFactory(name="Aerfrith")
        cls.story = StoryFactory(title="The Voice in the Dark")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_staff_patch_sets_the_persona_and_story_and_reads_them_back(self):
        url = reverse("secrets:authored-detail", args=[self.secret.pk])
        response = self.client.patch(
            url, {"about_persona": self.persona.pk, "story": self.story.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["about_persona_name"], "Aerfrith")
        self.assertEqual(response.data["story_title"], "The Voice in the Dark")
        self.secret.refresh_from_db()
        self.assertEqual(self.secret.about_persona_id, self.persona.pk)
        self.assertEqual(self.secret.story_id, self.story.pk)
        self.assertIn(self.secret, self.story.anchored_secrets.all())
        self.assertIn(self.secret, self.persona.secrets_about.all())

    def test_staff_create_carries_the_links(self):
        url = reverse("secrets:authored-list")
        response = self.client.post(
            url,
            {
                "subject_sheet": self.sheet.pk,
                "content": "A ring that is not the ring it looks like.",
                "about_persona": self.persona.pk,
                "story": self.story.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        created = Secret.objects.get(pk=response.data["id"])
        self.assertEqual(created.about_persona_id, self.persona.pk)
        self.assertEqual(created.story_id, self.story.pk)

    def test_a_deleted_story_leaves_the_secret_standing(self):
        self.secret.story = self.story
        self.secret.save(update_fields=["story"])
        self.story.delete()
        self.secret.refresh_from_db()
        self.assertIsNone(self.secret.story_id)


class SecretAdminPickerTests(TestCase):
    """The Secret admin lists the subject's held distinctions as a picker (#4528)."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = AccountFactory(username="picker-staff", is_staff=True, is_superuser=True)
        cls.sheet = CharacterSheetFactory()
        cls.secret = SecretFactory(subject_sheet=cls.sheet)
        cls.held = CharacterDistinctionFactory(
            character=cls.sheet, distinction=DistinctionFactory(name="Evil Advice")
        )
        cls.linked = CharacterDistinctionFactory(
            character=cls.sheet,
            distinction=DistinctionFactory(name="Maladaptive Coping Mechanism"),
            secret=cls.secret,
        )
        cls.elsewhere = CharacterDistinctionFactory(distinction=DistinctionFactory(name="Wrathful"))

    def test_change_page_offers_the_subjects_distinctions_with_the_linked_one_ticked(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:arxii_secret_change", args=[self.secret.pk]))
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        choices = list(form.fields["distinctions"].queryset)
        self.assertIn(self.held, choices)
        self.assertIn(self.linked, choices)
        self.assertNotIn(self.elsewhere, choices)
        self.assertEqual(list(form.fields["distinctions"].initial), [self.linked])
        self.assertContains(response, "Distinctions held in this secret")

    def test_add_page_has_no_picker(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:arxii_secret_add"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Distinctions held in this secret")
