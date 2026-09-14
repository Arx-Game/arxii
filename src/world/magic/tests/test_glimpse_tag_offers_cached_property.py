"""``GlimpseTag.offers`` - a ``PrunedCachedProperty`` over a tag's distinction offers
(#3675, #3816, ADR-0298).

``related_cache_fields`` is PRIMARY here: ``DistinctionOffer`` writes are
staff-authored/admin-tooling shaped (``web/admin/distinction_builder/paste.py``,
``tradition_slate/views.py``, seed data), not concentrated sole mutators, so this
relation relies solely on ``DistinctionOffer.related_cache_fields`` +
``RelatedCacheClearingMixin`` for invalidation - no direct write-site mutation.
Mirrors the worked example ADR-0278 names: a cache hung off an identity-mapped
``GlimpseTag`` outlives the request that filled it, so a saved/deleted offer has to
clear it, and a delete that never calls ``Model.delete()`` never reaches that writer
side at all, while ``Collector.delete()`` still nulls the pk on the shared instance -
so ``PrunedCachedProperty`` drops pk-less rows itself before returning anything.
"""

from django.test import TestCase

from world.character_creation.constants import OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.models import DistinctionOffer
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import GlimpseTagFactory


class GlimpseTagOffersCachedPropertyTests(TestCase):
    def test_new_offer_is_visible_on_next_read(self):
        tag = GlimpseTagFactory()
        self.assertEqual(tag.offers, [])  # warm, empty
        DistinctionOfferFactory(glimpse_tag=tag, chapter=OfferChapter.GLIMPSE, is_active=True)
        self.assertEqual(len(tag.offers), 1)

    def test_deactivated_offer_drops_out_on_next_read(self):
        tag = GlimpseTagFactory()
        offer = DistinctionOfferFactory(
            glimpse_tag=tag, chapter=OfferChapter.GLIMPSE, is_active=True
        )
        self.assertEqual(len(tag.offers), 1)
        offer.is_active = False
        offer.save(update_fields=["is_active"])
        self.assertEqual(tag.offers, [])

    def test_offers_list_in_sort_order(self):
        tag = GlimpseTagFactory(name="Mark")
        first = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="First"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=tag,
            sort_order=0,
        )
        later = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Later"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=tag,
            sort_order=5,
        )
        middle = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Middle"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=tag,
            sort_order=2,
        )
        assert list(tag.offers) == [first, middle, later]

    def test_an_inactive_offer_is_excluded_at_creation(self):
        tag = GlimpseTagFactory()
        active = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Active"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=tag,
        )
        DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Retired"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=tag,
            is_active=False,
        )
        assert list(tag.offers) == [active]

    def test_a_queryset_delete_is_caught_even_though_it_never_calls_delete(self):
        """The belt. ``queryset.delete()`` bypasses ``Model.delete()``, so no
        writer-side clearing happens - but the collector still nulls the pk on
        the shared instance, and ``PrunedCachedProperty`` refuses to hand that
        back on the next read."""
        tag = GlimpseTagFactory()
        keeper = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Keeper"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=tag,
            sort_order=0,
        )
        doomed = DistinctionOfferFactory(
            distinction=DistinctionFactory(name="Doomed"),
            chapter=OfferChapter.GLIMPSE,
            glimpse_tag=tag,
            sort_order=1,
        )
        warm = list(tag.offers)
        assert doomed in warm

        DistinctionOffer.objects.filter(pk=doomed.pk).delete()

        assert doomed.pk is None, "the collector no longer nulls the pk; revisit the property"
        served = list(tag.offers)
        assert served == [keeper], (
            f"an offer deleted through a queryset is still being served: {served}"
        )
