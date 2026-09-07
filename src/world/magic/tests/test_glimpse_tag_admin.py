"""GlimpseTag's stock change form gains a "What it offers" inline (#3675, Task 9).

A stock admin change form, extended - not a new builder page. Mirrors the
Distinction Builder's own offer save/credit test shape
(`web.admin.tests.test_distinction_builder`), scoped to this page's own
inline + preview.
"""

from pathlib import Path
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.character_creation.constants import OfferArrival
from world.character_creation.models import DistinctionOffer
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import GlimpseTagFactory


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class GlimpseTagOfferTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("glimpseadmin")
        cls.writer = ContentContributorFactory(name="Glimpse Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("glimpseunlinked")
        cls.tag = GlimpseTagFactory(name="Mark")
        cls.distinction = DistinctionFactory(name="Magical Scar", cost_per_rank=5, max_rank=3)

    def _change_url(self) -> str:
        return reverse("admin:arxii_glimpsetag_change", args=[self.tag.pk])


class GlimpseTagOfferGetTest(GlimpseTagOfferTestCase):
    def test_change_form_renders_the_offers_inline(self):
        self.client.force_login(self.author)
        resp = self.client.get(self._change_url())
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "What it offers" in body
        assert 'name="distinction_offers-TOTAL_FORMS"' in body

    def test_change_form_renders_the_preview_line_once_offered(self):
        DistinctionOffer.objects.create(
            distinction=self.distinction,
            glimpse_tag=self.tag,
            chapter="glimpse",
            arrives_as=OfferArrival.CHOICE,
            player_line="A scar that answers magic.",
        )
        self.client.force_login(self.author)
        resp = self.client.get(self._change_url())
        body = resp.content.decode()
        assert "A scar that answers magic." in body
        assert "arx-offer-preview" in body

    def test_change_form_shows_the_empty_preview_line_with_no_offer(self):
        self.client.force_login(self.author)
        resp = self.client.get(self._change_url())
        body = resp.content.decode()
        assert "Add an active offer to preview the CG line." in body


class GlimpseTagOfferSaveTest(GlimpseTagOfferTestCase):
    def _post_data(self, **overrides) -> dict:
        data = {
            "axis": self.tag.axis,
            "name": self.tag.name,
            "slug": self.tag.slug,
            "description": self.tag.description,
            "example": self.tag.example,
            "sort_order": "0",
            "is_active": "on",
            "paths": [],
            "distinction_offers-TOTAL_FORMS": "1",
            "distinction_offers-INITIAL_FORMS": "0",
            "distinction_offers-MIN_NUM_FORMS": "0",
            "distinction_offers-MAX_NUM_FORMS": "1000",
            "distinction_offers-0-distinction": str(self.distinction.pk),
            "distinction_offers-0-arrives_as": OfferArrival.CHOICE,
            "distinction_offers-0-name": "",
            "distinction_offers-0-player_line": "A scar that answers magic.",
            "distinction_offers-0-sort_order": "0",
            "distinction_offers-0-is_active": "on",
            "_save": "Save",
        }
        data.update(overrides)
        return data

    def test_posting_the_inline_saves_a_glimpse_offer_credited(self):
        self.client.force_login(self.author)
        resp = self.client.post(self._change_url(), self._post_data())
        assert resp.status_code == 302
        offer = DistinctionOffer.objects.get(distinction=self.distinction, glimpse_tag=self.tag)
        assert offer.chapter == "glimpse"
        assert offer.origin_choice_id is None
        assert offer.schooling_line_id is None
        assert offer.written_by == self.writer

    def test_posting_without_a_linked_contributor_still_saves_uncredited(self):
        """No setup-guidance gate exists on a stock change form (unlike the Builder pages)."""
        self.client.force_login(self.unlinked)
        resp = self.client.post(self._change_url(), self._post_data())
        assert resp.status_code == 302
        offer = DistinctionOffer.objects.get(distinction=self.distinction, glimpse_tag=self.tag)
        assert offer.written_by is None


class GlimpseTagOfferStylingTest(GlimpseTagOfferTestCase):
    """The shared preview fragment's own classes must have a rule reaching the page.

    Mirrors `DistinctionBuilderStylingTest`'s shape: asserting a class name
    appears in the body proves nothing on its own - the fragment carries its
    own self-contained ``<style>``, so this checks that style block is
    actually present in the rendered response, not merely that the class
    name is echoed somewhere in the markup.
    """

    def _body(self) -> str:
        self.client.force_login(self.author)
        resp = self.client.get(self._change_url())
        assert resp.status_code == 200
        return resp.content.decode()

    def _reachable_css(self, body: str) -> str:
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.DOTALL))
        hrefs = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', body)
        for href in hrefs:
            if not href.startswith(settings.STATIC_URL):
                continue
            found = finders.find(href[len(settings.STATIC_URL) :])
            if found is not None:
                css += "\n" + Path(found).read_text()
        return css

    def test_the_offer_preview_fragments_own_classes_reach_the_page(self):
        css = self._reachable_css(self._body())
        assert ".arx-offer-preview" in css
        assert ".arx-offer-preview-price" in css
