"""Tests for the Tradition Training distinction + ModifierTarget wiring (#2426 Task 7).

``wire_starting_technique_picks_target()`` seeds the ``starting_technique_picks``
ModifierTarget (in the ``character_creation`` ModifierCategory) that
``CharacterDraft.starting_technique_picks`` sums a distinction bonus against.
``ensure_tradition_training_distinction()`` seeds the "Tradition Training"
Distinction (+1 pick per rank, max_rank=2) targeting that row.
"""

from django.test import TestCase

from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    STARTING_TECHNIQUE_PICKS_TARGET,
)
from world.character_creation.factories import CharacterDraftFactory
from world.seeds.character_creation import (
    ensure_tradition_training_distinction,
    wire_starting_technique_picks_target,
)


class WireStartingTechniquePicksTargetTests(TestCase):
    """First-call + idempotency assertions for the ModifierTarget row."""

    def test_creates_modifier_target_in_character_creation_category(self) -> None:
        from world.mechanics.models import ModifierCategory, ModifierTarget

        target = wire_starting_technique_picks_target()

        self.assertEqual(target.name, STARTING_TECHNIQUE_PICKS_TARGET)
        self.assertEqual(target.category.name, CG_MODIFIER_CATEGORY)
        self.assertEqual(ModifierCategory.objects.filter(name=CG_MODIFIER_CATEGORY).count(), 1)
        self.assertEqual(
            ModifierTarget.objects.filter(
                name=STARTING_TECHNIQUE_PICKS_TARGET, category__name=CG_MODIFIER_CATEGORY
            ).count(),
            1,
        )

    def test_idempotent_second_call_returns_same_row(self) -> None:
        first = wire_starting_technique_picks_target()
        second = wire_starting_technique_picks_target()

        self.assertEqual(first.pk, second.pk)


class EnsureTraditionTrainingDistinctionTests(TestCase):
    """First-call, idempotency, edit-preservation, and end-to-end wiring."""

    def test_creates_distinction_with_expected_shape(self) -> None:
        from world.distinctions.models import Distinction, DistinctionEffect

        ensure_tradition_training_distinction()

        distinction = Distinction.objects.get(slug="tradition-training")
        self.assertEqual(distinction.name, "Tradition Training")
        self.assertEqual(distinction.max_rank, 2)
        self.assertEqual(distinction.cost_per_rank, 1)
        self.assertEqual(distinction.category.slug, "arcane")

        effect = DistinctionEffect.objects.get(distinction=distinction)
        self.assertEqual(effect.target.name, STARTING_TECHNIQUE_PICKS_TARGET)
        self.assertEqual(effect.value_per_rank, 1)

    def test_idempotent_second_call_creates_no_duplicates(self) -> None:
        from world.distinctions.models import Distinction, DistinctionEffect

        ensure_tradition_training_distinction()
        ensure_tradition_training_distinction()

        self.assertEqual(Distinction.objects.filter(slug="tradition-training").count(), 1)
        self.assertEqual(
            DistinctionEffect.objects.filter(distinction__slug="tradition-training").count(), 1
        )

    def test_staff_edit_to_distinction_survives_rerun(self) -> None:
        from world.distinctions.models import Distinction

        ensure_tradition_training_distinction()
        Distinction.objects.filter(slug="tradition-training").update(
            description="staff-edited description"
        )

        ensure_tradition_training_distinction()

        db_value = Distinction.objects.filter(slug="tradition-training").values("description").get()
        self.assertEqual(db_value["description"], "staff-edited description")

    def test_draft_starting_technique_picks_reflects_seeded_distinction(self) -> None:
        """End-to-end: a draft holding the real seeded distinction gets +1 per rank."""
        from world.distinctions.models import Distinction

        ensure_tradition_training_distinction()
        distinction = Distinction.objects.get(slug="tradition-training")

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 2}]}
        )

        self.assertEqual(draft.starting_technique_picks, 3)
