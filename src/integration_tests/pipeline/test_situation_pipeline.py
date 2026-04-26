"""End-to-end pipeline tests for the Situation system.

User story:
    As a GM, I place a Situation template at a room location. The system
    creates a SituationInstance and a set of ChallengeInstance rows — one
    per ChallengeTemplate in the template's SituationChallengeLink set.
    Players can then resolve each ChallengeInstance via the standard
    resolve_challenge pipeline. When all ChallengeInstances are resolved
    (deactivated), the GM can mark the Situation complete.

Covers:
    1. Instantiating a SituationTemplate manually creates SituationInstance
       + one ChallengeInstance per linked ChallengeTemplate.
    2. Resolving a single ChallengeInstance within a Situation writes a
       CharacterChallengeRecord and sets is_active=False on DESTROY outcomes.
    3. Resolving ALL ChallengeInstances leaves no active challenges in the
       Situation, which is the prerequisite for marking it complete.
    4. Attempting to resolve a challenge twice raises ChallengeResolutionError.

Architecture gaps documented:
    - No ``instantiate_situation(template, location)`` service function exists.
      The test builds the chain manually: SituationInstance + per-link
      ChallengeInstances. A proper service would belong in
      ``world/mechanics/challenge_resolution.py`` or a new
      ``world/mechanics/situation_services.py`` and is a Phase 1 follow-up.
    - No completion semantics on SituationInstance (no status field, only
      ``is_active`` bool). Completion is defined here as "no active
      ChallengeInstances remaining" — we verify that state rather than a
      terminal status enum.
    - SituationApproach model does not exist; challenge approaches live at
      ChallengeTemplate level (ChallengeApproach). The architectural notes
      describing per-situation approach overrides were speculative design;
      the implemented schema does not include them.
    - Cooperative resolution is unimplemented at the model/service layer.
      The CharacterChallengeRecord unique constraint enforces one record per
      (character, challenge_instance) — multiple characters can each resolve
      the same challenge, but there is no aggregation logic.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from integration_tests.game_content.challenges import ChallengeContent
from integration_tests.game_content.characters import CharacterContent
from integration_tests.game_content.social import SocialContent
from world.mechanics.models import (
    ChallengeInstance,
    CharacterChallengeRecord,
    SituationChallengeLink,
    SituationInstance,
    SituationTemplate,
)
from world.mechanics.types import ChallengeResolutionError


class TestSituationPipeline(TestCase):
    """SituationTemplate → SituationInstance → ChallengeInstance chain + resolution.

    setUpTestData seeds:
    - Full ChallengeContent suite (capabilities, properties, applications,
      6 starter ChallengeTemplates with consequences)
    - A SituationTemplate with two linked ChallengeTemplates
      ("Darkness" + "Locked Door") via SituationChallengeLink
    - A room ObjectDB to host the situation
    - A character with challenge stats (strength/agility/perception) for resolution
    - A SituationInstance + two ChallengeInstances at the room

    Individual tests either use cls.situation_instance + cls.challenge_instances
    directly, or create fresh instances where isolation is required (resolution
    deactivates challenges, making re-use across tests unsafe).
    """

    content: object  # ChallengeContentResult
    situation_template: SituationTemplate

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.factories import (
            ChallengeInstanceFactory,
            SituationChallengeLinkFactory,
            SituationInstanceFactory,
            SituationTemplateFactory,
        )

        social_result = SocialContent.create_all()
        cls.content = ChallengeContent.create_all(social_result.outcomes)

        # Two challenges that will form our Situation.
        cls.darkness_template = cls.content.challenges["Darkness"]
        cls.locked_door_template = cls.content.challenges["Locked Door"]

        # SituationTemplate needs a ChallengeCategory.
        # Re-use the "Environmental" category already created by ChallengeContent.
        env_category = cls.content.challenge_categories["Environmental"]

        cls.situation_template = SituationTemplateFactory(
            name="The Sealed Passage",
            description_template="A sealed corridor shrouded in darkness.",
            category=env_category,
        )

        # Link two challenges in display order.
        SituationChallengeLinkFactory(
            situation_template=cls.situation_template,
            challenge_template=cls.darkness_template,
            display_order=0,
        )
        SituationChallengeLinkFactory(
            situation_template=cls.situation_template,
            challenge_template=cls.locked_door_template,
            display_order=1,
        )

        # Room that will host the situation.
        cls.room = ObjectDBFactory(
            db_key="sealed_passage_room",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        # Character with challenge traits.
        cls.char, cls.persona = CharacterContent.create_base_challenge_character(name="Pathfinder")

        # Instantiate the situation manually (no service exists — see docstring gap note).
        cls.situation_instance = SituationInstanceFactory(
            template=cls.situation_template,
            location=cls.room,
        )

        # Create one ChallengeInstance per linked ChallengeTemplate.
        cls.challenge_instances: dict[str, ChallengeInstance] = {}
        links = SituationChallengeLink.objects.filter(
            situation_template=cls.situation_template
        ).order_by("display_order")
        for link in links:
            target = ObjectDBFactory(db_key=f"target_{link.challenge_template.name}")
            instance = ChallengeInstanceFactory(
                template=link.challenge_template,
                situation_instance=cls.situation_instance,
                location=cls.room,
                target_object=target,
            )
            cls.challenge_instances[link.challenge_template.name] = instance

    # -----------------------------------------------------------------------
    # Scenario 1: Instantiation creates the expected chain
    # -----------------------------------------------------------------------

    def test_situation_instance_created(self) -> None:
        """SituationInstance exists and references the correct template and location."""
        assert self.situation_instance.template == self.situation_template
        assert self.situation_instance.location == self.room
        assert self.situation_instance.is_active is True

    def test_challenge_instances_linked_to_situation(self) -> None:
        """One ChallengeInstance per linked ChallengeTemplate, all tied to SituationInstance."""
        linked_instances = ChallengeInstance.objects.filter(
            situation_instance=self.situation_instance
        )
        assert linked_instances.count() == 2

        template_names = set(linked_instances.values_list("template__name", flat=True))
        assert "Darkness" in template_names
        assert "Locked Door" in template_names

    def test_all_challenge_instances_start_active(self) -> None:
        """All ChallengeInstances created as part of the Situation start active and revealed."""
        linked_instances = ChallengeInstance.objects.filter(
            situation_instance=self.situation_instance
        )
        for instance in linked_instances:
            assert instance.is_active is True, f"{instance.template.name} should be active"
            assert instance.is_revealed is True, f"{instance.template.name} should be revealed"

    def test_situation_challenge_links_ordered(self) -> None:
        """SituationChallengeLinks are retrievable in display_order."""
        links = list(
            SituationChallengeLink.objects.filter(
                situation_template=self.situation_template
            ).order_by("display_order")
        )
        assert len(links) == 2
        assert links[0].challenge_template.name == "Darkness"
        assert links[1].challenge_template.name == "Locked Door"

    # -----------------------------------------------------------------------
    # Scenario 2: Resolving a ChallengeInstance within a Situation
    # -----------------------------------------------------------------------

    def _resolve_darkness(self, char: object) -> object:
        """Create a fresh Darkness instance and resolve it (high roll → DESTROY outcome)."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.challenge_resolution import resolve_challenge
        from world.mechanics.factories import ChallengeInstanceFactory
        from world.mechanics.models import ChallengeApproach
        from world.mechanics.services import get_available_actions
        from world.mechanics.types import CapabilitySource

        fresh_room = ObjectDBFactory(
            db_key="resolve_test_room", db_typeclass_path="typeclasses.rooms.Room"
        )
        fresh_instance = ChallengeInstanceFactory(
            template=self.darkness_template,
            situation_instance=self.situation_instance,
            location=fresh_room,
            target_object=ObjectDBFactory(db_key="resolve_dark_target"),
        )

        actions = get_available_actions(char, fresh_room)
        matching = [a for a in actions if a.challenge_instance_id == fresh_instance.pk]
        assert matching, "No available actions found for the fresh Darkness instance"

        action = matching[0]
        approach = ChallengeApproach.objects.get(pk=action.approach_id)
        source: CapabilitySource = action.capability_source

        with patch("world.checks.services.random.randint", return_value=95):
            result = resolve_challenge(char, fresh_instance, approach, source)

        return result, fresh_instance

    def test_resolving_challenge_creates_record(self) -> None:
        """resolve_challenge writes a CharacterChallengeRecord for the challenge instance."""
        _result, fresh_instance = self._resolve_darkness(self.char)

        assert CharacterChallengeRecord.objects.filter(
            character=self.char,
            challenge_instance=fresh_instance,
        ).exists()

    def test_destroy_resolution_deactivates_challenge(self) -> None:
        """A success/critical outcome with DESTROY resolution_type sets is_active=False."""
        _result, fresh_instance = self._resolve_darkness(self.char)

        fresh_instance.refresh_from_db()
        # Success/critical consequences have ResolutionType.DESTROY in the seed data.
        assert fresh_instance.is_active is False, (
            "Darkness challenge should be deactivated after a high-roll success"
        )

    def test_resolve_challenge_returns_result_with_situation_context(self) -> None:
        """Resolution result includes challenge_instance_id matching the instance."""
        result, fresh_instance = self._resolve_darkness(self.char)

        assert result.challenge_instance_id == fresh_instance.pk
        assert result.challenge_name == "Darkness"

    # -----------------------------------------------------------------------
    # Scenario 3: Situation completion when all challenges resolved
    # -----------------------------------------------------------------------

    def test_situation_completion_when_all_challenges_resolved(self) -> None:
        """Resolving all ChallengeInstances leaves zero active challenges in the Situation.

        Completion semantics: SituationInstance has only ``is_active`` (bool).
        There is no terminal status enum. "Complete" is defined here as having no
        remaining active ChallengeInstances — the GM can then set is_active=False
        on the SituationInstance to clean up.

        This test verifies the state, not a service function (no completion service
        exists — see docstring gap note at module level).
        """
        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.challenge_resolution import resolve_challenge
        from world.mechanics.factories import ChallengeInstanceFactory
        from world.mechanics.models import ChallengeApproach
        from world.mechanics.services import get_available_actions

        # Use a dedicated room and situation for this test.
        completion_room = ObjectDBFactory(
            db_key="completion_test_room", db_typeclass_path="typeclasses.rooms.Room"
        )
        completion_situation = SituationInstance.objects.create(
            template=self.situation_template,
            location=completion_room,
            is_active=True,
        )

        challenge_instances_to_resolve: list[ChallengeInstance] = []
        links = SituationChallengeLink.objects.filter(
            situation_template=self.situation_template
        ).order_by("display_order")

        for link in links:
            target = ObjectDBFactory(db_key=f"comp_target_{link.challenge_template.name}")
            ci = ChallengeInstanceFactory(
                template=link.challenge_template,
                situation_instance=completion_situation,
                location=completion_room,
                target_object=target,
            )
            challenge_instances_to_resolve.append(ci)

        # Resolve all challenges with a high roll (success → DESTROY).
        for ci in challenge_instances_to_resolve:
            actions = get_available_actions(self.char, completion_room)
            matching = [a for a in actions if a.challenge_instance_id == ci.pk]
            assert matching, f"No actions found for {ci.template.name}"

            action = matching[0]
            approach = ChallengeApproach.objects.get(pk=action.approach_id)

            with patch("world.checks.services.random.randint", return_value=95):
                resolve_challenge(self.char, ci, approach, action.capability_source)

        # After resolution: no active challenges remain in this situation.
        active_count = ChallengeInstance.objects.filter(
            situation_instance=completion_situation,
            is_active=True,
        ).count()

        assert active_count == 0, (
            f"Expected 0 active challenges after full resolution, found {active_count}"
        )

        # The situation itself is still marked is_active (no auto-complete service).
        # Deactivating it is a manual GM step — verify we can toggle it.
        completion_situation.is_active = False
        completion_situation.save()
        completion_situation.refresh_from_db()
        assert completion_situation.is_active is False

    # -----------------------------------------------------------------------
    # Scenario 4: Double-resolution guard
    # -----------------------------------------------------------------------

    def test_resolving_challenge_twice_raises_error(self) -> None:
        """Attempting to resolve the same challenge twice raises ChallengeResolutionError."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.challenge_resolution import resolve_challenge
        from world.mechanics.factories import ChallengeInstanceFactory
        from world.mechanics.models import ChallengeApproach
        from world.mechanics.services import get_available_actions

        dupe_room = ObjectDBFactory(
            db_key="dupe_test_room", db_typeclass_path="typeclasses.rooms.Room"
        )
        dupe_instance = ChallengeInstanceFactory(
            template=self.darkness_template,
            situation_instance=self.situation_instance,
            location=dupe_room,
            target_object=ObjectDBFactory(db_key="dupe_dark_target"),
        )

        actions = get_available_actions(self.char, dupe_room)
        matching = [a for a in actions if a.challenge_instance_id == dupe_instance.pk]
        assert matching, "No available actions found for dupe instance"

        action = matching[0]
        approach = ChallengeApproach.objects.get(pk=action.approach_id)
        source = action.capability_source

        with patch("world.checks.services.random.randint", return_value=10):
            resolve_challenge(self.char, dupe_instance, approach, source)

        # Second resolution attempt — challenge may still be active (low roll = PERSONAL),
        # but CharacterChallengeRecord already exists → should raise.
        dupe_instance.is_active = True
        dupe_instance.save()

        import pytest

        with pytest.raises(ChallengeResolutionError, match="already resolved"):
            with patch("world.checks.services.random.randint", return_value=10):
                resolve_challenge(self.char, dupe_instance, approach, source)

    # -----------------------------------------------------------------------
    # Cooperative resolution (not implemented — documented)
    # -----------------------------------------------------------------------

    def test_multiple_characters_can_each_resolve_same_challenge(self) -> None:
        """Two characters can both resolve the same ChallengeInstance independently.

        Cooperative resolution aggregation is not implemented (no service layer
        combines results, no 'cooperative success' outcome). Each character's
        resolution is independent. The CharacterChallengeRecord unique constraint
        is per (character, challenge_instance), so two different characters
        each get their own record.

        This test documents the current behaviour: independent resolution,
        no aggregation.
        """
        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.challenge_resolution import resolve_challenge
        from world.mechanics.factories import ChallengeInstanceFactory
        from world.mechanics.models import ChallengeApproach
        from world.mechanics.services import get_available_actions

        coop_room = ObjectDBFactory(
            db_key="coop_test_room", db_typeclass_path="typeclasses.rooms.Room"
        )
        coop_instance = ChallengeInstanceFactory(
            template=self.darkness_template,
            situation_instance=self.situation_instance,
            location=coop_room,
            target_object=ObjectDBFactory(db_key="coop_dark_target"),
        )

        char_a, _ = CharacterContent.create_base_challenge_character(name="CoopA")
        char_b, _ = CharacterContent.create_base_challenge_character(name="CoopB")

        def _resolve_for(char: object) -> None:
            actions = get_available_actions(char, coop_room)
            matching = [a for a in actions if a.challenge_instance_id == coop_instance.pk]
            assert matching, f"No actions for char {char}"
            action = matching[0]
            approach = ChallengeApproach.objects.get(pk=action.approach_id)
            # Use a low roll so the challenge stays active for the second character.
            with patch("world.checks.services.random.randint", return_value=10):
                resolve_challenge(char, coop_instance, approach, action.capability_source)

        _resolve_for(char_a)

        # Challenge may have been deactivated; re-activate for char_b's turn.
        coop_instance.is_active = True
        coop_instance.save()

        _resolve_for(char_b)

        records = CharacterChallengeRecord.objects.filter(challenge_instance=coop_instance)
        assert records.count() == 2, (
            f"Expected 2 records (one per character), found {records.count()}"
        )
        record_chars = {r.character_id for r in records}
        assert char_a.pk in record_chars
        assert char_b.pk in record_chars
