"""Saving a skill in the admin gives it the modifier target a card's bonus lands on (#4820)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.skills.factories import (
    PathSkillSuggestionFactory,
    SkillFactory,
    SpecializationFactory,
)
from world.traits.models import Trait, TraitType


class SkillAdminSaveTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("skilladmin", "s@example.com", "pw-123456")
        cls.skill = SkillFactory(name="Sailing")

    def _post_change(self, skill, **extra):
        self.client.force_login(self.staff)
        data = {
            "name": skill.name,
            "category": skill.category,
            "is_public": "on",
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
        assert ModifierTarget.get_for_trait(self.skill) is None
        response = self._post_change(self.skill)
        assert response.status_code == 200
        target = ModifierTarget.objects.get(target_trait=self.skill)
        assert (target.name, target.category.name) == ("sailing", "stat")

    def test_saving_again_keeps_the_one_target(self) -> None:
        self._post_change(self.skill)
        self._post_change(self.skill)
        assert ModifierTarget.objects.filter(target_trait=self.skill).count() == 1

    def test_a_same_named_target_in_another_category_is_left_alone_and_named(self) -> None:
        """The ``stealth`` roll modifier predates the Stealth skill: the save makes no second
        row of that name (the paste would refuse the shared name) and tells staff to
        retarget the existing one."""
        skill = SkillFactory(name="Stealth")
        roll = ModifierTargetFactory(
            name="stealth", category=ModifierCategoryFactory(name="roll_modifier")
        )
        response = self._post_change(skill)
        assert ModifierTarget.objects.filter(name="stealth").count() == 1
        assert ModifierTarget.get_for_trait(skill) is None
        assert roll.target_trait_id is None
        messages = [str(message) for message in response.context["messages"]]
        assert any("Retarget that row" in message for message in messages), messages

    def _retype_to_stat(self, skill):
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_trait_change", args=[skill.pk])
        data = {
            "name": skill.name,
            "trait_type": TraitType.STAT,
            "category": skill.category,
            "display_order": 0,
            "is_active": "on",
            "_save": "Save",
        }
        for inline in self.client.get(url).context["inline_admin_formsets"]:
            formset = inline.formset
            for field, value in formset.management_form.initial.items():
                data[f"{formset.prefix}-{field}"] = value
        return self.client.post(url, data, follow=True).content.decode()

    def test_a_skill_in_use_cannot_be_retyped_on_the_trait_page(self) -> None:
        skill = SkillFactory(name="Rigging Lore")
        SpecializationFactory(parent_skill=skill, name="Knots")
        assert "This skill is still used by specializations" in self._retype_to_stat(skill)
        assert Trait.objects.filter(pk=skill.pk, trait_type=TraitType.SKILL).exists()

    def test_any_skill_fk_blocks_the_retype_not_only_specializations(self) -> None:
        skill = SkillFactory(name="Chart Reading")
        PathSkillSuggestionFactory(skill=skill)
        assert "path skill suggestions" in self._retype_to_stat(skill)
        assert Trait.objects.filter(pk=skill.pk, trait_type=TraitType.SKILL).exists()
