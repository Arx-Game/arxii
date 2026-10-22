"""Model shape of vow added effects and their combat firing ledger (#4581).

Covers the header's natural key and constraints (scope uniqueness with null
narrowing, gift-or-technique, one upgrade per role per base), the PROTECT on
an upgraded base, the cascade from the header to its four payload children and
its ledger rows, ledger uniqueness, and the two new technique function tags.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import RestrictedError
from django.test import TestCase

from world.combat.factories import CombatParticipantFactory, VowAddedEffectFiringFactory
from world.combat.models import VowAddedEffectFiring
from world.covenants.constants import VowEffectFrequency
from world.covenants.factories import (
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectDamageProfileFactory,
    VowAddedEffectFactory,
    VowAddedEffectRemovedConditionFactory,
    VowAddedEffectTreatmentFactory,
)
from world.covenants.models import (
    VowAddedEffect,
    VowAddedEffectAppliedCondition,
    VowAddedEffectDamageProfile,
    VowAddedEffectRemovedCondition,
    VowAddedEffectTreatment,
)
from world.magic.constants import TechniqueFunction
from world.magic.factories import GiftFactory, TechniqueFactory, TechniqueFunctionTagFactory


class VowAddedEffectModelTests(TestCase):
    """The header row: natural key, scope uniqueness, narrowing, upgrades."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory()

    def test_natural_key_round_trips(self) -> None:
        effect = VowAddedEffectFactory(
            covenant_role=self.role, gift=None, technique=None, situation=""
        )
        self.assertEqual(VowAddedEffect.objects.get_by_natural_key(*effect.natural_key()), effect)

    def test_natural_key_round_trips_with_a_technique_narrowing(self) -> None:
        effect = VowAddedEffectFactory(covenant_role=self.role, technique=TechniqueFactory())
        self.assertEqual(VowAddedEffect.objects.get_by_natural_key(*effect.natural_key()), effect)

    def test_scope_is_unique_with_null_narrowing(self) -> None:
        first = VowAddedEffectFactory(
            covenant_role=self.role, gift=None, technique=None, situation=""
        )
        twin = VowAddedEffect(
            covenant_role=first.covenant_role,
            function=first.function,
            beneficiary=first.beneficiary,
        )
        with self.assertRaises(ValidationError):
            twin.full_clean()

    def test_a_different_unlock_level_is_a_different_scope(self) -> None:
        first = VowAddedEffectFactory(covenant_role=self.role)
        other = VowAddedEffect(
            covenant_role=first.covenant_role,
            function=first.function,
            beneficiary=first.beneficiary,
            unlock_thread_level=2,
        )
        other.full_clean()

    def test_gift_and_technique_together_are_refused_by_the_database(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            VowAddedEffectFactory(
                covenant_role=self.role, gift=GiftFactory(), technique=TechniqueFactory()
            )

    def test_a_role_upgrades_a_base_once(self) -> None:
        base = VowAddedEffectFactory(covenant_role=self.role)
        sub = SubroleCovenantRoleFactory(parent_role=base.covenant_role)
        VowAddedEffectFactory(
            covenant_role=sub, upgrades=base, frequency=VowEffectFrequency.EVERY_CAST
        )
        again = VowAddedEffect(
            covenant_role=sub,
            function=base.function,
            beneficiary=base.beneficiary,
            upgrades=base,
            unlock_thread_level=1,
        )
        with self.assertRaises(ValidationError):
            again.full_clean()

    def test_an_upgraded_base_cannot_be_deleted(self) -> None:
        base = VowAddedEffectFactory(covenant_role=self.role)
        sub = SubroleCovenantRoleFactory(parent_role=base.covenant_role)
        VowAddedEffectFactory(covenant_role=sub, upgrades=base)
        with self.assertRaises(RestrictedError):
            base.delete()

    def test_deleting_a_role_takes_its_base_and_its_own_upgrade(self) -> None:
        role = CovenantRoleFactory()
        base = VowAddedEffectFactory(covenant_role=role, unlock_thread_level=0)
        upgrade = VowAddedEffectFactory(covenant_role=role, upgrades=base, unlock_thread_level=3)
        role.delete()
        self.assertFalse(VowAddedEffect.objects.filter(pk__in=[base.pk, upgrade.pk]).exists())

    def test_strike_and_mend_are_valid_function_tags(self) -> None:
        for value in (TechniqueFunction.STRIKE, TechniqueFunction.MEND):
            TechniqueFunctionTagFactory(function=value).full_clean()


class VowAddedEffectChildrenAndLedgerTests(TestCase):
    """Payload children and ledger rows hang off the header and go with it."""

    def test_deleting_the_header_takes_children_and_firings(self) -> None:
        effect = VowAddedEffectFactory()
        VowAddedEffectAppliedConditionFactory(effect=effect)
        VowAddedEffectRemovedConditionFactory(effect=effect)
        VowAddedEffectTreatmentFactory(effect=effect)
        VowAddedEffectDamageProfileFactory(effect=effect)
        VowAddedEffectFiringFactory(effect=effect)

        effect.delete()

        for model in (
            VowAddedEffectAppliedCondition,
            VowAddedEffectRemovedCondition,
            VowAddedEffectTreatment,
            VowAddedEffectDamageProfile,
            VowAddedEffectFiring,
        ):
            self.assertFalse(model.objects.exists(), model.__name__)

    def test_a_child_save_refreshes_the_headers_cached_list(self) -> None:
        effect = VowAddedEffectFactory()
        self.assertEqual(effect.cached_applied_conditions, [])
        child = VowAddedEffectAppliedConditionFactory(effect=effect)
        self.assertEqual(effect.cached_applied_conditions, [child])

    def test_a_firing_is_unique_per_participant_effect_round(self) -> None:
        participant = CombatParticipantFactory()
        effect = VowAddedEffectFactory()
        VowAddedEffectFiringFactory(participant=participant, effect=effect, round_number=1)
        again = VowAddedEffectFiring(participant=participant, effect=effect, round_number=1)
        with self.assertRaises(ValidationError):
            again.full_clean()
