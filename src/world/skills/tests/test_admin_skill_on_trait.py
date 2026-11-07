"""A skill is authored on one admin page: the Trait form's Skill section (#5006).

Drives the real admin add/change views through the test client, the way staff do, and
checks the rows the one Save leaves behind: the trait, its skill, and the modifier
target a distinction's bonus to the skill lands on (#4820).
"""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.mechanics.models import ModifierTarget
from world.skills.admin import SKILL_ON_NON_SKILL_TRAIT_MESSAGE
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import Skill
from world.traits.factories import TraitFactory
from world.traits.models import Trait, TraitCategory, TraitType


class SkillOnTraitAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser(
            "traitskilladmin", "t@example.com", "pw-123456"
        )

    def setUp(self) -> None:
        # get_for_trait keeps a class-level map that outlives each test's rollback, and
        # trait pks repeat across tests, so a stale entry would hide a missing target.
        ModifierTarget.clear_trait_cache()
        self.client.force_login(self.staff)

    def _management(self, response) -> dict[str, object]:
        """The management-form fields of every inline the page rendered, untouched."""
        data: dict[str, object] = {}
        for inline in response.context["inline_admin_formsets"]:
            formset = inline.formset
            for field, value in formset.management_form.initial.items():
                data[f"{formset.prefix}-{field}"] = value
        return data

    def _skill_prefix(self, response) -> str:
        prefixes = [
            inline.formset.prefix
            for inline in response.context["inline_admin_formsets"]
            if inline.formset.model is Skill
        ]
        assert prefixes, "the page has no Skill section"
        return prefixes[0]

    def _add(self, *, trait_type: str, skill_fields: dict[str, object] | None):
        page = self.client.get(reverse("admin:arxii_trait_add"), {"trait_type": trait_type})
        assert page.status_code == 200
        prefix = self._skill_prefix(page)
        data: dict[str, object] = {
            "name": "Invocation",
            "trait_type": trait_type,
            "category": TraitCategory.MAGIC,
            "description": "Calling on a power that answers.",
            "is_public": "on",
            "_save": "Save",
            **self._management(page),
        }
        # What a browser posts for the untouched section: its rendered defaults.
        data[f"{prefix}-0-display_order"] = 0
        data[f"{prefix}-0-is_active"] = "on"
        for field, value in (skill_fields or {}).items():
            data[f"{prefix}-0-{field}"] = value
        return self.client.post(reverse("admin:arxii_trait_add"), data, follow=True)

    def test_the_add_page_prefills_the_skill_type_from_the_new_skill_link(self) -> None:
        page = self.client.get(reverse("admin:arxii_trait_add"), {"trait_type": "skill"})
        assert page.context["adminform"].form.initial["trait_type"] == "skill"
        assert "Skill (fill in to make this trait a skill)" in page.content.decode()

    def test_one_save_makes_the_trait_the_skill_and_its_bonus_target(self) -> None:
        response = self._add(
            trait_type=TraitType.SKILL,
            skill_fields={
                "tooltip": "Calling down a power.",
                "display_order": 7,
                "is_active": "on",
            },
        )
        assert response.status_code == 200
        trait = Trait.objects.get(name="Invocation")
        skill = Skill.objects.get(trait=trait)
        assert (skill.tooltip, skill.display_order, skill.is_active) == (
            "Calling down a power.",
            7,
            True,
        )
        target = ModifierTarget.objects.get(target_trait=trait)
        assert (target.name, target.category.name) == ("invocation", "stat")

    def test_an_untouched_skill_section_makes_no_skill(self) -> None:
        """Some skill-type traits are rolled by checks without being a trained skill."""
        self._add(trait_type=TraitType.SKILL, skill_fields=None)
        trait = Trait.objects.get(name="Invocation")
        assert not Skill.objects.filter(trait=trait).exists()

    def test_a_skill_section_on_a_stat_trait_is_refused(self) -> None:
        response = self._add(trait_type=TraitType.STAT, skill_fields={"tooltip": "Nope."})
        assert not Trait.objects.filter(name="Invocation").exists()
        assert SKILL_ON_NON_SKILL_TRAIT_MESSAGE in response.content.decode()

    def test_editing_the_skill_on_its_trait_page_saves_and_links_specializations(self) -> None:
        skill = SkillFactory(trait__name="Evocation", trait__category=TraitCategory.MAGIC)
        SpecializationFactory(parent_skill=skill, name="Wards")
        url = reverse("admin:arxii_trait_change", args=[skill.trait.pk])
        page = self.client.get(url)
        html = page.content.decode()
        assert "Wards" in html
        assert reverse("admin:arxii_skill_change", args=[skill.pk]) in html
        prefix = self._skill_prefix(page)
        data: dict[str, object] = {
            "name": "Evocation",
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.MAGIC,
            "description": "",
            "is_public": "on",
            "_save": "Save",
            **self._management(page),
            f"{prefix}-0-id": skill.pk,
            f"{prefix}-0-trait": skill.trait.pk,
            f"{prefix}-0-tooltip": "Words that bind.",
            f"{prefix}-0-display_order": 3,
            f"{prefix}-0-is_active": "on",
        }
        response = self.client.post(url, data, follow=True)
        assert response.status_code == 200
        skill.refresh_from_db()
        assert skill.tooltip == "Words that bind."
        assert ModifierTarget.get_for_trait(skill.trait) is not None

    def test_a_stat_trait_page_has_no_skill_section(self) -> None:
        stat = TraitFactory(name="Grace", trait_type=TraitType.STAT)
        page = self.client.get(reverse("admin:arxii_trait_change", args=[stat.pk]))
        assert page.status_code == 200
        models = [inline.formset.model for inline in page.context["inline_admin_formsets"]]
        assert Skill not in models
