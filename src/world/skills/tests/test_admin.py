"""Saving a skill in the admin gives it the modifier target a card's bonus lands on (#4820)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.skills.factories import SkillFactory


class SkillAdminSaveTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("skilladmin", "s@example.com", "pw-123456")
        cls.skill = SkillFactory(trait__name="Sailing")

    def _post_change(self, skill, **extra):
        self.client.force_login(self.staff)
        data = {
            "trait": skill.trait.pk,
            "tooltip": "Boats.",
            "display_order": 0,
            "is_active": "on",
            "specializations-TOTAL_FORMS": 0,
            "specializations-INITIAL_FORMS": 0,
            "specializations-MIN_NUM_FORMS": 0,
            "specializations-MAX_NUM_FORMS": 1000,
            "_save": "Save",
        }
        data.update(extra)
        return self.client.post(
            reverse("admin:arxii_skill_change", args=[skill.pk]), data, follow=True
        )

    def test_saving_a_skill_makes_its_stat_target(self) -> None:
        assert ModifierTarget.get_for_trait(self.skill.trait) is None
        response = self._post_change(self.skill)
        assert response.status_code == 200
        target = ModifierTarget.objects.get(target_trait=self.skill.trait)
        assert (target.name, target.category.name) == ("sailing", "stat")

    def test_saving_again_keeps_the_one_target(self) -> None:
        self._post_change(self.skill)
        self._post_change(self.skill)
        assert ModifierTarget.objects.filter(target_trait=self.skill.trait).count() == 1

    def test_a_same_named_target_in_another_category_is_left_alone_and_named(self) -> None:
        """The ``stealth`` roll modifier predates the Stealth skill: the save makes no second
        row of that name (the paste would refuse the shared name) and tells staff to
        retarget the existing one."""
        skill = SkillFactory(trait__name="Stealth")
        roll = ModifierTargetFactory(
            name="stealth", category=ModifierCategoryFactory(name="roll_modifier")
        )
        response = self._post_change(skill)
        assert ModifierTarget.objects.filter(name="stealth").count() == 1
        assert ModifierTarget.get_for_trait(skill.trait) is None
        assert roll.target_trait_id is None
        messages = [str(message) for message in response.context["messages"]]
        assert any("Retarget that row" in message for message in messages), messages
