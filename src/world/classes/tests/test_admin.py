"""Saving an Aspect in the admin gives it the modifier target a card's bonus lands on (#4827)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.classes.factories import AspectFactory
from world.mechanics.constants import ASPECT_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget


class AspectAdminSaveTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("aspectadmin", "a@example.com", "pw-123456")

    def _post_change(self, aspect):
        self.client.force_login(self.staff)
        return self.client.post(
            reverse("admin:arxii_aspect_change", args=[aspect.pk]),
            {"name": aspect.name, "description": "Words and people.", "_save": "Save"},
            follow=True,
        )

    def test_saving_an_aspect_makes_its_target(self) -> None:
        diplomacy = AspectFactory(name="Diplomacy")
        response = self._post_change(diplomacy)
        assert response.status_code == 200
        target = ModifierTarget.objects.get(target_aspect=diplomacy)
        assert (target.name, target.category.name) == ("diplomacy", ASPECT_CATEGORY_NAME)

    def test_saving_again_keeps_the_one_target(self) -> None:
        diplomacy = AspectFactory(name="Diplomacy")
        self._post_change(diplomacy)
        self._post_change(diplomacy)
        assert ModifierTarget.objects.filter(target_aspect=diplomacy).count() == 1

    def test_a_same_named_target_elsewhere_is_left_alone_and_named(self) -> None:
        warfare = AspectFactory(name="Warfare")
        ModifierTargetFactory(name="warfare", category=ModifierCategoryFactory(name="check"))
        response = self._post_change(warfare)
        assert ModifierTarget.objects.filter(name="warfare").count() == 1
        assert not ModifierTarget.objects.filter(target_aspect=warfare).exists()
        messages = [str(message) for message in response.context["messages"]]
        assert any("Modifier targets admin" in message for message in messages), messages
