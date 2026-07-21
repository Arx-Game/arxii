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

Also covers ``wire_magic_learning_ap_cost_target()`` + ``ensure_unbound_drawback_
distinction()`` (#2442): the "Unbound" drawback distinction (+50% AP surcharge on
magic-learning activities) now wired onto Unbound's own ``BeginningTradition`` rows
via ``required_distinction`` — see ``world.magic.tests.test_gift_acquisition_service``
and ``world.npc_services.tests.test_train_offers`` for the surcharge's live-play read,
and ``world.character_creation.tests.test_traditions.UnboundTraditionSelectionTests``
for the CG select-tradition endpoint behavior this gate produces.
"""

from django.test import TestCase

from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    SHROUDWATCH_ACADEMY_NAME,
    STARTING_TECHNIQUE_PICKS_TARGET,
)
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    RealmFactory,
    StartingAreaFactory,
)
from world.seeds.character_creation import (
    ensure_orphaned_tradition_distinction,
    ensure_shroudwatch_academy,
    ensure_somehow_always_broke_distinction,
    ensure_tradition_training_distinction,
    ensure_unbound_drawback_distinction,
    seed_beginning_traditions,
    seed_metallic_order_tradition,
    wire_magic_learning_ap_cost_target,
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


class WireMagicLearningApCostTargetTests(TestCase):
    """First-call + idempotency assertions for the 'magic_learning_ap_cost'
    ModifierTarget row (#2442)."""

    def test_creates_modifier_target_in_magic_category(self) -> None:
        from world.magic.constants import (
            MAGIC_LEARNING_AP_COST_TARGET_NAME,
            MAGIC_MODIFIER_CATEGORY_NAME,
        )
        from world.mechanics.models import ModifierCategory, ModifierTarget

        target = wire_magic_learning_ap_cost_target()

        self.assertEqual(target.name, MAGIC_LEARNING_AP_COST_TARGET_NAME)
        self.assertEqual(target.category.name, MAGIC_MODIFIER_CATEGORY_NAME)
        self.assertEqual(
            ModifierCategory.objects.filter(name=MAGIC_MODIFIER_CATEGORY_NAME).count(), 1
        )
        self.assertEqual(
            ModifierTarget.objects.filter(
                name=MAGIC_LEARNING_AP_COST_TARGET_NAME,
                category__name=MAGIC_MODIFIER_CATEGORY_NAME,
            ).count(),
            1,
        )

    def test_idempotent_second_call_returns_same_row(self) -> None:
        first = wire_magic_learning_ap_cost_target()
        second = wire_magic_learning_ap_cost_target()

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


class EnsureUnboundDrawbackDistinctionTests(TestCase):
    """First-call, idempotency, edit-preservation, and the +50% AP effect
    shape for the 'Unbound' drawback distinction (#2442)."""

    def test_creates_distinction_with_expected_shape(self) -> None:
        from world.distinctions.models import Distinction, DistinctionEffect
        from world.magic.constants import MAGIC_LEARNING_AP_COST_TARGET_NAME

        ensure_unbound_drawback_distinction()

        distinction = Distinction.objects.get(slug="unbound")
        self.assertEqual(distinction.name, "Unbound")
        self.assertEqual(distinction.max_rank, 1)
        self.assertEqual(
            distinction.cost_per_rank,
            -2,
            "Mirrors ensure_orphaned_tradition_distinction's -2 refund convention.",
        )
        self.assertEqual(distinction.category.slug, "arcane")

        effect = DistinctionEffect.objects.get(distinction=distinction)
        self.assertEqual(effect.target.name, MAGIC_LEARNING_AP_COST_TARGET_NAME)
        self.assertEqual(effect.value_per_rank, 50)

    def test_idempotent_second_call_creates_no_duplicates(self) -> None:
        from world.distinctions.models import Distinction, DistinctionEffect

        ensure_unbound_drawback_distinction()
        ensure_unbound_drawback_distinction()

        self.assertEqual(Distinction.objects.filter(slug="unbound").count(), 1)
        self.assertEqual(DistinctionEffect.objects.filter(distinction__slug="unbound").count(), 1)

    def test_staff_edit_to_distinction_survives_rerun(self) -> None:
        from world.distinctions.models import Distinction

        ensure_unbound_drawback_distinction()
        Distinction.objects.filter(slug="unbound").update(description="staff-edited description")

        ensure_unbound_drawback_distinction()

        db_value = Distinction.objects.filter(slug="unbound").values("description").get()
        self.assertEqual(db_value["description"], "staff-edited description")


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
        # #2442: Unbound now gates on its own "Unbound" drawback distinction —
        # was required_distiction=None pre-#2442 (see EnsureUnboundDrawbackDistinctionTests
        # for the drawback row's own shape).
        self.assertIsNotNone(bt.required_distinction)
        self.assertEqual(bt.required_distinction.slug, "unbound")

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


class EnsureShroudwatchAcademyTests(TestCase):
    """Tests for ``ensure_shroudwatch_academy()`` (#2428).

    The Academy org resolved-by-name at CG-finalize time to create the
    Unbound entrance obligation / sponsor-settled row (see
    ``world.character_creation.services._finalize_academy_entrance_obligation``
    and ``AcademyEntranceObligationTest`` in
    ``world.character_creation.tests.test_magic_stage``).
    """

    def test_creates_academy_org_with_null_tradition(self) -> None:
        from world.societies.models import Organization

        ensure_shroudwatch_academy()

        academy = Organization.objects.get(name=SHROUDWATCH_ACADEMY_NAME)
        self.assertIsNone(
            academy.tradition_id,
            "Academy tradition must be NULL — a multi-tradition teaching org (#2426 ruling).",
        )

    def test_idempotent_second_call_creates_no_duplicate(self) -> None:
        from world.societies.models import Organization

        ensure_shroudwatch_academy()
        ensure_shroudwatch_academy()

        self.assertEqual(Organization.objects.filter(name=SHROUDWATCH_ACADEMY_NAME).count(), 1)

    def test_does_not_overwrite_a_staff_adjusted_row(self) -> None:
        from world.societies.models import Organization

        ensure_shroudwatch_academy()
        Organization.objects.filter(name=SHROUDWATCH_ACADEMY_NAME).update(
            description="staff-edited description"
        )

        ensure_shroudwatch_academy()

        db_value = (
            Organization.objects.filter(name=SHROUDWATCH_ACADEMY_NAME).values("description").get()
        )
        self.assertEqual(db_value["description"], "staff-edited description")


class EnsureOrphanedTraditionDistinctionTests(TestCase):
    """First-call, idempotency, edit-preservation for the drawback distinction (#2428)."""

    def test_creates_distinction_with_expected_shape(self) -> None:
        from world.distinctions.models import Distinction, DistinctionEffect

        ensure_orphaned_tradition_distinction()

        distinction = Distinction.objects.get(slug="orphaned-tradition")
        self.assertEqual(distinction.name, "Orphaned Tradition")
        self.assertEqual(distinction.max_rank, 1)
        self.assertLess(
            distinction.cost_per_rank,
            0,
            "Drawback convention: negative cost_per_rank reimburses CG points.",
        )
        self.assertEqual(distinction.category.slug, "arcane")
        self.assertFalse(
            DistinctionEffect.objects.filter(distinction=distinction).exists(),
            "No DistinctionEffect — the drawback's teeth are trainerlessness (#2440), "
            "not a stat penalty (#2428 spec ruling 4).",
        )

    def test_idempotent_second_call_creates_no_duplicates(self) -> None:
        from world.distinctions.models import Distinction

        ensure_orphaned_tradition_distinction()
        ensure_orphaned_tradition_distinction()

        self.assertEqual(Distinction.objects.filter(slug="orphaned-tradition").count(), 1)

    def test_staff_edit_to_distinction_survives_rerun(self) -> None:
        from world.distinctions.models import Distinction

        ensure_orphaned_tradition_distinction()
        Distinction.objects.filter(slug="orphaned-tradition").update(
            description="staff-edited description"
        )

        ensure_orphaned_tradition_distinction()

        db_value = Distinction.objects.filter(slug="orphaned-tradition").values("description").get()
        self.assertEqual(db_value["description"], "staff-edited description")


class SeedMetallicOrderTraditionTests(TestCase):
    """Tests for ``seed_metallic_order_tradition()`` (#2428 Task 5).

    Covers: the defensive skip when the magic cluster hasn't run yet, the
    shape of the created rows (Tradition + its 5 TraditionGiftGrant rows +
    Arx-scoped BeginningTradition rows gated by the orphaned drawback),
    idempotency, and that seeding Metallic Order never touches Unbound's own
    rows.
    """

    def _seed_unbound_with_starter_grants(self, gift_count: int = 5):
        from world.magic.factories import GiftFactory, TraditionFactory, TraditionGiftGrantFactory

        unbound = TraditionFactory(name="Unbound")
        gifts = [GiftFactory() for _ in range(gift_count)]
        for gift in gifts:
            TraditionGiftGrantFactory(tradition=unbound, gift=gift)
        return unbound, gifts

    def _arx_beginning(self):
        realm = RealmFactory(name="Arx")
        area = StartingAreaFactory(realm=realm)
        return BeginningsFactory(starting_area=area)

    def test_skips_silently_when_unbound_tradition_not_seeded(self) -> None:
        from world.magic.models import Tradition

        result = seed_metallic_order_tradition()

        self.assertIsNone(result)
        self.assertFalse(Tradition.objects.filter(name="Metallic Order").exists())

    def test_skips_silently_when_unbound_has_no_starter_grants(self) -> None:
        from world.magic.factories import TraditionFactory
        from world.magic.models import Tradition

        TraditionFactory(name="Unbound")

        result = seed_metallic_order_tradition()

        self.assertIsNone(result)
        self.assertFalse(Tradition.objects.filter(name="Metallic Order").exists())

    def test_creates_tradition_grants_and_beginning_traditions(self) -> None:
        from world.character_creation.models import BeginningTradition
        from world.distinctions.models import Distinction
        from world.magic.models.grants import TraditionGiftGrant

        _unbound, gifts = self._seed_unbound_with_starter_grants()
        beginning = self._arx_beginning()
        other_realm_beginning = BeginningsFactory()  # default realm != "Arx"

        tradition = seed_metallic_order_tradition()

        self.assertIsNotNone(tradition)
        self.assertEqual(tradition.name, "Metallic Order")
        self.assertTrue(tradition.is_active)

        granted_gift_ids = set(
            TraditionGiftGrant.objects.filter(tradition=tradition).values_list("gift_id", flat=True)
        )
        self.assertEqual(granted_gift_ids, {gift.id for gift in gifts})

        distinction = Distinction.objects.get(slug="orphaned-tradition")
        bt = BeginningTradition.objects.get(beginning=beginning, tradition=tradition)
        self.assertEqual(bt.required_distinction_id, distinction.id)

        self.assertFalse(
            BeginningTradition.objects.filter(
                beginning=other_realm_beginning, tradition=tradition
            ).exists(),
            "Only Arx-realm Beginnings should get a Metallic Order row.",
        )

    def test_idempotent_second_call_creates_no_duplicates(self) -> None:
        from world.character_creation.models import BeginningTradition
        from world.magic.models import Tradition
        from world.magic.models.grants import TraditionGiftGrant

        self._seed_unbound_with_starter_grants()
        self._arx_beginning()

        seed_metallic_order_tradition()
        seed_metallic_order_tradition()

        self.assertEqual(Tradition.objects.filter(name="Metallic Order").count(), 1)
        self.assertEqual(
            TraditionGiftGrant.objects.filter(tradition__name="Metallic Order").count(), 5
        )
        self.assertEqual(
            BeginningTradition.objects.filter(tradition__name="Metallic Order").count(), 1
        )

    def test_does_not_overwrite_a_staff_adjusted_row(self) -> None:
        from world.character_creation.models import BeginningTradition

        self._seed_unbound_with_starter_grants()
        self._arx_beginning()
        seed_metallic_order_tradition()

        # Staff clears the gate — a recovery quest restored the tradition's teachers.
        BeginningTradition.objects.filter(tradition__name="Metallic Order").update(
            required_distinction=None
        )

        seed_metallic_order_tradition()

        # SharedMemoryModel (idmapper) — re-fetch via .values() so a stale cached
        # instance can't mask a regression (mirrors SeedBeginningTraditionsTests).
        db_value = (
            BeginningTradition.objects.filter(tradition__name="Metallic Order")
            .values("required_distinction_id")
            .get()
        )
        self.assertIsNone(db_value["required_distinction_id"])

    def test_unbound_rows_unaffected(self) -> None:
        from world.character_creation.models import BeginningTradition
        from world.magic.models.grants import TraditionGiftGrant

        unbound, gifts = self._seed_unbound_with_starter_grants()
        beginning = self._arx_beginning()
        seed_beginning_traditions()  # seeds the Unbound BeginningTradition row too
        unbound_bt_count_before = BeginningTradition.objects.filter(tradition=unbound).count()
        unbound_grant_count_before = TraditionGiftGrant.objects.filter(tradition=unbound).count()

        seed_metallic_order_tradition()

        self.assertEqual(
            TraditionGiftGrant.objects.filter(tradition=unbound).count(),
            unbound_grant_count_before,
        )
        self.assertEqual(
            {grant.gift_id for grant in TraditionGiftGrant.objects.filter(tradition=unbound)},
            {gift.id for gift in gifts},
        )
        self.assertEqual(
            BeginningTradition.objects.filter(tradition=unbound).count(),
            unbound_bt_count_before,
        )
        unbound_bt = BeginningTradition.objects.get(beginning=beginning, tradition=unbound)
        # #2442: Unbound's own row now gates on the "Unbound" drawback (not None).
        self.assertIsNotNone(unbound_bt.required_distinction_id)
        self.assertEqual(unbound_bt.required_distinction.slug, "unbound")


class EnsureSomehowAlwaysBrokeDistinctionTests(TestCase):
    """Shape, the drain sidecar, idempotency, and staff-edit survival (#2613)."""

    def test_creates_distinction_and_drain_with_expected_shape(self) -> None:
        from world.currency.models import DistinctionPurseDrain
        from world.distinctions.models import Distinction

        ensure_somehow_always_broke_distinction()

        distinction = Distinction.objects.get(slug="somehow-always-broke")
        self.assertEqual(distinction.name, "Somehow Always Broke")
        self.assertEqual(distinction.cost_per_rank, -50)
        self.assertEqual(distinction.max_rank, 1)
        self.assertEqual(distinction.category.slug, "personality")

        drain = DistinctionPurseDrain.objects.get(distinction=distinction)
        self.assertEqual(drain.drain_percent, 100)
        self.assertEqual(drain.floor_coppers, 0)

    def test_idempotent_second_call_creates_no_duplicates(self) -> None:
        from world.currency.models import DistinctionPurseDrain
        from world.distinctions.models import Distinction

        ensure_somehow_always_broke_distinction()
        ensure_somehow_always_broke_distinction()

        self.assertEqual(Distinction.objects.filter(slug="somehow-always-broke").count(), 1)
        self.assertEqual(
            DistinctionPurseDrain.objects.filter(distinction__slug="somehow-always-broke").count(),
            1,
        )

    def test_staff_edit_to_drain_percent_survives_rerun(self) -> None:
        from world.currency.models import DistinctionPurseDrain

        ensure_somehow_always_broke_distinction()
        DistinctionPurseDrain.objects.filter(distinction__slug="somehow-always-broke").update(
            drain_percent=50
        )

        ensure_somehow_always_broke_distinction()

        # Read via .values() to hit the DB, not the SharedMemoryModel identity
        # map (which still holds the pre-.update() instance) — mirrors
        # test_staff_edit_to_distinction_survives_rerun above.
        db_value = (
            DistinctionPurseDrain.objects.filter(distinction__slug="somehow-always-broke")
            .values("drain_percent")
            .get()
        )
        self.assertEqual(db_value["drain_percent"], 50)
