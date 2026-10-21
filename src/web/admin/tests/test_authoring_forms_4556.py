"""Authoring-form admin changes for #4556: pickers, fields, list pages, help text."""

from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.classes.factories import PathFactory
from world.conditions.factories import ConditionCheckModifierFactory, ConditionTemplateFactory
from world.game_clock.models import GameClock
from world.items.factories import ItemTemplateFactory
from world.items.models import WeaponClass
from world.mechanics.factories import ModifierTargetFactory
from world.tasking.factories import TaskTemplateFactory

ADD_PAGES = (
    "arxii_path",
    "arxii_achievement",
    "arxii_tasktemplate",
    "arxii_conditiontemplate",
    "arxii_modifiertarget",
    "arxii_conditioncheckmodifier",
    "arxii_itemtemplate",
    "arxii_weaponclass",
    "arxii_domaincrisistype",
    "arxii_consequencepool",
)


class AuthoringFormPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True, is_superuser=True)
        cls.path = PathFactory()
        cls.task_template = TaskTemplateFactory()
        cls.condition = ConditionTemplateFactory()
        cls.target = ModifierTargetFactory()
        cls.check_type = CheckTypeFactory()
        cls.other_check_type = CheckTypeFactory()
        cls.mod = ConditionCheckModifierFactory(condition=cls.condition, check_type=cls.check_type)
        ConditionCheckModifierFactory(condition=cls.condition, check_type=cls.other_check_type)
        cls.weapon_class = WeaponClass.objects.create(name="Test Blade Class")
        cls.template = ItemTemplateFactory(weapon_class=cls.weapon_class)

    def setUp(self) -> None:
        self.client.force_login(self.staff)

    def test_add_pages_load(self) -> None:
        for name in ADD_PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(f"admin:{name}_add"))
                self.assertEqual(response.status_code, 200)

    def test_game_clock_add_page_carries_year_help(self) -> None:
        GameClock.objects.all().delete()
        response = self.client.get(reverse("admin:arxii_gameclock_add"))
        self.assertContains(response, "world's")
        self.assertContains(response, "first-appearance")

    def test_change_pages_load(self) -> None:
        pages = (
            ("arxii_path", self.path),
            ("arxii_tasktemplate", self.task_template),
            ("arxii_conditiontemplate", self.condition),
            ("arxii_modifiertarget", self.target),
            ("arxii_conditioncheckmodifier", self.mod),
            ("arxii_itemtemplate", self.template),
        )
        for name, obj in pages:
            with self.subTest(page=name):
                response = self.client.get(reverse(f"admin:{name}_change", args=(obj.pk,)))
                self.assertEqual(response.status_code, 200)

    def test_path_form_has_style_action_category_and_icon_name(self) -> None:
        response = self.client.get(reverse("admin:arxii_path_add"))
        for field in ("style", "action_category", "icon_name"):
            self.assertIn(field, response.context["adminform"].form.fields)

    def test_modifier_target_help_text_names_language_traits(self) -> None:
        response = self.client.get(reverse("admin:arxii_modifiertarget_add"))
        field = response.context["adminform"].form.fields["target_trait"]
        self.assertIn("language", field.help_text)

    def test_check_modifier_changelist_filters_by_check_type(self) -> None:
        url = reverse("admin:arxii_conditioncheckmodifier_changelist")
        response = self.client.get(url, {"check_type__id__exact": self.check_type.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].result_list), [self.mod])

    def test_item_template_changelist_shows_weapon_class(self) -> None:
        response = self.client.get(reverse("admin:arxii_itemtemplate_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("weapon_class", response.context["cl"].list_editable)
        self.assertContains(response, "form-0-weapon_class")

    def test_weapon_class_changelist_shows_template_count(self) -> None:
        response = self.client.get(reverse("admin:arxii_weaponclass_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cl"].result_list[0].template_total, 1)

    def test_task_template_check_type_autocomplete_answers(self) -> None:
        response = self.client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "arxii",
                "model_name": "tasktemplate",
                "field_name": "check_type",
                "term": "x",
            },
        )
        self.assertEqual(response.status_code, 200)
