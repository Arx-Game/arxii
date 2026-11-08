"""A skill is authored on one admin page: its Trait (#5006, #5008).

Saving a skill-type trait gives it the modifier target a card's bonus lands on (#4820).
"""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import Specialization
from world.traits.admin import (
    SKILL_WITH_SPECIALIZATIONS_RETYPED_MESSAGE,
    SPECIALIZATIONS_ON_NON_SKILL_TRAIT_MESSAGE,
)
from world.traits.models import Trait, TraitCategory, TraitType


class TraitAdminSkillTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("skilladmin", "s@example.com", "pw-123456")

    def setUp(self) -> None:
        # get_for_trait's class-level map outlives each test's rollback.
        ModifierTarget.clear_trait_cache()
        self.client.force_login(self.staff)

    def _post(self, url: str, trait_type: str, name: str, **extra: object):
        """Post the Trait form as a browser does, every inline at its defaults."""
        data: dict[str, object] = {
            "name": name,
            "trait_type": trait_type,
            "category": TraitCategory.MAGIC,
            "is_public": "on",
            "display_order": 0,
            "is_active": "on",
            "_save": "Save",
        }
        for inline in self.client.get(url).context["inline_admin_formsets"]:
            formset = inline.formset
            for field, value in formset.management_form.initial.items():
                data[f"{formset.prefix}-{field}"] = value
            for form in formset.extra_forms:  # an untouched row, as the browser sends it
                for field in form.fields:
                    initial = form.get_initial_for_field(form.fields[field], field)
                    if initial is True:
                        data[form.add_prefix(field)] = "on"
                    elif initial is not None and initial is not False:
                        data[form.add_prefix(field)] = initial
        data.update(extra)
        return self.client.post(url, data, follow=True)

    def _add(self, trait_type: str, **extra: object):
        return self._post(reverse("admin:arxii_trait_add"), trait_type, "Invocation", **extra)

    def test_one_save_makes_the_skill_its_specialization_and_its_bonus_target(self) -> None:
        self._add(
            TraitType.SKILL,
            tooltip="Calling down a power.",
            display_order=7,
            **{"specializations-0-name": "Storms", "specializations-0-display_order": 0},
        )
        skill = Trait.objects.get(name="Invocation")
        assert (skill.tooltip, skill.display_order, skill.is_active) == (
            "Calling down a power.",
            7,
            True,
        )
        assert list(Specialization.objects.filter(parent_skill=skill).values_list("name")) == [
            ("Storms",)
        ]
        target = ModifierTarget.objects.get(target_trait=skill)
        assert (target.name, target.category.name) == ("invocation", "stat")

    def test_specializations_on_a_stat_trait_are_refused(self) -> None:
        response = self._add(TraitType.STAT, **{"specializations-0-name": "Storms"})
        assert not Trait.objects.filter(name="Invocation").exists()
        assert SPECIALIZATIONS_ON_NON_SKILL_TRAIT_MESSAGE in response.content.decode()

    def test_a_skill_with_specializations_cannot_be_retyped(self) -> None:
        skill = SkillFactory(name="Sailing", category=TraitCategory.MAGIC)
        SpecializationFactory(parent_skill=skill, name="Rigging")
        url = reverse("admin:arxii_trait_change", args=[skill.pk])
        response = self._post(url, TraitType.STAT, "Sailing")
        assert SKILL_WITH_SPECIALIZATIONS_RETYPED_MESSAGE in response.content.decode()
        assert Trait.objects.filter(pk=skill.pk).values_list("trait_type", flat=True)[0] == (
            TraitType.SKILL
        )

    def test_saving_again_keeps_the_one_target(self) -> None:
        skill = SkillFactory(name="Sailing", category=TraitCategory.MAGIC)
        url = reverse("admin:arxii_trait_change", args=[skill.pk])
        self._post(url, TraitType.SKILL, "Sailing")
        self._post(url, TraitType.SKILL, "Sailing")
        assert ModifierTarget.objects.filter(target_trait=skill).count() == 1

    def test_a_same_named_target_in_another_category_is_left_alone_and_named(self) -> None:
        """The ``stealth`` roll modifier predates the Stealth skill: the save makes no second
        row of that name (the paste would refuse the shared name) and tells staff to
        retarget the existing one."""
        skill = SkillFactory(name="Stealth", category=TraitCategory.MAGIC)
        roll = ModifierTargetFactory(
            name="stealth", category=ModifierCategoryFactory(name="roll_modifier")
        )
        url = reverse("admin:arxii_trait_change", args=[skill.pk])
        response = self._post(url, TraitType.SKILL, "Stealth")
        assert ModifierTarget.objects.filter(name="stealth").count() == 1
        assert ModifierTarget.get_for_trait(skill) is None
        assert roll.target_trait_id is None
        messages = [str(message) for message in response.context["messages"]]
        assert any("Retarget that row" in message for message in messages), messages
