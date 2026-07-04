"""End-to-end test: a signed technique's damage profile lands in combat (#1728, Task 2).

Proves the ``CombatTechniqueResolver._apply_damage`` seam now folds a signed
technique's ``SignatureMotifBonusDamageProfile`` rows in alongside the technique's
own ``TechniqueDamageProfile`` rows — differential assertion: the same combat cast
resolved once with the technique signed and once unsigned must deal strictly more
opponent damage when signed.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.combat.constants import ActionCategory
from world.combat.services import resolve_combat_technique
from world.combat.tests.test_combat_magic_integration import _setup_pc_attacking_mook
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    FacetFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
)
from world.magic.models import SignatureMotifBonus, Thread
from world.magic.models.signature import SignatureMotifBonusDamageProfile
from world.magic.services.signature import set_signature_bonus


class SignatureCombatDamageE2ETests(TestCase):
    """Differential: signed technique deals strictly more combat damage (#1728)."""

    @classmethod
    def setUpTestData(cls) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )

    def _resolve_total_damage(self, *, sign_technique: bool) -> int:
        """Build a fresh combat-cast fixture and return total opponent damage dealt.

        The technique carries its own TechniqueDamageProfile (base_damage=20, via
        the EffectType base_power auto-seed). When ``sign_technique`` is True the
        caster's technique Thread is signed with a SignatureMotifBonus carrying its
        own SignatureMotifBonusDamageProfile (base_damage=50) — the resolver should
        combine both profiles against the opponent.
        """
        participant, action, opponent, _anima, technique, _room = _setup_pc_attacking_mook(
            technique_intensity=5,
            technique_control=10,
            technique_anima_cost=2,
            base_power=20,
            opponent_health=999,
        )
        sheet = participant.character_sheet
        CharacterTechniqueFactory(character=sheet, technique=technique)

        if sign_technique:
            motif = MotifFactory(character=sheet)
            resonance = ResonanceFactory()
            facet = FacetFactory(name="SigCombatDamageFacet")
            motif_res = MotifResonanceFactory(motif=motif, resonance=resonance)
            MotifResonanceAssociationFactory(motif_resonance=motif_res, facet=facet)

            bonus = SignatureMotifBonus.objects.create(
                name="Combat Signature Bonus",
                required_facet=facet,
            )
            SignatureMotifBonusDamageProfile.objects.create(
                signature_bonus=bonus,
                base_damage=50,
                minimum_success_level=1,
            )

            thread = Thread.objects.create(
                owner=sheet,
                resonance=resonance,
                target_kind=TargetKind.TECHNIQUE,
                target_technique=technique,
            )
            sheet.character.threads.invalidate()
            set_signature_bonus(thread, bonus)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            result = resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        opponent.refresh_from_db()
        return sum(r.damage_dealt for r in result.damage_results)

    def test_signed_technique_deals_signature_bonus_damage_in_combat(self) -> None:
        """A signed technique's SignatureMotifBonusDamageProfile adds to combat damage."""
        unsigned_damage = self._resolve_total_damage(sign_technique=False)
        signed_damage = self._resolve_total_damage(sign_technique=True)

        self.assertGreater(
            signed_damage,
            unsigned_damage,
            f"Expected signed damage ({signed_damage}) > unsigned damage "
            f"({unsigned_damage}) — the signature bonus's damage profile must "
            "land alongside the technique's own.",
        )
