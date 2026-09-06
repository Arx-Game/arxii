from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_creation.constants import OfferArrival, OfferChapter, TraditionState
from world.character_creation.factories import (
    BeginningTraditionFactory,
    DistinctionOfferFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    SchoolingLineFactory,
    TraditionStateLineFactory,
)
from world.character_creation.models import DistinctionOffer
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import GlimpseTagFactory


class OfferModelTests(TestCase):
    def test_slate_line_defaults_to_living_masters(self):
        bt = BeginningTraditionFactory()
        assert bt.state == TraditionState.LIVING_MASTERS
        assert bt.own_wording == ""

    def test_schooling_line_price_is_derived(self):
        training = DistinctionFactory(name="Tradition Training", cost_per_rank=1, max_rank=2)
        line = SchoolingLineFactory(rank=2, grants=training)
        assert line.price == 2
        assert SchoolingLineFactory(rank=0, grants=None).price == 0

    def test_state_line_price_is_the_carried_drawback(self):
        drawback = DistinctionFactory(name="Unbound", cost_per_rank=-75)
        line = TraditionStateLineFactory(state=TraditionState.SELF_TAUGHT, carries=drawback)
        assert line.price == -75

    def test_offer_takes_at_most_one_opener(self):
        offer = DistinctionOffer(
            distinction=DistinctionFactory(),
            chapter=OfferChapter.GLIMPSE,
            arrives_as=OfferArrival.CHOICE,
            glimpse_tag=GlimpseTagFactory(),
            origin_choice=OriginTemplateSlotChoiceFactory(),
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()

    def test_offer_chapter_constrains_opener_kind(self):
        offer = DistinctionOffer(
            distinction=DistinctionFactory(),
            chapter=OfferChapter.LINEAGE,
            arrives_as=OfferArrival.CHOICE,
            glimpse_tag=GlimpseTagFactory(),
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()

    def test_tradition_step_offer_with_schooling_line_is_valid(self):
        offer = DistinctionOffer(
            distinction=DistinctionFactory(),
            chapter=OfferChapter.TRADITION_STEP,
            arrives_as=OfferArrival.CHOICE,
            schooling_line=SchoolingLineFactory(),
        )
        offer.full_clean()

    def test_glimpse_offer_with_no_opener_is_invalid(self):
        offer = DistinctionOffer(
            distinction=DistinctionFactory(),
            chapter=OfferChapter.GLIMPSE,
            arrives_as=OfferArrival.CHOICE,
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()

    def test_offer_name_defaults_to_distinction_name(self):
        offer = DistinctionOfferFactory(distinction=DistinctionFactory(name="Impoverished"))
        assert offer.name == "Impoverished"

    def test_route_closes_distinctions(self):
        route = OriginTemplateFactory(closed_reason="The yards do not make those.")
        highborn = DistinctionFactory(name="Highborn")
        route.closed_distinctions.add(highborn)
        assert list(route.closed_distinctions.all()) == [highborn]
