"""Tests for codex models."""

from django.db import IntegrityError
from django.test import TestCase

from world.action_points.factories import ActionPointPoolFactory
from world.action_points.models import ActionPointPool
from world.codex.factories import (
    CharacterCodexKnowledgeFactory,
    CodexCategoryFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
    CodexTeachingOfferFactory,
)
from world.codex.models import (
    CharacterCodexKnowledge,
    CodexCategory,
    CodexEntry,
    CodexSubject,
    CodexTeachingOffer,
)
from world.roster.factories import RosterTenureFactory


class CodexCategoryModelTests(TestCase):
    """Tests for CodexCategory model."""

    def test_str_representation(self):
        """CodexCategory string shows name."""
        category = CodexCategoryFactory(name="Arx Lore")
        assert str(category) == "Arx Lore"

    def test_name_unique(self):
        """CodexCategory names must be unique."""
        CodexCategoryFactory(name="Unique Category")
        with self.assertRaises(IntegrityError):
            CodexCategory.objects.create(name="Unique Category")

    def test_ordering_by_display_order_then_name(self):
        """Categories are ordered by display_order then name."""
        cat3 = CodexCategoryFactory(name="Charlie", display_order=2)
        cat1 = CodexCategoryFactory(name="Alpha", display_order=1)
        cat2 = CodexCategoryFactory(name="Beta", display_order=1)

        categories = list(CodexCategory.objects.all())
        assert categories[0] == cat1  # Alpha (order=1)
        assert categories[1] == cat2  # Beta (order=1)
        assert categories[2] == cat3  # Charlie (order=2)


class CodexSubjectModelTests(TestCase):
    """Tests for CodexSubject model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.category = CodexCategoryFactory(name="Test Category")

    def test_str_top_level_subject(self):
        """Top-level subject string shows category and name."""
        subject = CodexSubjectFactory(
            category=self.category,
            parent=None,
            name="The Shroud",
        )
        assert "Test Category" in str(subject)
        assert "The Shroud" in str(subject)

    def test_str_nested_subject(self):
        """Nested subject string shows parent and name."""
        parent = CodexSubjectFactory(
            category=self.category,
            name="The Shroud",
        )
        child = CodexSubjectFactory(
            category=self.category,
            parent=parent,
            name="The Flickering",
        )
        assert "The Shroud" in str(child)
        assert "The Flickering" in str(child)

    def test_unique_name_per_category_parent(self):
        """Subject names must be unique within category and parent (non-null)."""
        parent = CodexSubjectFactory(category=self.category, name="Parent")
        CodexSubjectFactory(category=self.category, parent=parent, name="Unique")
        with self.assertRaises(IntegrityError):
            CodexSubject.objects.create(category=self.category, parent=parent, name="Unique")

    def test_same_name_different_parent(self):
        """Same name allowed with different parent."""
        parent1 = CodexSubjectFactory(category=self.category, name="Parent1")
        parent2 = CodexSubjectFactory(category=self.category, name="Parent2")
        CodexSubjectFactory(category=self.category, parent=parent1, name="Child")
        child2 = CodexSubjectFactory(category=self.category, parent=parent2, name="Child")
        assert child2.name == "Child"


class CodexEntryModelTests(TestCase):
    """Tests for CodexEntry model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.subject = CodexSubjectFactory()

    def test_str_representation(self):
        """CodexEntry string shows name."""
        entry = CodexEntryFactory(subject=self.subject, name="Secret of the Shroud")
        assert str(entry) == "Secret of the Shroud"

    def test_unique_name_per_subject(self):
        """Entry names must be unique within subject."""
        CodexEntryFactory(subject=self.subject, name="Unique Entry")
        with self.assertRaises(IntegrityError):
            CodexEntry.objects.create(
                subject=self.subject,
                name="Unique Entry",
                content="Content",
            )

    def test_prerequisites_can_be_set(self):
        """Entries can have prerequisites."""
        prereq = CodexEntryFactory(subject=self.subject, name="Prerequisite")
        entry = CodexEntryFactory(subject=self.subject, name="Advanced")
        entry.prerequisites.add(prereq)

        assert prereq in entry.prerequisites.all()
        assert entry in prereq.unlocks.all()

    def test_default_costs(self):
        """Entries have default cost values."""
        entry = CodexEntry.objects.create(
            subject=self.subject,
            name="Test Entry",
            content="Test content",
        )
        assert entry.share_cost == 5
        assert entry.learn_cost == 5
        assert entry.learn_difficulty == 10
        assert entry.learn_threshold == 10


class CharacterCodexKnowledgeModelTests(TestCase):
    """Tests for CharacterCodexKnowledge model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.tenure = RosterTenureFactory()
        cls.roster_entry = cls.tenure.roster_entry
        cls.entry = CodexEntryFactory(learn_threshold=10)

    def test_str_representation(self):
        """CharacterCodexKnowledge string shows roster_entry, entry, and status."""
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry,
            status=CharacterCodexKnowledge.Status.UNCOVERED,
        )
        assert self.entry.name in str(knowledge)
        assert "uncovered" in str(knowledge)

    def test_unique_roster_entry_entry(self):
        """Character can only have one knowledge entry per CodexEntry."""
        CharacterCodexKnowledgeFactory(roster_entry=self.roster_entry, entry=self.entry)
        with self.assertRaises(IntegrityError):
            CharacterCodexKnowledge.objects.create(
                roster_entry=self.roster_entry,
                entry=self.entry,
            )

    def test_add_progress_increments(self):
        """add_progress increments learning_progress."""
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry,
            learning_progress=0,
        )
        knowledge.add_progress(5)
        knowledge.refresh_from_db()
        assert knowledge.learning_progress == 5

    def test_add_progress_completes_learning(self):
        """add_progress completes learning when threshold reached."""
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry,
            learning_progress=5,
        )
        result = knowledge.add_progress(5)  # Reaches threshold of 10
        knowledge.refresh_from_db()

        assert result is True
        assert knowledge.status == CharacterCodexKnowledge.Status.KNOWN
        assert knowledge.learned_at is not None

    def test_add_progress_does_not_complete_below_threshold(self):
        """add_progress does not complete if below threshold."""
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry,
            learning_progress=0,
        )
        result = knowledge.add_progress(5)
        knowledge.refresh_from_db()

        assert result is False
        assert knowledge.status == CharacterCodexKnowledge.Status.UNCOVERED

    def test_add_progress_on_known_does_nothing(self):
        """add_progress on already known entry returns False."""
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        result = knowledge.add_progress(5)
        assert result is False

    def test_is_complete_true_when_known(self):
        """is_complete returns True when status is KNOWN."""
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        assert knowledge.is_complete() is True

    def test_is_complete_false_when_uncovered(self):
        """is_complete returns False when status is UNCOVERED."""
        knowledge = CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.entry,
            status=CharacterCodexKnowledge.Status.UNCOVERED,
        )
        assert knowledge.is_complete() is False


class CodexTeachingOfferTestCase(TestCase):
    """Base test case for CodexTeachingOffer tests."""

    def setUp(self):
        """Clear caches."""
        ActionPointPool.flush_instance_cache()


class CodexTeachingOfferModelTests(CodexTeachingOfferTestCase):
    """Tests for CodexTeachingOffer model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.teacher = RosterTenureFactory()
        cls.entry = CodexEntryFactory()

    def test_str_representation(self):
        """CodexTeachingOffer string shows teacher and entry."""
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )
        assert self.entry.name in str(offer)


class CodexTeachingOfferCancelTests(CodexTeachingOfferTestCase):
    """Tests for CodexTeachingOffer.cancel method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.teacher = RosterTenureFactory()
        cls.entry = CodexEntryFactory()

    def test_cancel_restores_banked_ap(self):
        """cancel restores banked AP to teacher."""
        pool = ActionPointPoolFactory(
            character=self.teacher.character,
            current=100,
            maximum=200,
            banked=50,
        )
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
            banked_ap=50,
        )

        restored = offer.cancel()

        pool.refresh_from_db()
        assert restored == 50
        assert pool.current == 150
        assert pool.banked == 0

    def test_cancel_deletes_offer(self):
        """cancel deletes the offer."""
        ActionPointPoolFactory(character=self.teacher.character, banked=50)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
            banked_ap=50,
        )
        offer_id = offer.id

        offer.cancel()

        assert not CodexTeachingOffer.objects.filter(id=offer_id).exists()


class CodexTeachingOfferCanAcceptTests(CodexTeachingOfferTestCase):
    """Tests for CodexTeachingOffer.can_accept method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.teacher = RosterTenureFactory()
        cls.learner = RosterTenureFactory()
        cls.entry = CodexEntryFactory(learn_cost=10)

    def test_cannot_accept_own_offer(self):
        """Teacher cannot accept their own offer."""
        ActionPointPoolFactory(character=self.teacher.character, current=100)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        can_accept, reason = offer.can_accept(self.teacher)

        assert can_accept is False
        assert "own" in reason.lower()

    def test_cannot_accept_if_already_known(self):
        """Cannot accept if character already knows the entry."""
        ActionPointPoolFactory(character=self.learner.character, current=100)
        CharacterCodexKnowledgeFactory(
            roster_entry=self.learner.roster_entry,
            entry=self.entry,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        can_accept, reason = offer.can_accept(self.learner)

        assert can_accept is False
        assert "already know" in reason.lower()

    def test_cannot_accept_if_already_learning(self):
        """Cannot accept if character is already learning the entry."""
        ActionPointPoolFactory(character=self.learner.character, current=100)
        CharacterCodexKnowledgeFactory(
            roster_entry=self.learner.roster_entry,
            entry=self.entry,
            status=CharacterCodexKnowledge.Status.UNCOVERED,
        )
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        can_accept, reason = offer.can_accept(self.learner)

        assert can_accept is False
        assert "already learning" in reason.lower()

    def test_cannot_accept_without_prerequisites(self):
        """Cannot accept if missing prerequisites."""
        prereq = CodexEntryFactory()
        self.entry.prerequisites.add(prereq)
        ActionPointPoolFactory(character=self.learner.character, current=100)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        can_accept, reason = offer.can_accept(self.learner)

        assert can_accept is False
        assert "prerequisite" in reason.lower()

    def test_can_accept_with_prerequisites_met(self):
        """Can accept if character's prerequisites are met."""
        prereq = CodexEntryFactory()
        self.entry.prerequisites.add(prereq)
        ActionPointPoolFactory(character=self.learner.character, current=100)
        CharacterCodexKnowledgeFactory(
            roster_entry=self.learner.roster_entry,
            entry=prereq,
            status=CharacterCodexKnowledge.Status.KNOWN,
        )
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        can_accept, reason = offer.can_accept(self.learner)

        assert can_accept is True
        assert reason == ""

    def test_cannot_accept_without_ap(self):
        """Cannot accept without sufficient AP."""
        # Less than learn_cost=10
        ActionPointPoolFactory(character=self.learner.character, current=5)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        can_accept, reason = offer.can_accept(self.learner)

        assert can_accept is False
        assert "action points" in reason.lower()

    def test_can_accept_valid_offer(self):
        """Can accept a valid offer."""
        ActionPointPoolFactory(character=self.learner.character, current=100)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        can_accept, reason = offer.can_accept(self.learner)

        assert can_accept is True
        assert reason == ""


class CodexTeachingOfferAcceptTests(CodexTeachingOfferTestCase):
    """Tests for CodexTeachingOffer.accept method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.teacher = RosterTenureFactory()
        cls.learner = RosterTenureFactory()
        cls.entry = CodexEntryFactory(learn_cost=10)

    def test_accept_creates_knowledge(self):
        """accept creates a CharacterCodexKnowledge entry."""
        ActionPointPoolFactory(character=self.teacher.character, banked=50)
        ActionPointPoolFactory(character=self.learner.character, current=100)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
            banked_ap=50,
        )

        knowledge = offer.accept(self.learner)

        assert knowledge.roster_entry == self.learner.roster_entry
        assert knowledge.entry == self.entry
        assert knowledge.status == CharacterCodexKnowledge.Status.UNCOVERED
        assert knowledge.learned_from == self.teacher

    def test_accept_spends_learner_ap(self):
        """accept spends learner's AP."""
        ActionPointPoolFactory(character=self.teacher.character, banked=50)
        pool = ActionPointPoolFactory(character=self.learner.character, current=100)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
            banked_ap=50,
        )

        offer.accept(self.learner)

        pool.refresh_from_db()
        assert pool.current == 90  # 100 - 10 (learn_cost)

    def test_accept_consumes_teacher_banked_ap(self):
        """accept consumes teacher's banked AP."""
        pool = ActionPointPoolFactory(
            character=self.teacher.character,
            current=100,
            banked=50,
        )
        ActionPointPoolFactory(character=self.learner.character, current=100)
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
            banked_ap=50,
        )

        offer.accept(self.learner)

        pool.refresh_from_db()
        assert pool.banked == 0  # 50 consumed

    def test_accept_raises_on_invalid(self):
        """accept raises ValueError if cannot accept."""
        ActionPointPoolFactory(character=self.learner.character, current=5)  # Insufficient
        offer = CodexTeachingOfferFactory(
            teacher=self.teacher,
            entry=self.entry,
        )

        with self.assertRaises(ValueError) as ctx:
            offer.accept(self.learner)

        assert "action points" in str(ctx.exception).lower()
