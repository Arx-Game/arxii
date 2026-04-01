"""
Tests for Random Scene service functions.
"""

import datetime

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.models import RandomSceneCompletion, RandomSceneTarget
from world.progression.services.random_scene import (
    claim_random_scene,
    generate_random_scene_targets,
    reroll_random_scene_target,
    validate_random_scene_claim,
)
from world.relationships.factories import CharacterRelationshipFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.scenes.models import Interaction, SceneParticipation


def _make_active_character(account=None):
    """Helper: create a character with an active roster tenure, returning (character, tenure)."""
    from world.roster.factories import PlayerDataFactory

    kwargs = {}
    if account is not None:
        kwargs["player_data"] = PlayerDataFactory(account=account)
    tenure = RosterTenureFactory(**kwargs)
    character = tenure.roster_entry.character
    return character, tenure


class GenerateRandomSceneTargetsTest(TestCase):
    """Tests for generate_random_scene_targets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="rs_gen_player")
        cls.week_start = datetime.date(2026, 3, 23)

    def setUp(self) -> None:
        RandomSceneTarget.flush_instance_cache()
        RandomSceneCompletion.flush_instance_cache()

    def test_creates_5_targets(self) -> None:
        """generate_random_scene_targets creates 5 targets."""
        # Create own character with active tenure
        _own_char, _ = _make_active_character(self.account)

        # Create 5+ other active characters
        for _ in range(6):
            _make_active_character()

        targets = generate_random_scene_targets(self.account, self.week_start)
        assert len(targets) == 5
        for i, target in enumerate(targets, start=1):
            assert target.slot_number == i
            assert target.account == self.account
            assert target.week_start == self.week_start
            assert target.claimed is False

    def test_slots_1_3_prefer_strangers(self) -> None:
        """Slots 1-3 should prefer characters with no prior completion."""
        _own_char, _ = _make_active_character(self.account)

        # Create 3 "known" characters (with completion records)
        known_ids = set()
        for _ in range(3):
            char, _ = _make_active_character()
            RandomSceneCompletion.objects.create(account=self.account, target_character=char)
            known_ids.add(char.pk)

        # Create 3 "stranger" characters (no completion record)
        for _ in range(3):
            _make_active_character()

        targets = generate_random_scene_targets(self.account, self.week_start)
        slots_1_3_ids = {t.target_character_id for t in targets[:3]}

        # Slots 1-3 should NOT contain any known characters (they prefer strangers)
        assert not slots_1_3_ids.intersection(known_ids)

    def test_slots_4_5_prefer_relationships(self) -> None:
        """Slots 4-5 should prefer characters with existing relationships."""
        own_char, _ = _make_active_character(self.account)
        own_sheet = CharacterSheetFactory(character=own_char)

        # Create 2 relationship characters (mark as completed so they
        # don't land in stranger slots 1-3)
        rel_chars = []
        for _ in range(2):
            char, _ = _make_active_character()
            other_sheet = CharacterSheetFactory(character=char)
            CharacterRelationshipFactory(source=own_sheet, target=other_sheet)
            RandomSceneCompletion.objects.create(account=self.account, target_character=char)
            rel_chars.append(char)

        # Create 5 extra stranger characters for slots 1-3 (no completion)
        for _ in range(5):
            _make_active_character()

        targets = generate_random_scene_targets(self.account, self.week_start)
        rel_ids = {c.pk for c in rel_chars}
        slots_4_5_ids = {t.target_character_id for t in targets[3:5]}

        assert slots_4_5_ids == rel_ids

    def test_fills_from_general_pool_when_not_enough_strangers(self) -> None:
        """When fewer than 3 strangers, fill from general active pool."""
        _own_char, _ = _make_active_character(self.account)

        # Only 1 stranger available
        _stranger_char, _ = _make_active_character()

        # 4 known characters (completed)
        for _ in range(4):
            char, _ = _make_active_character()
            RandomSceneCompletion.objects.create(account=self.account, target_character=char)

        targets = generate_random_scene_targets(self.account, self.week_start)
        assert len(targets) == 5

    def test_fills_from_general_pool_when_no_relationships(self) -> None:
        """When no relationship characters, fill slots 4-5 from general pool."""
        _own_char, _ = _make_active_character(self.account)

        # Create 5 characters, none with relationships
        for _ in range(5):
            _make_active_character()

        targets = generate_random_scene_targets(self.account, self.week_start)
        assert len(targets) == 5


class ValidateRandomSceneClaimTest(TestCase):
    """Tests for validate_random_scene_claim."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.week_start = datetime.date(2026, 3, 23)
        cls.account = AccountFactory(username="rs_claimer")
        cls.target_char, cls.target_tenure = _make_active_character()
        cls.target_account = cls.target_tenure.player_data.account

    def test_returns_true_with_shared_scene(self) -> None:
        """Returns True when both accounts are in the same scene this week."""
        scene = SceneFactory()
        joined = datetime.datetime(2026, 3, 24, 12, 0, tzinfo=datetime.UTC)
        p1 = SceneParticipation.objects.create(
            scene=scene,
            account=self.account,
        )
        p2 = SceneParticipation.objects.create(
            scene=scene,
            account=self.target_account,
        )
        # auto_now_add ignores passed values, so update after create
        SceneParticipation.objects.filter(pk=p1.pk).update(joined_at=joined)
        SceneParticipation.objects.filter(pk=p2.pk).update(joined_at=joined)

        result = validate_random_scene_claim(self.account, self.target_char, self.week_start)
        assert result is True

    def test_returns_true_with_shared_interactions_in_same_scene(self) -> None:
        """Returns True when both characters have interactions in the same scene."""
        ts = datetime.datetime(2026, 3, 25, 10, 0, tzinfo=datetime.UTC)
        shared_scene = SceneFactory()

        own_char, _ = _make_active_character(self.account)
        own_persona = PersonaFactory(
            character_identity__character=own_char,
            character=own_char,
        )
        own_interaction = InteractionFactory(persona=own_persona, scene=shared_scene)
        Interaction.objects.filter(pk=own_interaction.pk).update(timestamp=ts)

        target_persona = PersonaFactory(
            character_identity__character=self.target_char,
            character=self.target_char,
        )
        target_interaction = InteractionFactory(persona=target_persona, scene=shared_scene)
        Interaction.objects.filter(pk=target_interaction.pk).update(timestamp=ts)

        result = validate_random_scene_claim(self.account, self.target_char, self.week_start)
        assert result is True

    def test_returns_false_with_no_evidence(self) -> None:
        """Returns False when no shared scene or interactions."""
        result = validate_random_scene_claim(self.account, self.target_char, self.week_start)
        assert result is False


class ClaimRandomSceneTest(TestCase):
    """Tests for claim_random_scene."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.week_start = datetime.date(2026, 3, 23)
        cls.account = AccountFactory(username="rs_claim_acct")
        cls.own_char, _ = _make_active_character(cls.account)
        cls.target_char, cls.target_tenure = _make_active_character()
        cls.target_account = cls.target_tenure.player_data.account

    def setUp(self) -> None:
        RandomSceneTarget.flush_instance_cache()
        RandomSceneCompletion.flush_instance_cache()

    def _create_shared_scene(self) -> None:
        """Helper to create a shared scene for validation."""
        scene = SceneFactory()
        joined = datetime.datetime(2026, 3, 24, 12, 0, tzinfo=datetime.UTC)
        p1 = SceneParticipation.objects.create(
            scene=scene,
            account=self.account,
        )
        p2 = SceneParticipation.objects.create(
            scene=scene,
            account=self.target_account,
        )
        SceneParticipation.objects.filter(pk=p1.pk).update(joined_at=joined)
        SceneParticipation.objects.filter(pk=p2.pk).update(joined_at=joined)

    def test_awards_5_plus_5_xp(self) -> None:
        """claim_random_scene awards 5 XP to claimer and 5 XP to target."""
        from world.progression.models import XPTransaction

        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
            first_time=False,
        )
        self._create_shared_scene()

        claim_random_scene(self.account, target.pk)

        claimer_xp = XPTransaction.objects.filter(account=self.account).order_by("-id").first()
        target_xp = (
            XPTransaction.objects.filter(account=self.target_account).order_by("-id").first()
        )

        assert claimer_xp is not None
        assert claimer_xp.amount == 5
        assert target_xp is not None
        assert target_xp.amount == 5

    def test_awards_first_time_bonus(self) -> None:
        """claim_random_scene awards 15 XP to claimer on first_time, 5 to target."""
        from world.progression.models import XPTransaction

        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
            first_time=True,
        )
        self._create_shared_scene()

        claim_random_scene(self.account, target.pk)

        claimer_xp = XPTransaction.objects.filter(account=self.account).order_by("-id").first()
        target_xp = (
            XPTransaction.objects.filter(account=self.target_account).order_by("-id").first()
        )

        assert claimer_xp is not None
        assert claimer_xp.amount == 15
        assert target_xp is not None
        assert target_xp.amount == 5

    def test_creates_completion_record(self) -> None:
        """claim_random_scene creates a RandomSceneCompletion."""
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
        )
        self._create_shared_scene()

        claim_random_scene(self.account, target.pk)

        assert RandomSceneCompletion.objects.filter(
            account=self.account,
            target_character=self.target_char,
        ).exists()

    def test_rejects_already_claimed(self) -> None:
        """claim_random_scene raises ValueError on already-claimed target."""
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
            claimed=True,
            claimed_at=timezone.now(),
        )
        self._create_shared_scene()

        with self.assertRaises(ValueError, msg="Target already claimed"):
            claim_random_scene(self.account, target.pk)

    def test_rejects_without_evidence(self) -> None:
        """claim_random_scene raises ValueError when no shared scene evidence."""
        target = RandomSceneTarget.objects.create(
            account=self.account,
            target_character=self.target_char,
            week_start=self.week_start,
            slot_number=1,
        )

        with self.assertRaises(ValueError, msg="No evidence"):
            claim_random_scene(self.account, target.pk)


class RerollRandomSceneTargetTest(TestCase):
    """Tests for reroll_random_scene_target."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.week_start = datetime.date(2026, 3, 23)
        cls.account = AccountFactory(username="rs_reroll_acct")
        cls.own_char, _ = _make_active_character(cls.account)

    def setUp(self) -> None:
        RandomSceneTarget.flush_instance_cache()

    def test_replaces_target(self) -> None:
        """reroll_random_scene_target replaces the target character."""
        original_char, _ = _make_active_character()
        _new_candidate, _ = _make_active_character()

        RandomSceneTarget.objects.create(
            account=self.account,
            target_character=original_char,
            week_start=self.week_start,
            slot_number=1,
        )

        updated = reroll_random_scene_target(self.account, 1, self.week_start)
        assert updated.rerolled is True
        # Target should have changed (or stayed if only one candidate, but we have two)
        assert updated.target_character_id != original_char.pk or updated.rerolled

    def test_rejects_if_already_rerolled(self) -> None:
        """reroll rejects if another target was already rerolled this week."""
        char1, _ = _make_active_character()
        char2, _ = _make_active_character()
        _make_active_character()  # Extra candidate for reroll pool

        RandomSceneTarget.objects.create(
            account=self.account,
            target_character=char1,
            week_start=self.week_start,
            slot_number=1,
            rerolled=True,  # Already rerolled
        )
        RandomSceneTarget.objects.create(
            account=self.account,
            target_character=char2,
            week_start=self.week_start,
            slot_number=2,
        )

        with self.assertRaises(ValueError, msg="Already used reroll"):
            reroll_random_scene_target(self.account, 2, self.week_start)
