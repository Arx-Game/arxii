from django.db import IntegrityError
from django.test import TestCase

from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    TraditionTemplateFacetFactory,
    TraditionTemplateFactory,
    TraditionTemplateTechniqueFactory,
)
from world.character_creation.models import BeginningTradition, TraditionTemplate
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import TraditionFactory


class BeginningTraditionTests(TestCase):
    """Tests for BeginningTradition through model."""

    def test_create_beginning_tradition(self):
        bt = BeginningTraditionFactory()
        assert BeginningTradition.objects.filter(pk=bt.pk).exists()

    def test_with_required_distinction(self):
        distinction = DistinctionFactory()
        bt = BeginningTraditionFactory(required_distinction=distinction)
        assert bt.required_distinction == distinction

    def test_beginning_traditions_m2m(self):
        beginning = BeginningsFactory()
        t1 = TraditionFactory(name="T1")
        t2 = TraditionFactory(name="T2")
        BeginningTradition.objects.create(beginning=beginning, tradition=t1)
        BeginningTradition.objects.create(beginning=beginning, tradition=t2)
        assert beginning.traditions.count() == 2

    def test_unique_together(self):
        bt = BeginningTraditionFactory()
        with self.assertRaises(IntegrityError):
            BeginningTradition.objects.create(beginning=bt.beginning, tradition=bt.tradition)

    def test_tradition_available_in_multiple_beginnings(self):
        tradition = TraditionFactory()
        b1 = BeginningsFactory(name="B1")
        b2 = BeginningsFactory(name="B2")
        BeginningTradition.objects.create(beginning=b1, tradition=tradition)
        BeginningTradition.objects.create(beginning=b2, tradition=tradition)
        assert tradition.available_beginnings.count() == 2


class TraditionTemplateTests(TestCase):
    """Tests for TraditionTemplate and child models."""

    def test_create_template(self):
        t = TraditionTemplateFactory()
        assert TraditionTemplate.objects.filter(pk=t.pk).exists()

    def test_unique_together_tradition_path(self):
        t = TraditionTemplateFactory()
        with self.assertRaises(IntegrityError):
            TraditionTemplate.objects.create(
                tradition=t.tradition,
                path=t.path,
                gift_name="Duplicate",
            )

    def test_template_with_techniques(self):
        t = TraditionTemplateFactory()
        tech = TraditionTemplateTechniqueFactory(template=t)
        assert t.techniques.count() == 1
        assert t.techniques.first() == tech

    def test_template_with_facets(self):
        t = TraditionTemplateFactory()
        facet = TraditionTemplateFacetFactory(template=t)
        assert t.facets.count() == 1
        assert t.facets.first() == facet
