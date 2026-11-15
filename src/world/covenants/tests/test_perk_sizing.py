"""A vow perk is a share of one level's width at the rung of its HOLDER's vow thread (#5093).

``sum_potency_scaled_magnitudes`` sizes each fired perk as ``magnitude_tenths / 10 x`` the CHECK
lane's width at ``thread_rung`` of the holder's COVENANT_ROLE thread on the perk's role. A
holder's other threads add nothing, and the helped character's threads never count, so a
covenant mate's perk is sized by the mate. A holder with no vow thread adds 0 and never raises.

Not ``setUpTestData``: factories create Evennia ``ObjectDB`` instances (``DbHolder``, not
deepcopyable), the same rationale as the other perk suites.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane
from world.checks.modifier_models import ModifierLevelBaseline
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.services import FiredPerk, sum_potency_scaled_magnitudes
from world.magic.factories import ThreadFactory
from world.traits.factories import ensure_level_ladder


class PerkSizingTests(TestCase):
    def setUp(self) -> None:
        ensure_level_ladder()  # CHECK baselines 18 + 8 x (level - 1): one level is 8 wide
        self.holder = CharacterSheetFactory(character=CharacterFactory())
        self.role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.holder,
            covenant=CovenantFactory(),
            covenant_role=self.role,
            engaged=True,
        )

    def _firing(self, *, tenths: int = 10, holder=None, is_secondary: bool = False) -> FiredPerk:
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=tenths,
        )
        return FiredPerk(
            perk=perk,
            holder=holder or self.holder,
            magnitude_tenths=tenths,
            rung_number=None,
            is_secondary=is_secondary,
        )

    def test_a_one_point_oh_perk_on_a_rung_eleven_vow_thread_adds_one_level_width(self) -> None:
        ThreadFactory(owner=self.holder, level=110, as_covenant_role_thread=self.role)

        self.assertEqual(sum_potency_scaled_magnitudes([self._firing()]), 8)
        self.assertEqual(sum_potency_scaled_magnitudes([self._firing(tenths=5)]), 4)

    def test_the_holders_other_threads_and_a_helped_characters_threads_add_nothing(self) -> None:
        ThreadFactory(owner=self.holder, level=110, as_covenant_role_thread=self.role)
        helped = CharacterSheetFactory(character=CharacterFactory())
        ThreadFactory(owner=helped, level=300, as_covenant_role_thread=CovenantRoleFactory())
        ThreadFactory(owner=self.holder, level=300)  # a TRAIT thread, not the vow thread

        # The firing is the holder's perk helping someone else; only her vow thread sizes it.
        self.assertEqual(sum_potency_scaled_magnitudes([self._firing()]), 8)

    def test_a_holder_with_no_vow_thread_adds_nothing_and_never_raises(self) -> None:
        ThreadFactory(owner=self.holder, level=300)  # other threads only
        self.assertEqual(sum_potency_scaled_magnitudes([self._firing()]), 0)

        ThreadFactory(owner=self.holder, level=9, as_covenant_role_thread=self.role)
        # A vow thread under rung 1 has no level to act at either.
        self.assertEqual(sum_potency_scaled_magnitudes([self._firing()]), 0)

    def test_the_width_is_the_one_at_the_vow_threads_rung(self) -> None:
        ModifierLevelBaseline.objects.filter(lane=ModifierLane.CHECK).delete()
        for level, baseline in ((1, 20), (2, 30), (3, 50), (4, 80)):
            ModifierLevelBaseline.objects.create(
                lane=ModifierLane.CHECK, level=level, baseline=baseline
            )
        thread = ThreadFactory(owner=self.holder, level=20, as_covenant_role_thread=self.role)
        self.assertEqual(sum_potency_scaled_magnitudes([self._firing()]), 20)  # rung 2: 50 - 30

        thread.level = 30
        thread.save()
        self.holder.character.threads.invalidate()
        self.assertEqual(sum_potency_scaled_magnitudes([self._firing()]), 30)  # rung 3: 80 - 50

    def test_a_secondary_firing_is_scaled_by_the_secondary_potency(self) -> None:
        ThreadFactory(owner=self.holder, level=110, as_covenant_role_thread=self.role)
        # width 8 x 2.0 = 16, x the default secondary potency 0.6 = 9.6, truncated to 9.
        self.assertEqual(
            sum_potency_scaled_magnitudes([self._firing(tenths=20, is_secondary=True)]), 9
        )
