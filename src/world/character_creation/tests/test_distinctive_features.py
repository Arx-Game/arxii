"""Distinctive physical features: one point per feature, then the axes (#3739).

Three layers, per the project's test policy: the offer/reconcile rules, the sync
endpoint's validation, and one end-to-end journey from an unlocked feature to
the ``CharacterDistinction`` rows and the widened palette a finalized character
carries.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import OfferChapter
from world.character_creation.factories import (
    AppearanceSectionFactory,
    BeginningsFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
)
from world.character_creation.offers import (
    offers_for,
    opened_feature_traits,
    reconcile_offer_picks,
)
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import (
    DEFAULT_STATS,
    FinalizationTestMixin,
)
from world.character_creation.validators import _get_form_trait_errors
from world.distinctions.factories import DistinctionFactory
from world.distinctions.types import build_distinction_entry
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.forms.models import SpeciesFormTrait
from world.forms.services import get_cg_form_options
from world.species.models import Species


class FeatureOfferTests(TestCase):
    """``offers_for`` and ``reconcile_offer_picks`` on the per-feature rows."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory()
        cls.opener = DistinctionFactory(
            name="Make It Distinctive",
            cost_per_rank=1,
            max_rank=1,
            taken_per_feature=True,
            opens_feature=True,
        )
        cls.alluring = DistinctionFactory(
            name="Alluring",
            cost_per_rank=2,
            max_rank=5,
            cg_max_rank=3,
            taken_per_feature=True,
            requires_feature_opened=True,
        )
        cls.opener_offer = DistinctionOfferFactory(
            distinction=cls.opener, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )
        cls.alluring_offer = DistinctionOfferFactory(
            distinction=cls.alluring, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )

    def _draft(self, **data):
        return CharacterDraftFactory(
            account=self.account, selected_beginnings=self.beginning, draft_data=data
        )

    def _entry(self, distinction, *, trait="", marking=0, rank=1, offer=None):
        return build_distinction_entry(
            distinction,
            rank,
            offer=offer or (self.opener_offer if distinction is self.opener else None),
            feature_trait=trait,
            feature_marking=marking,
        )

    def test_a_feature_rows_line_is_open_with_no_section(self):
        """The chapter itself opens it: it is offered on every feature (#3739)."""
        offers = offers_for(self._draft(), OfferChapter.APPEARANCE)
        by_id = {o.offer_id: o for o in offers}
        assert set(by_id) == {self.opener_offer.id, self.alluring_offer.id}
        assert by_id[self.opener_offer.id].opener_key == "feature"
        assert by_id[self.opener_offer.id].taken_per_feature is True
        assert by_id[self.opener_offer.id].opens_feature is True
        assert by_id[self.alluring_offer.id].requires_feature_opened is True
        assert by_id[self.alluring_offer.id].cg_max_rank == 3

    def test_a_sectioned_line_and_a_feature_line_both_show(self):
        """Adding the feature rows does not displace the section blocks (#3709)."""
        section = AppearanceSectionFactory(name="Frame", sort_order=1)
        plain = DistinctionFactory(name="Broad Shouldered")
        plain_offer = DistinctionOfferFactory(
            distinction=plain, chapter=OfferChapter.APPEARANCE, appearance_section=section
        )
        offers = offers_for(self._draft(), OfferChapter.APPEARANCE)
        # The sectioned line sorts before the feature rows, which belong to no section.
        assert next(o.offer_id for o in offers) == plain_offer.id
        assert len(offers) == 3

    def test_a_per_feature_line_is_never_marked_held_elsewhere(self):
        """It is offered on every feature at once, so "held" is per feature (#3739)."""
        draft = self._draft(distinctions=[self._entry(self.opener, trait="hair_color")])
        offers = {o.offer_id: o for o in offers_for(draft, OfferChapter.APPEARANCE)}
        assert offers[self.opener_offer.id].held is False

    def test_the_same_distinction_is_held_once_per_feature(self):
        """Two features, two entries, two prices — the point of the feature key."""
        draft = self._draft(
            distinctions=[
                self._entry(self.opener, trait="hair_color"),
                self._entry(self.opener, trait="eye_color"),
            ]
        )
        reconcile_offer_picks(draft)
        draft.refresh_from_db()
        entries = draft.draft_data["distinctions"]
        assert len(entries) == 2
        assert {e["feature_trait"] for e in entries} == {"hair_color", "eye_color"}
        assert [e["cost"] for e in entries] == [1, 1]

    def test_an_axis_is_dropped_when_its_feature_is_no_longer_distinctive(self):
        """Refund the unlock and the axes bought under it go with it (#3739)."""
        draft = self._draft(
            distinctions=[
                self._entry(self.alluring, trait="hair_color", rank=2, offer=self.alluring_offer)
            ]
        )
        changed = reconcile_offer_picks(draft)
        draft.refresh_from_db()
        assert draft.draft_data["distinctions"] == []
        assert "Alluring" in changed

    def test_an_axis_survives_alongside_its_unlock(self):
        draft = self._draft(
            distinctions=[
                self._entry(self.opener, trait="hair_color"),
                self._entry(self.alluring, trait="hair_color", rank=2, offer=self.alluring_offer),
            ]
        )
        reconcile_offer_picks(draft)
        draft.refresh_from_db()
        assert len(draft.draft_data["distinctions"]) == 2

    def test_a_pick_on_a_deleted_marking_is_dropped(self):
        """A marking the player removed takes its per-feature picks with it (#3739)."""
        draft = self._draft()
        marking = draft.markings.create(body_region="face", kind="scar", name="Burn")
        draft.draft_data["distinctions"] = [self._entry(self.opener, marking=marking.pk)]
        draft.save()
        reconcile_offer_picks(draft)
        draft.refresh_from_db()
        assert len(draft.draft_data["distinctions"]) == 1

        marking.delete()
        reconcile_offer_picks(draft)
        draft.refresh_from_db()
        assert draft.draft_data["distinctions"] == []

    def test_opened_feature_traits_names_only_unlocked_rows(self):
        draft = self._draft(
            distinctions=[
                self._entry(self.opener, trait="hair_color"),
                self._entry(self.opener, marking=7),
            ]
        )
        assert opened_feature_traits(draft.draft_data) == {"hair_color"}


class FeatureSyncTests(TestCase):
    """The sync endpoint's per-feature validation (#3739)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="feat", password="pw")
        cls.draft = CharacterDraftFactory(account=cls.user)
        cls.trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        FormTraitOptionFactory(trait=cls.trait, name="black", display_name="Black")
        cls.opener = DistinctionFactory(
            name="Make It Distinctive",
            cost_per_rank=1,
            max_rank=1,
            taken_per_feature=True,
            opens_feature=True,
        )
        cls.alluring = DistinctionFactory(
            name="Alluring",
            cost_per_rank=2,
            max_rank=5,
            cg_max_rank=3,
            taken_per_feature=True,
            requires_feature_opened=True,
        )
        cls.plain = DistinctionFactory(name="Broad Shouldered")
        cls.opener_offer = DistinctionOfferFactory(
            distinction=cls.opener, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )
        cls.alluring_offer = DistinctionOfferFactory(
            distinction=cls.alluring, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )
        cls.plain_offer = DistinctionOfferFactory(
            distinction=cls.plain, chapter=OfferChapter.APPEARANCE
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _sync(self, entries):
        return self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {"distinctions": entries},
            format="json",
        )

    def _unlock(self, **extra):
        return {
            "id": self.opener.id,
            "rank": 1,
            "offer_id": self.opener_offer.id,
            "feature_trait": "hair_color",
            **extra,
        }

    def test_unlock_and_axis_on_one_feature(self):
        resp = self._sync(
            [
                self._unlock(),
                {
                    "id": self.alluring.id,
                    "rank": 3,
                    "offer_id": self.alluring_offer.id,
                    "feature_trait": "hair_color",
                },
            ]
        )
        assert resp.status_code == status.HTTP_200_OK
        entries = {e["distinction_id"]: e for e in resp.data["distinctions"]}
        assert entries[self.alluring.id]["rank"] == 3
        assert entries[self.alluring.id]["cost"] == 6
        # The source is the feature's own display name, not the generic opener word.
        assert entries[self.alluring.id]["sources"] == ["Hair Color"]

    def test_an_axis_without_its_unlock_is_refused(self):
        resp = self._sync(
            [
                {
                    "id": self.alluring.id,
                    "rank": 1,
                    "offer_id": self.alluring_offer.id,
                    "feature_trait": "hair_color",
                }
            ]
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_per_feature_pick_must_name_exactly_one_feature(self):
        assert self._sync([self._unlock(feature_trait="")]).status_code == 400
        both = self._unlock(feature_marking=5)
        assert self._sync([both]).status_code == 400

    def test_an_unknown_trait_is_refused(self):
        resp = self._sync([self._unlock(feature_trait="not_a_trait")])
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_another_drafts_marking_is_refused(self):
        other = CharacterDraftFactory(account=AccountFactory())
        marking = other.markings.create(body_region="face", kind="scar", name="Theirs")
        resp = self._sync([self._unlock(feature_trait="", feature_marking=marking.pk)])
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_plain_distinction_may_not_name_a_feature(self):
        resp = self._sync(
            [
                {
                    "id": self.plain.id,
                    "rank": 1,
                    "offer_id": self.plain_offer.id,
                    "feature_trait": "hair_color",
                }
            ]
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_an_axis_stops_at_the_cg_ceiling(self):
        """Rank 5 exists in play; character creation stops at 3 (#3739)."""
        resp = self._sync(
            [
                self._unlock(),
                {
                    "id": self.alluring.id,
                    "rank": 4,
                    "offer_id": self.alluring_offer.id,
                    "feature_trait": "hair_color",
                },
            ]
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_one_distinction_on_two_features_is_two_entries(self):
        FormTraitFactory(name="eye_color", display_name="Eye Color")
        resp = self._sync([self._unlock(), self._unlock(feature_trait="eye_color")])
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["distinctions"]) == 2
        assert sum(e["cost"] for e in resp.data["distinctions"]) == 2


class FeatureFinalizeTests(FinalizationTestMixin, TestCase):
    """From a distinctive feature in the draft to the rows a character carries."""

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="featurefinalize")
        self._setup_finalization_base(self, prefix="Feature Test", height_min=700, height_max=800)
        self.trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        self.option = FormTraitOptionFactory(trait=self.trait, name="black", display_name="Black")
        self.opener = DistinctionFactory(
            name="Make It Distinctive",
            cost_per_rank=1,
            max_rank=1,
            taken_per_feature=True,
            opens_feature=True,
        )
        self.alluring = DistinctionFactory(
            name="Alluring",
            cost_per_rank=2,
            max_rank=5,
            cg_max_rank=3,
            taken_per_feature=True,
            requires_feature_opened=True,
        )
        self.opener_offer = DistinctionOfferFactory(
            distinction=self.opener, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )
        self.alluring_offer = DistinctionOfferFactory(
            distinction=self.alluring, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )

    def _entry(self, distinction, offer, *, trait="", marking=0, rank=1):
        return build_distinction_entry(
            distinction, rank, offer=offer, feature_trait=trait, feature_marking=marking
        )

    def test_finalize_binds_each_pick_to_its_feature(self):
        """A trait pick lands on the FormTrait; a marking pick on the row it became."""
        from world.distinctions.models import CharacterDistinction

        draft = self._create_base_draft(first_name="Sable", stats=DEFAULT_STATS)
        marking = draft.markings.create(body_region="face", kind="scar", name="Burn")
        draft.draft_data["form_traits"] = {"hair_color": self.option.id}
        draft.draft_data["distinctions"] = [
            self._entry(self.opener, self.opener_offer, trait="hair_color"),
            self._entry(self.alluring, self.alluring_offer, trait="hair_color", rank=2),
            self._entry(self.opener, self.opener_offer, marking=marking.pk),
            self._entry(self.alluring, self.alluring_offer, marking=marking.pk, rank=1),
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        rows = CharacterDistinction.objects.filter(character=character.sheet_data)
        assert rows.count() == 4
        alluring = rows.filter(distinction=self.alluring)
        assert alluring.count() == 2
        on_trait = alluring.get(feature_trait=self.trait)
        assert on_trait.rank == 2
        assert on_trait.feature_marking_id is None
        on_marking = alluring.exclude(feature_trait=self.trait).get()
        # The draft marking id is gone by now; the row points at the FormMarking
        # ``_materialize_draft_markings`` created for it.
        assert on_marking.feature_marking.name == "Burn"
        assert on_marking.feature_trait_id is None

    def test_a_marking_pick_is_skipped_when_no_marking_was_made(self):
        """The GM finalize path creates no markings, so it grants no marking rows."""
        from world.distinctions.models import CharacterDistinction

        draft = self._create_base_draft(first_name="Ghost", stats=DEFAULT_STATS)
        draft.draft_data["distinctions"] = [
            self._entry(self.opener, self.opener_offer, marking=999),
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        assert not CharacterDistinction.objects.filter(
            character=character.sheet_data, distinction=self.opener
        ).exists()


class FeaturePaletteTests(TestCase):
    """A distinctive feature reaches past its species palette (#3739)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.species = Species.objects.create(name="Palette Test Species")
        cls.trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.allowed = FormTraitOptionFactory(trait=cls.trait, name="black", display_name="Black")
        cls.unnatural = FormTraitOptionFactory(
            trait=cls.trait, name="unnatural", display_name="Unnatural"
        )
        cls.trait.unnatural_option = cls.unnatural
        cls.trait.save(update_fields=["unnatural_option"])
        link = SpeciesFormTrait.objects.create(
            species=cls.species, trait=cls.trait, is_available_in_cg=True
        )
        link.allowed_options.set([cls.allowed])
        cls.opener = DistinctionFactory(
            name="Make It Distinctive", taken_per_feature=True, opens_feature=True
        )
        cls.opener_offer = DistinctionOfferFactory(
            distinction=cls.opener, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )

    def _draft(self, **data):
        return CharacterDraftFactory(
            account=self.account, selected_species=self.species, draft_data=data
        )

    def test_an_off_palette_option_is_an_error_without_the_unlock(self):
        draft = self._draft(form_traits={"hair_color": self.unnatural.id})
        errors = _get_form_trait_errors(draft)
        assert any("not available" in e for e in errors)

    def test_the_unlock_makes_every_option_legal_on_that_trait(self):
        draft = self._draft(
            form_traits={"hair_color": self.unnatural.id},
            distinctions=[
                build_distinction_entry(
                    self.opener, offer=self.opener_offer, feature_trait="hair_color"
                )
            ],
        )
        assert _get_form_trait_errors(draft) == []

    def test_the_unnatural_option_is_never_in_the_cg_palette(self):
        """It is reached through the widened list, never offered as a species value."""
        palette = get_cg_form_options(self.species)
        assert [o.name for o in palette[self.trait]] == ["black"]


class MarkingDeletionRefundTests(TestCase):
    """Deleting a marking refunds what was bought on it (#3739)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="markingrefund", password="pw")
        cls.draft = CharacterDraftFactory(account=cls.user)
        cls.opener = DistinctionFactory(
            name="Make It Distinctive",
            cost_per_rank=1,
            max_rank=1,
            taken_per_feature=True,
            opens_feature=True,
        )
        cls.opener_offer = DistinctionOfferFactory(
            distinction=cls.opener, chapter=OfferChapter.APPEARANCE, feature_rows=True
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_removing_the_marking_drops_the_picks_that_named_it(self):
        marking = self.draft.markings.create(body_region="face", kind="scar", name="Seam")
        self.draft.draft_data["distinctions"] = [
            build_distinction_entry(
                self.opener, offer=self.opener_offer, feature_marking=marking.pk
            )
        ]
        self.draft.save()

        resp = self.client.delete(f"/api/character-creation/draft-markings/{marking.pk}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

        self.draft.refresh_from_db()
        assert self.draft.draft_data["distinctions"] == []
