"""``GlimpseTag.offers`` - the handler owning a tag's distinction offers (#3675, ADR-0278).

Mirrors ``UpbringingQuestionsHandlerTest``
(``world.character_creation.tests.test_upbringing_models``), the worked example ADR-0278
names: a cache hung off an identity-mapped ``GlimpseTag`` outlives the request that filled
it, so a saved offer has to clear it (the writer side,
``DistinctionOffer.related_cache_fields``), and a delete that never calls ``Model.delete()``
never reaches that writer side at all, while ``Collector.delete()`` still nulls the pk on
the shared instance - so the handler drops pk-less rows itself before returning anything.
"""

from django.test import TestCase

from world.character_creation.constants import OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.models import DistinctionOffer
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import GlimpseTagFactory
from world.magic.models import GlimpseTag, GlimpseTagOffersHandler


class GlimpseTagOffersHandlerTest(TestCase):
    def setUp(self):
        self.tag = GlimpseTagFactory(name="Mark")
        self.first = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="First"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=self.tag,
            sort_order=0,
        )

    def test_rows_lists_active_offers_in_order(self):
        later = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Later"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=self.tag,
            sort_order=5,
        )
        middle = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Middle"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=self.tag,
            sort_order=2,
        )
        assert list(self.tag.offers.rows) == [self.first, middle, later]

    def test_an_inactive_offer_is_excluded(self):
        DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Retired"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=self.tag,
            is_active=False,
        )
        assert list(self.tag.offers.rows) == [self.first]

    def test_a_queryset_delete_is_caught_even_though_it_never_calls_delete(self):
        """The belt. ``queryset.delete()`` bypasses ``Model.delete()``, so no
        writer-side clearing happens - but the collector still nulls the pk on
        the shared instance, and the handler refuses to hand that back."""
        doomed = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Doomed"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=self.tag,
            sort_order=1,
        )
        warm = list(self.tag.offers.rows)
        assert doomed in warm

        DistinctionOffer.objects.filter(pk=doomed.pk).delete()

        assert doomed.pk is None, "the collector no longer nulls the pk; revisit the handler"
        served = list(self.tag.offers.rows)
        assert served == [self.first], (
            f"an offer deleted through a queryset is still being served: {served}"
        )

    def test_saving_a_new_offer_invalidates_the_tags_cache(self):
        assert list(self.tag.offers.rows) == [self.first]
        added = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Added"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=self.tag,
            sort_order=1,
        )
        assert list(self.tag.offers.rows) == [self.first, added], (
            "the handler served a stale list; saving an offer must clear its "
            "tag's cached properties via related_cache_fields"
        )

    def test_prime_fills_two_tags_from_one_query(self):
        other_tag = GlimpseTagFactory(name="Loss")
        DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Elsewhere"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=other_tag,
        )
        tags = list(GlimpseTag.objects.filter(pk__in=[self.tag.pk, other_tag.pk]))

        with self.assertNumQueries(1):
            GlimpseTagOffersHandler.prime(tags)

        with self.assertNumQueries(0):
            by_tag = {tag.pk: list(tag.offers.rows) for tag in tags}
        assert [o.distinction.name for o in by_tag[self.tag.pk]] == ["First"]
        assert [o.distinction.name for o in by_tag[other_tag.pk]] == ["Elsewhere"]
