"""A declared pull on a technique-enhanced social action reaches the roll.

The plain branch of ``_resolve_action_against_persona`` folds the charged
pull's FLAT_BONUS into the check; the technique branch must do the same, or a
player pays resonance for nothing.
"""

from __future__ import annotations

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.models import ActionEnhancement
from evennia_extensions.factories import AccountFactory
from world.checks.factories import create_social_action_templates
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterResonance
from world.magic.types.pull import CastPullDeclaration
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes import action_services
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionPullDeclaration
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory
from world.traits.factories import CheckSystemSetupFactory

PULL_FLAT_BONUS = 5


class TechniqueSocialPullTests(APITestCase):
    """Declare a pull on a technique-enhanced flirt, accept, read the roll."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        # Both sides are played by accounts, so the REST path can be driven as each.
        target_character = cls.target.character_sheet.character
        cls.target_account = AccountFactory()
        target_character.db_account = cls.target_account
        target_character.save(update_fields=["db_account"])
        cls.initiator_account = AccountFactory()
        initiator_character = cls.initiator.character_sheet.character
        initiator_character.db_account = cls.initiator_account
        initiator_character.save(update_fields=["db_account"])
        for account, persona in (
            (cls.initiator_account, cls.initiator),
            (cls.target_account, cls.target),
        ):
            RosterTenureFactory(
                player_data=PlayerDataFactory(account=account),
                roster_entry=RosterEntryFactory(character_sheet=persona.character_sheet),
            )

        cls.sheet = cls.initiator.character_sheet
        cls.technique = TechniqueFactory(intensity=3, control=8, anima_cost=2)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.technique,
        )
        CharacterAnimaFactory(character=cls.sheet, current=20, maximum=30)
        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.resonance, balance=20, lifetime_earned=20
        )
        cls.thread = ThreadFactory(owner=cls.sheet, resonance=cls.resonance, as_track_thread=True)
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=PULL_FLAT_BONUS,
        )

    def _accept(self, *, with_pull: bool) -> tuple[list[int], int]:
        """Accept a technique flirt; return (roll modifiers seen, roll total points)."""
        pull = (
            CastPullDeclaration(resonance=self.resonance, tier=1, threads=(self.thread,))
            if with_pull
            else None
        )
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
            pull=pull,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])
        seen: list[int] = []
        real = action_services.start_action_resolution

        def spy(**kwargs):
            seen.append(kwargs["extra_modifiers"])
            return real(**kwargs)

        with (
            patch("world.scenes.action_services._accrue_engagement_for_primary"),
            patch.object(action_services, "start_action_resolution", side_effect=spy),
            # Fatigue from the first action would otherwise skew the second roll.
            patch("world.fatigue.services.get_fatigue_penalty", return_value=0),
        ):
            result = respond_to_action_request(
                action_request=request, decision=ConsentDecision.ACCEPT
            )
        assert result is not None
        assert result.technique_result is not None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        main_result = result.action_resolution.main_result
        assert main_result is not None
        return seen, main_result.check_result.total_points

    def test_declared_pull_bonus_reaches_the_technique_roll(self) -> None:
        seen, _total = self._accept(with_pull=True)

        decl = SceneActionPullDeclaration.objects.get()
        assert decl.charged_flat_bonus == PULL_FLAT_BONUS
        balance = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        ).balance
        assert balance == 18  # charged exactly once
        assert seen == [PULL_FLAT_BONUS]

    def test_roll_total_differs_by_the_pull_bonus(self) -> None:
        """Same character, same technique: the pulled roll totals PULL_FLAT_BONUS more."""
        seen_plain, total_plain = self._accept(with_pull=False)
        seen_pulled, total_pulled = self._accept(with_pull=True)

        assert seen_plain == [0]
        assert seen_pulled == [PULL_FLAT_BONUS]
        assert total_pulled - total_plain == PULL_FLAT_BONUS

    def test_pull_on_a_technique_flirt_through_the_rest_endpoints(self) -> None:
        """The player's path: POST the request with technique and pull, the target accepts."""
        self.client.force_authenticate(user=self.initiator_account)
        created = self.client.post(
            reverse("sceneactionrequest-list"),
            {
                "scene": self.scene.pk,
                "initiator_persona": self.initiator.pk,
                "target_persona": self.target.pk,
                "action_key": "flirt",
                "technique_id": self.technique.pk,
                "pull": {
                    "resonance_id": self.resonance.pk,
                    "tier": 1,
                    "thread_ids": [self.thread.pk],
                },
            },
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED, created.data

        seen: list[int] = []
        real = action_services.start_action_resolution

        def spy(**kwargs):
            seen.append(kwargs["extra_modifiers"])
            return real(**kwargs)

        self.client.force_authenticate(user=self.target_account)
        with (
            patch("world.scenes.action_services._accrue_engagement_for_primary"),
            patch.object(action_services, "start_action_resolution", side_effect=spy),
        ):
            accepted = self.client.post(
                reverse("sceneactionrequest-respond", kwargs={"pk": created.data["id"]}),
                {"decision": ConsentDecision.ACCEPT},
                format="json",
            )
        assert accepted.status_code == status.HTTP_200_OK, accepted.data
        assert accepted.data["status"] == ActionRequestStatus.RESOLVED
        assert accepted.data["result"]["technique_result"] is not None
        assert seen == [PULL_FLAT_BONUS]
        balance = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        ).balance
        assert balance == 18

    def _standing_seen(self, *, technique) -> list[int]:
        """Accept a flirt with a -7 fatigue penalty; the main check's extra_standing."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])
        import actions.services as pipeline

        seen: list[int] = []
        real = pipeline.perform_check

        def spy(*args, **kwargs):
            seen.append(kwargs.get("extra_standing", 0))
            return real(*args, **kwargs)

        with (
            patch("world.scenes.action_services._accrue_engagement_for_primary"),
            patch.object(pipeline, "perform_check", side_effect=spy),
            patch("world.fatigue.services.get_fatigue_penalty", return_value=-7),
        ):
            respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)
        return seen

    def test_fatigue_counts_as_own_standing_on_the_technique_branch(self) -> None:
        """Social fatigue is folded into the roll's modifiers but is her own standing, so
        the hopeless pin reads it as standing (#4601)."""
        self.assertIn(-7, self._standing_seen(technique=self.technique))

    def test_fatigue_counts_as_own_standing_on_the_plain_branch(self) -> None:
        self.assertIn(-7, self._standing_seen(technique=None))
