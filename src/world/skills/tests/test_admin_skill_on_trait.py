"""A skill is authored on one admin page: the Trait form's Skill section (#5006)."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.mechanics.models import ModifierTarget
from world.skills.admin_inlines import SKILL_ON_NON_SKILL_TRAIT_MESSAGE
from world.skills.models import Skill
from world.traits.models import Trait, TraitCategory, TraitType


class SkillOnTraitAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("skilltrait", "t@example.com", "pw-1234")

    def setUp(self) -> None:
        # get_for_trait's class-level map outlives each test's rollback.
        ModifierTarget.clear_trait_cache()
        self.client.force_login(self.staff)

    def _add(self, trait_type: str, **skill_fields: object):
        """Post the Trait add form as a browser does, the Skill section at its defaults."""
        url = reverse("admin:arxii_trait_add")
        data: dict[str, object] = {
            "name": "Invocation",
            "trait_type": trait_type,
            "category": TraitCategory.MAGIC,
            "_save": "Save",
        }
        for inline in self.client.get(url).context["inline_admin_formsets"]:
            formset = inline.formset
            for field, value in formset.management_form.initial.items():
                data[f"{formset.prefix}-{field}"] = value
        fields = {"display_order": 0, "is_active": "on", **skill_fields}
        data.update({f"skill-0-{field}": value for field, value in fields.items()})
        return self.client.post(url, data, follow=True)

    def test_one_save_makes_the_trait_the_skill_and_its_bonus_target(self) -> None:
        self._add(TraitType.SKILL, tooltip="Calling down a power.", display_order=7)
        trait = Trait.objects.get(name="Invocation")
        skill = Skill.objects.get(trait=trait)
        assert (skill.tooltip, skill.display_order) == ("Calling down a power.", 7)
        target = ModifierTarget.objects.get(target_trait=trait)
        assert (target.name, target.category.name) == ("invocation", "stat")

    def test_an_untouched_skill_section_makes_no_skill(self) -> None:
        self._add(TraitType.SKILL)
        assert Trait.objects.filter(name="Invocation").exists()
        assert not Skill.objects.filter(trait__name="Invocation").exists()

    def test_a_skill_section_on_a_stat_trait_is_refused(self) -> None:
        response = self._add(TraitType.STAT, tooltip="Nope.")
        assert not Trait.objects.filter(name="Invocation").exists()
        assert SKILL_ON_NON_SKILL_TRAIT_MESSAGE in response.content.decode()
