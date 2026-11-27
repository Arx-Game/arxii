from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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
from world.magic.constants import GlimpseMemory, GlimpseTagAxis
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

    def test_actors_sheet_offer_needs_a_prompt(self):
        """The actor's sheet and Appearance have openers now (#3709)."""
        offer = DistinctionOffer(
            distinction=DistinctionFactory(),
            chapter=OfferChapter.ACTORS_SHEET,
            arrives_as=OfferArrival.CHOICE,
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()
        offer.prompt = "protect"
        offer.full_clean()

    def test_enemy_offer_is_opened_by_a_reason_or_a_marking_degree(self):
        from world.character_creation.factories import EnemyReasonFactory

        offer = DistinctionOffer(
            distinction=DistinctionFactory(),
            chapter=OfferChapter.ENEMY,
            arrives_as=OfferArrival.BUNDLED,
            enemy_degree="thwarted",
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()
        offer.enemy_degree = "destroy"
        offer.full_clean()
        assert offer.opener_key == "degree:destroy"
        offer.enemy_reason = EnemyReasonFactory()
        with self.assertRaises(ValidationError):
            offer.full_clean()

    def test_a_final_touches_offer_is_opened_by_a_card_and_never_by_itself(self):
        """#4846: the chapter's one opener is ``unlocked_by``; a card does not unlock itself."""
        escape = DistinctionFactory(name="Escape Artist")
        jailbird = DistinctionFactory(name="Jailbird")
        offer = DistinctionOffer(
            distinction=escape,
            chapter=OfferChapter.FINAL_TOUCHES,
            arrives_as=OfferArrival.CHOICE,
            glimpse_tag=GlimpseTagFactory(),
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()
        offer.glimpse_tag = None
        with self.assertRaises(ValidationError):
            offer.full_clean()
        offer.unlocked_by = escape
        with self.assertRaises(ValidationError):
            offer.full_clean()
        offer.unlocked_by = jailbird
        offer.full_clean()
        assert offer.opener_key == f"unlocked:{jailbird.pk}"
        assert offer.chapter_opener_fields == ("unlocked_by",)

    def test_an_identity_offer_takes_no_opener(self):
        """#5255: the Identity chapter is its own opener; any opener field is refused."""
        offer = DistinctionOffer(
            distinction=DistinctionFactory(name="Indolent"),
            chapter=OfferChapter.IDENTITY,
            arrives_as=OfferArrival.CHOICE,
        )
        offer.full_clean()
        assert offer.chapter_opener_fields == ()
        assert offer.opener_key == ""
        offer.prompt = "never_do"
        with self.assertRaises(ValidationError):
            offer.full_clean()

    def test_an_identity_offer_is_a_choice_and_a_card_has_one(self):
        """#5255: every Identity line is open to every draft, so a bundled one would hand
        the card to everyone; and with no opener a second line would be the same line."""
        indolent = DistinctionFactory(name="Indolent")
        bundled = DistinctionOffer(
            distinction=indolent, chapter=OfferChapter.IDENTITY, arrives_as=OfferArrival.BUNDLED
        )
        with self.assertRaises(ValidationError) as refused:
            bundled.full_clean()
        assert "arrives_as" in refused.exception.message_dict

        DistinctionOfferFactory(distinction=indolent, chapter=OfferChapter.IDENTITY)
        second = DistinctionOffer(
            distinction=indolent, chapter=OfferChapter.IDENTITY, arrives_as=OfferArrival.CHOICE
        )
        with self.assertRaises(ValidationError) as refused:
            second.full_clean()
        assert "already placed on the Identity stage" in str(refused.exception)
        with self.assertRaises(IntegrityError), transaction.atomic():
            second.save()
        # The same card is still free to be offered in another chapter.
        DistinctionOfferFactory(distinction=indolent, chapter=OfferChapter.ACTORS_SHEET)

    def test_offer_name_defaults_to_distinction_name(self):
        offer = DistinctionOfferFactory(distinction=DistinctionFactory(name="Impoverished"))
        assert offer.name == "Impoverished"

    def test_route_closes_distinctions(self):
        route = OriginTemplateFactory()
        highborn = DistinctionFactory(name="Highborn")
        route.closed_distinctions.add(highborn)
        assert list(route.closed_distinctions.all()) == [highborn]


class GlimpseOfferRuleTests(TestCase):
    """What a line of the Glimpse chapter may be (#5292).

    A Glimpse answer gives one card, free; the card is the Glimpse's alone; a blackout
    and no memory are each marked by a card through a line the memory state opens.
    """

    @classmethod
    def setUpTestData(cls):
        cls.wonder = GlimpseTagFactory(name="Wonder", axis=GlimpseTagAxis.TONE)
        cls.terror = GlimpseTagFactory(name="Terror", axis=GlimpseTagAxis.TONE)
        cls.crisis = GlimpseTagFactory(name="Crisis", axis=GlimpseTagAxis.TRIGGER)
        cls.public = GlimpseTagFactory(name="Public", axis=GlimpseTagAxis.WITNESS)

    def line(self, card=None, **kwargs) -> DistinctionOffer:
        return DistinctionOffer(
            distinction=card or DistinctionFactory(), chapter=OfferChapter.GLIMPSE, **kwargs
        )

    def refusal(self, offer: DistinctionOffer) -> str:
        with self.assertRaises(ValidationError) as raised:
            offer.full_clean()
        return " ".join(raised.exception.messages)

    def test_a_glimpse_line_is_saved_bundled_whatever_it_was_given(self):
        offer = self.line(glimpse_tag=self.wonder, arrives_as=OfferArrival.CHOICE)
        offer.full_clean()
        offer.save()
        offer.refresh_from_db()
        assert offer.arrives_as == OfferArrival.BUNDLED

    def test_a_line_of_another_chapter_keeps_the_arrival_it_was_given(self):
        offer = DistinctionOfferFactory(chapter=OfferChapter.APPEARANCE)
        assert offer.arrives_as == OfferArrival.CHOICE

    def test_a_memory_state_opens_a_line_and_only_the_two_a_card_marks(self):
        offer = self.line(glimpse_memory=GlimpseMemory.NO_MEMORY)
        offer.full_clean()
        assert offer.opener_key == "memory:no_memory"
        for state in (GlimpseMemory.REMEMBERED, GlimpseMemory.LATER):
            with self.subTest(state=state):
                assert "is not a valid choice" in self.refusal(self.line(glimpse_memory=state))

    def test_a_line_names_an_answer_or_a_memory_state_never_both(self):
        offer = self.line(glimpse_tag=self.wonder, glimpse_memory=GlimpseMemory.BLACKED_OUT)
        assert "An offer is opened by at most one thing." in self.refusal(offer)

    def test_a_memory_state_opens_no_line_outside_the_glimpse(self):
        offer = DistinctionOffer(
            distinction=DistinctionFactory(),
            chapter=OfferChapter.IDENTITY,
            glimpse_memory=GlimpseMemory.NO_MEMORY,
        )
        assert "not opened by this field" in self.refusal(offer)

    def test_an_answer_of_a_part_that_gives_no_card_is_refused(self):
        assert "An answer to Witness & Secrecy gives no card." in self.refusal(
            self.line(glimpse_tag=self.public)
        )

    def test_an_answer_gives_one_card(self):
        first = DistinctionOfferFactory(chapter=OfferChapter.GLIMPSE, glimpse_tag=self.wonder)
        assert "This answer already gives a card." in self.refusal(
            self.line(glimpse_tag=self.wonder)
        )
        # A line switched off gives nothing, so it is in nobody's way.
        first.is_active = False
        first.save()
        self.line(glimpse_tag=self.wonder).full_clean()
        # And the line itself can be saved again.
        first.is_active = True
        first.full_clean()

    def test_a_card_sits_under_answers_of_one_part(self):
        card = DistinctionFactory(name="Stormcalled")
        DistinctionOfferFactory(
            distinction=card, chapter=OfferChapter.GLIMPSE, glimpse_tag=self.wonder
        )
        self.line(card, glimpse_tag=self.terror).full_clean()
        assert "An answer to another part of the Glimpse already gives this card." in (
            self.refusal(self.line(card, glimpse_tag=self.crisis))
        )

    def test_a_glimpse_card_is_offered_on_no_other_stage(self):
        card = DistinctionFactory(name="Stormcalled")
        DistinctionOfferFactory(
            distinction=card, chapter=OfferChapter.GLIMPSE, glimpse_tag=self.wonder
        )
        elsewhere = DistinctionOffer(distinction=card, chapter=OfferChapter.IDENTITY)
        assert "The Glimpse gives this card, so no other stage offers it." in self.refusal(
            elsewhere
        )

    def test_a_card_another_stage_offers_cannot_be_a_glimpse_card(self):
        card = DistinctionFactory(name="Proud")
        DistinctionOfferFactory(distinction=card, chapter=OfferChapter.IDENTITY)
        assert "Another stage offers this card, so the Glimpse cannot give it." in (
            self.refusal(self.line(card, glimpse_tag=self.wonder))
        )

    def test_the_marking_card_may_sit_under_both_states_and_under_no_answer(self):
        mystery = DistinctionFactory(name="Glimpse Mystery")
        one = DistinctionOfferFactory(
            distinction=mystery,
            chapter=OfferChapter.GLIMPSE,
            glimpse_memory=GlimpseMemory.BLACKED_OUT,
        )
        other = self.line(mystery, glimpse_memory=GlimpseMemory.NO_MEMORY)
        other.full_clean()
        other.save()
        # The memory state is part of what names a line, so the two are told apart.
        assert one.natural_key() != other.natural_key()
        assert "so no answer can give it" in self.refusal(
            self.line(mystery, glimpse_tag=self.wonder)
        )

    def test_an_answers_card_cannot_also_mark_a_memory_state(self):
        card = DistinctionFactory(name="Stormcalled")
        DistinctionOfferFactory(
            distinction=card, chapter=OfferChapter.GLIMPSE, glimpse_tag=self.wonder
        )
        assert "so it cannot mark a memory" in self.refusal(
            self.line(card, glimpse_memory=GlimpseMemory.NO_MEMORY)
        )
