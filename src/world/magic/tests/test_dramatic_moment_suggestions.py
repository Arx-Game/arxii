"""Tests for the technique-entrance suggestion bridge (#2183).

Task 3 of the dramatic-technique-driven-combat-entrance feature: the
GMPrompt model + maybe_suggest_dramatic_moments /
resolve_dramatic_moment_suggestion services + the "Grand Entrance" seed. Nothing
calls these services yet — Tasks 4/5/6 wire the actual technique-entrance cast
path to maybe_suggest_dramatic_moments and a GM-facing resolve surface to
resolve_dramatic_moment_suggestion.
"""

from unittest import mock

from django.test import TestCase, override_settings

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptGroup, GMPromptStatus
from world.gm.factories import GMPromptFilterFactory
from world.gm.models import GMPrompt
from world.magic.constants import GainSource
from world.magic.exceptions import DramaticMomentSuggestionAlreadyResolved
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
    ResonanceFactory,
    ensure_dramatic_entrance_content,
)
from world.magic.models import CharacterResonance, ResonanceGrant
from world.magic.models.dramatic_moment import DramaticMomentType
from world.magic.services.gain import (
    maybe_suggest_dramatic_moments,
    resolve_dramatic_moment_suggestion,
)
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
)


class MaybeSuggestDramaticMomentsTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            suggest_on_technique_entrance=True,
            suggestion_min_success_level=3,
            per_scene_cap=1,
        )
        self.scene = SceneFactory()
        self.interaction = InteractionFactory(scene=self.scene)

    def test_suggest_creates_pending_rows(self):
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=3,
            interaction=self.interaction,
        )
        self.assertEqual(len(created), 1)
        suggestion = created[0]
        self.assertEqual(suggestion.status, GMPromptStatus.PENDING)
        self.assertEqual(suggestion.success_level, 3)
        self.assertEqual(suggestion.scene, self.scene)
        self.assertEqual(suggestion.interaction, self.interaction)
        self.assertEqual(suggestion.interaction_timestamp, self.interaction.timestamp)
        self.assertEqual(GMPrompt.objects.filter(status=GMPromptStatus.PENDING).count(), 1)

    def test_suggest_respects_threshold(self):
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=2,
        )
        self.assertEqual(created, [])
        self.assertFalse(GMPrompt.objects.exists())

    def test_suggest_skips_unflagged(self):
        self.moment_type.suggest_on_technique_entrance = False
        self.moment_type.save()
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(GMPrompt.objects.exists())

    def test_suggest_does_not_filter_on_claimed_resonance(self):
        """Eligibility is the success threshold and the per-scene cap, nothing else.

        The old claimed-resonance filter (ruled out 2026-08-04) made a moment
        type unreachable the moment its authored resonance was one nobody
        claims — which is exactly what happened to the only authored type.
        What the moment resonates AS is resolved at confirm time instead.
        """
        other_sheet = CharacterSheetFactory()
        created = maybe_suggest_dramatic_moments(
            character_sheet=other_sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].character_sheet, other_sheet)
        self.assertTrue(GMPrompt.objects.exists())

    def test_suggest_records_the_entrance_technique(self):
        """The technique is carried so confirm-time can read its woven thread."""
        from world.magic.factories import TechniqueFactory

        technique = TechniqueFactory()
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
            technique=technique,
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].technique, technique)

    def test_suggest_skips_capped(self):
        DramaticMomentTagFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(GMPrompt.objects.exists())

    def test_suggest_idempotent_per_scene(self):
        first = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=3,
        )
        self.assertEqual(len(first), 1)
        second = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=4,
        )
        self.assertEqual(second, [])
        self.assertEqual(GMPrompt.objects.filter(status=GMPromptStatus.PENDING).count(), 1)

    def test_suggest_returns_empty_without_scene(self):
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=None,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(GMPrompt.objects.exists())

    def test_suggest_skips_when_every_scene_gm_muted_dramatic_moment(self):
        """#4101 fix round 1: the group-mute check is now one batched query
        (prompt_recipients) instead of a per-GM prompts_enabled() loop -- same
        semantics, proven here: every scene GM muted the group means no suggestion."""
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=gm)
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.DRAMATIC_MOMENT, enabled=False)
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(GMPrompt.objects.exists())

    def test_suggest_proceeds_when_one_of_two_gms_unmuted(self):
        muted_gm = AccountFactory()
        unmuted_gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=muted_gm)
        SceneGMParticipationFactory(scene=self.scene, account=unmuted_gm)
        GMPromptFilterFactory(account=muted_gm, group=GMPromptGroup.DRAMATIC_MOMENT, enabled=False)
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(len(created), 1)

    def test_suggest_proceeds_with_no_scene_gms(self):
        """No GM participations at all -- the gate only screens an existing,
        fully-muted GM pool, never an empty one (matches the pre-fix behavior)."""
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(len(created), 1)

    def test_new_suggestion_is_pushed_live_to_unmuted_scene_gms(self):
        """#4101 final review, F1: a dramatic moment reaches the scene's GMs live
        with the same gm_prompt frame a narration prompt gets; a GM who muted the
        group and a non-GM owner get nothing."""
        gm = AccountFactory()
        muted_gm = AccountFactory()
        owner = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=gm)
        SceneGMParticipationFactory(scene=self.scene, account=muted_gm)
        SceneOwnerParticipationFactory(scene=self.scene, account=owner)
        GMPromptFilterFactory(account=muted_gm, group=GMPromptGroup.DRAMATIC_MOMENT, enabled=False)
        for account in (gm, muted_gm, owner):
            account.msg = mock.Mock()
        with self.captureOnCommitCallbacks(execute=True):
            [created] = maybe_suggest_dramatic_moments(
                character_sheet=self.sheet, scene=self.scene, success_level=5
            )
        gm.msg.assert_called_once()
        self.assertEqual(
            gm.msg.call_args.kwargs["gm_prompt"][1],
            {"prompt_id": created.pk, "scene_id": self.scene.pk, "kind": created.kind},
        )
        muted_gm.msg.assert_not_called()
        owner.msg.assert_not_called()


class ResolveDramaticMomentSuggestionTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            resonance_amount=15,
            suggest_on_technique_entrance=True,
            suggestion_min_success_level=3,
        )
        self.scene = SceneFactory()
        self.resolver = AccountFactory()
        [self.suggestion] = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=4,
        )

    def test_confirm_creates_tag_and_links(self):
        resolved = resolve_dramatic_moment_suggestion(
            self.suggestion, resolver=self.resolver, confirm=True
        )
        self.assertEqual(resolved.status, GMPromptStatus.CONFIRMED)
        self.assertIsNotNone(resolved.confirmed_tag)
        self.assertEqual(resolved.resolved_by, self.resolver)
        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.balance, 15)
        grant = ResonanceGrant.objects.get(source=GainSource.DRAMATIC_MOMENT)
        self.assertEqual(grant.amount, 15)

    def test_dismiss_no_tag(self):
        resolved = resolve_dramatic_moment_suggestion(
            self.suggestion, resolver=self.resolver, confirm=False
        )
        self.assertEqual(resolved.status, GMPromptStatus.DISMISSED)
        self.assertIsNone(resolved.confirmed_tag)
        self.assertEqual(resolved.resolved_by, self.resolver)
        self.assertFalse(ResonanceGrant.objects.filter(source=GainSource.DRAMATIC_MOMENT).exists())

    def test_double_resolve_raises(self):
        resolve_dramatic_moment_suggestion(self.suggestion, resolver=self.resolver, confirm=False)
        with self.assertRaises(DramaticMomentSuggestionAlreadyResolved):
            resolve_dramatic_moment_suggestion(
                self.suggestion, resolver=self.resolver, confirm=True
            )

    def test_resolve_refuses_non_dramatic_moment_kind(self):
        """#4101 fix round 1: this service must never act on a narration prompt."""
        from world.gm.constants import GMPromptKind
        from world.gm.prompt_services import route_narratable_event
        from world.gm.types import NarratableEvent
        from world.magic.exceptions import DramaticMomentSuggestionWrongKind

        [narration_prompt] = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.DEATH,
                scene=self.scene,
                character_sheet=self.sheet,
            ),
            candidates=[self.resolver],
        )
        with self.assertRaises(DramaticMomentSuggestionWrongKind):
            resolve_dramatic_moment_suggestion(
                narration_prompt, resolver=self.resolver, confirm=False
            )


@override_settings(SEED_SAMPLE_CONTENT=True)
class EnsureDramaticEntranceContentTest(TestCase):
    """Exercises the sample-seeding path directly (#2698) — the DramaticMomentType
    is content-repo-owned, so this suite needs ``SEED_SAMPLE_CONTENT`` on to get
    a real row to test idempotency against.
    """

    def test_seed_creates_no_resonance(self):
        """#2967: "Grand Entrance" is seeded unpinned, not against an invented
        "Fervor" nobody could claim."""
        from world.magic.models import Resonance

        moment_type = ensure_dramatic_entrance_content()

        self.assertIsNone(moment_type.resonance_id)
        self.assertFalse(Resonance.objects.exists())

    def test_seed_idempotent(self):
        first = ensure_dramatic_entrance_content()
        second = ensure_dramatic_entrance_content()
        self.assertEqual(first.pk, second.pk)
        qs = DramaticMomentType.objects.filter(label="Grand Entrance")
        self.assertEqual(qs.count(), 1)
        moment_type = qs.get()
        self.assertTrue(moment_type.suggest_on_technique_entrance)
        self.assertEqual(moment_type.suggestion_min_success_level, 3)

    def test_seed_preserves_staff_edits(self):
        """A re-run must not clobber staff tuning of the existing row (#2183)."""
        first = ensure_dramatic_entrance_content()
        first.resonance_amount = 999
        first.save(update_fields=["resonance_amount"])

        second = ensure_dramatic_entrance_content()

        self.assertEqual(first.pk, second.pk)
        qs = DramaticMomentType.objects.filter(label="Grand Entrance")
        self.assertEqual(qs.count(), 1)
        moment_type = qs.get()
        self.assertEqual(moment_type.resonance_amount, 999)
