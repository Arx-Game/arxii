"""Capstone E2E: technique -> world-interaction -> currency, at the highest seam (#2503).

Proves the full chain the bridge exists to connect, with NOTHING mocked except the
dice roll:

1. A character KNOWS a technique whose ``TechniqueCapabilityGrant`` (prerequisite-null)
   grants ``generation`` -- the ONLY source of that capability (no innate baseline, no
   ``CharacterModifier``; ``CapabilityTypeFactory`` defaults ``innate_baseline=0`` and
   nothing here creates a modifier row). This is the #2504 technique-fold path
   (``world.mechanics.services._get_technique_sources`` /
   ``get_capability_sources_for_character``).
2. A torch is spawned from an ``ItemTemplate`` carrying ``flammable`` via
   ``ItemTemplateProperty`` and materialized through
   ``materialize_item_game_object_in_room`` -- the Task 2 chokepoint
   (``world.items.services.materialize``) -- rather than a raw ``ObjectPropertyFactory``
   row, so the property arrives the same way a crafted/looted/staged torch's would.
3. ``get_player_actions`` (the real picker read, ``actions.player_interface``) surfaces
   the synthesized Ignite ``WORLD_INTERACTION`` affordance for that torch (Task 3's
   bare-object scan, gated on the technique-sourced capability).
4. ``dispatch_player_action`` mints a ``ChallengeInstance`` and resolves it through the
   unchanged ``resolve_challenge`` path (Task 4).
5. A success consequence adds the ``lit`` ``ObjectProperty`` to the torch (not the
   character) via the real effect-handler pipeline.

Mirrors ``actions.tests.test_player_interface.TestDispatchPlayerActionWorldInteraction``
(which proves the same dispatch/resolve/effect chain against a bare ``ObjectDBFactory``
torch) but starts the object from the real ItemTemplate/materialize chokepoint, per the
task-6 brief's "highest seam" framing.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action, get_player_actions
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.conditions.factories import CapabilityTypeFactory
from world.items.factories import ItemTemplateFactory, ItemTemplatePropertyFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object_in_room
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, ObjectProperty
from world.mechanics.types import ChallengeResolutionResult
from world.traits.factories import CheckOutcomeFactory

_MODERATE_DIFFICULTY_PATCH = patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)


def _set_character_location(character: ObjectDB, room: ObjectDB) -> ObjectDB:
    """Place *character* in *room* without triggering Evennia's postsave hook.

    Mirrors the identical helper in ``actions/tests/test_player_interface.py`` and
    ``integration_tests/pipeline/test_challenge_dispatch_telnet_e2e.py``.
    """
    ObjectDB.objects.filter(pk=character.pk).update(db_location=room)
    character.db_location = room
    return character


class TechniqueToWorldToCurrencyE2ETests(TestCase):
    """The full fantasy: technique-known capability -> materialized torch -> Ignite -> lit."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_key="CapstoneE2ERoom")
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

        # (1) The ONLY capability source: a known technique's prereq-null grant.
        # innate_baseline defaults to 0 (CapabilityTypeFactory) and no CharacterModifier
        # is ever created for this capability -- the technique is load-bearing alone.
        cls.capability = CapabilityTypeFactory(name="generation_capstone", innate_baseline=0)
        cls.technique = TechniqueFactory(intensity=2)
        cls.grant = TechniqueCapabilityGrantFactory(
            technique=cls.technique,
            capability=cls.capability,
            base_value=5,
            intensity_multiplier=1,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        # Control character: otherwise identical, but does NOT know the technique --
        # the fail-closed side of the comparison (mirrors
        # ``world.assets.tests.test_effects
        # .TechniqueSourcedPromotionCapabilityModifierEffectTests``). No
        # ``CharacterTechniqueFactory`` call for this sheet.
        cls.sheet_without_technique = CharacterSheetFactory()
        cls.character_without_technique = cls.sheet_without_technique.character

        # (2) Torch spawned from an ItemTemplate via the real materialization chokepoint.
        cls.prop_flammable = PropertyFactory(name="flammable_capstone")
        cls.item_template = ItemTemplateFactory(name="Capstone Torch Template")
        ItemTemplatePropertyFactory(
            item_template=cls.item_template, property=cls.prop_flammable, value=1
        )
        instance = ItemInstance.objects.create(template=cls.item_template)
        cls.torch = materialize_item_game_object_in_room(instance, cls.room)
        _set_character_location(cls.character, cls.room)
        _set_character_location(cls.character_without_technique, cls.room)

        # Ignite: Application/ChallengeTemplate/Approach wired to the technique-sourced
        # capability + the template-materialized flammable property.
        cls.template = ChallengeTemplateFactory(name="Ignite Torch Capstone", severity=3)
        cls.application = ApplicationFactory(
            name="Ignite Capstone",
            capability=cls.capability,
            target_property=cls.prop_flammable,
            default_template=cls.template,
        )
        cls.approach = ChallengeApproachFactory(
            challenge_template=cls.template,
            application=cls.application,
            display_name="Ignite it",
        )

        # (5) Success consequence: add 'lit' to the TARGET (the torch), not the character.
        cls.prop_lit = PropertyFactory(name="lit_capstone")
        cls.outcome_success = CheckOutcomeFactory(name="Capstone Success", success_level=1)
        cls.consequence = ConsequenceFactory(
            outcome_tier=cls.outcome_success, label="Torch catches fire"
        )
        ChallengeTemplateConsequenceFactory(
            challenge_template=cls.template, consequence=cls.consequence
        )
        ConsequenceEffectFactory(
            consequence=cls.consequence,
            effect_type=EffectType.ADD_PROPERTY,
            target=EffectTarget.TARGET,
            property=cls.prop_lit,
            property_value=1,
        )

    def setUp(self) -> None:
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def test_full_chain_technique_to_lit_torch(self) -> None:
        """get_player_actions surfaces Ignite; dispatch mints+resolves; success lights it."""
        # (3) The real picker read: get_player_actions surfaces the synthesized Ignite
        # WORLD_INTERACTION affordance for the materialized torch.
        actions = get_player_actions(self.character)
        wi_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.WORLD_INTERACTION
            and a.ref.target_object_id == self.torch.pk
        ]
        self.assertEqual(len(wi_actions), 1, "Ignite must surface for the materialized torch")
        action = wi_actions[0]
        self.assertEqual(action.display_name, "Ignite it")
        ref = action.ref

        # (4) dispatch_player_action mints the instance and resolves through the real
        # resolve_challenge pipeline -- only the dice roll (perform_check) is patched.
        with patch(
            "world.mechanics.challenge_resolution.perform_check",
            return_value=CheckResult(
                check_type=self.approach.check_type,
                outcome=self.outcome_success,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            ),
        ):
            result = dispatch_player_action(self.character, ref, {})

        self.assertFalse(result.deferred)
        self.assertEqual(result.backend, ActionBackend.WORLD_INTERACTION)
        self.assertIsInstance(result.detail, ChallengeResolutionResult)

        # The mint happened (instantiate_challenge ran).
        ChallengeInstance.objects.get(template=self.template, target_object=self.torch)

        # (5) The success consequence adds 'lit' to the torch, not the character.
        self.assertTrue(
            ObjectProperty.objects.filter(
                object=self.torch, property=self.prop_lit, value=1
            ).exists(),
            "success consequence must add 'lit' to the torch",
        )
        self.assertFalse(
            ObjectProperty.objects.filter(object=self.character, property=self.prop_lit).exists(),
            "the character itself must never receive the 'lit' property",
        )

    def test_identical_character_without_technique_gets_no_ignite_action(self) -> None:
        """Fail-closed proof: identical setup minus the CharacterTechnique link -> no Ignite.

        Mirrors ``world.assets.tests.test_effects
        .TechniqueSourcedPromotionCapabilityModifierEffectTests
        .test_identical_character_without_technique_still_fails`` -- same room, same
        materialized torch, same Application/ChallengeTemplate/Approach wiring; the ONLY
        difference from ``self.character`` is the absent ``CharacterTechnique`` link, so
        ``get_capability_sources_for_character`` has no source for the capability and
        ``get_player_actions`` must not synthesize the WORLD_INTERACTION affordance.
        """
        actions = get_player_actions(self.character_without_technique)
        wi_actions = [
            a
            for a in actions
            if a.backend == ActionBackend.WORLD_INTERACTION
            and a.ref.target_object_id == self.torch.pk
        ]
        self.assertEqual(
            len(wi_actions),
            0,
            "Ignite must NOT surface for a character who never learned the technique",
        )

    def test_capability_comes_only_from_the_technique(self) -> None:
        """Sanity: no innate baseline, no CharacterModifier -- the technique alone gates it."""
        from world.mechanics.models import CharacterModifier

        self.assertEqual(self.capability.innate_baseline, 0)
        self.assertFalse(
            CharacterModifier.objects.filter(target__target_capability=self.capability).exists(),
            "no CharacterModifier may exist for this capability -- technique-only proof",
        )
        self.assertEqual(self.grant.calculate_value(), 7)
