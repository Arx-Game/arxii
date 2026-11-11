"""Journeys for the Power Builder, the staff page for "I want people to be able to do X"
(item 8 of #5066).

A staff member signed in to the admin opens one Application, Evade (dodges, landing by
blinking, needs ``teleport``), from the Authoring Workbench's Builders panel. Staff have
authored, around the capability ``traversal``:

- Shadow Step (Shadow, listed in the Skirmisher path's Shadow techniques): teleport and
  shadow, grants traversal base 3 + 1 per power, 4 anima.
- Storm Jump (Storm, a minor gift, on no path): teleport, grants base 5 + 0 per power.
- Shadow Walk (Shadow): shadow only, grants base 2 + 1 per power. One property away.
- Radiant Mark (Storm): carries teleport, grants nothing. One grant away.
- Agility -> traversal, base 0 + 1.00 per point (trained ability).
- Smoke Form, a condition carrying teleport, traversal +4, scaling with severity.
- Fleet of Foot, a distinction, traversal 2 per rank.
- Climb, a second application of traversal needing no property.

The page is read and saved as a browser does: every field inside the page's form is
collected from the rendered HTML and posted back, with the staff member's own changes on
top.

Expected numbers are worked by hand from those rows and the field defaults (no
CapabilityPowerConfig row, so a grant is base + per power x power; MovementConfig's
strength_per_success_level_percent 50, so one level better is 150 percent, rounded down):
at the default reference (power 6, trait 3, rank 2, severity 1) Shadow Step gives 3 + 6 = 9
and 13 one level better, Storm Jump 5 and 7, Agility 3, Smoke Form 4, Fleet of Foot 4. At
power 10 Shadow Step gives 13 and 19.
"""

from __future__ import annotations

from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse

from evennia_extensions.models import PlayerData
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal
from world.classes.factories import PathFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
)
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.locations.constants import StatKey
from world.magic.constants import GiftKind, SubstanceDirection
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.magic.models import GiftSubstance, Technique, TechniqueCapabilityGrant
from world.mechanics.factories import (
    ModifierTargetFactory,
    MovementApplicationFactory,
    PropertyFactory,
    TraitCapabilityDerivationFactory,
)
from world.mechanics.models import Application
from world.traits.factories import TraitFactory

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "web" / "templates" / "admin" / "power_builder"


class _FormFields(HTMLParser):
    """What a browser would post from one form: every named field inside ``form_id``.

    A field that belongs to another form (``form="..."``) is left out, as a browser does.
    """

    def __init__(self, form_id: str) -> None:
        super().__init__()
        self.form_id = form_id
        self.inside = False
        self.fields: dict[str, list[str]] = {}
        self._select: str | None = None
        self._select_value: str | None = None
        self._select_first: str | None = None
        self._textarea: str | None = None

    def _add(self, name: str, value: str) -> None:
        self.fields.setdefault(name, []).append(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "form":
            self.inside = attr.get("id") == self.form_id
        elif not self.inside or "form" in attr:
            return
        elif tag == "input" and attr.get("name"):
            self._input(attr)
        elif tag == "select":
            self._select, self._select_value, self._select_first = attr["name"], None, None
        elif tag == "option" and self._select is not None:
            self._option(attr)
        elif tag == "textarea":
            self._textarea = attr["name"]
            self._add(attr["name"], "")

    def _input(self, attr: dict[str, str]) -> None:
        kind = attr.get("type", "text")
        if kind in ("checkbox", "radio"):
            if "checked" in attr:
                self._add(attr["name"], attr.get("value", "on"))
        elif kind != "submit":
            self._add(attr["name"], attr.get("value", ""))

    def _option(self, attr: dict[str, str]) -> None:
        value = attr.get("value", "")
        if self._select_first is None:
            self._select_first = value
        if "selected" in attr:
            self._select_value = value

    def handle_data(self, data: str) -> None:
        if self._textarea is not None:
            self.fields[self._textarea][-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.inside = False
        elif tag == "select" and self._select is not None:
            chosen = self._select_value if self._select_value is not None else self._select_first
            self._add(self._select, chosen or "")
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def _form_data(body: str) -> dict[str, list[str]]:
    parser = _FormFields("pb-form")
    parser.feed(body)
    data = parser.fields
    for name, values in data.items():
        if name.endswith("description") or name == "description":
            data[name] = [value.lstrip("\n") for value in values]
    return data


def _module(body: str, module_id: str) -> str:
    """One module of the page: from its id to the next module's."""
    start = body.index(f'id="{module_id}"')
    end = body.find('class="module"', start + 1)
    return body[start : end if end != -1 else len(body)]


def _row(section: str, name: str) -> str:
    """The table row in ``section`` naming ``name``."""
    for row in section.split("<tr>"):
        if f"<td>{name}</td>" in row:
            return row
    msg = f"no row for {name}"
    raise AssertionError(msg)


class PowerBuilder(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.staff = get_user_model().objects.create_superuser(
            "staff5066", "s5066@example.com", "pw-5066"
        )
        self.writer = ContentContributorFactory(name="Power Writer")
        PlayerData.objects.create(account=self.staff, contributor=self.writer)
        self.client = Client()
        self.client.force_login(self.staff)

        self.traversal = CapabilityTypeFactory(name="traversal", innate_baseline=0)
        self.teleport = PropertyFactory(name="teleport")
        self.shadow = PropertyFactory(name="shadow")
        self.flame = PropertyFactory(name="flame")
        self.evade = MovementApplicationFactory(
            name="Evade",
            capability=self.traversal,
            required_effect_property=self.teleport,
            dodges=True,
            way_of_moving=CreatureTraversal.BLINKS,
            description="She vanishes and reappears out of reach.",
        )
        MovementApplicationFactory(
            name="Climb", capability=self.traversal, way_of_moving=CreatureTraversal.CLIMBS
        )

        self.shadow_gift = GiftFactory(name="Shadow")
        self.storm_gift = GiftFactory(name="Storm", kind=GiftKind.MINOR)
        self.flame_gift = GiftFactory(name="Flame")
        GiftSubstance.objects.create(
            gift=self.flame_gift,
            label="flame",
            stat_key=StatKey.LIGHTING,
            direction=SubstanceDirection.FALLING,
            property=self.flame,
        )
        skirmisher = PathFactory(name="Skirmisher")
        self.shadow_path = PathGiftGrantFactory(path=skirmisher, gift=self.shadow_gift)
        self.flame_path = PathGiftGrantFactory(path=skirmisher, gift=self.flame_gift)

        self.step = self._technique("Shadow Step", self.shadow_gift, [self.teleport, self.shadow])
        self.step_grant = TechniqueCapabilityGrantFactory(
            technique=self.step, capability=self.traversal, base_value=3, intensity_multiplier=1
        )
        self.shadow_path.starter_techniques.add(self.step)
        self.jump = self._technique("Storm Jump", self.storm_gift, [self.teleport], anima=6)
        TechniqueCapabilityGrantFactory(
            technique=self.jump, capability=self.traversal, base_value=5, intensity_multiplier=0
        )
        self.walk = self._technique("Shadow Walk", self.shadow_gift, [self.shadow])
        TechniqueCapabilityGrantFactory(
            technique=self.walk, capability=self.traversal, base_value=2, intensity_multiplier=1
        )
        self.mark = self._technique("Radiant Mark", self.storm_gift, [self.teleport])

        self.agility = TraitCapabilityDerivationFactory(
            trait=TraitFactory(name="Agility"),
            capability=self.traversal,
            base_value=0,
            trait_multiplier=Decimal("1.00"),
        )
        smoke = ConditionTemplateFactory(name="Smoke Form")
        smoke.properties.add(self.teleport)
        self.smoke = ConditionCapabilityEffectFactory(
            condition=smoke, capability=self.traversal, value=4, scales_with_severity=True
        )
        self.fleet = DistinctionEffectFactory(
            distinction=DistinctionFactory(name="Fleet of Foot"),
            target=ModifierTargetFactory(name="traversal bonus", target_capability=self.traversal),
            value_per_rank=2,
        )
        self.url = reverse("admin_power_builder", args=[self.evade.pk])

    def _technique(self, name: str, gift, properties, anima: int = 4) -> Technique:
        technique = TechniqueFactory(name=name, gift=gift, anima_cost=anima)
        technique.properties.set(properties)
        return technique

    def _page(self, query: str = "") -> str:
        response = self.client.get(f"{self.url}{query}")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _post(self, edits: dict[str, list[str]]) -> object:
        data = _form_data(self._page())
        data.update(edits)
        return self.client.post(self.url, data)

    def test_the_workbench_offers_the_power_builder(self) -> None:
        body = self.client.get(reverse("admin_authoring")).content.decode()
        change_form = self.client.get(
            reverse("admin:arxii_application_change", args=[self.evade.pk])
        ).content.decode()

        self.assertIn("Power Builder", body)
        self.assertIn("Let people", body)
        self.assertIn(f'<option value="{self.evade.pk}">Evade</option>', body)
        self.assertIn(reverse("admin_power_builder_new"), body)
        self.assertIn("Open in the Power Builder", change_form)
        self.assertIn(self.url, change_form)
        picked = self.client.get(reverse("admin_power_builder_pick"), {"pk": self.evade.pk})
        self.assertRedirects(picked, self.url)

    def test_the_page_compares_every_way_to_evade(self) -> None:
        body = self._page()

        self.assertIn("Evade · Power Builder", body)
        doing = _module(body, "techniques-module")
        step = _row(doing, "Shadow Step")
        self.assertIn("Shadow &middot; Skirmisher", step)
        self.assertIn("9; 13 one level better", step)
        self.assertIn("a cast: 4 anima, its own roll", step)
        jump = _row(doing, "Storm Jump")
        self.assertIn("Storm (minor gift) &middot; no path", jump)
        self.assertIn("5; 7 one level better", jump)
        self.assertNotIn("Shadow Walk", doing)

        others = _module(body, "others-module")
        agility = _row(others, "Agility")
        self.assertIn("<td>3</td>", agility)
        self.assertIn('<span class="pb-no">no</span>: no property', agility)
        self.assertIn("1 physical fatigue", agility)
        smoke = _row(others, "Smoke Form")
        self.assertIn("<td>4</td>", smoke)
        self.assertIn('<span class="pb-yes">yes</span>', smoke)
        fleet = _row(others, "Fleet of Foot")
        self.assertIn("<td>4</td>", fleet)
        self.assertIn("no property", fleet)

        near = _module(body, "near-module")
        self.assertIn("Shadow Walk", near)
        self.assertIn("Radiant Mark", near)
        self.assertIn("In words: a source of traversal carrying teleport dodges", body)
        rail = _module(body, "other-applications-module")
        self.assertIn("Climb</a> (climbs on her turn, no property)", rail)

    def test_a_higher_reference_power_raises_a_technique_strength(self) -> None:
        body = self._page("?power=10")

        self.assertIn(
            "13; 19 one level better", _row(_module(body, "techniques-module"), "Shadow Step")
        )

    def test_ticking_teleport_on_a_near_miss_makes_it_do_evade(self) -> None:
        response = self._post(
            {f"t{self.walk.pk}-properties": [str(self.shadow.pk), str(self.teleport.pk)]}
        )

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        doing = _module(self._page(), "techniques-module")
        # Shadow Walk: base 2 + 1 x 6 = 8; one level better 12.
        self.assertIn("8; 12 one level better", _row(doing, "Shadow Walk"))
        evade = Application.objects.get(pk=self.evade.pk)
        self.assertEqual(evade.written_by, self.writer)
        self.assertEqual(Technique.objects.get(pk=self.walk.pk).written_by, self.writer)

    def test_adding_a_technique_on_a_gift_and_path(self) -> None:
        response = self._post(
            {
                "new-gift": [str(self.flame_gift.pk)],
                "new-path_grant": [str(self.flame_path.pk)],
                "new-name": ["Flame Step"],
                "new-grant_base": ["3"],
                "new-grant_per_power": ["1"],
            }
        )

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        added = Technique.objects.get(gift=self.flame_gift, name="Flame Step")
        self.assertEqual(
            set(added.properties.values_list("name", flat=True)), {"teleport", "flame"}
        )
        grant = TechniqueCapabilityGrant.objects.get(technique=added)
        self.assertEqual((grant.capability_id, grant.base_value), (self.traversal.pk, 3))
        self.assertEqual(grant.intensity_multiplier, Decimal(1))
        self.assertIn(added, self.flame_path.starter_techniques.all())
        self.assertEqual(added.written_by, self.writer)
        step = _row(_module(self._page(), "techniques-module"), "Flame Step")
        self.assertIn("Flame &middot; Skirmisher", step)

    def test_a_refused_save_writes_nothing_and_leaves_the_rows_as_stored(self) -> None:
        response = self._post(
            {
                "name": ["Evade Changed"],
                f"t{self.step.pk}-grant_base": ["abc"],
                f"t{self.walk.pk}-properties": [str(self.shadow.pk), str(self.teleport.pk)],
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Enter a whole number.", response.content.decode())
        self.assertEqual(Application.objects.get(pk=self.evade.pk).name, "Evade")
        self.assertEqual(
            Application.objects.filter(pk=self.evade.pk).values_list("name", flat=True)[0],
            "Evade",
        )
        self.assertIsNone(Application.objects.get(pk=self.evade.pk).written_by)
        self.assertEqual(TechniqueCapabilityGrant.objects.get(pk=self.step_grant.pk).base_value, 3)
        self.assertNotIn(self.teleport, self.walk.properties.all())
        self.assertIn("Evade · Power Builder", self._page())

    def test_a_new_application_starts_from_its_capability(self) -> None:
        new_url = f"{reverse('admin_power_builder_new')}?capability={self.traversal.pk}"
        body = self.client.get(new_url).content.decode()
        data = _form_data(body)
        data.update({"name": ["Leap"], "way_of_moving": [CreatureTraversal.LEAPS]})

        response = self.client.post(new_url, data)

        self.assertEqual(data["capability"], [str(self.traversal.pk)])
        leap = Application.objects.get(name="Leap")
        self.assertRedirects(response, reverse("admin_power_builder", args=[leap.pk]))
        self.assertEqual(leap.capability, self.traversal)
        self.assertEqual(leap.written_by, self.writer)

    def test_mark_reviewed_stamps_the_application(self) -> None:
        response = self.client.post(reverse("admin_power_builder_review", args=[self.evade.pk]))

        self.assertRedirects(response, self.url)
        self.assertEqual(Application.objects.get(pk=self.evade.pk).reviewed_by, self.writer)

    def test_every_class_the_page_emits_has_a_rule_that_reaches_it(self) -> None:
        body = self._page()
        emitted: set[str] = set()
        for path in sorted(TEMPLATE_DIR.glob("*.html")):
            markup = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", path.read_text(), flags=re.DOTALL)
            for attr in re.findall(r'class="([^"]*)"', markup):
                emitted.update(token for token in attr.split() if token)
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.DOTALL))
        for href in re.findall(r'<link rel="stylesheet"[^>]*href="([^"]+)"', body):
            if href.startswith(settings.STATIC_URL):
                found = finders.find(href[len(settings.STATIC_URL) :])
                self.assertIsNotNone(found, f"the page links a missing stylesheet: {href}")
                css += "\n" + Path(found).read_text()
        self.assertIn("admin/css/forms.css", body)

        undefined = sorted(token for token in emitted if f".{token}" not in css)

        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
