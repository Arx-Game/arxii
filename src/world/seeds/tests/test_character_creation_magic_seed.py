"""Tests for the Tradition Training distinction + ModifierTarget wiring (#2426 Task 7).

``wire_starting_technique_picks_target()`` seeds the ``starting_technique_picks``
ModifierTarget (in the ``character_creation`` ModifierCategory) that
``CharacterDraft.starting_technique_picks`` sums a distinction bonus against.
``ensure_tradition_training_distinction()`` seeds the "Tradition Training"
Distinction (+1 pick per rank, max_rank=2) targeting that row.

Also covers ``seed_beginning_traditions()`` (#2426 whole-branch-review fix): the
join-row seeder that links every seeded ``Beginnings`` to the magic-seeded
"Unbound" Tradition, without which the CG Tradition step is empty on a fresh
Big-Button-only DB.
"""

from django.test import TestCase

from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    STARTING_TECHNIQUE_PICKS_TARGET,
)
from world.character_creation.factories import BeginningsFactory, CharacterDraftFactory
from world.seeds.character_creation import (
    ensure_tradition_training_distinction,
    seed_beginning_traditions,
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


class SeedBeginningTraditionsTests(TestCase):
    """Tests for ``seed_beginning_traditions()`` (#2426 whole-branch-review fix).

    Without this seeder, no ``BeginningTradition`` rows ever exist on a fresh
    Big-Button-only DB, so the CG Tradition step is empty for every Beginning —
    even the tradition-agnostic Unbound path. See the strengthened
    ``test_playable_slice.py::TestSeededCharacterCreation`` assertions for the
    end-to-end (real-endpoint) proof; these tests cover the seeder function
    directly: creation, idempotency, and the defensive missing-Tradition skip.
    """

    def test_creates_beginning_tradition_for_unbound(self) -> None:
        from world.character_creation.models import BeginningTradition
        from world.magic.factories import TraditionFactory

        TraditionFactory(name="Unbound")
        beginning = BeginningsFactory()

        seed_beginning_traditions()

        bt = BeginningTradition.objects.get(beginning=beginning, tradition__name="Unbound")
        self.assertIsNone(bt.required_distinction)

    def test_creates_a_row_for_every_beginning(self) -> None:
        from world.character_creation.models import BeginningTradition
        from world.magic.factories import TraditionFactory

        TraditionFactory(name="Unbound")
        beginnings = [BeginningsFactory() for _ in range(3)]

        seed_beginning_traditions()

        for beginning in beginnings:
            self.assertTrue(
                BeginningTradition.objects.filter(
                    beginning=beginning, tradition__name="Unbound"
                ).exists(),
                f"expected a seeded BeginningTradition for {beginning}",
            )

    def test_arx_beginnings_link_the_arx_traditions_when_present(self) -> None:
        """Arx beginnings get Vigil/Metallic/Fractals links; others get Unbound only.

        The three Arx Tradition rows are lore-repo fixture content, so the
        seeder links whichever exist rather than creating them (beginnings/arx.md).
        """
        from world.character_creation.factories import StartingAreaFactory
        from world.character_creation.models import BeginningTradition
        from world.magic.factories import TraditionFactory

        TraditionFactory(name="Unbound")
        TraditionFactory(name="The Vigil")
        TraditionFactory(name="Metallic Order")
        arx_area = StartingAreaFactory(name="Arx City")
        caretaker = BeginningsFactory(name="Caretaker", starting_area=arx_area)
        elsewhere = BeginningsFactory()

        seed_beginning_traditions()

        linked = set(
            BeginningTradition.objects.filter(beginning=caretaker).values_list(
                "tradition__name", flat=True
            )
        )
        self.assertEqual(linked, {"Unbound", "The Vigil", "Metallic Order"})
        elsewhere_linked = set(
            BeginningTradition.objects.filter(beginning=elsewhere).values_list(
                "tradition__name", flat=True
            )
        )
        self.assertEqual(elsewhere_linked, {"Unbound"})

    def test_idempotent_second_call_creates_no_duplicates(self) -> None:
        from world.character_creation.models import BeginningTradition
        from world.magic.factories import TraditionFactory

        TraditionFactory(name="Unbound")
        BeginningsFactory()

        seed_beginning_traditions()
        seed_beginning_traditions()

        self.assertEqual(
            BeginningTradition.objects.filter(tradition__name="Unbound").count(),
            1,
        )

    def test_does_not_overwrite_a_staff_adjusted_row(self) -> None:
        """A staff-set required_distinction on the seeded row survives a re-run."""
        from world.character_creation.models import BeginningTradition
        from world.distinctions.factories import DistinctionFactory
        from world.magic.factories import TraditionFactory

        TraditionFactory(name="Unbound")
        BeginningsFactory()
        seed_beginning_traditions()

        distinction = DistinctionFactory()
        bt = BeginningTradition.objects.get(tradition__name="Unbound")
        bt.required_distinction = distinction
        bt.save(update_fields=["required_distinction"])

        seed_beginning_traditions()

        # BeginningTradition is a SharedMemoryModel (idmapper) — re-fetch via
        # .values() rather than .get() so a stale cached instance can't mask a
        # regression (mirrors EnsureTraditionTrainingDistinctionTests above).
        db_value = (
            BeginningTradition.objects.filter(tradition__name="Unbound")
            .values("required_distinction_id")
            .get()
        )
        self.assertEqual(db_value["required_distinction_id"], distinction.id)

    def test_skips_silently_when_unbound_tradition_not_seeded(self) -> None:
        """Defensive skip (logged) when the magic cluster hasn't run yet."""
        from world.character_creation.models import BeginningTradition

        BeginningsFactory()

        seed_beginning_traditions()

        self.assertEqual(BeginningTradition.objects.count(), 0)
