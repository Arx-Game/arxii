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


def _persist_all_standard_lines() -> tuple[list[TraditionStateLine], list[SchoolingLine]]:
    """All three state lines and all three schooling lines, already authored.

    Used by tests about *editing* a standard line - the page's own GET no
    longer writes these rows for a test to discover afterward (#3675
    demo-fidelity ruling), so a test that needs existing rows to edit creates
    them itself, the same way a real author's first save would have.
    """
    state_lines = [
        TraditionStateLineFactory(state=state, entry_line=f"{state} line")
        for state in TraditionState.values
    ]
    schooling_lines = [
        SchoolingLineFactory(rank=rank, name=f"Schooling {rank}", player_line="A line.")
        for rank in range(3)
    ]
    return state_lines, schooling_lines


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

    def test_shows_three_rows_of_each_standard_table_without_persisting_anything(self):
        """The demo-fidelity ruling (#3675): a GET must not write placeholder rows.

        A fresh database still renders three state-line rows and three
        schooling-line rows - their identity (state/rank) fixed by an unsaved
        formset row's own hidden field, not a real database row - and nothing
        is written until Save.
        """
        assert TraditionStateLine.objects.count() == 0
        assert SchoolingLine.objects.count() == 0
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_tradition_slate", args=[self.beginning.pk]))
        assert resp.status_code == 200

        # Still nothing in the database - the page rendered three rows of
        # each table without a single write.
        assert TraditionStateLine.objects.count() == 0
        assert SchoolingLine.objects.count() == 0

        body = resp.content.decode()
        assert 'name="state-TOTAL_FORMS" value="3"' in body
        assert 'name="state-INITIAL_FORMS" value="0"' in body
        assert 'name="schooling-TOTAL_FORMS" value="3"' in body
        assert 'name="schooling-INITIAL_FORMS" value="0"' in body
        for state in TraditionState.values:
            assert f'value="{state}"' in body
        for rank in range(3):
            assert f'value="{rank}"' in body
        for label in ("Self-taught", "Teachers gone", "Living masters"):
            assert label in body

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
    def _post_data(
        self,
        *,
        state_lines,
        schooling_lines,
        slate_rows,
        state_overrides=None,
        schooling_overrides=None,
    ):
        """Build the three formsets' POST body for editing already-persisted rows.

        ``state_overrides``/``schooling_overrides`` (keyed by state/rank) supply
        the fields a caller wants posted for one row, without mutating the
        ``TraditionStateLine``/``SchoolingLine`` instances themselves - they are
        ``SharedMemoryModel`` rows, so an attribute set directly on one of these
        objects is visible to every later query in the same test process
        (idmapper identity cache), which would make the view's own freshly-
        queried instance already carry the "changed" value and never register
        as changed at all.
        """
        state_overrides = state_overrides or {}
        schooling_overrides = schooling_overrides or {}
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
            carries = override.get("carries", "__unset__")
            if carries == "__unset__":
                carries_pk = line.carries_id
            else:
                carries_pk = carries.pk if carries else ""
            data[f"state-{i}-id"] = str(line.pk)
            data[f"state-{i}-state"] = line.state
            data[f"state-{i}-entry_line"] = entry_line
            data[f"state-{i}-carries"] = str(carries_pk or "")
        for i, line in enumerate(schooling_lines):
            override = schooling_overrides.get(line.rank, {})
            grants = override.get("grants", "__unset__")
            if grants == "__unset__":
                grants_pk = line.grants_id
            else:
                grants_pk = grants.pk if grants else ""
            default_name = line.name or f"Schooling {line.rank}"
            data[f"schooling-{i}-id"] = str(line.pk)
            data[f"schooling-{i}-rank"] = str(line.rank)
            data[f"schooling-{i}-name"] = override.get("name", default_name)
            data[f"schooling-{i}-player_line"] = override.get(
                "player_line", line.player_line or "A line."
            )
            data[f"schooling-{i}-grants"] = str(grants_pk or "")
        for i, row in enumerate(slate_rows):
            data[f"slate-{i}-tradition"] = str(row["tradition"].pk)
            data[f"slate-{i}-state"] = row["state"]
            data[f"slate-{i}-own_wording"] = row.get("own_wording", "")
            data[f"slate-{i}-sort_order"] = str(row.get("sort_order", 0))
        return data

    def test_post_saves_state_own_wording_and_standard_lines_and_credits_operator(self):
        self.client.force_login(self.author)
        state_lines, schooling_lines = _persist_all_standard_lines()
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
            # A schooling line is only credited when this save actually
            # changes it - editing rank 0's player_line here is what makes
            # the "every touched row is credited" assertion below meaningful,
            # rather than accidentally passing on unchanged rows.
            schooling_overrides={0: {"player_line": "Taken in after the Glimpse, changed."}},
        )
        resp = self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)
        assert resp.status_code == 302

        self_taught_line = TraditionStateLine.objects.get(state=TraditionState.SELF_TAUGHT)
        assert self_taught_line.carries_id == drawback.pk
        assert self_taught_line.entry_line == "Self-taught, alone"
        assert self_taught_line.written_by_id == self.writer.pk
        assert self_taught_line.written_on is not None

        rank_zero = SchoolingLine.objects.get(rank=0)
        assert rank_zero.player_line == "Taken in after the Glimpse, changed."
        assert rank_zero.written_by_id == self.writer.pk
        assert rank_zero.written_on is not None

        slate_row = BeginningTradition.objects.get(beginning=self.beginning, tradition=tradition)
        assert slate_row.state == TraditionState.TEACHERS_GONE
        assert slate_row.own_wording == "Its books outlived its people."

    def test_post_creates_missing_standard_lines_from_unsaved_extra_rows(self):
        """The demo-fidelity ruling's other half: Save is what writes a new row.

        Posts the exact shape a fresh GET renders - three unsaved state rows
        and three unsaved schooling rows, each row's identity fixed by its own
        hidden field - and checks all six land in the database, credited.
        """
        self.client.force_login(self.author)
        assert TraditionStateLine.objects.count() == 0
        assert SchoolingLine.objects.count() == 0

        data = {
            "state-TOTAL_FORMS": "3",
            "state-INITIAL_FORMS": "0",
            "state-MIN_NUM_FORMS": "0",
            "state-MAX_NUM_FORMS": "1000",
            "schooling-TOTAL_FORMS": "3",
            "schooling-INITIAL_FORMS": "0",
            "schooling-MIN_NUM_FORMS": "0",
            "schooling-MAX_NUM_FORMS": "1000",
            "slate-TOTAL_FORMS": "0",
            "slate-INITIAL_FORMS": "0",
            "slate-MIN_NUM_FORMS": "0",
            "slate-MAX_NUM_FORMS": "1000",
            "save": "Save",
        }
        for i, state in enumerate(TraditionState.values):
            data[f"state-{i}-id"] = ""
            data[f"state-{i}-state"] = state
            data[f"state-{i}-entry_line"] = f"{state} line"
            data[f"state-{i}-carries"] = ""
        for i in range(3):
            data[f"schooling-{i}-id"] = ""
            data[f"schooling-{i}-rank"] = str(i)
            data[f"schooling-{i}-name"] = f"Schooling {i}"
            data[f"schooling-{i}-player_line"] = "A line."
            data[f"schooling-{i}-grants"] = ""

        resp = self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)
        assert resp.status_code == 302

        assert TraditionStateLine.objects.count() == 3
        assert SchoolingLine.objects.count() == 3
        for state in TraditionState.values:
            line = TraditionStateLine.objects.get(state=state)
            assert line.entry_line == f"{state} line"
            assert line.written_by_id == self.writer.pk
        for rank in range(3):
            line = SchoolingLine.objects.get(rank=rank)
            assert line.name == f"Schooling {rank}"
            assert line.written_by_id == self.writer.pk

    def test_post_creates_missing_tradition_step_offer_for_a_granting_schooling_line(self):
        self.client.force_login(self.author)
        state_lines, schooling_lines = _persist_all_standard_lines()
        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1)
        rank_one = next(line for line in schooling_lines if line.rank == 1)

        assert not DistinctionOffer.objects.filter(schooling_line=rank_one).exists()

        data = self._post_data(
            state_lines=state_lines,
            schooling_lines=schooling_lines,
            slate_rows=[],
            schooling_overrides={1: {"grants": training}},
        )
        resp = self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)
        assert resp.status_code == 302

        offer = DistinctionOffer.objects.get(schooling_line_id=rank_one.pk)
        assert offer.chapter == OfferChapter.TRADITION_STEP
        assert offer.distinction_id == training.pk
        assert offer.is_active
        assert offer.written_by_id == self.writer.pk
        assert offer.written_on is not None

    def test_post_leaves_existing_offer_alone(self):
        self.client.force_login(self.author)
        state_lines, schooling_lines = _persist_all_standard_lines()
        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1)
        rank_one = next(line for line in schooling_lines if line.rank == 1)
        rank_one.grants = training
        rank_one.save()
        existing = DistinctionOfferFactory(
            chapter=OfferChapter.TRADITION_STEP, schooling_line=rank_one, distinction=training
        )

        data = self._post_data(
            state_lines=state_lines,
            schooling_lines=schooling_lines,
            slate_rows=[],
            schooling_overrides={1: {"grants": training}},
        )
        self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)

        assert DistinctionOffer.objects.filter(schooling_line=rank_one).count() == 1
        existing.refresh_from_db()
        assert existing.distinction_id == training.pk
        assert existing.is_active

    def test_post_deactivates_offer_when_grant_is_cleared(self):
        """Important 3 (#3675 review): clearing a grant must not leave its offer active forever."""
        self.client.force_login(self.author)
        state_lines, schooling_lines = _persist_all_standard_lines()
        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1)
        rank_one = next(line for line in schooling_lines if line.rank == 1)
        rank_one.grants = training
        rank_one.save()
        offer = DistinctionOfferFactory(
            chapter=OfferChapter.TRADITION_STEP, schooling_line=rank_one, distinction=training
        )
        assert offer.is_active

        data = self._post_data(
            state_lines=state_lines,
            schooling_lines=schooling_lines,
            slate_rows=[],
            schooling_overrides={1: {"grants": None}},
        )
        resp = self.client.post(reverse("admin_tradition_slate", args=[self.beginning.pk]), data)
        assert resp.status_code == 302

        offer.refresh_from_db()
        assert not offer.is_active
        assert offer.written_by_id == self.writer.pk

    def test_unlinked_superuser_post_saves_nothing(self):
        self.client.force_login(self.unlinked)
        state_lines, schooling_lines = _persist_all_standard_lines()
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
    REQUIRED_SCRIPTS = ("admin/js/builder_formsets.js",)

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

    def _script_srcs(self, body: str) -> list[str]:
        return re.findall(r'<script[^>]*\bsrc="([^"]+)"', body)

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

    def test_the_page_links_the_shared_builder_formsets_script(self):
        body = self._body()
        srcs = self._script_srcs(body)
        missing = [
            script
            for script in self.REQUIRED_SCRIPTS
            if not any(src.endswith(script) for src in srcs)
        ]
        assert not missing, f"the page does not link {missing}. Linked scripts: {srcs}"
        for script in self.REQUIRED_SCRIPTS:
            src = next(s for s in srcs if s.endswith(script))
            if src.startswith(settings.STATIC_URL):
                found = finders.find(src[len(settings.STATIC_URL) :])
                assert found is not None, f"the page links a script that does not resolve: {src}"

    def test_the_page_is_laid_out_two_column_with_the_rail_on_the_right(self):
        body = self._body()
        assert 'class="ts-columns"' in body
        assert 'class="ts-rail"' in body
        assert "grid-template-columns" in body, "the two-column shell has no rule"

    def test_check_kind_classes_both_have_rules_reaching_the_page(self):
        """The template-emitted-class scan below only proves the "tradition-check"
        prefix has a rule - ``class="tradition-check tradition-check--{{ kind }}"``
        is a template-variable token, not a literal class name the regex can see,
        so neither kind-suffixed class is provable that way (#3675 review)."""
        css = self._reachable_css(self._body())
        assert ".tradition-check--ok" in css
        assert ".tradition-check--warn" in css

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
