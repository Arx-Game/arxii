"""Technique-learning prerequisite gate (#4097, Task 4; fix round 1).

``charge_and_learn`` now checks ``check_requirements_for_technique`` (Task 3)
right after the "already knows this technique" gate, raising
``TechniqueRequirementsNotMet`` when an active requirement targeting the
technique isn't met.

``get_technique_options`` (CG catalog) takes an ``exclude_gated: bool = False``
keyword (fix round 1 — review finding, Critical). **Character-creation call
sites only** (``character_creation.validators`` / ``character_creation.views``
/ the starting-kit analytics report, which explicitly models "the picks a new
character gets") pass ``exclude_gated=True``: a draft has no character yet to
evaluate ``check_requirements_for_technique`` against, so CG picks skip gated
techniques outright rather than offering one nobody can finalize. **In-play
callers keep the default** (``exclude_gated=False``) — Academy TRAIN's
eligibility check (``npc_services.effects._technique_available_to_learner``)
must still offer a prerequisite-gated technique, because the learner may
already meet the prerequisite and ``charge_and_learn``'s own per-character
``check_requirements_for_technique`` call is the correct gate for them. Round 1
caught this: the original unconditional exclusion inside the shared
``get_technique_options`` also fed TRAIN eligibility, so TRAIN refused a
gated technique to every learner, even one who met the prerequisite.

Fixture setup for the ``charge_and_learn`` tests mirrors
``ChargeAndLearnGoldCostTest`` (``test_gift_acquisition_service.py``): the
learner already owns the gift + a level-10 GIFT thread, sidestepping the
XP-unlock gate and the technique cap so these tests stay focused on the
prerequisite gate. Fixture setup for the TRAIN tests mirrors
``TrainOfferHappyPathTests`` (``world/npc_services/tests/test_train_offers.py``).
"""

from __future__ import annotations

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.currency.services import get_or_create_purse, mint_favor_token
from world.magic.constants import GiftKind, TargetKind
from world.magic.exceptions import TechniqueRequirementsNotMet
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterGiftUnlockFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    GiftUnlockFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
)
from world.magic.models import Thread
from world.magic.seeds_cast import get_standalone_cast_template
from world.magic.services.cg_catalog import get_technique_options
from world.magic.services.gift_acquisition import charge_and_learn
from world.npc_services.constants import OfferKind
from world.npc_services.effects import run_train_offer
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    TrainOfferDetailsFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import TechniqueKnownRequirement
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class ChargeAndLearnPrerequisitesTest(TestCase):
    """``charge_and_learn`` gates on ``check_requirements_for_technique``."""

    def setUp(self):
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.sheet = CharacterSheetFactory()
        # Already-owned gift + provisioned thread — sidesteps the XP-unlock
        # gate and the technique cap so these tests stay focused on
        # prerequisites (mirrors ChargeAndLearnGoldCostTest).
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )
        self.technique = TechniqueFactory(gift=self.gift)
        self.prerequisite = TechniqueFactory()
        self.ap_pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.ap_pool.current = 200
        self.ap_pool.save()

    def _learn(self):
        return charge_and_learn(
            self.sheet,
            self.technique,
            base_ap_cost=5,
            source=AccessChangeSource.ACADEMY_TRAINING,
        )

    def test_blocked_without_prerequisite(self):
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=True,
        )

        with self.assertRaises(TechniqueRequirementsNotMet) as ctx:
            self._learn()

        exc = ctx.exception
        self.assertEqual(exc.user_message, "You have not yet met what this technique requires.")
        self.assertEqual(len(exc.failed), 1)
        self.assertIn(self.prerequisite.name, exc.failed[0])

    def test_succeeds_after_learning_prerequisite(self):
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=True,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.prerequisite)

        progress = self._learn()

        self.assertEqual(progress.technique, self.technique)

    def test_inactive_requirement_does_not_block(self):
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=False,
        )

        progress = self._learn()

        self.assertEqual(progress.technique, self.technique)


class CgCatalogExcludesGatedTechniquesTest(TestCase):
    """``get_technique_options(exclude_gated=True)`` excludes an actively-gated technique.

    ``exclude_gated`` is opt-in (default ``False``) — see the module docstring for why.
    These tests exercise the CG call shape (``exclude_gated=True``) explicitly; the
    default-False shape (what TRAIN and other in-play callers use) is covered by
    ``TrainOfferStillOffersGatedTechniqueTest`` below.
    """

    def setUp(self):
        self.path = PathFactory()
        self.gift = GiftFactory()
        self.tradition = TraditionFactory()
        cast_template = get_standalone_cast_template()

        self.ungated_technique = TechniqueFactory(gift=self.gift, action_template=cast_template)
        self.gated_technique = TechniqueFactory(gift=self.gift, action_template=cast_template)
        other_technique = TechniqueFactory()
        TechniqueKnownRequirement.objects.create(
            technique=self.gated_technique,
            required_technique=other_technique,
            is_active=True,
        )

        path_grant = PathGiftGrantFactory(path=self.path, gift=self.gift)
        path_grant.starter_techniques.set([self.ungated_technique, self.gated_technique])

    def test_gated_technique_excluded_from_pool(self):
        options = get_technique_options(self.path, self.gift, self.tradition, exclude_gated=True)

        self.assertIn(self.ungated_technique, options.pool)
        self.assertNotIn(self.gated_technique, options.pool)

    def test_inactive_requirement_does_not_exclude(self):
        requirement = TechniqueKnownRequirement.objects.get(technique=self.gated_technique)
        requirement.is_active = False
        requirement.save()

        options = get_technique_options(self.path, self.gift, self.tradition, exclude_gated=True)

        self.assertIn(self.gated_technique, options.pool)

    def test_default_does_not_exclude_gated_technique(self):
        """``exclude_gated`` defaults to False — the in-play-caller shape (#4097 fix round 1)."""
        options = get_technique_options(self.path, self.gift, self.tradition)

        self.assertIn(self.gated_technique, options.pool)


class TrainOfferStillOffersGatedTechniqueTest(TestCase):
    """Academy TRAIN keeps offering a gated technique; ``charge_and_learn`` is the real gate.

    Fixture setup mirrors ``TrainOfferHappyPathTests``
    (``world/npc_services/tests/test_train_offers.py``). The technique carries an
    active ``TechniqueKnownRequirement`` — fix round 1's review finding was that the
    unconditional exclusion inside ``get_technique_options`` also fed
    ``_technique_available_to_learner`` (TRAIN's eligibility check), so TRAIN refused
    the technique to every learner regardless of whether they met the prerequisite.
    With ``exclude_gated`` defaulting to False, TRAIN's own availability check no
    longer excludes it, and ``charge_and_learn``'s per-character
    ``check_requirements_for_technique`` call decides per learner.
    """

    def setUp(self):
        from world.action_points.models import ActionPointPool

        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character

        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(ResonanceFactory())
        self.technique = TechniqueFactory(gift=self.gift)
        self.prerequisite = TechniqueFactory()
        TechniqueKnownRequirement.objects.create(
            technique=self.technique,
            required_technique=self.prerequisite,
            is_active=True,
        )
        self.path = PathFactory()
        CharacterPathHistoryFactory(character=self.character.sheet_data, path=self.path)
        grant = PathGiftGrantFactory(path=self.path, gift=self.gift)
        grant.starter_techniques.add(self.technique)

        # XP-unlock receipt: the first technique from an unowned gift needs
        # the gate satisfied (mirrors accept_technique_offer's own gate).
        CharacterGiftUnlockFactory(character=self.sheet, unlock=GiftUnlockFactory(gift=self.gift))

        self.role = NPCRoleFactory(faction_affiliation=self.academy)
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.TRAIN, label="Learn a technique", is_final=True
        )
        self.details = TrainOfferDetailsFactory(
            offer=self.offer, technique=self.technique, learn_ap_cost=5, gold_cost=0
        )

        self.ap_pool = ActionPointPool.get_or_create_for_character(self.character)
        self.ap_pool.current = 200
        self.ap_pool.save()
        self.purse = get_or_create_purse(self.sheet)
        self.purse.balance = 1000
        self.purse.save()
        mint_favor_token(self.academy, self.sheet, provenance_note="Cleared the trial")

    def test_learner_meeting_prerequisite_can_learn_via_train(self):
        CharacterTechniqueFactory(character=self.sheet, technique=self.prerequisite)

        result = run_train_offer(self.offer, self.persona)

        # Success shape (not the eligibility refusal, not the prerequisite refusal):
        # the technique was never excluded from TRAIN's offered pool, and the
        # per-character prerequisite check passed because the learner knows it.
        self.assertIsNotNone(result.object_pk)
        self.assertIn(self.technique.name, result.message)

    def test_learner_without_prerequisite_is_refused_with_requirements_message(self):
        result = run_train_offer(self.offer, self.persona)

        self.assertEqual(result.message, TechniqueRequirementsNotMet.user_message)
