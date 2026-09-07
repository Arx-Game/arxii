"""The Builders panel on the Authoring Workbench dashboard (#3675 Task 10).

Every builder (Distinction Builder, tradition slate, Upbringing Builder,
Glimpse tags) is one click from the workbench (Decision 11 of the #3675
spec): a small picker row per builder, each backed by a plain GET redirect
view (`*_pick`), plus the Glimpse tag changelist link. The cross-links each
builder page draws to the others are tested alongside that builder's own
suite (`test_distinction_builder.py`, `test_tradition_slate.py`,
`test_upbringing_builder.py`), not here.
"""

from pathlib import Path
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.character_creation.factories import BeginningsFactory, OriginTemplateFactory
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import GlimpseTagFactory


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class BuildersPanelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("panelauthor")
        cls.writer = ContentContributorFactory(name="Panel Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("panelunlinked")
        cls.distinction = DistinctionFactory(name="Iron Nerve")
        cls.beginning = BeginningsFactory(name="Panel Beginning")
        cls.upbringing = OriginTemplateFactory(beginning=cls.beginning, name="Panel Upbringing")
        cls.tag = GlimpseTagFactory(name="Panel Tag")


class BuildersPanelRenderTest(BuildersPanelTestCase):
    def test_panel_lists_the_four_builders_and_their_options(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_authoring"))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert 'id="panel-authoring-builders"' in body
        assert "Builders" in body
        assert f'value="{self.distinction.pk}"' in body
        assert self.distinction.name in body
        assert f'value="{self.beginning.pk}"' in body
        assert self.beginning.name in body
        assert f"{self.beginning.name} › {self.upbringing.name}" in body
        assert reverse("admin:arxii_glimpsetag_changelist") in body
        assert "1 active tag" in body
        assert reverse("admin_distinction_builder_new") in body
        assert reverse("admin_distinction_builder_pick") in body
        assert reverse("admin_tradition_slate_pick") in body
        assert reverse("admin_upbringing_builder_pick") in body
        assert reverse("admin_upbringing_builder_new") in body

    def test_panel_absent_when_setup_required(self):
        self.client.force_login(self.unlinked)
        resp = self.client.get(reverse("admin_authoring"))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert 'id="panel-authoring-builders"' not in body
        assert "Builders" not in body

    def test_inactive_rows_are_excluded_from_every_picker(self):
        DistinctionFactory(name="Retired Distinction", is_active=False)
        BeginningsFactory(name="Retired Beginning", is_active=False)
        OriginTemplateFactory(beginning=self.beginning, name="Retired Upbringing", is_active=False)
        GlimpseTagFactory(name="Retired Tag", is_active=False)
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_authoring"))
        body = resp.content.decode()
        assert "Retired Distinction" not in body
        assert "Retired Beginning" not in body
        assert "Retired Upbringing" not in body
        assert "1 active tag" in body  # the inactive tag never bumps the count


class DistinctionBuilderPickTest(BuildersPanelTestCase):
    def test_redirects_to_the_builder(self):
        self.client.force_login(self.author)
        resp = self.client.get(
            reverse("admin_distinction_builder_pick"), {"pk": self.distinction.pk}
        )
        assert resp.status_code == 302
        assert resp["Location"] == reverse("admin_distinction_builder", args=[self.distinction.pk])

    def test_400_on_missing_pk(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder_pick"))
        assert resp.status_code == 400

    def test_400_on_unknown_pk(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder_pick"), {"pk": "999999"})
        assert resp.status_code == 400

    def test_400_on_non_numeric_pk(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder_pick"), {"pk": "not-a-number"})
        assert resp.status_code == 400


class TraditionSlatePickTest(BuildersPanelTestCase):
    def test_redirects_to_the_slate(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate_pick"), {"pk": self.beginning.pk})
        assert resp.status_code == 302
        assert resp["Location"] == reverse("admin_tradition_slate", args=[self.beginning.pk])

    def test_400_on_missing_pk(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate_pick"))
        assert resp.status_code == 400

    def test_400_on_unknown_pk(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate_pick"), {"pk": "999999"})
        assert resp.status_code == 400


class UpbringingBuilderPickTest(BuildersPanelTestCase):
    def test_redirects_to_the_builder(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder_pick"), {"pk": self.upbringing.pk})
        assert resp.status_code == 302
        assert resp["Location"] == reverse("admin_upbringing_builder", args=[self.upbringing.pk])

    def test_400_on_missing_pk(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder_pick"))
        assert resp.status_code == 400

    def test_400_on_unknown_pk(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder_pick"), {"pk": "999999"})
        assert resp.status_code == 400


class BuildersPanelStylingTest(BuildersPanelTestCase):
    """Every class the panel emits must have a rule reaching the dashboard page.

    Mirrors `BuilderStylingTest`'s shape (`test_upbringing_builder.py`):
    asserting a class name appears in the body proves nothing on its own -
    the dashboard has to actually carry a rule for it, not just admin's
    unrelated `responsive.css` mentioning the same name in a media query.
    """

    #: Classes the panel relies on that admin/the dashboard's own
    #: `_panel_css.html` already style - not this template's own to define.
    ADMIN_PROVIDED_CLASSES = frozenset({"tuning-panel", "tuning-table", "help"})

    def _body(self) -> str:
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_authoring"))
        assert resp.status_code == 200
        return resp.content.decode()

    def _stylesheet_hrefs(self, body: str) -> list[str]:
        hrefs = []
        for tag in re.findall(r"<link[^>]*>", body):
            if 'rel="stylesheet"' not in tag:
                continue
            match = re.search(r'href="([^"]+)"', tag)
            if match is not None:
                hrefs.append(match.group(1))
        return hrefs

    def _reachable_css(self, body: str) -> str:
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.DOTALL))
        missing: list[str] = []
        for href in self._stylesheet_hrefs(body):
            if not href.startswith(settings.STATIC_URL):
                continue
            found = finders.find(href[len(settings.STATIC_URL) :])
            if found is None:
                missing.append(href)
                continue
            css += "\n" + Path(found).read_text()
        assert not missing, f"the page links stylesheets that do not resolve: {missing}"
        return css

    def test_every_class_the_panel_emits_has_a_rule_that_reaches_the_page(self):
        template_path = (
            Path(__file__).resolve().parents[2] / "templates/admin/authoring/_builders_panel.html"
        )
        markup = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", template_path.read_text(), flags=re.DOTALL)
        emitted: set[str] = set()
        for attr in re.findall(r'class="([^"]*)"', markup):
            emitted.update(token for token in attr.split() if token)

        css = self._reachable_css(self._body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        assert not undefined, f"class hooks with no CSS rule reaching the page: {undefined}"
