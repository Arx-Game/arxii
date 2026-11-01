"""The Final Touches chapter (#4846, slice 5 of #4813): card-unlocked lines and Jailbird's crime.

The journey (``integration_tests/test_final_touches_chapter_journeys.py``) walks the API seam;
these are the refusal and edge paths it does not reach: the opener closing again when the
card is unpicked, the prompt list, the crime validator's shapes, and finalize's silence when
no held card asks the question.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
    RealmFactory,
)
from world.character_creation.models import CharacterDraft, StartingArea
from world.character_creation.offers import (
    final_touches_prompts,
    offers_for,
    reconcile_offer_picks,
)
from world.character_creation.serializers import CharacterDraftSerializer
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.justice.factories import CrimeKindFactory
from world.justice.models import CharacterCrimeNote


def _held(distinction, offer=None) -> dict:
    """A draft entry holding ``distinction``: from ``offer`` when given, else a catalogue pick
    with no ``offer_ids`` key, which the reconcile keeps as stored (an empty list would read
    as a pick whose last source vanished)."""
    entry = {
        "distinction_id": distinction.pk,
        "distinction_name": distinction.name,
        "rank": 1,
        "cost": distinction.cost_per_rank,
    }
    if offer is not None:
        entry.update(offer_ids=[offer.pk], sources=[offer.name], arrivals=[offer.arrives_as])
    return entry


class FinalTouchesOpenerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.jailbird = DistinctionFactory(name="Jailbird", final_touches_prompt="crime")
        cls.escape = DistinctionFactory(name="Escape Artist", cost_per_rank=5)
        cls.line = DistinctionOfferFactory(
            distinction=cls.escape,
            chapter=OfferChapter.FINAL_TOUCHES,
            arrives_as=OfferArrival.CHOICE,
            appearance_section=None,
            unlocked_by=cls.jailbird,
        )

    def _draft(self, *held):
        return CharacterDraftFactory(
            account=self.account,
            selected_beginnings=self.beginning,
            draft_data={"distinctions": [_held(d) for d in held]},
        )

    def test_the_line_shows_only_while_the_card_is_held(self):
        assert offers_for(self._draft(), OfferChapter.FINAL_TOUCHES) == []
        (offer,) = offers_for(self._draft(self.jailbird), OfferChapter.FINAL_TOUCHES)
        assert offer.offer_id == self.line.pk
        assert offer.opener_label == "Jailbird"
        assert offer.opener_key == f"unlocked:{self.jailbird.pk}"

    def test_unpicking_the_card_drops_what_it_unlocked(self):
        draft = self._draft(self.jailbird)
        draft.draft_data["distinctions"].append(_held(self.escape, self.line))
        draft.save(update_fields=["draft_data"])
        assert reconcile_offer_picks(draft) == []
        draft.draft_data["distinctions"] = [_held(self.escape, self.line)]
        draft.save(update_fields=["draft_data"])
        assert reconcile_offer_picks(draft) == ["Escape Artist"]
        assert draft.draft_data["distinctions"] == []

    def test_the_prompts_are_those_of_the_held_cards_once_each(self):
        twice = DistinctionFactory(name="Repeat Offender", final_touches_prompt="crime")
        assert final_touches_prompts(self._draft()) == []
        assert final_touches_prompts(self._draft(self.escape)) == []
        assert final_touches_prompts(self._draft(self.jailbird, twice)) == ["crime"]


class CrimeValidationTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountDB.objects.create(username="crime_validation")
        area = StartingArea.objects.create(
            name="Test Area",
            description="Test area",
            realm=RealmFactory(),
            access_level=StartingArea.AccessLevel.ALL,
        )
        self.draft = CharacterDraft.objects.create(account=self.account, selected_area=area)
        self.theft = CrimeKindFactory(slug="theft", name="Theft")

    def _patch(self, value):
        return CharacterDraftSerializer(
            instance=self.draft, data={"draft_data": {"crime": value}}, partial=True
        )

    def test_a_kind_and_a_line_are_accepted_and_null_clears(self) -> None:
        crime = {"kind_id": self.theft.pk, "line": "A purse that was not mine."}
        serializer = self._patch(crime)
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().draft_data["crime"] == crime
        serializer = self._patch({"kind_id": self.theft.pk})
        assert serializer.is_valid(), serializer.errors
        serializer = self._patch(None)
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().draft_data["crime"] is None

    def test_the_shape_is_checked(self) -> None:
        bad = (
            "theft",
            {"kind_id": "theft"},
            {"kind_id": self.theft.pk + 1000},
            {"kind_id": self.theft.pk, "line": 3},
            {"kind_id": self.theft.pk, "line": "x" * 501},
            {"kind_id": self.theft.pk, "heat": 5},
        )
        for value in bad:
            serializer = self._patch(value)
            assert not serializer.is_valid(), value
            assert "crime" in str(serializer.errors)
        serializer = self._patch(bad[4])
        assert not serializer.is_valid()
        assert "500" in str(serializer.errors)


class CrimeNoteFinalizeTests(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="crime_note")
        self._setup_finalization_base(self, prefix="Crime Note", height_min=700, height_max=800)
        self.jailbird = DistinctionFactory(
            name="Jailbird", cost_per_rank=-5, max_rank=1, final_touches_prompt="crime"
        )
        self.theft = CrimeKindFactory(slug="theft", name="Theft")
        self.crime = {"kind_id": self.theft.pk, "line": "  A purse that was not mine.  "}

    def test_a_held_asking_card_writes_the_note_stripped(self) -> None:
        draft = self._create_base_draft(
            first_name="Maud", distinctions=[_held(self.jailbird)], crime=self.crime
        )
        character = finalize_character(draft, add_to_roster=True)
        (note,) = CharacterCrimeNote.objects.filter(sheet=character.sheet_data)
        assert note.crime_kind == self.theft
        assert note.note == "A purse that was not mine."

    def test_no_asking_card_held_writes_nothing(self) -> None:
        draft = self._create_base_draft(first_name="Maud", crime=self.crime)
        character = finalize_character(draft, add_to_roster=True)
        assert not CharacterCrimeNote.objects.filter(sheet=character.sheet_data).exists()

    def test_a_held_card_with_no_crime_named_writes_nothing(self) -> None:
        draft = self._create_base_draft(
            first_name="Maud", distinctions=[_held(self.jailbird)], crime=None
        )
        character = finalize_character(draft, add_to_roster=True)
        assert not CharacterCrimeNote.objects.filter(sheet=character.sheet_data).exists()
