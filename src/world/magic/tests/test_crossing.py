"""Tests for thread crossing player choices (generalized, #1990).

Crossing options reference a ConditionTemplate (the buff) whose
ConditionModifierEffect rows define the stat modifiers. Tests verify
the handler creates pending offers, auto-resolves skipped crossings,
and the service resolves offers correctly.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.models.crossing import (
    CrossingChoice,
    CrossingOption,
    PendingCrossingOffer,
)


def _make_condition_template(name: str = "Test Buff", value: int = 5) -> object:
    """Create a ConditionTemplate with a ConditionModifierEffect for testing."""
    from world.conditions.factories import (
        ConditionModifierEffectFactory,
        ConditionTemplateFactory,
    )
    from world.mechanics.factories import ModifierTargetFactory

    template = ConditionTemplateFactory(name=name, default_duration_type="permanent")
    target = ModifierTargetFactory()
    ConditionModifierEffectFactory(
        condition=template,
        modifier_target=target,
        value=value,
    )
    return template


class CrossingOptionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import ResonanceFactory

        cls.resonance = ResonanceFactory()
        cls.condition_template = _make_condition_template()

    def test_clean_valid(self) -> None:
        opt = CrossingOption(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=3,
            name="Burning Vigor",
            condition_template=self.condition_template,
        )
        opt.clean()  # should not raise

    def test_clean_missing_condition_template(self) -> None:
        opt = CrossingOption(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=3,
            name="Bad",
            condition_template=None,  # type: ignore[arg-type]
        )
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            opt.clean()

    def test_is_default_unique_per_kind_resonance_level(self) -> None:
        from django.db import IntegrityError

        CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=3,
            name="Default",
            condition_template=self.condition_template,
            is_default=True,
        )
        with self.assertRaises(IntegrityError):
            CrossingOption.objects.create(
                target_kind=TargetKind.TRAIT,
                resonance=self.resonance,
                crossing_level=3,
                name="Also Default",
                condition_template=self.condition_template,
                is_default=True,
            )

    def test_is_default_allowed_for_different_target_kind(self) -> None:
        """Same resonance + level but different target_kind can each have a default."""
        CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=3,
            name="Trait Default",
            condition_template=self.condition_template,
            is_default=True,
        )
        # Should not raise — different target_kind
        CrossingOption.objects.create(
            target_kind=TargetKind.FACET,
            resonance=self.resonance,
            crossing_level=3,
            name="Facet Default",
            condition_template=self.condition_template,
            is_default=True,
        )


class CrossingChoiceModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            condition_template=cls.condition_template,
        )

    def test_create_choice(self) -> None:
        choice = CrossingChoice.objects.create(
            thread=self.thread,
            crossing_level=3,
            option=self.option,
        )
        self.assertEqual(choice.option, self.option)
        self.assertEqual(choice.crossing_level, 3)

    def test_unique_choice_per_thread_per_crossing(self) -> None:
        from django.db import IntegrityError

        CrossingChoice.objects.create(
            thread=self.thread,
            crossing_level=3,
            option=self.option,
        )
        with self.assertRaises(IntegrityError):
            CrossingChoice.objects.create(
                thread=self.thread,
                crossing_level=3,
                option=self.option,
            )


class PendingCrossingOfferModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
        )

    def test_create_offer(self) -> None:
        offer = PendingCrossingOffer.objects.create(
            thread=self.thread,
            crossing_level=3,
        )
        self.assertEqual(offer.crossing_level, 3)

    def test_one_pending_per_thread(self) -> None:
        from django.db import IntegrityError

        PendingCrossingOffer.objects.create(
            thread=self.thread,
            crossing_level=3,
        )
        with self.assertRaises(IntegrityError):
            PendingCrossingOffer.objects.create(
                thread=self.thread,
                crossing_level=6,
            )


class TraitCrossingHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=2,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            condition_template=cls.condition_template,
            is_default=True,
        )

    def test_crossing_creates_pending_offer(self) -> None:
        from world.magic.crossing.handlers import TraitCrossingHandler

        self.thread.level = 3
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=3)
            mock_beat.assert_called_once()
        self.assertTrue(PendingCrossingOffer.objects.filter(thread=self.thread).exists())

    def test_non_crossing_level_no_offer(self) -> None:
        from world.magic.crossing.handlers import TraitCrossingHandler

        self.thread.level = 4
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=3, new_level=4)
            mock_beat.assert_not_called()
        self.assertFalse(PendingCrossingOffer.objects.filter(thread=self.thread).exists())

    def test_multi_crossing_auto_resolves_lower(self) -> None:
        """Crossing from 2->11 auto-resolves 3 and 6, offers 11."""
        from world.magic.crossing.handlers import TraitCrossingHandler

        CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=6,
            name="Greater vigor",
            condition_template=self.condition_template,
            is_default=True,
        )
        CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=11,
            name="Master vigor",
            condition_template=self.condition_template,
            is_default=True,
        )
        self.thread.level = 11
        with patch("world.magic.crossing.handlers.execute_ceremony_beat"):
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=11)
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=6).exists()
        )
        self.assertTrue(
            PendingCrossingOffer.objects.filter(thread=self.thread, crossing_level=11).exists()
        )

    def test_no_crossing_in_range_noop(self) -> None:
        from world.magic.crossing.handlers import TraitCrossingHandler

        self.thread.level = 5
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = TraitCrossingHandler()
            handler.execute(thread=self.thread, starting_level=3, new_level=5)
            mock_beat.assert_not_called()


class FacetCrossingHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Facet, Thread

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.facet = Facet.objects.create(name="Spider")
        cls.thread = Thread.objects.create(
            owner=cls.sheet,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            resonance=cls.resonance,
            level=2,
        )
        cls.condition_template = _make_condition_template("Spider Aura", value=3)
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            crossing_level=3,
            name="Smirk of the Spidery Seductress",
            description="Your spider-facet aura enhances your allure.",
            condition_template=cls.condition_template,
            is_default=True,
        )

    def test_crossing_creates_pending_offer(self) -> None:
        from world.magic.crossing.handlers import FacetCrossingHandler

        self.thread.level = 3
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = FacetCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=3)
            mock_beat.assert_called_once()
        self.assertTrue(PendingCrossingOffer.objects.filter(thread=self.thread).exists())


class ResolveCrossingOfferTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=3,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            condition_template=cls.condition_template,
        )

    def setUp(self) -> None:
        self.offer = PendingCrossingOffer.objects.create(
            thread=self.thread,
            crossing_level=3,
        )

    def test_resolve_creates_choice(self) -> None:
        from world.magic.services.crossing import resolve_crossing_offer

        result = resolve_crossing_offer(self.offer, option=self.option)
        self.assertEqual(result.option_name, "Burning vigor")
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )
        self.assertFalse(PendingCrossingOffer.objects.filter(pk=self.offer.pk).exists())

    def test_resolve_wrong_resonance_raises_stale(self) -> None:
        from world.magic.exceptions import CrossingOfferStaleError
        from world.magic.factories import ResonanceFactory
        from world.magic.services.crossing import resolve_crossing_offer

        other_resonance = ResonanceFactory()
        wrong_option = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=other_resonance,
            crossing_level=3,
            name="Wrong",
            condition_template=self.condition_template,
        )
        with self.assertRaises(CrossingOfferStaleError):
            resolve_crossing_offer(self.offer, option=wrong_option)
        self.assertFalse(PendingCrossingOffer.objects.filter(pk=self.offer.pk).exists())

    def test_resolve_wrong_crossing_level_raises_stale(self) -> None:
        from world.magic.exceptions import CrossingOfferStaleError
        from world.magic.services.crossing import resolve_crossing_offer

        wrong_level_option = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=6,
            name="Wrong level",
            condition_template=self.condition_template,
        )
        with self.assertRaises(CrossingOfferStaleError):
            resolve_crossing_offer(self.offer, option=wrong_level_option)

    def test_resolve_wrong_target_kind_raises_stale(self) -> None:
        from world.magic.exceptions import CrossingOfferStaleError
        from world.magic.services.crossing import resolve_crossing_offer

        wrong_kind_option = CrossingOption.objects.create(
            target_kind=TargetKind.FACET,
            resonance=self.resonance,
            crossing_level=3,
            name="Wrong kind",
            condition_template=self.condition_template,
        )
        with self.assertRaises(CrossingOfferStaleError):
            resolve_crossing_offer(self.offer, option=wrong_kind_option)


class ResolveCrossingOfferActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=3,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            condition_template=cls.condition_template,
        )

    def setUp(self) -> None:
        self.offer = PendingCrossingOffer.objects.create(thread=self.thread, crossing_level=3)

    def test_action_resolves_offer(self) -> None:
        from actions.definitions.crossing import ResolveCrossingOfferAction

        actor = self.sheet.character
        action = ResolveCrossingOfferAction()
        result = action.run(actor=actor, offer=self.offer, option=self.option)
        self.assertTrue(result.success)
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )


# ---------------------------------------------------------------------------
# RELATIONSHIP_TRACK + RELATIONSHIP_CAPSTONE crossing tests (#1991)
# ---------------------------------------------------------------------------


class RelationshipTrackCrossingHandlerTests(TestCase):
    """RELATIONSHIP_TRACK thread crossing — player-chosen bond expression."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_track_thread=True,
            level=2,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning devotion",
            description="Your fire-resonant bond blazes with protective warmth.",
            condition_template=cls.condition_template,
            is_default=True,
        )

    def test_crossing_creates_pending_offer(self) -> None:
        from world.magic.crossing.handlers import RelationshipTrackCrossingHandler

        self.thread.level = 3
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = RelationshipTrackCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=3)
            mock_beat.assert_called_once()
        self.assertTrue(PendingCrossingOffer.objects.filter(thread=self.thread).exists())

    def test_non_crossing_level_no_offer(self) -> None:
        from world.magic.crossing.handlers import RelationshipTrackCrossingHandler

        self.thread.level = 4
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = RelationshipTrackCrossingHandler()
            handler.execute(thread=self.thread, starting_level=3, new_level=4)
            mock_beat.assert_not_called()
        self.assertFalse(PendingCrossingOffer.objects.filter(thread=self.thread).exists())

    def test_multi_crossing_auto_resolves_lower(self) -> None:
        """Crossing from 2->11 auto-resolves 3 and 6, offers 11."""
        from world.magic.crossing.handlers import RelationshipTrackCrossingHandler

        CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=self.resonance,
            crossing_level=6,
            name="Greater devotion",
            condition_template=self.condition_template,
            is_default=True,
        )
        CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=self.resonance,
            crossing_level=11,
            name="Master devotion",
            condition_template=self.condition_template,
            is_default=True,
        )
        self.thread.level = 11
        with patch("world.magic.crossing.handlers.execute_ceremony_beat"):
            handler = RelationshipTrackCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=11)
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=6).exists()
        )
        self.assertTrue(
            PendingCrossingOffer.objects.filter(thread=self.thread, crossing_level=11).exists()
        )


class RelationshipCapstoneCrossingHandlerTests(TestCase):
    """RELATIONSHIP_CAPSTONE thread crossing — player-chosen bond expression."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_capstone_thread=True,
            level=2,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=cls.resonance,
            crossing_level=3,
            name="Eternal bond",
            description="Your capstone bond deepens into permanence.",
            condition_template=cls.condition_template,
            is_default=True,
        )

    def test_crossing_creates_pending_offer(self) -> None:
        from world.magic.crossing.handlers import RelationshipCapstoneCrossingHandler

        self.thread.level = 3
        with patch("world.magic.crossing.handlers.execute_ceremony_beat") as mock_beat:
            handler = RelationshipCapstoneCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=3)
            mock_beat.assert_called_once()
        self.assertTrue(PendingCrossingOffer.objects.filter(thread=self.thread).exists())

    def test_multi_crossing_auto_resolves_lower(self) -> None:
        """Crossing from 2->11 auto-resolves 3 and 6, offers 11."""
        from world.magic.crossing.handlers import RelationshipCapstoneCrossingHandler

        CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.resonance,
            crossing_level=6,
            name="Greater bond",
            condition_template=self.condition_template,
            is_default=True,
        )
        CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.resonance,
            crossing_level=11,
            name="Master bond",
            condition_template=self.condition_template,
            is_default=True,
        )
        self.thread.level = 11
        with patch("world.magic.crossing.handlers.execute_ceremony_beat"):
            handler = RelationshipCapstoneCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=11)
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=3).exists()
        )
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.thread, crossing_level=6).exists()
        )
        self.assertTrue(
            PendingCrossingOffer.objects.filter(thread=self.thread, crossing_level=11).exists()
        )


class RelationshipCrossingResolutionTests(TestCase):
    """resolve_crossing_offer works for RELATIONSHIP_TRACK and RELATIONSHIP_CAPSTONE."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.track_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_track_thread=True,
            level=3,
        )
        cls.capstone_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_capstone_thread=True,
            level=3,
        )
        cls.condition_template = _make_condition_template()
        cls.track_option = CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning devotion",
            condition_template=cls.condition_template,
        )
        cls.capstone_option = CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=cls.resonance,
            crossing_level=3,
            name="Eternal bond",
            condition_template=cls.condition_template,
        )

    def test_resolve_track_offer(self) -> None:
        from world.magic.services.crossing import resolve_crossing_offer

        offer = PendingCrossingOffer.objects.create(
            thread=self.track_thread,
            crossing_level=3,
        )
        result = resolve_crossing_offer(offer, option=self.track_option)
        self.assertEqual(result.option_name, "Burning devotion")
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.track_thread, crossing_level=3).exists()
        )
        self.assertFalse(PendingCrossingOffer.objects.filter(pk=offer.pk).exists())

    def test_resolve_capstone_offer(self) -> None:
        from world.magic.services.crossing import resolve_crossing_offer

        offer = PendingCrossingOffer.objects.create(
            thread=self.capstone_thread,
            crossing_level=3,
        )
        result = resolve_crossing_offer(offer, option=self.capstone_option)
        self.assertEqual(result.option_name, "Eternal bond")
        self.assertTrue(
            CrossingChoice.objects.filter(thread=self.capstone_thread, crossing_level=3).exists()
        )
        self.assertFalse(PendingCrossingOffer.objects.filter(pk=offer.pk).exists())

    def test_resolve_wrong_kind_raises_stale(self) -> None:
        """Resolving a track offer with a capstone option raises StaleError."""
        from world.magic.exceptions import CrossingOfferStaleError
        from world.magic.services.crossing import resolve_crossing_offer

        offer = PendingCrossingOffer.objects.create(
            thread=self.track_thread,
            crossing_level=3,
        )
        with self.assertRaises(CrossingOfferStaleError):
            resolve_crossing_offer(offer, option=self.capstone_option)
        self.assertFalse(PendingCrossingOffer.objects.filter(pk=offer.pk).exists())


class SoulTetherNonInterferenceTests(TestCase):
    """RELATIONSHIP_CAPSTONE crossing does not touch Soul Tether Hollow state."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_capstone_thread=True,
            level=2,
            hollow_current=5,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=cls.resonance,
            crossing_level=3,
            name="Deepened hollow",
            condition_template=cls.condition_template,
            is_default=True,
        )

    def test_crossing_does_not_change_hollow_current(self) -> None:
        """The crossing ceremony must not touch hollow_current."""
        from world.magic.crossing.handlers import RelationshipCapstoneCrossingHandler

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 5)

        self.thread.level = 3
        with patch("world.magic.crossing.handlers.execute_ceremony_beat"):
            handler = RelationshipCapstoneCrossingHandler()
            handler.execute(thread=self.thread, starting_level=2, new_level=3)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 5)


class AnchorLabelTests(TestCase):
    """_anchor_label_for resolves relationship anchors correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.track_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_track_thread=True,
            level=2,
        )
        cls.capstone_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_capstone_thread=True,
            level=2,
        )

    def test_track_anchor_label_includes_partner_and_track(self) -> None:
        from world.magic.crossing.handlers import _anchor_label_for

        label = _anchor_label_for(self.track_thread)
        self.assertIn("bond with", label)
        track = self.track_thread.target_relationship_track
        self.assertIn(track.track.name, label)

    def test_capstone_anchor_label_includes_title_and_partner(self) -> None:
        from world.magic.crossing.handlers import _anchor_label_for

        label = _anchor_label_for(self.capstone_thread)
        self.assertIn("capstone", label)
        cap = self.capstone_thread.target_capstone
        self.assertIn(cap.title, label)
