"""The item template family authoring pages (#5041), driven through the admin itself."""

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from core.app_domains import credited_content_models
from evennia_extensions.factories import AccountFactory
from web.admin.authoring.links import workbench_editor_url
from world.items.constants import (
    ARMOR_TEMPLATE_KINDS,
    WEAPON_TEMPLATE_KINDS,
    WORN_TEMPLATE_KINDS,
    GearArchetype,
)
from world.items.factories import ItemTemplateFactory
from world.items.models import (
    ArmorTemplate,
    ItemTemplate,
    ShieldTemplate,
    WeaponTemplate,
    WornTemplate,
)
from world.skills.models import Skill
from world.traits.models import Trait

FAMILY_PAGES = {
    "weapontemplate": WeaponTemplate,
    "armortemplate": ArmorTemplate,
    "shieldtemplate": ShieldTemplate,
    "worntemplate": WornTemplate,
}


def _post_data(response, fields: dict) -> dict:
    """The add form's own management data (every inline empty) plus ``fields``."""
    data = {"_save": "Save", **fields}
    for inline in response.context["inline_admin_formsets"]:
        prefix = inline.formset.prefix
        data[f"{prefix}-TOTAL_FORMS"] = "0"
        data[f"{prefix}-INITIAL_FORMS"] = "0"
    return data


class ItemTemplateFamilyAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True, is_superuser=True)
        cls.sword = ItemTemplateFactory(name="Family Sword", gear_archetype="melee_one_hand")
        cls.plate = ItemTemplateFactory(name="Family Plate", gear_archetype="heavy_armor")
        cls.buckler = ItemTemplateFactory(name="Family Buckler", gear_archetype="shield")
        cls.ring = ItemTemplateFactory(name="Family Ring", gear_archetype="jewelry")
        cls.potion = ItemTemplateFactory(name="Family Potion", gear_archetype="other")

    def setUp(self) -> None:
        self.client.force_login(self.staff)

    def test_each_family_page_lists_only_its_own_templates(self) -> None:
        expected = {
            "weapontemplate": self.sword,
            "armortemplate": self.plate,
            "shieldtemplate": self.buckler,
            "worntemplate": self.ring,
        }
        everyone = {self.sword, self.plate, self.buckler, self.ring, self.potion}
        for page, template in expected.items():
            with self.subTest(page=page):
                response = self.client.get(reverse(f"admin:arxii_{page}_changelist"))
                self.assertEqual(response.status_code, 200)
                listed = set(response.context["cl"].queryset)
                self.assertIn(template, listed)
                self.assertFalse(listed & (everyone - {template}))

    def test_a_family_list_links_each_credit_to_the_workbench_as_an_item_template(self) -> None:
        # Empty the identity map so the list loads its rows as WeaponTemplate instances.
        ItemTemplate.flush_instance_cache()
        response = self.client.get(reverse("admin:arxii_weapontemplate_changelist"))
        expected = workbench_editor_url("items.ItemTemplate", self.sword.pk)
        self.assertContains(response, escape(expected))
        self.assertNotContains(response, "items.WeaponTemplate")
        offered = response.context["cl"].filter_specs[1].lookup_choices
        self.assertEqual([value for value, _label in offered], list(WEAPON_TEMPLATE_KINDS))

    def test_the_family_pages_sit_beside_item_templates_on_the_admin_home(self) -> None:
        response = self.client.get(reverse("admin:index"))
        items = next(
            app
            for app in response.context["app_list"]
            if any(entry["object_name"] == "ItemTemplate" for entry in app["models"])
        )
        names = [entry["object_name"] for entry in items["models"]]
        start = names.index("ItemTemplate")
        self.assertEqual(
            names[start : start + 5],
            ["ItemTemplate", "WeaponTemplate", "ArmorTemplate", "ShieldTemplate", "WornTemplate"],
        )

    def test_each_add_page_offers_only_its_kinds_and_fields_with_no_inline_rows(self) -> None:
        expected_kinds = {
            "weapontemplate": WEAPON_TEMPLATE_KINDS,
            "armortemplate": ARMOR_TEMPLATE_KINDS,
            "worntemplate": WORN_TEMPLATE_KINDS,
        }
        for page in FAMILY_PAGES:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"admin:arxii_{page}_add"))
                self.assertEqual(response.status_code, 200)
                form = response.context["adminform"].form
                for inline in response.context["inline_admin_formsets"]:
                    self.assertEqual(inline.formset.total_form_count(), 0)
                # Never on a family page: the all-kinds page's container and on-use groups.
                for absent in ("is_container", "is_consumable", "on_use_pool", "is_stackable"):
                    self.assertNotIn(absent, form.fields)
                if page == "shieldtemplate":
                    self.assertNotIn("gear_archetype", form.fields)
                    # The fixed kind still shows, as a read-only row, before the first save.
                    self.assertContains(response, '<div class="readonly">Shield</div>', html=True)
                    continue
                offered = [value for value, _label in form.fields["gear_archetype"].choices]
                self.assertEqual(offered, ["", *expected_kinds[page]])
                self.assertEqual(form.initial["gear_archetype"], "")
        weapon_form = self.client.get(reverse("admin:arxii_weapontemplate_add"))
        self.assertNotIn("base_armor_soak", weapon_form.context["adminform"].form.fields)
        worn_form = self.client.get(reverse("admin:arxii_worntemplate_add"))
        for combat in ("base_armor_soak", "base_weapon_damage", "weapon_class"):
            self.assertNotIn(combat, worn_form.context["adminform"].form.fields)

    def test_a_throwable_dagger_saves_through_the_weapon_page(self) -> None:
        url = reverse("admin:arxii_weapontemplate_add")
        page = self.client.get(url)
        response = self.client.post(
            url,
            _post_data(
                page,
                {
                    "name": "Family Dagger",
                    "description": "Short.",
                    "is_active": "on",
                    "gear_archetype": GearArchetype.MELEE_ONE_HAND,
                    "base_weapon_damage": "4",
                    "can_be_thrown": "on",
                    "weight": "1.00",
                    "size": "1",
                    "value": "10",
                    "max_durability": "0",
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        dagger = ItemTemplate.objects.get(name="Family Dagger")
        self.assertEqual(dagger.gear_archetype, GearArchetype.MELEE_ONE_HAND)
        self.assertEqual(dagger.base_weapon_damage, 4)
        self.assertTrue(dagger.can_be_thrown)

    def test_a_weapon_page_refuses_a_kind_from_another_family(self) -> None:
        url = reverse("admin:arxii_weapontemplate_add")
        page = self.client.get(url)
        fields = {"name": "Not A Weapon", "gear_archetype": GearArchetype.CLOTHING}
        fields |= {"weight": "1", "size": "1", "value": "0", "max_durability": "0"}
        response = self.client.post(url, _post_data(page, fields))
        self.assertEqual(response.status_code, 200)
        self.assertIn("gear_archetype", response.context["adminform"].form.errors)
        self.assertFalse(ItemTemplate.objects.filter(name="Not A Weapon").exists())

    def test_a_shield_saves_as_a_shield_with_soak_and_bash(self) -> None:
        url = reverse("admin:arxii_shieldtemplate_add")
        page = self.client.get(url)
        fields = {"name": "Family Round Shield", "base_armor_soak": "2", "base_weapon_damage": "1"}
        fields |= {"weight": "6", "size": "2", "value": "30", "max_durability": "0"}
        response = self.client.post(url, _post_data(page, fields))
        self.assertEqual(response.status_code, 302)
        shield = ItemTemplate.objects.get(name="Family Round Shield")
        self.assertEqual(shield.gear_archetype, GearArchetype.SHIELD)
        self.assertEqual((shield.base_armor_soak, shield.base_weapon_damage), (2, 1))


class ItemTemplateFamilyPlumbingTests(TestCase):
    def test_staff_with_item_template_rights_can_use_a_family_page(self) -> None:
        staff = AccountFactory(is_staff=True)
        staff.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="arxii",
                codename__in=["view_itemtemplate", "add_itemtemplate", "change_itemtemplate"],
            )
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("admin:arxii_weapontemplate_add"))
        self.assertEqual(response.status_code, 200)

    def test_every_item_template_page_opens_its_inlines_with_no_rows(self) -> None:
        for model in (ItemTemplate, *FAMILY_PAGES.values()):
            for inline in admin.site._registry[model].inlines:
                with self.subTest(model=model.__name__, inline=inline.__name__):
                    self.assertEqual(inline.extra, 0)

    def test_the_workbench_counts_item_templates_once(self) -> None:
        found = credited_content_models()
        self.assertIn(ItemTemplate, found)
        # Every proxy of a credited model is left out, the older Skill proxy of Trait too.
        for proxy in (*FAMILY_PAGES.values(), Skill):
            self.assertNotIn(proxy, found)
        self.assertIn(Trait, found)
