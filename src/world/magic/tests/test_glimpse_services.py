"""Tests for world.magic.services.glimpse (#2427)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_creation.constants import OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.magic.constants import GlimpseMemory, GlimpseState, GlimpseTagAxis
from world.magic.factories import AffinityFactory, CharacterAuraFactory, GlimpseTagFactory
from world.magic.models import CharacterGlimpseTag
from world.magic.services.glimpse import (
    GLIMPSE_AFFINITY_NUDGE_PERCENT,
    keep_stand_alone,
    link_distinction_to_glimpse,
    player_can_finish_glimpse,
    refresh_glimpse_state,
    set_glimpse_memory,
    set_glimpse_prose,
    set_glimpse_tags,
    unlink_distinction_from_glimpse,
    write_glimpse,
)
from world.magic.tests.glimpse_helpers import axis_takes_several


class SetGlimpseTagsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.aura = CharacterAuraFactory()
        cls.tone_a = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-a")
        cls.tone_b = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-b")
        cls.consequence_a = GlimpseTagFactory(axis=GlimpseTagAxis.CONSEQUENCE, slug="consequence-a")
        cls.consequence_b = GlimpseTagFactory(axis=GlimpseTagAxis.CONSEQUENCE, slug="consequence-b")

    def test_sets_tags_and_state_becomes_tags_only(self):
        set_glimpse_tags(self.aura, [self.tone_a], axis=GlimpseTagAxis.TONE)
        assert self.aura.glimpse_state == GlimpseState.TAGS_ONLY
        assert list(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag__slug", flat=True)
        ) == ["tone-a"]

    def test_replaces_tags_for_axis_only(self):
        set_glimpse_tags(self.aura, [self.consequence_a], axis=GlimpseTagAxis.CONSEQUENCE)
        set_glimpse_tags(self.aura, [self.tone_a], axis=GlimpseTagAxis.TONE)
        set_glimpse_tags(self.aura, [self.tone_b], axis=GlimpseTagAxis.TONE)
        slugs = set(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag__slug", flat=True)
        )
        assert slugs == {"consequence-a", "tone-b"}

    def test_tone_rejects_multiple_tags(self):
        with self.assertRaises(ValidationError):
            set_glimpse_tags(self.aura, [self.tone_a, self.tone_b], axis=GlimpseTagAxis.TONE)

    def test_every_axis_takes_one_answer(self):
        """#5292: an answer carries one bonus, so no axis takes several."""
        for axis in GlimpseTagAxis:
            first = GlimpseTagFactory(axis=axis, slug=f"one-{axis.value.lower()}-a")
            second = GlimpseTagFactory(axis=axis, slug=f"one-{axis.value.lower()}-b")
            with self.subTest(axis=axis), self.assertRaises(ValidationError):
                set_glimpse_tags(self.aura, [first, second], axis=axis)

    @axis_takes_several(GlimpseTagAxis.CONSEQUENCE)
    def test_an_axis_set_to_take_several_still_does(self):
        """The several-answers path is kept as the way back."""
        set_glimpse_tags(
            self.aura,
            [self.consequence_a, self.consequence_b],
            axis=GlimpseTagAxis.CONSEQUENCE,
        )
        assert CharacterGlimpseTag.objects.filter(aura=self.aura).count() == 2

    def test_rejects_tag_from_wrong_axis(self):
        with self.assertRaises(ValidationError):
            set_glimpse_tags(self.aura, [self.consequence_a], axis=GlimpseTagAxis.TONE)

    def test_clearing_all_tags_returns_to_not_started(self):
        set_glimpse_tags(self.aura, [self.tone_a], axis=GlimpseTagAxis.TONE)
        set_glimpse_tags(self.aura, [], axis=GlimpseTagAxis.TONE)
        assert self.aura.glimpse_state == GlimpseState.NOT_STARTED


@axis_takes_several(GlimpseTagAxis.REFLECTION)
class StandAloneTagTests(TestCase):
    """A tag that stands alone is the only tag of its axis (#5193).

    The rule only shows on an axis that takes several answers, which none does since
    #5292; the class opens The Reflection to hold the kept path.
    """

    @classmethod
    def setUpTestData(cls):
        cls.aura = CharacterAuraFactory()
        cls.majestic = GlimpseTagFactory(
            axis=GlimpseTagAxis.REFLECTION, slug="alone-majestic", name="Majestic", sort_order=1
        )
        cls.terrifying = GlimpseTagFactory(
            axis=GlimpseTagAxis.REFLECTION, slug="alone-terrifying", name="Terrifying", sort_order=2
        )
        cls.fugue = GlimpseTagFactory(
            axis=GlimpseTagAxis.REFLECTION,
            slug="alone-fugue",
            name="Fugue",
            sort_order=3,
            stands_alone=True,
        )

    def test_a_tag_does_not_stand_alone_unless_staff_say_so(self):
        assert self.majestic.stands_alone is False

    def test_a_stand_alone_tag_is_saved_alone(self):
        set_glimpse_tags(self.aura, [self.fugue], axis=GlimpseTagAxis.REFLECTION)
        assert list(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag__slug", flat=True)
        ) == ["alone-fugue"]

    def test_a_stand_alone_tag_beside_another_is_refused_and_nothing_changes(self):
        set_glimpse_tags(self.aura, [self.majestic], axis=GlimpseTagAxis.REFLECTION)
        with self.assertRaises(ValidationError) as raised:
            set_glimpse_tags(self.aura, [self.majestic, self.fugue], axis=GlimpseTagAxis.REFLECTION)
        assert raised.exception.messages == [
            "Fugue cannot be chosen with another The Reflection tag."
        ]
        assert list(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag__slug", flat=True)
        ) == ["alone-majestic"]

    def test_the_axis_still_takes_several_ordinary_tags(self):
        set_glimpse_tags(
            self.aura, [self.majestic, self.terrifying], axis=GlimpseTagAxis.REFLECTION
        )
        assert CharacterGlimpseTag.objects.filter(aura=self.aura).count() == 2

    def test_keep_stand_alone_drops_the_others(self):
        assert keep_stand_alone([self.majestic, self.fugue, self.terrifying]) == [self.fugue]

    def test_keep_stand_alone_leaves_ordinary_tags_as_given(self):
        assert keep_stand_alone([self.terrifying, self.majestic]) == [
            self.terrifying,
            self.majestic,
        ]
        assert keep_stand_alone([]) == []


class GlimpseStateTransitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tone = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-x")

    def setUp(self):
        self.aura = CharacterAuraFactory()

    def test_prose_alone_completes(self):
        set_glimpse_prose(self.aura, "I saw the threads.")
        assert self.aura.glimpse_state == GlimpseState.COMPLETE
        assert self.aura.glimpse_story == "I saw the threads."

    def test_tags_then_prose_completes(self):
        set_glimpse_tags(self.aura, [self.tone], axis=GlimpseTagAxis.TONE)
        assert self.aura.glimpse_state == GlimpseState.TAGS_ONLY
        set_glimpse_prose(self.aura, "It was horrifying.")
        assert self.aura.glimpse_state == GlimpseState.COMPLETE

    def test_erasing_prose_with_tags_returns_to_tags_only(self):
        set_glimpse_tags(self.aura, [self.tone], axis=GlimpseTagAxis.TONE)
        set_glimpse_prose(self.aura, "Draft text.")
        set_glimpse_prose(self.aura, "")
        assert self.aura.glimpse_state == GlimpseState.TAGS_ONLY

    def test_refresh_recomputes_from_truth(self):
        self.aura.glimpse_story = "Written out of band."
        self.aura.save()
        assert refresh_glimpse_state(self.aura) == GlimpseState.COMPLETE


class GlimpseDistinctionLinkTests(TestCase):
    def test_link_and_unlink(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.distinctions.factories import CharacterDistinctionFactory

        aura = CharacterAuraFactory()
        sheet = CharacterSheetFactory(character=aura.character)
        cd = CharacterDistinctionFactory(character=sheet)
        link_distinction_to_glimpse(cd, aura)
        assert cd.from_glimpse_id == aura.pk
        unlink_distinction_from_glimpse(cd)
        assert cd.from_glimpse_id is None

    def test_link_rejects_other_characters_aura(self):
        from world.distinctions.factories import CharacterDistinctionFactory

        aura = CharacterAuraFactory()
        cd = CharacterDistinctionFactory()  # different character
        with self.assertRaises(ValidationError):
            link_distinction_to_glimpse(cd, aura)


class WriteGlimpseTests(TestCase):
    """``write_glimpse``: what a player may write in play, and the card an answer gives (#5292)."""

    @classmethod
    def setUpTestData(cls):
        cls.tone = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="w-wonder", name="Wonder")
        cls.tone_other = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="w-terror", name="Terror")
        cls.trigger = GlimpseTagFactory(axis=GlimpseTagAxis.TRIGGER, slug="w-crisis", name="Crisis")
        cls.witness = GlimpseTagFactory(axis=GlimpseTagAxis.WITNESS, slug="w-public", name="Public")
        cls.tone_card = DistinctionFactory(name="Wonderstruck", slug="w-wonderstruck")
        cls.other_card = DistinctionFactory(name="Dreadmarked", slug="w-dreadmarked")
        DistinctionOfferFactory(
            distinction=cls.tone_card, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.tone
        )
        DistinctionOfferFactory(
            distinction=cls.other_card, chapter=OfferChapter.GLIMPSE, glimpse_tag=cls.tone_other
        )

    def setUp(self):
        self.aura = CharacterAuraFactory()
        self.sheet = self.aura.character

    def held(self):
        return set(
            CharacterDistinction.objects.filter(character=self.sheet).values_list(
                "distinction__name", flat=True
            )
        )

    def answers(self):
        return set(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag__name", flat=True)
        )

    def test_an_answer_gives_its_card_marked_as_from_the_glimpse(self):
        given = write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        assert [card.distinction.name for card in given] == ["Wonderstruck"]
        card = CharacterDistinction.objects.get(character=self.sheet, distinction=self.tone_card)
        assert card.rank == 1
        assert card.origin == DistinctionOrigin.GAMEPLAY
        assert card.from_glimpse_id == self.aura.pk
        assert card.source_description == "Wonder"

    def test_an_answer_with_no_card_gives_nothing(self):
        given = write_glimpse(
            self.aura, by_staff=False, answers={GlimpseTagAxis.TRIGGER: [self.trigger]}
        )
        assert given == []
        assert self.held() == set()
        assert self.answers() == {"Crisis"}

    def test_a_secret_card_arrives_with_its_secret(self):
        self.tone_card.secret_by_default = True
        self.tone_card.save()
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        card = CharacterDistinction.objects.get(character=self.sheet, distinction=self.tone_card)
        assert card.secret_id is not None

    def test_a_player_cannot_clear_an_answered_axis(self):
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        with self.assertRaises(ValidationError):
            write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: []})
        assert self.answers() == {"Wonder"}

    def test_the_same_answer_sent_again_is_accepted_and_gives_nothing_new(self):
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        given = write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        assert given == []
        assert CharacterDistinction.objects.filter(character=self.sheet).count() == 1

    def test_one_refused_axis_keeps_the_whole_write_out(self):
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        with self.assertRaises(ValidationError):
            write_glimpse(
                self.aura,
                by_staff=False,
                answers={
                    GlimpseTagAxis.WITNESS: [self.witness],
                    GlimpseTagAxis.TONE: [self.tone_other],
                },
            )
        assert self.answers() == {"Wonder"}

    def test_an_unanswered_axis_can_be_answered_after_the_story_is_written(self):
        write_glimpse(self.aura, by_staff=False, story="It rained upward.")
        assert self.aura.glimpse_state == GlimpseState.COMPLETE
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        assert self.held() == {"Wonderstruck"}

    def test_staff_write_where_a_player_is_refused(self):
        set_glimpse_memory(self.aura, GlimpseMemory.NO_MEMORY)
        write_glimpse(self.aura, by_staff=True, answers={GlimpseTagAxis.TONE: [self.tone]})
        assert self.answers() == {"Wonder"}
        assert self.held() == {"Wonderstruck"}

    def test_staff_change_an_answer_and_the_old_card_stays(self):
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        given = write_glimpse(
            self.aura, by_staff=True, answers={GlimpseTagAxis.TONE: [self.tone_other]}
        )
        assert [card.distinction.name for card in given] == ["Dreadmarked"]
        assert self.answers() == {"Terror"}
        assert self.held() == {"Wonderstruck", "Dreadmarked"}

    def test_an_answer_written_before_its_card_existed_gives_it_at_the_next_write(self):
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TRIGGER: [self.trigger]})
        late_card = DistinctionFactory(name="Crisisborn", slug="w-crisisborn")
        DistinctionOfferFactory(
            distinction=late_card, chapter=OfferChapter.GLIMPSE, glimpse_tag=self.trigger
        )
        given = write_glimpse(self.aura, by_staff=False, story="It began in the fire.")
        assert [card.distinction.name for card in given] == ["Crisisborn"]

    def test_a_card_the_character_already_holds_is_left_as_it_is(self):
        mine = CharacterDistinctionFactory(character=self.sheet, distinction=self.tone_card)
        given = write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        assert given == []
        mine.refresh_from_db()
        assert mine.from_glimpse_id is None

    def test_a_card_that_excludes_a_held_card_refuses_the_whole_write(self):
        rival = DistinctionFactory(name="Unmoved", slug="w-unmoved")
        self.tone_card.mutually_exclusive_with.add(rival)
        CharacterDistinctionFactory(character=self.sheet, distinction=rival)
        with self.assertRaises(ValidationError) as raised:
            write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        assert raised.exception.messages == ["Unavailable because mutually exclusive with Unmoved."]
        assert self.answers() == set()
        assert self.held() == {"Unmoved"}

    def test_a_refused_write_saves_nothing_and_leaves_no_phantom_on_the_aura(self):
        """Every refusal comes before any save, so the cached aura never shows a story
        or a shifted aura that the database does not hold, and the player is told of no
        card they were not given."""
        from world.narrative.models import NarrativeMessage

        celestial = AffinityFactory(name="Celestial")
        self.trigger.affinity = celestial
        self.trigger.save()
        rival = DistinctionFactory(name="Unmoved", slug="w-unmoved-2")
        self.tone_card.mutually_exclusive_with.add(rival)
        CharacterDistinctionFactory(character=self.sheet, distinction=rival)
        before = self.aura.shares.get(affinity=celestial).settled_percent
        told = NarrativeMessage.objects.count()

        with self.assertRaises(ValidationError):
            write_glimpse(
                self.aura,
                by_staff=False,
                answers={GlimpseTagAxis.TRIGGER: [self.trigger], GlimpseTagAxis.TONE: [self.tone]},
                story="Refused with the rest.",
            )

        assert self.aura.glimpse_story == ""
        assert self.aura.glimpse_state == GlimpseState.NOT_STARTED
        assert [
            share.settled_percent
            for share in self.aura.cached_shares
            if share.affinity == celestial
        ] == [before]
        assert self.answers() == set()
        assert NarrativeMessage.objects.count() == told

    def test_a_card_owed_from_an_earlier_answer_never_blocks_a_later_write(self):
        """An answer written before its card existed is owed the card. If the character
        cannot hold it (it excludes a card they have), a later write still goes through."""
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TRIGGER: [self.trigger]})
        late_card = DistinctionFactory(name="Crisisborn", slug="w-crisisborn-2")
        rival = DistinctionFactory(name="Unshaken", slug="w-unshaken")
        late_card.mutually_exclusive_with.add(rival)
        CharacterDistinctionFactory(character=self.sheet, distinction=rival)
        DistinctionOfferFactory(
            distinction=late_card, chapter=OfferChapter.GLIMPSE, glimpse_tag=self.trigger
        )

        given = write_glimpse(self.aura, by_staff=False, story="It began in the fire.")

        assert given == []
        assert self.aura.glimpse_story == "It began in the fire."
        assert self.held() == {"Unshaken"}

    def test_an_answer_of_another_path_is_refused_to_a_player_and_open_to_staff(self):
        from world.classes.factories import PathFactory

        claimed = GlimpseTagFactory(axis=GlimpseTagAxis.CHOOSING, slug="w-claimed", name="Claimed")
        claimed.paths.add(PathFactory(name="Path of the Chosen"))
        with self.assertRaises(ValidationError) as raised:
            write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.CHOOSING: [claimed]})
        assert raised.exception.messages == [
            "Claimed is not an answer this character's path can give."
        ]
        assert self.answers() == set()
        write_glimpse(self.aura, by_staff=True, answers={GlimpseTagAxis.CHOOSING: [claimed]})
        assert self.answers() == {"Claimed"}

    def test_staff_changing_the_memory_tells_the_character_once(self):
        from world.narrative.models import NarrativeMessage

        told = NarrativeMessage.objects.count()
        set_glimpse_memory(self.aura, GlimpseMemory.NO_MEMORY)
        set_glimpse_memory(self.aura, GlimpseMemory.NO_MEMORY)
        set_glimpse_memory(self.aura, GlimpseMemory.REMEMBERED)
        bodies = list(NarrativeMessage.objects.order_by("pk").values_list("body", flat=True)[told:])
        assert bodies == [
            "You have no memory of your Glimpse.",
            "The memory of your Glimpse has returned. You can write it from your character sheet.",
        ]

    def test_a_first_tone_answer_shifts_the_aura_once_and_a_changed_one_does_not(self):
        celestial = AffinityFactory(name="Celestial")
        self.tone.affinity = celestial
        self.tone.save()
        abyssal = AffinityFactory(name="Abyssal")
        self.tone_other.affinity = abyssal
        self.tone_other.save()

        def settled(affinity):
            return self.aura.shares.get(affinity=affinity).settled_percent

        before = settled(celestial)
        write_glimpse(self.aura, by_staff=False, answers={GlimpseTagAxis.TONE: [self.tone]})
        after_first = settled(celestial)
        assert after_first > before
        assert after_first - before <= Decimal(GLIMPSE_AFFINITY_NUDGE_PERCENT)
        abyssal_before = settled(abyssal)
        write_glimpse(self.aura, by_staff=True, answers={GlimpseTagAxis.TONE: [self.tone_other]})
        assert settled(abyssal) == abyssal_before
        assert settled(celestial) == after_first


class PlayerCanFinishGlimpseTests(TestCase):
    """The sheet's "Finish your Glimpse" door (#5292)."""

    @classmethod
    def setUpTestData(cls):
        cls.tone = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="f-tone")
        cls.witness = GlimpseTagFactory(axis=GlimpseTagAxis.WITNESS, slug="f-witness")

    def setUp(self):
        self.aura = CharacterAuraFactory()

    def test_open_while_the_story_is_blank(self):
        assert player_can_finish_glimpse(self.aura, path_id=None) is True

    def test_open_after_the_story_while_an_axis_has_no_answer(self):
        set_glimpse_prose(self.aura, "Written.")
        assert player_can_finish_glimpse(self.aura, path_id=None) is True

    def test_closed_once_the_story_and_every_axis_with_answers_are_written(self):
        set_glimpse_prose(self.aura, "Written.")
        set_glimpse_tags(self.aura, [self.tone], axis=GlimpseTagAxis.TONE)
        set_glimpse_tags(self.aura, [self.witness], axis=GlimpseTagAxis.WITNESS)
        assert player_can_finish_glimpse(self.aura, path_id=None) is False

    def test_an_axis_only_another_path_can_answer_does_not_keep_it_open(self):
        from world.classes.factories import PathFactory

        set_glimpse_prose(self.aura, "Written.")
        set_glimpse_tags(self.aura, [self.tone], axis=GlimpseTagAxis.TONE)
        set_glimpse_tags(self.aura, [self.witness], axis=GlimpseTagAxis.WITNESS)
        chosen = PathFactory()
        claimed = GlimpseTagFactory(axis=GlimpseTagAxis.CHOOSING, slug="f-choosing")
        claimed.paths.add(chosen)
        assert player_can_finish_glimpse(self.aura, path_id=None) is False
        assert player_can_finish_glimpse(self.aura, path_id=chosen.pk) is True

    def test_never_open_with_no_memory(self):
        set_glimpse_memory(self.aura, GlimpseMemory.NO_MEMORY)
        assert player_can_finish_glimpse(self.aura, path_id=None) is False

    def test_after_a_blackout_the_lost_axes_do_not_keep_it_open(self):
        set_glimpse_memory(self.aura, GlimpseMemory.BLACKED_OUT)
        set_glimpse_prose(self.aura, "Written.")
        set_glimpse_tags(self.aura, [self.witness], axis=GlimpseTagAxis.WITNESS)
        assert player_can_finish_glimpse(self.aura, path_id=None) is False
