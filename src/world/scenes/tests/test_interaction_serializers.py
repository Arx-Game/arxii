"""TDD tests for endorsement-related fields on InteractionListSerializer (#1138).

Tests cover Tasks 1-4 of Phase A:
  Task 1: pose_kind + endorsee_sheet_id
  Task 2: endorsable_resonances
  Task 3: pose_endorsers + my_pose_endorsement
  Task 4: entry_endorsers + entry_endorsed_by_me
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.db.models import Prefetch
from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    PoseEndorsementFactory,
    ResonanceFactory,
    SceneEntryEndorsementFactory,
)
from world.scenes.constants import PoseKind
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.interaction_serializers import InteractionListSerializer


def _make_context(
    user_pk: int | None = None,
    persona_ids: set | None = None,
    roster_entry_ids: set | None = None,
    character_sheet_ids: set | None = None,
    scene_entry_endorsements: dict | None = None,
) -> dict:
    """Build a minimal serializer context."""
    mock_request = MagicMock()
    mock_request.user.pk = user_pk
    mock_request.user.is_authenticated = user_pk is not None
    return {
        "request": mock_request,
        "persona_ids": persona_ids or set(),
        "roster_entry_ids": roster_entry_ids or set(),
        "character_sheet_ids": character_sheet_ids or set(),
        "scene_entry_endorsements": scene_entry_endorsements or {},
    }


def _set_empty_cached_attrs(interaction) -> None:
    """Set all cached_* attrs to empty so serializer doesn't try to query."""
    interaction.cached_receivers = []
    interaction.cached_target_personas = []
    interaction.cached_favorites = []
    interaction.cached_reactions = []
    interaction.cached_action_links = []
    interaction.cached_endorsements = []
    interaction.cached_reaction_windows = None


class Task1PoseKindEndorseeSheetIdTests(TestCase):
    """Task 1: pose_kind + endorsee_sheet_id exposed on InteractionListSerializer."""

    @classmethod
    def setUpTestData(cls) -> None:
        idmapper_models.flush_cache()
        cls.sheet = CharacterSheetFactory()
        cls.persona = cls.sheet.primary_persona
        cls.entry_pose = InteractionFactory(persona=cls.persona, pose_kind=PoseKind.ENTRY)
        cls.standard_pose = InteractionFactory(persona=cls.persona, pose_kind=PoseKind.STANDARD)

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_pose_kind_entry(self) -> None:
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        data = InteractionListSerializer(interaction, context=_make_context()).data
        assert data["pose_kind"] == "entry"

    def test_pose_kind_standard(self) -> None:
        interaction = self.standard_pose
        _set_empty_cached_attrs(interaction)
        data = InteractionListSerializer(interaction, context=_make_context()).data
        assert data["pose_kind"] == "standard"

    def test_endorsee_sheet_id_matches_persona_character_sheet(self) -> None:
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        data = InteractionListSerializer(interaction, context=_make_context()).data
        assert data["endorsee_sheet_id"] == self.sheet.pk


class Task2EndorsableResonancesTests(TestCase):
    """Task 2: endorsable_resonances lists the endorsee's claimed resonances."""

    @classmethod
    def setUpTestData(cls) -> None:
        idmapper_models.flush_cache()
        cls.sheet = CharacterSheetFactory()
        cls.persona = cls.sheet.primary_persona
        cls.r1 = ResonanceFactory()
        cls.r2 = ResonanceFactory()
        cls.cr1 = CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.r1)
        cls.cr2 = CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.r2)
        cls.entry_pose = InteractionFactory(persona=cls.persona, pose_kind=PoseKind.ENTRY)

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_endorsable_resonances_lists_all_claimed(self) -> None:
        from world.magic.models import CharacterResonance
        from world.scenes.models import Interaction

        interaction = (
            Interaction.objects.select_related("persona__character_sheet").prefetch_related(
                Prefetch(
                    "persona__character_sheet__resonances",
                    queryset=CharacterResonance.objects.select_related("resonance"),
                    to_attr="cached_resonances",
                )
            )
        ).get(pk=self.entry_pose.pk)
        _set_empty_cached_attrs(interaction)

        data = InteractionListSerializer(interaction, context=_make_context()).data
        resonance_list = data["endorsable_resonances"]
        assert isinstance(resonance_list, list)
        returned_ids = {r["id"] for r in resonance_list}
        assert self.r1.pk in returned_ids
        assert self.r2.pk in returned_ids
        for entry in resonance_list:
            assert "id" in entry
            assert "name" in entry

    def test_endorsable_resonances_empty_when_none_claimed(self) -> None:
        from world.scenes.models import Interaction

        bare_sheet = CharacterSheetFactory()
        interaction = InteractionFactory(persona=bare_sheet.primary_persona)
        interaction = Interaction.objects.select_related("persona__character_sheet").get(
            pk=interaction.pk
        )
        _set_empty_cached_attrs(interaction)
        # No cached_resonances attr — serializer falls back to live query (empty).
        data = InteractionListSerializer(interaction, context=_make_context()).data
        assert data["endorsable_resonances"] == []


class Task3PoseEndorsersMyPoseEndorsementTests(TestCase):
    """Task 3: pose_endorsers + my_pose_endorsement."""

    @classmethod
    def setUpTestData(cls) -> None:
        idmapper_models.flush_cache()
        cls.alice_sheet = CharacterSheetFactory()
        cls.alice_persona = cls.alice_sheet.primary_persona
        cls.bob_sheet = CharacterSheetFactory()
        cls.bob_persona = cls.bob_sheet.primary_persona
        cls.resonance = ResonanceFactory()
        cls.entry_pose = InteractionFactory(persona=cls.alice_persona, pose_kind=PoseKind.ENTRY)
        cls.endorsement = PoseEndorsementFactory(
            endorser_sheet=cls.bob_sheet,
            endorsee_sheet=cls.alice_sheet,
            interaction=cls.entry_pose,
            resonance=cls.resonance,
        )

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def _get_endorsement_with_cache(self):
        """Return the endorsement with cached_primary_persona set on endorser_sheet."""
        from world.magic.models import PoseEndorsement

        endorsement = PoseEndorsement.objects.select_related("endorser_sheet", "resonance").get(
            pk=self.endorsement.pk
        )
        endorsement.endorser_sheet.cached_primary_persona = [self.bob_persona]
        return endorsement

    def test_pose_endorsers_list_with_third_party_viewer(self) -> None:
        """A non-participant viewer sees the endorser list."""
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        endorsement = self._get_endorsement_with_cache()
        interaction.cached_endorsements = [endorsement]

        data = InteractionListSerializer(
            interaction, context=_make_context(character_sheet_ids=set())
        ).data
        endorsers = data["pose_endorsers"]
        assert len(endorsers) == 1
        assert endorsers[0]["persona_id"] == self.bob_persona.pk
        assert endorsers[0]["persona_name"] == self.bob_persona.name
        assert endorsers[0]["resonance_id"] == self.resonance.pk

    def test_my_pose_endorsement_when_bob_is_viewer(self) -> None:
        """When Bob views, my_pose_endorsement shows Bob's endorsement."""
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        endorsement = self._get_endorsement_with_cache()
        interaction.cached_endorsements = [endorsement]

        data = InteractionListSerializer(
            interaction,
            context=_make_context(character_sheet_ids={self.bob_sheet.pk}),
        ).data
        my_endorsement = data["my_pose_endorsement"]
        assert my_endorsement is not None
        assert my_endorsement["id"] == endorsement.pk
        assert my_endorsement["resonance_id"] == self.resonance.pk
        # settled_at is None → settled should be False
        assert my_endorsement["settled"] is False

    def test_my_pose_endorsement_none_when_alice_is_viewer(self) -> None:
        """Alice did not endorse her own pose, so my_pose_endorsement is None."""
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        endorsement = self._get_endorsement_with_cache()
        interaction.cached_endorsements = [endorsement]

        data = InteractionListSerializer(
            interaction,
            context=_make_context(character_sheet_ids={self.alice_sheet.pk}),
        ).data
        assert data["my_pose_endorsement"] is None

    def test_pose_endorsers_empty_when_no_endorsements(self) -> None:
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        interaction.cached_endorsements = []
        data = InteractionListSerializer(interaction, context=_make_context()).data
        assert data["pose_endorsers"] == []
        assert data["my_pose_endorsement"] is None


class Task4EntryEndorsersTests(TestCase):
    """Task 4: entry_endorsers + entry_endorsed_by_me."""

    @classmethod
    def setUpTestData(cls) -> None:
        idmapper_models.flush_cache()
        cls.alice_sheet = CharacterSheetFactory()
        cls.alice_persona = cls.alice_sheet.primary_persona
        cls.bob_sheet = CharacterSheetFactory()
        cls.bob_persona = cls.bob_sheet.primary_persona
        cls.resonance = ResonanceFactory()
        cls.scene = SceneFactory()
        cls.entry_pose = InteractionFactory(
            persona=cls.alice_persona, pose_kind=PoseKind.ENTRY, scene=cls.scene
        )
        cls.standard_pose = InteractionFactory(
            persona=cls.alice_persona, pose_kind=PoseKind.STANDARD, scene=cls.scene
        )
        cls.endorsement = SceneEntryEndorsementFactory(
            endorser_sheet=cls.bob_sheet,
            endorsee_sheet=cls.alice_sheet,
            scene=cls.scene,
            resonance=cls.resonance,
        )

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def _build_entry_map(self):
        """Build a scene_entry_endorsements dict with the endorsement loaded."""
        from world.magic.models import SceneEntryEndorsement

        row = SceneEntryEndorsement.objects.select_related("endorser_sheet", "resonance").get(
            pk=self.endorsement.pk
        )
        row.endorser_sheet.cached_primary_persona = [self.bob_persona]
        return {self.alice_sheet.pk: [row]}

    def test_entry_endorsers_has_bob(self) -> None:
        """Third-party viewer sees Bob's entry endorsement for Alice's entry pose."""
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        entry_map = self._build_entry_map()

        data = InteractionListSerializer(
            interaction,
            context=_make_context(
                character_sheet_ids=set(),
                scene_entry_endorsements=entry_map,
            ),
        ).data
        endorsers = data["entry_endorsers"]
        assert len(endorsers) == 1
        assert endorsers[0]["persona_id"] == self.bob_persona.pk
        assert endorsers[0]["persona_name"] == self.bob_persona.name
        assert endorsers[0]["resonance_id"] == self.resonance.pk

    def test_entry_endorsed_by_me_true_for_bob(self) -> None:
        """Bob's viewer context → entry_endorsed_by_me is True for Alice's entry pose."""
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        entry_map = self._build_entry_map()

        data = InteractionListSerializer(
            interaction,
            context=_make_context(
                character_sheet_ids={self.bob_sheet.pk},
                scene_entry_endorsements=entry_map,
            ),
        ).data
        assert data["entry_endorsed_by_me"] is True

    def test_entry_endorsed_by_me_false_for_alice(self) -> None:
        """Alice (endorsee) did not endorse herself, so entry_endorsed_by_me is False."""
        interaction = self.entry_pose
        _set_empty_cached_attrs(interaction)
        entry_map = self._build_entry_map()

        data = InteractionListSerializer(
            interaction,
            context=_make_context(
                character_sheet_ids={self.alice_sheet.pk},
                scene_entry_endorsements=entry_map,
            ),
        ).data
        assert data["entry_endorsed_by_me"] is False

    def test_standard_pose_returns_empty_for_entry_endorsement_fields(self) -> None:
        """STANDARD poses always return empty entry_endorsers and False entry_endorsed_by_me."""
        interaction = self.standard_pose
        _set_empty_cached_attrs(interaction)
        entry_map = self._build_entry_map()

        data = InteractionListSerializer(
            interaction,
            context=_make_context(
                character_sheet_ids={self.bob_sheet.pk},
                scene_entry_endorsements=entry_map,
            ),
        ).data
        assert data["entry_endorsers"] == []
        assert data["entry_endorsed_by_me"] is False
