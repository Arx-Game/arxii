"""``OriginTemplate.questions`` - a ``PrunedCachedProperty`` over a route's slots
(#3673, #3816, ADR-0298).

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

Every self-heal case below also proves the CACHING itself, with
``assertNumQueries`` - not just the eventual answer. A plain uncached ``@property``
would return the right value in every assertion here too, since it always
requeries fresh; the whole point of #3816 is that repeated reads cost zero queries
once warm, and that only a genuine invalidation (not a lucky pk-pruning coincidence)
triggers the next one.
"""

from django.test import TestCase

from world.character_creation.factories import OriginTemplateFactory, OriginTemplateSlotFactory
from world.character_creation.models import OriginTemplateSlot


class UpbringingQuestionsCachedPropertyTests(TestCase):
    def test_new_slot_is_visible_on_next_read(self):
        template = OriginTemplateFactory()
        self.assertEqual(template.questions, [])  # warm, empty

        with self.assertNumQueries(0):
            # Genuinely cached: a second read of the same, unchanged state costs
            # nothing. A plain @property would issue a query here too.
            self.assertEqual(template.questions, [])

        OriginTemplateSlotFactory(template=template)

        with self.assertNumQueries(1):
            # related_cache_fields invalidated the stale empty cache - this is a
            # real requery, not a Python-level filter reusing the old list.
            self.assertEqual(len(template.questions), 1)

        with self.assertNumQueries(0):
            # And the fresh answer is itself cached again.
            self.assertEqual(len(template.questions), 1)

    def test_questions_come_back_in_the_order_a_player_answers_them(self):
        template = OriginTemplateFactory()
        first = OriginTemplateSlotFactory(template=template, name="First", sort_order=0)
        later = OriginTemplateSlotFactory(template=template, name="Later", sort_order=5)
        middle = OriginTemplateSlotFactory(template=template, name="Middle", sort_order=2)
        assert list(template.questions) == [first, middle, later]

    def test_reassigning_a_slot_clears_both_templates(self):
        old_template = OriginTemplateFactory()
        new_template = OriginTemplateFactory()
        slot = OriginTemplateSlotFactory(template=old_template)

        self.assertEqual(list(old_template.questions), [slot])
        self.assertEqual(list(new_template.questions), [])

        slot.template = new_template
        slot.save()

        self.assertEqual(list(old_template.questions), [])
        self.assertEqual(list(new_template.questions), [slot])

    def test_a_deleted_slot_is_gone_from_a_warm_cache(self):
        template = OriginTemplateFactory()
        first = OriginTemplateSlotFactory(template=template, name="First", sort_order=0)
        doomed = OriginTemplateSlotFactory(template=template, name="Doomed", sort_order=1)
        warm = list(template.questions)
        assert doomed in warm

        with self.assertNumQueries(0):
            # Genuinely cached before any write happens.
            assert list(template.questions) == warm

        doomed.delete()
        assert list(template.questions) == [first], (
            "the cache served a stale list; deleting a slot must clear its "
            "Upbringing's cached properties via related_cache_fields"
        )

    def test_model_delete_invalidates_via_related_cache_fields_not_just_pk_pruning(self):
        """Isolates ``related_cache_fields``' own contribution from the pk-pruning
        belt proven below.

        ``test_a_deleted_slot_is_gone_from_a_warm_cache`` above gets the right
        ANSWER even if ``related_cache_fields`` silently failed to fire: Django's
        ``Model.delete()`` nulls ``doomed.pk`` regardless, and
        ``PrunedCachedProperty``'s own pruning would filter the pk-less row out of
        the still-cached, stale list for free - zero queries, no requery needed,
        masking a broken invalidation path. The mixin's contribution is that it
        clears the cache BEFORE the row's pk goes null, so the next read is a
        genuine requery, not a Python-level filter of an already-cached list.
        """
        template = OriginTemplateFactory()
        first = OriginTemplateSlotFactory(template=template, name="First", sort_order=0)
        doomed = OriginTemplateSlotFactory(template=template, name="Doomed", sort_order=1)
        assert doomed in list(template.questions)  # warm

        doomed.delete()

        with self.assertNumQueries(1):
            # A requery, not a free Python-level filter of the stale warm list -
            # proves related_cache_fields actually cleared the cache.
            served = list(template.questions)
        assert served == [first]

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
