"""The vow page through the test client (#4880, slice 2 of #4843).

Staff open one vow, edit its fields, specialties, focus picks and limits, and save once.
A save that moves the price of a pick live characters hold stops first with each
holder's old and new total, and writes nothing until confirmed.

Built in ``setUp``: the holder memberships create Evennia objects, which
``setUpTestData`` cannot deepcopy. Holder rows come straight from factories, since
``CharacterVowFocusPick`` runs its rules in ``clean()`` only.
"""

from __future__ import annotations

from pathlib import Path
import re

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.contributors.factories import ContentContributorFactory
from world.covenants.constants import FocusPickLimitKind
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CharacterVowFocusPickFactory,
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
    VowAddedEffectFactory,
    VowFocusPickFactory,
    VowFocusPickLimitFactory,
)
from world.covenants.models import CharacterVowFocusPick, CovenantRole, VowFocusPick
from world.magic.constants import TechniqueFunction


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class VowPageCase(TestCase):
    def setUp(self) -> None:
        self.author = _superuser("vbauthor")
        self.writer = ContentContributorFactory(name="Vow Writer")
        PlayerData.objects.create(account=self.author, contributor=self.writer)
        self.unlinked = _superuser("vbunlinked")
        self.role = CovenantRoleFactory(name="Fulmination", slug="fulmination", speed_rank=3)
        self.specialty = CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=self.role, function=TechniqueFunction.BARRIER, multiplier_tenths=15
        )
        self.charge = VowFocusPickFactory(
            covenant_role=self.role, pick_level=1, name="Arcing Charge", value=4
        )
        self.kneel = VowFocusPickFactory(
            covenant_role=self.role, pick_level=3, name="Kneel", value=4
        )
        self.kneel_limit = VowFocusPickLimitFactory(
            pick=self.kneel, kind=FocusPickLimitKind.TARGET, frequency_tenths=5
        )  # Kneel costs 2
        self.halo = VowFocusPickFactory(
            covenant_role=self.role, pick_level=3, name="Static Halo", value=2
        )
        self.ysolde = CharacterCovenantRoleFactory(
            covenant_role=self.role, character_sheet__character__db_key="Ysolde Marrow"
        )
        self.corvin = CharacterCovenantRoleFactory(
            covenant_role=self.role, character_sheet__character__db_key="Corvin Ashe"
        )
        CharacterVowFocusPickFactory(character_role=self.ysolde, pick=self.kneel)
        CharacterVowFocusPickFactory(character_role=self.corvin, pick=self.kneel)
        CharacterVowFocusPickFactory(character_role=self.corvin, pick=self.halo)

    @property
    def url(self) -> str:
        return reverse("admin_vow_builder", args=[self.role.pk])

    def _get(self) -> str:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _payload(self, **overrides: str) -> dict[str, str]:
        """Everything the page posts for the vow as stored, with ``overrides`` on top."""
        role = self.role
        data: dict[str, str] = {
            "name": role.name,
            "covenant_type": role.covenant_type,
            "description": role.description,
            "parent_role": "",
            "resonance": "",
            "speed_rank": str(role.speed_rank),
            "sword_weight": str(role.sword_weight),
            "shield_weight": str(role.shield_weight),
            "crown_weight": str(role.crown_weight),
            "command_tier": role.command_tier,
            "specialties-TOTAL_FORMS": "1",
            "specialties-INITIAL_FORMS": "1",
            "specialties-0-id": str(self.specialty.pk),
            "specialties-0-covenant_role": str(role.pk),
            "specialties-0-function": self.specialty.function,
            "specialties-0-multiplier_tenths": str(self.specialty.multiplier_tenths),
        }
        picks = list(VowFocusPick.objects.filter(covenant_role=role).order_by("pick_level", "name"))
        data["picks-TOTAL_FORMS"] = str(len(picks))
        data["picks-INITIAL_FORMS"] = str(len(picks))
        for index, pick in enumerate(picks):
            prefix = f"picks-{index}"
            data[f"{prefix}-id"] = str(pick.pk)
            data[f"{prefix}-covenant_role"] = str(role.pk)
            data[f"{prefix}-pick_level"] = str(pick.pick_level)
            data[f"{prefix}-name"] = pick.name
            data[f"{prefix}-value"] = str(pick.value)
            data[f"{prefix}-description"] = pick.description
            limits = list(pick.limits.order_by("kind"))
            lprefix = f"l{pick.pk}"
            data[f"{lprefix}-TOTAL_FORMS"] = str(len(limits))
            data[f"{lprefix}-INITIAL_FORMS"] = str(len(limits))
            for lindex, limit in enumerate(limits):
                data[f"{lprefix}-{lindex}-id"] = str(limit.pk)
                data[f"{lprefix}-{lindex}-pick"] = str(pick.pk)
                data[f"{lprefix}-{lindex}-kind"] = limit.kind
                data[f"{lprefix}-{lindex}-frequency_tenths"] = str(limit.frequency_tenths)
                data[f"{lprefix}-{lindex}-reduction"] = str(limit.reduction)
                data[f"{lprefix}-{lindex}-description"] = limit.description
        data.update(overrides)
        return data

    def _pick_key(self, pick: VowFocusPick, field: str) -> str:
        picks = list(
            VowFocusPick.objects.filter(covenant_role=self.role).order_by("pick_level", "name")
        )
        return f"picks-{picks.index(pick)}-{field}"

    def _stored_value(self, pick: VowFocusPick) -> int:
        return VowFocusPick.objects.filter(pk=pick.pk).values_list("value", flat=True).get()


class VowPageGetTests(VowPageCase):
    def test_renders_inside_the_admin_chrome_with_picks_by_level_and_the_rail(self) -> None:
        self.client.force_login(self.author)
        body = self._get()
        self.assertIn(str(admin.site.site_header), body)
        self.assertIn("Fulmination", body)
        for text in ("Level 1", "Level 2", "Level 3", "Arcing Charge", "Kneel", "Static Halo"):
            self.assertIn(text, body)
        self.assertIn("Budget by level", body)
        self.assertIn("Techniques this vow rides", body)
        self.assertIn("held by 2", body)  # Kneel

    def test_payload_lines_and_prefilled_add_links(self) -> None:
        VowAddedEffectFactory(
            covenant_role=self.role, function=TechniqueFunction.BARRIER, focus_pick=self.kneel
        )
        self.client.force_login(self.author)
        body = self._get()
        self.assertIn("Added effect: On your own Barrier casts", body)
        add = reverse("admin:arxii_vowaddedeffect_add")
        self.assertIn(
            f"{add}?covenant_role={self.role.pk}&amp;focus_pick={self.kneel.pk}&amp;_popup=1", body
        )
        self.assertIn(f"{add}?covenant_role={self.role.pk}&amp;_popup=1", body)

    def test_the_stock_add_form_prefills_the_vow_and_the_pick(self) -> None:
        self.client.force_login(self.author)
        url = (
            f"{reverse('admin:arxii_vowaddedeffect_add')}"
            f"?covenant_role={self.role.pk}&focus_pick={self.kneel.pk}&_popup=1"
        )
        body = self.client.get(url).content.decode()
        self.assertRegex(body, rf'<option value="{self.role.pk}" selected>')
        self.assertRegex(body, rf'<option value="{self.kneel.pk}" selected>')

    def test_an_unlinked_operator_sees_setup_guidance(self) -> None:
        self.client.force_login(self.unlinked)
        body = self._get()
        self.assertIn('id="panel-builder-setup"', body)
        self.assertNotIn('id="vow-form"', body)

    def test_pick_route_redirects_and_refuses_an_unknown_pk(self) -> None:
        self.client.force_login(self.author)
        pick = reverse("admin_vow_builder_pick")
        self.assertRedirects(
            self.client.get(pick, {"pk": self.role.pk}), self.url, fetch_redirect_response=False
        )
        self.assertEqual(self.client.get(pick, {"pk": "999999"}).status_code, 400)
        self.assertEqual(self.client.get(pick).status_code, 400)

    def test_a_staff_member_who_is_not_superuser_is_refused(self) -> None:
        staff = AccountDB.objects.create_user("vbstaff", "s@example.com", "pw-123456")
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class VowPageWaysInTests(VowPageCase):
    def test_the_covenant_role_list_links_each_vow_page(self) -> None:
        self.client.force_login(self.author)
        body = self.client.get(reverse("admin:arxii_covenantrole_changelist")).content.decode()
        self.assertIn(f'<a href="{self.url}">Vow page</a>', body)

    def test_the_covenant_role_change_form_has_the_object_tool(self) -> None:
        self.client.force_login(self.author)
        change = reverse("admin:arxii_covenantrole_change", args=[self.role.pk])
        body = self.client.get(change).content.decode()
        self.assertIn(self.url, body)
        self.assertIn("Open the vow page", body)


class VowPageSaveTests(VowPageCase):
    def test_raising_an_unheld_pick_saves_and_credits(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(
            self.url, self._payload(**{self._pick_key(self.charge, "value"): "5"})
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(self._stored_value(self.charge), 5)
        charge = VowFocusPick.objects.get(pk=self.charge.pk)
        self.assertEqual(charge.written_by, self.writer)
        self.assertEqual(CovenantRole.objects.get(pk=self.role.pk).written_by, self.writer)
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.role.pk)).exists())
        self.assertIn("value 5", self._get())

    def test_raising_a_held_pick_warns_with_each_holder_and_saves_nothing(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(
            self.url, self._payload(**{self._pick_key(self.kneel, "value"): "6"})
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Before you save", body)
        self.assertRegex(body, r"Ysolde Marrow</a>, level 3:\s+2 to 3 of 4")
        self.assertRegex(
            body, r"Corvin Ashe</a>, level 3:\s+4 to 5 of 4\s+<span class=\"vb-over\">"
        )
        self.assertEqual(self._stored_value(self.kneel), 4)
        self.assertEqual(VowFocusPick.objects.get(pk=self.kneel.pk).value, 4)

    def test_confirming_saves_the_held_pick(self) -> None:
        self.client.force_login(self.author)
        payload = self._payload(
            **{self._pick_key(self.kneel, "value"): "6", "confirm_holders": "1"}
        )
        response = self.client.post(self.url, payload)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(self._stored_value(self.kneel), 6)

    def test_deleting_a_held_pick_warns_then_removes_its_holder_rows(self) -> None:
        self.client.force_login(self.author)
        key = self._pick_key(self.kneel, "DELETE")
        body = self.client.post(self.url, self._payload(**{key: "on"})).content.decode()
        self.assertRegex(body, r"Corvin Ashe</a>, level 3:\s+4 to 2 of 4")
        self.assertTrue(VowFocusPick.objects.filter(pk=self.kneel.pk).exists())
        response = self.client.post(self.url, self._payload(**{key: "on", "confirm_holders": "1"}))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertFalse(VowFocusPick.objects.filter(pk=self.kneel.pk).exists())
        self.assertFalse(CharacterVowFocusPick.objects.filter(pick_id=self.kneel.pk).exists())
        self.assertTrue(CharacterVowFocusPick.objects.filter(pick=self.halo).exists())

    def test_deleting_a_pick_with_payload_rows_is_refused(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, focus_pick=self.charge)
        self.client.force_login(self.author)
        key = self._pick_key(self.charge, "DELETE")
        body = self.client.post(self.url, self._payload(**{key: "on"})).content.decode()
        self.assertIn("still has payload rows", body)
        self.assertTrue(VowFocusPick.objects.filter(pk=self.charge.pk).exists())

    def test_a_limit_added_lowers_the_price_and_warns_nobody_for_an_unheld_pick(self) -> None:
        self.client.force_login(self.author)
        prefix = f"l{self.charge.pk}"
        payload = self._payload(
            **{
                f"{prefix}-TOTAL_FORMS": "1",
                f"{prefix}-0-pick": str(self.charge.pk),
                f"{prefix}-0-kind": FocusPickLimitKind.SETTING,
                f"{prefix}-0-frequency_tenths": "6",
                f"{prefix}-0-reduction": "0",
                f"{prefix}-0-description": "Under open sky",
            }
        )
        response = self.client.post(self.url, payload)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        charge = VowFocusPick.objects.get(pk=self.charge.pk)
        self.assertEqual([limit.kind for limit in charge.cached_limits], ["setting"])
        self.assertIn("Setting ×0.6", self._get())

    def test_a_limit_on_a_held_pick_warns_with_the_lower_total(self) -> None:
        self.client.force_login(self.author)
        key = f"l{self.kneel.pk}-0-frequency_tenths"
        body = self.client.post(self.url, self._payload(**{key: "3"})).content.decode()
        self.assertRegex(body, r"Ysolde Marrow</a>, level 3:\s+2 to 1 of 4")

    def test_a_refused_edit_leaves_the_cached_pick_as_stored(self) -> None:
        self.client.force_login(self.author)
        payload = self._payload(
            **{self._pick_key(self.charge, "value"): "9", self._pick_key(self.charge, "name"): ""}
        )
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("errorlist", response.content.decode())
        cached = VowFocusPick.objects.get(pk=self.charge.pk)
        self.assertEqual((cached.name, cached.value), ("Arcing Charge", 4))

    def test_a_warned_edit_leaves_the_cached_pick_as_stored(self) -> None:
        self.client.force_login(self.author)
        self.client.post(self.url, self._payload(**{self._pick_key(self.kneel, "value"): "6"}))
        self.assertEqual(VowFocusPick.objects.get(pk=self.kneel.pk).value, 4)

    def test_an_unlinked_operator_saves_nothing(self) -> None:
        self.client.force_login(self.unlinked)
        body = self.client.post(
            self.url, self._payload(**{self._pick_key(self.charge, "value"): "5"})
        ).content.decode()
        self.assertIn('id="panel-builder-setup"', body)
        self.assertEqual(self._stored_value(self.charge), 4)

    def test_mark_reviewed_stamps_the_vow_and_its_picks(self) -> None:
        self.client.force_login(self.author)
        self.client.post(reverse("admin_vow_builder_review", args=[self.role.pk]))
        self.assertEqual(CovenantRole.objects.get(pk=self.role.pk).reviewed_by, self.writer)
        self.assertEqual(VowFocusPick.objects.get(pk=self.kneel.pk).reviewed_by, self.writer)


class VowBuilderStylingTest(VowPageCase):
    """Every rule the page's layout needs reaches the page (#3667's rule, for #4880)."""

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")
    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "help",
            "errornote",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-table",
        }
    )

    def test_the_page_links_forms_css_and_widgets_css(self) -> None:
        self.client.force_login(self.author)
        linked = stylesheet_hrefs(self._get())
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"Linked: {linked}")

    def test_every_class_the_templates_emit_has_a_rule_reaching_the_page(self) -> None:
        self.client.force_login(self.author)
        css = reachable_css(self._get())
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/vow_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        undefined = sorted(
            token
            for token in emitted - self.ADMIN_PROVIDED_CLASSES
            if not re.search(rf"\.{re.escape(token)}\b", css)
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
