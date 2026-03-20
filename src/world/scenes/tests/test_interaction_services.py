from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import GuiseFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    ScenePrivacyMode,
)
from world.scenes.factories import (
    InteractionAudienceFactory,
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
)
from world.scenes.interaction_services import (
    can_view_interaction,
    create_interaction,
    delete_interaction,
    mark_very_private,
)
from world.scenes.models import Interaction, InteractionAudience


class TestCreateInteraction(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_guise = GuiseFactory()
        cls.writer_persona = PersonaFactory(guise=cls.writer_guise)
        cls.audience_guise_1 = GuiseFactory()
        cls.audience_guise_2 = GuiseFactory()

    def test_basic_creation_with_audience(self) -> None:
        interaction = create_interaction(
            persona=self.writer_persona,
            content="strides into the room.",
            mode=InteractionMode.POSE,
            audience_guises=[self.audience_guise_1, self.audience_guise_2],
        )
        assert interaction is not None
        assert interaction.content == "strides into the room."
        assert interaction.mode == InteractionMode.POSE
        assert interaction.persona == self.writer_persona
        assert interaction.scene is None
        assert InteractionAudience.objects.filter(interaction=interaction).count() == 2

    def test_creation_with_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        interaction = create_interaction(
            persona=self.writer_persona,
            content="waves hello.",
            mode=InteractionMode.POSE,
            audience_guises=[self.audience_guise_1],
            scene=scene,
        )
        assert interaction is not None
        assert interaction.scene == scene

    def test_ephemeral_scene_returns_none(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        interaction = create_interaction(
            persona=self.writer_persona,
            content="secret whisper",
            mode=InteractionMode.WHISPER,
            audience_guises=[self.audience_guise_1],
            scene=scene,
        )
        assert interaction is None
        assert Interaction.objects.count() == 0
        assert InteractionAudience.objects.count() == 0

    def test_creation_with_target_personas(self) -> None:
        scene = SceneFactory()
        audience_persona = PersonaFactory(guise=self.audience_guise_1)
        interaction = create_interaction(
            persona=self.writer_persona,
            content="looks at someone.",
            mode=InteractionMode.POSE,
            audience_guises=[self.audience_guise_1],
            scene=scene,
            target_personas=[audience_persona],
        )
        assert interaction is not None
        assert audience_persona in interaction.target_personas.all()

    def test_creation_with_audience_personas(self) -> None:
        audience_persona = PersonaFactory(guise=self.audience_guise_1)
        interaction = create_interaction(
            persona=self.writer_persona,
            content="nods.",
            mode=InteractionMode.POSE,
            audience_guises=[self.audience_guise_1],
            audience_personas={self.audience_guise_1.pk: audience_persona},
        )
        assert interaction is not None
        aud = InteractionAudience.objects.get(
            interaction=interaction,
            guise=self.audience_guise_1,
        )
        assert aud.persona == audience_persona


class TestCanViewInteraction(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_guise = GuiseFactory()
        cls.writer_persona = PersonaFactory(guise=cls.writer_guise)
        cls.audience_guise = GuiseFactory()
        cls.outsider_guise = GuiseFactory()

    def _make_interaction(
        self,
        *,
        mode: str = InteractionMode.POSE,
        visibility: str = InteractionVisibility.DEFAULT,
        scene: "SceneFactory | None" = None,
    ) -> Interaction:
        interaction = InteractionFactory(
            persona=self.writer_persona,
            mode=mode,
            visibility=visibility,
            scene=scene,
        )
        InteractionAudienceFactory(
            interaction=interaction,
            guise=self.audience_guise,
        )
        return interaction

    def test_audience_can_view_default(self) -> None:
        interaction = self._make_interaction()
        assert can_view_interaction(interaction, self.audience_guise) is True

    def test_outsider_cannot_view_private_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        interaction = self._make_interaction(scene=scene)
        assert can_view_interaction(interaction, self.outsider_guise) is False

    def test_staff_can_view_private_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        interaction = self._make_interaction(scene=scene)
        assert can_view_interaction(interaction, self.outsider_guise, is_staff=True) is True

    def test_staff_cannot_view_very_private(self) -> None:
        interaction = self._make_interaction(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(interaction, self.outsider_guise, is_staff=True) is False

    def test_audience_can_view_very_private(self) -> None:
        interaction = self._make_interaction(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(interaction, self.audience_guise) is True

    def test_writer_can_view_own(self) -> None:
        interaction = self._make_interaction(
            visibility=InteractionVisibility.VERY_PRIVATE,
        )
        assert can_view_interaction(interaction, self.writer_guise) is True

    def test_public_scene_viewable_by_anyone(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        interaction = self._make_interaction(scene=scene)
        assert can_view_interaction(interaction, self.outsider_guise) is True

    def test_whisper_without_scene_only_audience(self) -> None:
        interaction = self._make_interaction(mode=InteractionMode.WHISPER)
        assert can_view_interaction(interaction, self.audience_guise) is True
        assert can_view_interaction(interaction, self.outsider_guise) is False


class TestMarkVeryPrivate(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_guise = GuiseFactory()
        cls.writer_persona = PersonaFactory(guise=cls.writer_guise)
        cls.audience_guise = GuiseFactory()
        cls.outsider_guise = GuiseFactory()

    def _make_interaction(self) -> Interaction:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        InteractionAudienceFactory(
            interaction=interaction,
            guise=self.audience_guise,
        )
        return interaction

    def test_audience_can_mark(self) -> None:
        interaction = self._make_interaction()
        mark_very_private(interaction, self.audience_guise)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE

    def test_writer_can_mark(self) -> None:
        interaction = self._make_interaction()
        mark_very_private(interaction, self.writer_guise)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE

    def test_outsider_cannot_mark(self) -> None:
        interaction = self._make_interaction()
        mark_very_private(interaction, self.outsider_guise)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.DEFAULT

    def test_already_very_private_stays(self) -> None:
        interaction = self._make_interaction()
        interaction.visibility = InteractionVisibility.VERY_PRIVATE
        interaction.save(update_fields=["visibility"])
        mark_very_private(interaction, self.audience_guise)
        interaction.refresh_from_db()
        assert interaction.visibility == InteractionVisibility.VERY_PRIVATE


class TestDeleteInteraction(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer_guise = GuiseFactory()
        cls.writer_persona = PersonaFactory(guise=cls.writer_guise)
        cls.other_guise = GuiseFactory()

    def test_writer_can_delete_within_window(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        pk = interaction.pk
        result = delete_interaction(interaction, self.writer_guise)
        assert result is True
        assert not Interaction.objects.filter(pk=pk).exists()

    def test_non_writer_cannot_delete(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        result = delete_interaction(interaction, self.other_guise)
        assert result is False
        assert Interaction.objects.filter(pk=interaction.pk).exists()

    def test_cannot_delete_after_window(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        old_time = timezone.now() - timedelta(days=31)
        Interaction.objects.filter(pk=interaction.pk).update(timestamp=old_time)
        # SharedMemoryModel identity map caches instances, so .get() and
        # refresh_from_db() may return stale field values after a queryset
        # .update(). Flush the specific cache entry so the next fetch hits DB.
        Interaction.flush_cached_instance(interaction, force=True)
        interaction = Interaction.objects.get(pk=interaction.pk)
        result = delete_interaction(interaction, self.writer_guise)
        assert result is False
        assert Interaction.objects.filter(pk=interaction.pk).exists()

    def test_hard_delete_truly_gone(self) -> None:
        interaction = InteractionFactory(
            persona=self.writer_persona,
        )
        InteractionAudienceFactory(
            interaction=interaction,
            guise=self.other_guise,
        )
        pk = interaction.pk
        delete_interaction(interaction, self.writer_guise)
        assert not Interaction.objects.filter(pk=pk).exists()
        assert not InteractionAudience.objects.filter(interaction_id=pk).exists()
