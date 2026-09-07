"""The tradition slate page: standard lines and one Beginning's slate (#3675)."""

from pathlib import Path
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.character_creation.constants import OfferChapter, TraditionState
from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    DistinctionOfferFactory,
    SchoolingLineFactory,
    TraditionStateLineFactory,
)
from world.character_creation.models import (
    BeginningTradition,
    DistinctionOffer,
    SchoolingLine,
    TraditionStateLine,
)
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import TraditionFactory


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class SlateTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("slateauthor")
        cls.writer = ContentContributorFactory(name="Slate Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("slateunlinked")
        cls.beginning = BeginningsFactory(name="A Test Beginning")


class SlateGetTest(SlateTestCase):
    def test_renders_standard_lines_and_slate_with_derived_prices(self):
        drawback = DistinctionFactory(name="Unbound Drawback", cost_per_rank=-75)
        TraditionStateLineFactory(
            state=TraditionState.SELF_TAUGHT, entry_line="Self-taught", carries=drawback
        )
        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1)
        SchoolingLineFactory(
            rank=1, name="Apprentice", player_line="Some training.", grants=training
        )
        tradition = TraditionFactory(name="The Vigil")
        BeginningTraditionFactory(
            beginning=self.beginning, tradition=tradition, state=TraditionState.LIVING_MASTERS
        )

        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Traditions offered to A Test Beginning" in body
        assert "Standard lines" in body
        assert "Self-taught" in body
        assert "Refunds 75" in body
        assert "read from Unbound Drawback&#x27;s price" in body or "Unbound Drawback" in body
        assert "Apprentice" in body
        assert "Tradition Training" in body
        assert "per-rank price" in body  # the schooling line's derived-price help text
        assert "The Vigil" in body
        assert "The slate" in body

    def test_ensures_three_state_lines_and_three_schooling_lines_exist(self):
        assert TraditionStateLine.objects.count() == 0
        assert SchoolingLine.objects.count() == 0
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        assert resp.status_code == 200
        assert TraditionStateLine.objects.count() == 3
        assert SchoolingLine.objects.count() == 3
        assert set(TraditionStateLine.objects.values_list("state", flat=True)) == {
            TraditionState.SELF_TAUGHT,
            TraditionState.TEACHERS_GONE,
            TraditionState.LIVING_MASTERS,
        }
        assert set(SchoolingLine.objects.values_list("rank", flat=True)) == {0, 1, 2}

    def test_unlinked_superuser_sees_setup_panel(self):
        self.client.force_login(self.unlinked)
        resp = self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Link a contributor first" in body
        assert "Standard lines" not in body

    def test_preview_prefers_teachers_gone_over_self_taught_regardless_of_sort_order(self):
        """The demo's own worked example (#3675 review): state priority beats slate order.

        Self-taught sits at sort_order 0 and teachers-gone at sort_order 2 on the
        same slate - a plain "first by sort_order" preview would show the
        self-taught line, but teachers-gone must win: it is a state the player
        never chooses or fills in themselves, so it is the more informative
        preview.
        """
        TraditionStateLineFactory(state=TraditionState.SELF_TAUGHT, entry_line="Self-taught line")
        TraditionStateLineFactory(
            state=TraditionState.TEACHERS_GONE, entry_line="Teachers gone line"
        )
        self_taught_tradition = TraditionFactory(name="Unbound")
        teachers_gone_tradition = TraditionFactory(name="Metallic Order")
        BeginningTraditionFactory(
            beginning=self.beginning,
            tradition=self_taught_tradition,
            state=TraditionState.SELF_TAUGHT,
            sort_order=0,
        )
        BeginningTraditionFactory(
            beginning=self.beginning,
            tradition=teachers_gone_tradition,
            state=TraditionState.TEACHERS_GONE,
            sort_order=2,
        )

        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        preview = body[body.index('class="preview"') :]
        assert "Metallic Order" in preview
        assert "Unbound" not in preview


class SlatePostTest(SlateTestCase):
    def _post_data(self, *, state_lines, schooling_lines, slate_rows, state_overrides=None):
        """Build the three formsets' POST body.

        ``state_overrides`` (keyed by ``TraditionState``) supplies the entry_line/
        carries a caller wants posted for one row, without mutating the
        ``TraditionStateLine`` instances themselves - they are ``SharedMemoryModel``
        rows, so an attribute set directly on one of these objects is visible to
        every later query in the same test process (idmapper identity cache), which
        would make the view's own freshly-queried instance already carry the
        "changed" value and never register as changed at all.
        """
        state_overrides = state_overrides or {}
        data = {
            "state-TOTAL_FORMS": str(len(state_lines)),
            "state-INITIAL_FORMS": str(len(state_lines)),
            "state-MIN_NUM_FORMS": "0",
            "state-MAX_NUM_FORMS": "1000",
            "schooling-TOTAL_FORMS": str(len(schooling_lines)),
            "schooling-INITIAL_FORMS": str(len(schooling_lines)),
            "schooling-MIN_NUM_FORMS": "0",
            "schooling-MAX_NUM_FORMS": "1000",
            "slate-TOTAL_FORMS": str(len(slate_rows)),
            "slate-INITIAL_FORMS": "0",
            "slate-MIN_NUM_FORMS": "0",
            "slate-MAX_NUM_FORMS": "1000",
            "save": "Save",
        }
        for i, line in enumerate(state_lines):
            override = state_overrides.get(line.state, {})
            entry_line = override.get("entry_line", line.entry_line or f"{line.state} line")
            carries = override.get("carries")
            data[f"state-{i}-id"] = str(line.pk)
            data[f"state-{i}-entry_line"] = entry_line
            data[f"state-{i}-carries"] = str(carries.pk if carries else line.carries_id or "")
        for i, line in enumerate(schooling_lines):
            data[f"schooling-{i}-id"] = str(line.pk)
            data[f"schooling-{i}-name"] = line.name or f"Schooling {line.rank}"
            data[f"schooling-{i}-player_line"] = line.player_line or "A line."
            data[f"schooling-{i}-grants"] = str(line.grants_id or "")
        for i, row in enumerate(slate_rows):
            data[f"slate-{i}-tradition"] = str(row["tradition"].pk)
            data[f"slate-{i}-state"] = row["state"]
            data[f"slate-{i}-own_wording"] = row.get("own_wording", "")
            data[f"slate-{i}-sort_order"] = str(row.get("sort_order", 0))
        return data

    def test_post_saves_state_own_wording_and_standard_lines_and_credits_operator(self):
        self.client.force_login(self.author)
        # GET first, to ensure the three-plus-three standard lines exist.
        self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        state_lines = list(TraditionStateLine.objects.order_by("state"))
        schooling_lines = list(SchoolingLine.objects.order_by("rank"))
        drawback = DistinctionFactory(name="A Drawback", cost_per_rank=-10)

        tradition = TraditionFactory(name="An Order")
        data = self._post_data(
            state_lines=state_lines,
            schooling_lines=schooling_lines,
            slate_rows=[
                {
                    "tradition": tradition,
                    "state": TraditionState.TEACHERS_GONE,
                    "own_wording": "Its books outlived its people.",
                    "sort_order": 0,
                }
            ],
            state_overrides={
                TraditionState.SELF_TAUGHT: {
                    "entry_line": "Self-taught, alone",
                    "carries": drawback,
                }
            },
        )
        resp = self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)
        assert resp.status_code == 302

        self_taught_line = TraditionStateLine.objects.get(state=TraditionState.SELF_TAUGHT)
        assert self_taught_line.carries_id == drawback.pk
        assert self_taught_line.entry_line == "Self-taught, alone"
        assert self_taught_line.written_by_id == self.writer.pk
        assert self_taught_line.written_on is not None

        for line in schooling_lines:
            line.refresh_from_db()
            assert line.written_by_id == self.writer.pk

        slate_row = BeginningTradition.objects.get(beginning=self.beginning, tradition=tradition)
        assert slate_row.state == TraditionState.TEACHERS_GONE
        assert slate_row.own_wording == "Its books outlived its people."

    def test_post_creates_missing_tradition_step_offer_for_a_granting_schooling_line(self):
        self.client.force_login(self.author)
        self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        state_lines = list(TraditionStateLine.objects.order_by("state"))
        schooling_lines = list(SchoolingLine.objects.order_by("rank"))
        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1)
        rank_one = next(line for line in schooling_lines if line.rank == 1)
        rank_one.grants = training

        assert not DistinctionOffer.objects.filter(schooling_line=rank_one).exists()

        data = self._post_data(
            state_lines=state_lines, schooling_lines=schooling_lines, slate_rows=[]
        )
        resp = self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)
        assert resp.status_code == 302

        offer = DistinctionOffer.objects.get(schooling_line_id=rank_one.pk)
        assert offer.chapter == OfferChapter.TRADITION_STEP
        assert offer.distinction_id == training.pk

    def test_post_leaves_existing_offer_alone(self):
        self.client.force_login(self.author)
        self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        state_lines = list(TraditionStateLine.objects.order_by("state"))
        schooling_lines = list(SchoolingLine.objects.order_by("rank"))
        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1)
        rank_one = next(line for line in schooling_lines if line.rank == 1)
        rank_one.grants = training
        rank_one.save()
        existing = DistinctionOfferFactory(
            chapter=OfferChapter.TRADITION_STEP, schooling_line=rank_one, distinction=training
        )

        data = self._post_data(
            state_lines=state_lines, schooling_lines=schooling_lines, slate_rows=[]
        )
        self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)

        assert DistinctionOffer.objects.filter(schooling_line=rank_one).count() == 1
        existing.refresh_from_db()
        assert existing.distinction_id == training.pk

    def test_unlinked_superuser_post_saves_nothing(self):
        self.client.force_login(self.unlinked)
        self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        state_lines = list(TraditionStateLine.objects.order_by("state"))
        schooling_lines = list(SchoolingLine.objects.order_by("rank"))
        data = self._post_data(
            state_lines=state_lines, schooling_lines=schooling_lines, slate_rows=[]
        )
        resp = self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)
        assert resp.status_code == 200
        assert "Link a contributor first" in resp.content.decode()
        for line in state_lines:
            line.refresh_from_db()
            assert line.written_by_id is None


class ChangeFormObjectToolTest(SlateTestCase):
    def test_beginnings_change_form_shows_open_the_tradition_slate(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin:arxii_beginnings_change", args=[self.beginning.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Open the tradition slate" in body
        assert reverse("admin_tradition_slate", args=[self.beginning.pk]) in body


class SlateStylingTest(SlateTestCase):
    """Every rule the page's layout needs must REACH the page (#3667, mirrored for #3675).

    Copied from ``BuilderStylingTest``: asserting a class NAME appears in the HTML
    proves nothing, and neither does asserting the name appears anywhere in the
    page's reachable CSS - ``responsive.css`` (linked by ``base.html``) mentions
    admin's own class names inside media queries. The stylesheet has to be named.
    """

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css")

    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "aligned",
            "description",
            "help",
            "errornote",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-panel",
            "tuning-table",
            "stat-tiles",
            "stat-tile",
            "stat-value",
            "stat-label",
        }
    )

    def _body(self) -> str:
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
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

    def test_the_page_links_the_stylesheets_its_layout_needs(self):
        linked = self._stylesheet_hrefs(self._body())
        missing = [
            sheet
            for sheet in self.REQUIRED_STYLESHEETS
            if not any(href.endswith(sheet) for href in linked)
        ]
        assert not missing, (
            f"the page does not link {missing}; its admin markup has no rules behind it. "
            f"Linked: {linked}"
        )

    def test_the_page_is_laid_out_two_column_with_the_rail_on_the_right(self):
        body = self._body()
        assert 'class="ts-columns"' in body
        assert 'class="ts-rail"' in body
        assert "grid-template-columns" in body, "the two-column shell has no rule"

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self):
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/tradition_slate"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            markup = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", path.read_text(), flags=re.DOTALL)
            for attr in re.findall(r'class="([^"]*)"', markup):
                emitted.update(token for token in attr.split() if token)

        css = self._reachable_css(self._body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        assert not undefined, f"class hooks with no CSS rule reaching the page: {undefined}"
