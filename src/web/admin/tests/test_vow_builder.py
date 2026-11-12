"""The vow page through the test client (#4880, slice 2 of #4843).

Staff open one vow, edit its fields, specialties, focus picks and limits, and save once.
A save that moves the price of a pick live characters hold stops first with each
holder's old and new total, and writes nothing until confirmed.

Built in ``setUp``: the holder memberships create Evennia objects, which
``setUpTestData`` cannot deepcopy. Holder rows come straight from factories, since
``CharacterVowFocusPick`` runs its rules in ``clean()`` only.
"""

from __future__ import annotations

from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import re
from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.db import DatabaseError, connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB

from actions.factories import ActionTemplateFactory
from evennia_extensions.models import PlayerData
from web.admin.authoring import power_preview
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.contributors.factories import ContentContributorFactory
from world.covenants.constants import FocusPickLimitKind
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CharacterVowFocusPickFactory,
    CombatStyleFactory,
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
    SubroleCovenantRoleFactory,
    VowAddedEffectDamageProfileFactory,
    VowAddedEffectFactory,
    VowFocusPickFactory,
    VowFocusPickLimitFactory,
)
from world.covenants.models import (
    CharacterVowFocusPick,
    CovenantRole,
    VowFocusPick,
    VowFocusPickLimit,
)
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    TechniqueDamageProfileFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.skills.factories import SkillFactory
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart


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
            covenant_role=self.role, pick_level=10, name="Arcing Charge", value=4
        )
        self.kneel = VowFocusPickFactory(
            covenant_role=self.role, pick_level=30, name="Kneel", value=4
        )
        self.kneel_limit = VowFocusPickLimitFactory(
            pick=self.kneel, kind=FocusPickLimitKind.TARGET, frequency_tenths=5
        )  # Kneel costs 2
        self.halo = VowFocusPickFactory(
            covenant_role=self.role, pick_level=30, name="Static Halo", value=2
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
        for header in ("Level", "Pick", "Value", "Limits", "Price", "Payload", "Held by"):
            self.assertIn(f"<span>{header}</span>", body)
        self.assertIn('data-stored-price="2"', body)  # Kneel, the price the script compares to
        self.assertIn('href="/admin/_vow_builder/', body)

    def test_header_chip_sub_roles_and_specialty_rides(self) -> None:
        self.role.description = "Ranged damage. Strikes from afar."
        self.role.save()
        sub = SubroleCovenantRoleFactory(parent_role=self.role, name="Thunderhead")
        bolt = TechniqueFactory(name="Bolt")
        TechniqueFunctionTagFactory(technique=bolt, function=TechniqueFunction.BARRIER)
        self.client.force_login(self.author)
        body = self._get()
        self.assertIn("Covenant of the Durance · ranged damage", body)
        self.assertRegex(
            body, r"1 sub-role:\s+<a href=\"" + reverse("admin_vow_builder", args=[sub.pk])
        )
        self.assertIn("1 technique</td>", body)
        self.assertIn("Barrier specialty", body)
        self.assertIn(reverse("admin:arxii_technique_change", args=[bolt.pk]), body)

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
        self.assertIn("<span data-pick-value>5</span>", self._get())

    def test_raising_a_held_pick_warns_with_each_holder_and_saves_nothing(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(
            self.url, self._payload(**{self._pick_key(self.kneel, "value"): "6"})
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Before you save", body)
        self.assertIn("unsaved changes: 1", body)
        self.assertIn("Kneel&#x27;s price goes from 2 to 3. Two characters hold it.", body)
        self.assertRegex(
            body, r"Ysolde Marrow</a>\s+stays within level 30&#x27;s budget \(3 of 4\)\."
        )
        self.assertRegex(
            body,
            r"Corvin Ashe</a>\s+<span class=\"vb-over\">also holds Static Halo and goes over "
            r"level 30&#x27;s budget \(5 of 4\)\.",
        )
        self.assertIn('name="confirm_holders" value="Save anyway"', body)
        self.assertNotIn('name="save" value="Save"', body)
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
        self.assertIn("Deleting Kneel returns its price to 2 holders.", body)
        self.assertRegex(
            body,
            r"Corvin Ashe</a>\s+also holds Static Halo and stays within level 30&#x27;s budget "
            r"\(2 of 4\)",
        )
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
        self.assertIn("Kneel&#x27;s price goes from 2 to 1.", body)
        self.assertRegex(
            body, r"Ysolde Marrow</a>\s+stays within level 30&#x27;s budget \(1 of 4\)"
        )

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


class VowPageRestoreTests(VowPageCase):
    """A POST that writes nothing puts the shared rows back in place (#4880 review).

    Validating ``VowForm`` copies the posted values onto the identity-mapped vow, which
    other cached objects hold too: a membership a character's covenant-role handler
    loaded with ``select_related("covenant_role")``, a sub-role's ``parent_role``. So
    each refusal shape is checked through those holders, loaded before the POST, as
    well as through a fresh read.
    """

    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.author)
        character = self.ysolde.character_sheet.character
        self.held_role = character.covenant_roles.currently_held_role_in(self.ysolde.covenant)
        self.assertIs(self.held_role, CovenantRole.objects.get(pk=self.role.pk))
        self.sub = SubroleCovenantRoleFactory(parent_role=self.role, name="Thunderhead")
        self.sub_cached = CovenantRole.objects.get(pk=self.sub.pk)
        self.assertEqual(self.sub_cached.parent_role.sword_weight, 0)

    def _assert_stored_everywhere(self, sword: str = "0") -> None:
        expected = Decimal(sword)
        stored = CovenantRole.objects.filter(pk=self.role.pk).values_list("sword_weight", flat=True)
        self.assertEqual(stored.get(), expected)
        self.assertEqual(CovenantRole.objects.get(pk=self.role.pk).sword_weight, expected)
        self.assertEqual(self.held_role.sword_weight, expected)
        self.assertEqual(self.sub_cached.parent_role.sword_weight, expected)

    def test_a_role_field_error_then_the_corrected_post(self) -> None:
        refused = self.client.post(
            self.url, self._payload(name="", sword_weight="0.5", crown_weight="0.5")
        )
        self.assertEqual(refused.status_code, 200)
        self._assert_stored_everywhere()
        saved = self.client.post(self.url, self._payload(sword_weight="0.5", crown_weight="0.5"))
        self.assertRedirects(saved, self.url, fetch_redirect_response=False)
        self._assert_stored_everywhere("0.5")

    def test_a_limit_field_error_restores_the_role_and_the_limit(self) -> None:
        key = f"l{self.kneel.pk}-0-frequency_tenths"
        response = self.client.post(
            self.url, self._payload(sword_weight="0.5", crown_weight="0.5", **{key: "99"})
        )
        self.assertEqual(response.status_code, 200)
        self._assert_stored_everywhere()
        limit = VowFocusPickLimit.objects.get(pk=self.kneel_limit.pk)
        self.assertEqual(limit.frequency_tenths, 5)
        self.assertEqual(self.kneel_limit.frequency_tenths, 5)

    def test_the_held_pick_warning_restores_the_role_and_the_pick(self) -> None:
        response = self.client.post(
            self.url,
            self._payload(
                sword_weight="0.5", crown_weight="0.5", **{self._pick_key(self.kneel, "value"): "6"}
            ),
        )
        self.assertContains(response, "Before you save")
        self._assert_stored_everywhere()
        self.assertEqual(self.kneel.value, 4)

    def test_a_save_that_raises_restores_and_evicts_what_it_created(self) -> None:
        payload = self._payload(
            sword_weight="0.5",
            crown_weight="0.5",
            **{
                "picks-TOTAL_FORMS": "4",
                "picks-3-covenant_role": str(self.role.pk),
                "picks-3-pick_level": "20",
                "picks-3-name": "Under Open Sky",
                "picks-3-value": "4",
                "picks-3-description": "",
            },
        )
        with (
            patch("web.admin.vow_builder.views.stamp_written", side_effect=DatabaseError("boom")),
            self.assertRaises(DatabaseError),
        ):
            self.client.post(self.url, payload)
        self._assert_stored_everywhere()
        self.assertFalse(VowFocusPick.objects.filter(name="Under Open Sky").exists())
        self.assertFalse(
            any(pick.name == "Under Open Sky" for pick in VowFocusPick.get_all_cached_instances())
        )


def even_chart() -> None:
    """A two-band chart (SL 1 and SL 3, half each) and a x1 multiplier, so DE is not zero."""
    CheckRankFactory(rank=0, min_points=0)
    chart = ResultChartFactory(rank_difference=0, name="Preview even")
    for success_level, low, high in ((1, 1, 50), (3, 51, 100)):
        outcome = CheckOutcomeFactory(
            name=f"Preview SL {success_level}", success_level=success_level
        )
        ResultChartOutcomeFactory(chart=chart, outcome=outcome, min_roll=low, max_roll=high)
    DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("1.00"))
    ResultChart.clear_cache()


def _de_lines(body: str, technique: str) -> dict[str, int]:
    """The preview module's lines for one technique, label to DE."""
    module = body.split('id="power-preview-module"', 1)[1].split('id="credit-module"', 1)[0]
    block = module.split(f">{technique}</a>", 1)[1].split("Run the fight simulator", 1)[0]
    return {
        label: int(de) for label, de in re.findall(r"<span>([^<]+)</span><b>(\d+) DE</b>", block)
    }


class VowPowerPreviewTests(VowPageCase):
    """The rail's Power preview (#4930): each ridden technique with no vow, the base vow
    and each pick, then the fight simulator link."""

    def setUp(self) -> None:
        super().setUp()
        even_chart()
        # The catalog evaluation and reference are cached by catalog revision, which a
        # factory write does not bump: start every test from an empty cache.
        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_login(self.author)

    def _ridden(self, name: str, *, castable: bool = True, level: int = 3) -> object:
        template = ActionTemplateFactory() if castable else None
        technique = TechniqueFactory(name=name, intensity=4, action_template=template, level=level)
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.STRIKE)
        return technique

    def _peer(self, name: str, de: int, *, level: int = 3, function: str = "") -> None:
        """A catalog technique whose baseline DE is ``de``: one flat damage row."""
        technique = TechniqueFactory(name=name, level=level, damage_profile=False)
        TechniqueDamageProfileFactory(
            technique=technique,
            base_damage=de,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=0,
            minimum_success_level=1,
        )
        TechniqueFunctionTagFactory(
            technique=technique, function=function or TechniqueFunction.STRIKE
        )

    def _rank(self, body: str, technique: str) -> str:
        module = body.split('id="power-preview-module"', 1)[1]
        block = module.split(f">{technique}</a>", 1)[1]
        found = re.search(
            r'<div class="vb-stat vb-rank"><span>(Catalog rank[^<]*)</span><b>([^<]*)</b>', block
        )
        return f"{found.group(1)}: {found.group(2)}"

    def _base_damage(self) -> None:
        effect = VowAddedEffectFactory(
            covenant_role=self.role, function=TechniqueFunction.STRIKE, unlock_thread_level=100
        )
        VowAddedEffectDamageProfileFactory(effect=effect, base_damage=6)

    def test_each_technique_is_priced_with_no_vow_the_base_and_each_pick(self) -> None:
        technique = self._ridden("Arc Lash")
        self._base_damage()
        on_pick = VowAddedEffectFactory(
            covenant_role=self.role,
            function=TechniqueFunction.STRIKE,
            focus_pick=self.halo,
            unlock_thread_level=110,
        )
        VowAddedEffectDamageProfileFactory(effect=on_pick, base_damage=4)
        body = self._get()
        self.assertIn("Power preview &middot; Fulmination</h2>", body)
        lines = _de_lines(body, "Arc Lash")
        self.assertEqual(
            list(lines), ["No vow", "With base vow, level 30", f"With {self.halo.name}"]
        )
        self.assertGreater(lines["With base vow, level 30"], lines["No vow"])
        self.assertGreater(lines[f"With {self.halo.name}"], lines["With base vow, level 30"])
        self.assertIn("Level 30: the vow&#x27;s highest pick level.", body)
        self.assertIn("DE is damage equivalent per cast, from the technique power evaluator.", body)
        self.assertIn("Situational perks and stat scaling are not priced.", body)
        simulator = reverse("admin_tuning") + (
            f"?technique={technique.pk}&amp;covenant_role={self.role.pk}#panel-simulation"
        )
        self.assertIn(f'href="{simulator}">Run the fight simulator', body)

    def test_a_technique_with_no_action_template_gets_no_simulator_link(self) -> None:
        quiet = self._ridden("Quiet Lash", castable=False)
        self._base_damage()
        body = self._get()
        self.assertIn("Quiet Lash", body)
        self.assertNotIn(f"?technique={quiet.pk}&amp;", body)
        self.assertIn("No action template, so the fight simulator cannot cast it.", body)

    def test_a_vow_with_no_added_effect_says_so(self) -> None:
        self.assertIn("No added effect rides a technique yet.", self._get())

    def test_the_catalog_rank_counts_same_level_same_function_peers(self) -> None:
        self._ridden("Arc Lash")
        self._base_damage()
        best = max(_de_lines(self._get(), "Arc Lash").values())
        self._peer("Rank above", best + 50)
        self._peer("Rank below", 1)
        self._peer("Rank other level", best + 60, level=4)
        self._peer("Rank other job", best + 70, function=TechniqueFunction.BARRIER)
        cache.clear()  # the catalog changed after the first evaluation was cached
        self.assertEqual(
            self._rank(self._get(), "Arc Lash"), "Catalog rank, level 3 strike techniques: 2nd of 3"
        )

    def test_a_tie_shares_the_better_rank(self) -> None:
        self._ridden("Arc Lash")
        self._base_damage()
        best = max(_de_lines(self._get(), "Arc Lash").values())
        self._peer("Rank above", best + 50)
        self._peer("Rank tied", best)
        cache.clear()
        self.assertEqual(
            self._rank(self._get(), "Arc Lash"), "Catalog rank, level 3 strike techniques: 2nd of 3"
        )

    def test_with_nothing_to_compare_it_is_the_only_one(self) -> None:
        self._ridden("Arc Lash")
        self._base_damage()
        self.assertEqual(
            self._rank(self._get(), "Arc Lash"), "Catalog rank: the only level 3 strike technique"
        )

    def test_one_shown_or_three_costs_the_same_queries(self) -> None:
        self._base_damage()
        self._ridden("Preview A")
        self._get()  # warm the catalog evaluation, the reference and the site caches
        with CaptureQueriesContext(connection) as one:
            self._get()
        self._ridden("Preview B")
        self._ridden("Preview C")
        # Warm again: a technique already in the identity map skips its payload
        # prefetches, so both counts are taken with every shown technique cached.
        self._get()
        with CaptureQueriesContext(connection) as three:
            body = self._get()
        self.assertEqual(body.count("Catalog rank"), 3)
        self.assertEqual(len(three), len(one))

    def test_the_first_three_by_name_then_a_count_with_flat_queries(self) -> None:
        self._base_damage()
        for name in ("Preview A", "Preview B", "Preview C"):
            self._ridden(name)
        self._get()  # warm the reference frame and the site caches
        with CaptureQueriesContext(connection) as three:
            body = self._get()
        self.assertNotIn("more</p>", body)
        self._ridden("Preview D")
        with CaptureQueriesContext(connection) as four:
            body = self._get()
        self.assertIn("+1 more", body)
        self.assertNotIn(">Preview D</a>", body)
        self.assertEqual(len(four), len(three))


class VowStylesModuleTests(VowPageCase):
    """The "Combat styles that work with this vow" module (#4932, slice 7 of #4843)."""

    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.author)

    def _module(self, url: str | None = None) -> str:
        response = self.client.get(url or self.url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        return body.split('id="styles-module"', 1)[1].split('id="holders-module"', 1)[0]

    def _row(self, module: str, name: str) -> str:
        return module.split(f">{name}</a>", 1)[1].split("</tr>", 1)[0]

    def test_with_no_styles_it_says_so(self) -> None:
        module = self._module()
        self.assertIn("Combat styles that work with this vow</h2>", module)
        self.assertIn("No combat styles are authored yet.", module)

    def test_a_listed_style_works_and_an_unlisted_one_shows_its_cost(self) -> None:
        listed = CombatStyleFactory(name="Storm Footwork", skill=SkillFactory(name="Squall"))
        listed.compatible_roles.add(self.role)
        unlisted = CombatStyleFactory(name="Iron Guard", skill=SkillFactory(name="Bulwark"))
        module = self._module()
        url = reverse("admin:arxii_combatstyle_change", args=[listed.pk])
        self.assertIn(f'<a href="{url}">Storm Footwork</a>', module)
        works = self._row(module, "Storm Footwork")
        self.assertIn('<span class="vb-fit vb-fit-works">works</span>', works)
        self.assertIn("<td>Squall</td>", works)
        self.assertNotIn("loses", works)
        not_works = self._row(module, unlisted.name)
        self.assertIn('<span class="vb-fit vb-fit-not">does not work</span>', not_works)
        self.assertIn(
            "A holder fighting this style loses Bulwark on attack and defense rolls; "
            "its hit stat and defense type still apply.",
            not_works,
        )

    def test_a_style_with_no_skill_has_nothing_to_lose(self) -> None:
        CombatStyleFactory(name="Bare Stance")
        row = self._row(self._module(), "Bare Stance")
        self.assertIn("<td>none</td>", row)
        self.assertIn("No style skill to lose; its hit stat and defense type apply as usual.", row)

    def test_a_sub_role_page_counts_a_style_listing_its_anchor(self) -> None:
        sub = SubroleCovenantRoleFactory(
            name="Fulmination Choir", slug="fulmination-choir", parent_role=self.role
        )
        listed = CombatStyleFactory(name="Storm Footwork")
        listed.compatible_roles.add(self.role)
        row = self._row(self._module(reverse("admin_vow_builder", args=[sub.pk])), listed.name)
        self.assertIn("vb-fit-works", row)

    def test_holders_are_this_vows_live_primary_holders_of_that_style(self) -> None:
        style = CombatStyleFactory(name="Storm Footwork")
        style.compatible_roles.add(self.role)
        for membership in (self.ysolde, self.corvin):
            membership.character_sheet.combat_style = style
            membership.character_sheet.save()
        self.corvin.left_at = timezone.now()
        self.corvin.save()
        secondary = CharacterCovenantRoleFactory(covenant_role=self.role, is_secondary=True)
        secondary.character_sheet.combat_style = style
        secondary.character_sheet.save()
        other = CharacterCovenantRoleFactory(
            covenant_role=CovenantRoleFactory(name="Elsewhere", slug="elsewhere-vow")
        )
        other.character_sheet.combat_style = style
        other.character_sheet.save()
        self.assertIn("<td>1</td>", self._row(self._module(), "Storm Footwork"))

    def test_the_module_costs_the_same_queries_with_one_style_or_four(self) -> None:
        CombatStyleFactory(name="Count Style 0", skill=SkillFactory(name="Count 0"))
        self._module()  # warm the site caches
        with CaptureQueriesContext(connection) as one:
            self._module()
        for index in range(1, 4):
            style = CombatStyleFactory(
                name=f"Count Style {index}", skill=SkillFactory(name=f"Count {index}")
            )
            style.compatible_roles.add(self.role)
        self._module()  # warm the new styles' skills into the identity map
        with CaptureQueriesContext(connection) as four:
            module = self._module()
        self.assertEqual(module.count("Count Style"), 4)
        self.assertEqual(len(four), len(one))


class RankWordingTests(SimpleTestCase):
    """The rank row's arithmetic and wording (#4930), apart from any page."""

    def test_ordinals(self) -> None:
        cases = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 11: "11th", 12: "12th", 13: "13th"}
        cases |= {21: "21st", 22: "22nd", 23: "23rd", 101: "101st", 111: "111th"}
        for number, text in cases.items():
            with self.subTest(number=number):
                self.assertEqual(power_preview.ordinal(number), text)

    def test_rank_counts_the_technique_once_and_ties_share_the_better_rank(self) -> None:
        peers = {1: 40.0, 2: 30.4, 3: 29.6, 4: 10.0, 9: 12.0}
        # Technique 9 is itself (its catalog figure is replaced by its with-vow 30);
        # 30.4 and 29.6 round to 30 and tie it, so only 40 is above.
        self.assertEqual(power_preview.catalog_rank(9, 30, peers), (2, 5))
        self.assertEqual(power_preview.catalog_rank(7, 30, peers), (2, 6))

    def test_the_rank_line_and_the_single_technique_line(self) -> None:
        self.assertEqual(
            power_preview.rank_line(7, 41, level=3, function=TechniqueFunction.STRIKE),
            "Catalog rank, level 3 strike techniques: 7th of 41",
        )
        self.assertEqual(
            power_preview.rank_line(1, 1, level=3, function=TechniqueFunction.STRIKE),
            "Catalog rank: the only level 3 strike technique",
        )


class _ClassCollector(HTMLParser):
    """Collects what the styling test reads off a rendered page.

    Every class token inside ``#vow-builder-root`` (``<template>`` contents included: the
    parser reads them as ordinary tags), every ``<button>`` inside a ``.submit-row`` and
    whether it carries ``.button``, and how many ``<h1>`` sit inside ``#content``.
    """

    VOID = frozenset({"input", "br", "hr", "img", "link", "meta", "col", "source", "wbr"})

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, str, set[str]]] = []
        self.classes: set[str] = set()
        self.bare_submit_buttons = 0
        self.content_h1 = 0

    def _inside(self, *, element_id: str = "", css_class: str = "") -> bool:
        return any(
            (element_id and tag_id == element_id) or (css_class and css_class in tokens)
            for _, tag_id, tokens in self.stack
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        tokens = set((attributes.get("class") or "").split())
        element_id = attributes.get("id") or ""
        if element_id == "vow-builder-root" or self._inside(element_id="vow-builder-root"):
            self.classes |= tokens
        if tag == "button" and self._inside(css_class="submit-row") and "button" not in tokens:
            self.bare_submit_buttons += 1
        if tag == "h1" and self._inside(element_id="content"):
            self.content_h1 += 1
        if tag not in self.VOID:
            self.stack.append((tag, element_id, tokens))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return


class VowBuilderStylingTest(VowPageCase):
    """Every rule the page's layout needs reaches the page (#3667's rule, for #4880).

    Read off the rendered page in both its states, at rest and showing the held-pick
    warning, so a class only the warning emits is checked too.
    """

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")

    def _states(self) -> dict[str, str]:
        self.client.force_login(self.author)
        # A style that works and one that does not, so both chips are read (#4932).
        CombatStyleFactory(name="Styling Works").compatible_roles.add(self.role)
        CombatStyleFactory(name="Styling Not")
        warned = self.client.post(
            self.url, self._payload(**{self._pick_key(self.kneel, "value"): "6"})
        ).content.decode()
        self.assertIn("Before you save", warned)
        return {"at rest": self._get(), "warning": warned}

    def test_the_page_links_forms_css_and_widgets_css(self) -> None:
        self.client.force_login(self.author)
        linked = stylesheet_hrefs(self._get())
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"Linked: {linked}")

    def test_every_class_under_the_root_has_a_rule_reaching_the_page(self) -> None:
        for state, body in self._states().items():
            with self.subTest(state=state):
                collector = _ClassCollector()
                collector.feed(body)
                css = reachable_css(body)
                undefined = sorted(
                    token
                    for token in collector.classes
                    if not re.search(rf"\.{re.escape(token)}\b", css)
                )
                self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")

    def test_every_class_the_templates_emit_has_a_rule_reaching_the_page(self) -> None:
        css = reachable_css(self._get_logged_in())
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/vow_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        undefined = sorted(
            token for token in emitted if not re.search(rf"\.{re.escape(token)}\b", css)
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")

    def test_submit_controls_are_admin_styled_and_there_is_one_heading(self) -> None:
        for state, body in self._states().items():
            with self.subTest(state=state):
                collector = _ClassCollector()
                collector.feed(body)
                self.assertEqual(collector.bare_submit_buttons, 0)
                self.assertEqual(collector.content_h1, 1)
                self.assertEqual(body.count('class="submit-row"'), 2)  # the form's and the rail's

    def _get_logged_in(self) -> str:
        self.client.force_login(self.author)
        return self._get()
