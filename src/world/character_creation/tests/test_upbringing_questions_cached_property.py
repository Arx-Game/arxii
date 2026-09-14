"""``OriginTemplate.questions`` - a ``PrunedCachedProperty`` over a route's slots
(#3673, #3816, ADR-0296).

``related_cache_fields`` is the ONLY invalidation path here, by necessity, not by
choice: ``OriginTemplateSlot`` has no application-level write site at all - it is
purely admin-authored (Upbringing Builder tooling), so
``OriginTemplateSlot.related_cache_fields``/``RelatedCacheClearingMixin`` is the sole
writer side. Mirrors the worked example ADR-0278 names: a cache hung off an
identity-mapped ``OriginTemplate`` outlives the request that filled it, so a
saved/deleted slot has to clear it, and a delete that never calls ``Model.delete()``
never reaches that writer side at all, while ``Collector.delete()`` still nulls the
pk on the shared instance - so ``PrunedCachedProperty`` drops pk-less rows itself
before returning anything.
"""

from django.test import TestCase

from world.character_creation.factories import OriginTemplateFactory, OriginTemplateSlotFactory
from world.character_creation.models import OriginTemplateSlot


class UpbringingQuestionsCachedPropertyTests(TestCase):
    def test_new_slot_is_visible_on_next_read(self):
        template = OriginTemplateFactory()
        self.assertEqual(template.questions, [])
        OriginTemplateSlotFactory(template=template)
        self.assertEqual(len(template.questions), 1)

    def test_questions_come_back_in_the_order_a_player_answers_them(self):
        template = OriginTemplateFactory()
        first = OriginTemplateSlotFactory(template=template, name="First", sort_order=0)
        later = OriginTemplateSlotFactory(template=template, name="Later", sort_order=5)
        middle = OriginTemplateSlotFactory(template=template, name="Middle", sort_order=2)
        assert list(template.questions) == [first, middle, later]

    def test_a_deleted_slot_is_gone_from_a_warm_cache(self):
        template = OriginTemplateFactory()
        first = OriginTemplateSlotFactory(template=template, name="First", sort_order=0)
        doomed = OriginTemplateSlotFactory(template=template, name="Doomed", sort_order=1)
        assert doomed in list(template.questions)
        doomed.delete()
        assert list(template.questions) == [first], (
            "the cache served a stale list; deleting a slot must clear its "
            "Upbringing's cached properties via related_cache_fields"
        )

    def test_a_queryset_delete_is_caught_even_though_it_never_calls_delete(self):
        """The belt. ``queryset.delete()`` bypasses ``Model.delete()``, so no
        writer-side clearing happens - but the collector still nulls the pk on
        the shared instance, and ``PrunedCachedProperty`` refuses to hand that
        back on the next read."""
        template = OriginTemplateFactory()
        keeper = OriginTemplateSlotFactory(template=template, name="Keeper", sort_order=0)
        doomed = OriginTemplateSlotFactory(template=template, name="Doomed", sort_order=1)
        warm = list(template.questions)
        assert doomed in warm

        OriginTemplateSlot.objects.filter(pk=doomed.pk).delete()

        assert doomed.pk is None, "the collector no longer nulls the pk; revisit the property"
        served = list(template.questions)
        assert served == [keeper], (
            f"a question deleted through a queryset is still being served: {served}"
        )
