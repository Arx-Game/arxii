"""E2E for #1466 Tasks 5-6: danger is an ordinary STRICT scene round, and combat-end
hands off lingering acute peril to a scene round.

Task 5 — Danger stops being a round *type*. A peril (Bleeding-Out / Plummeting / poison
DoT) arising outside combat spins up a STRICT ``SceneRound(start_reason=DANGER)`` that
enrols everyone present. The peril ticks at *round resolution* — driven by a present,
conscious bystander declaring (presence-gated). When the peril clears, the round
auto-ends (COMPLETED) instead of starting the next round.

Task 6 — When a combat encounter ends while a participant is still Bleeding-Out,
``complete_encounter`` must hand the peril off to a scene round. The scene round exists
and advances the bleed-out when a present bystander declares.

AFK-safety guarantees (Task 5):
- An unconscious present victim must NOT deadlock the round (``can_act`` implicit-pass).
- A lone AFK victim with no conscious bystander does NOT advance the peril.
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import (
    BLEED_OUT_CONDITION_NAME,
    UNCONSCIOUS_CONDITION_NAME,
    DurationType,
    FoundationalCapability,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.scenes.constants import (
    RoundStatus,
    SceneRoundMode,
    SceneRoundStartReason,
)
from world.scenes.models import SceneActionDeclaration, SceneRound, SceneRoundParticipant
from world.scenes.round_services import (
    ensure_round_for_acute_condition,
    maybe_resolve_scene_round,
)


def _bleed_present(sheet):
    return ConditionInstance.objects.filter(
        target=sheet.character, condition__name=BLEED_OUT_CONDITION_NAME
    ).exists()


def _make_room():
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


def _char_in_room(room):
    sheet = CharacterSheetFactory()
    sheet.character.db_location = room
    sheet.character.save(update_fields=["db_location"])
    return sheet


def _give_bleed_out(sheet, *, rounds_remaining=1):
    """Apply a ROUNDS-duration Bleeding-Out condition that the end-tick will clear."""
    template = ConditionTemplateFactory(
        name=BLEED_OUT_CONDITION_NAME,
        default_duration_type=DurationType.ROUNDS,
        default_duration_value=rounds_remaining,
    )
    return ConditionInstanceFactory(
        target=sheet.character, condition=template, rounds_remaining=rounds_remaining
    )


def _declare_pass(rnd, participant):
    return SceneActionDeclaration.objects.create(
        scene_round=rnd,
        round_number=rnd.round_number,
        participant=participant,
        is_pass=True,
        is_immediate=False,
    )


def _participant(rnd, sheet):
    return SceneRoundParticipant.objects.get(scene_round=rnd, character_sheet=sheet)


class DangerAsStrictSceneRoundTest(TestCase):
    def setUp(self):
        self.room = _make_room()

    def test_danger_out_of_combat_uses_strict_scene_round(self):
        """A bleeding victim with a conscious bystander, no combat:

        - ``ensure_round_for_acute_condition`` yields a STRICT round.
        - the bystander declaring (presence-complete) drives ``maybe_resolve_scene_round``,
          which ticks the acute condition.
        - once the peril clears, the round auto-ends (COMPLETED).
        """
        victim = _char_in_room(self.room)
        bystander = _char_in_room(self.room)
        _give_bleed_out(victim, rounds_remaining=1)

        rnd = ensure_round_for_acute_condition(victim)
        assert rnd is not None
        assert rnd.start_reason == SceneRoundStartReason.DANGER
        # The behavioral heart of #1466: danger is NOT forced OPEN; it is STRICT.
        assert rnd.mode == SceneRoundMode.STRICT
        assert rnd.status == RoundStatus.DECLARING

        # Both present conscious participants declare -> presence-gated completion met.
        _declare_pass(rnd, _participant(rnd, victim))
        _declare_pass(rnd, _participant(rnd, bystander))
        maybe_resolve_scene_round(rnd)

        rnd.refresh_from_db()
        # The peril cleared (bleed-out expired in the end-tick) -> danger round auto-ends.
        assert not _bleed_present(victim)
        assert rnd.status == RoundStatus.COMPLETED


class DangerRoundAfkSafetyTest(TestCase):
    """AFK-safety is inherited from presence-gating."""

    def setUp(self):
        self.room = _make_room()

    def test_lone_afk_victim_does_not_advance(self):
        """A lone victim (no conscious bystander) -> nobody declares -> no resolution ->
        the peril does NOT advance (the round stays DECLARING, bleed-out intact)."""
        victim = _char_in_room(self.room)
        bleed = _give_bleed_out(victim, rounds_remaining=2)

        rnd = ensure_round_for_acute_condition(victim)
        assert rnd is not None
        assert rnd.mode == SceneRoundMode.STRICT

        # Nobody declares; the only present participant is the AFK victim.
        maybe_resolve_scene_round(rnd)

        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.DECLARING  # did not advance
        bleed.refresh_from_db()
        assert bleed.rounds_remaining == 2  # peril did not tick

    def test_unconscious_present_victim_does_not_deadlock(self):
        """An unconscious *present* victim is an implicit pass (``can_act`` False), so a
        conscious bystander's declaration alone drives resolution — no deadlock."""
        victim = _char_in_room(self.room)
        bystander = _char_in_room(self.room)
        _give_bleed_out(victim, rounds_remaining=1)
        # Seed AWARENESS; an Unconscious condition zeroes it -> can_act(victim) is False.
        awareness = CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
        unconscious_template = ConditionTemplateFactory(
            name=UNCONSCIOUS_CONDITION_NAME,
            default_duration_type=DurationType.UNTIL_CURED,
        )
        ConditionCapabilityEffectFactory(
            condition=unconscious_template, capability=awareness, value=-100
        )
        ConditionInstanceFactory(target=victim.character, condition=unconscious_template)

        rnd = ensure_round_for_acute_condition(victim)
        assert rnd is not None

        # Only the conscious bystander declares; the unconscious victim never will.
        _declare_pass(rnd, _participant(rnd, bystander))
        maybe_resolve_scene_round(rnd)

        rnd.refresh_from_db()
        # Resolution happened despite the victim having no declaration -> auto-ended.
        assert rnd.status == RoundStatus.COMPLETED


class CombatEndHandOffTest(TestCase):
    """Task 6: when a combat encounter ends with a participant still Bleeding-Out,
    ``complete_encounter`` must hand the peril off to a scene round."""

    def setUp(self):
        from evennia import create_object

        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.scenes.constants import RoundStatus
        from world.scenes.factories import SceneFactory
        from world.vitals.models import CharacterVitals

        # Build a room + encounter in it.
        self.room = create_object("typeclasses.rooms.Room", key="Hand-off Room", nohome=True)
        scene = SceneFactory(location=self.room)
        self.encounter = CombatEncounterFactory(
            scene=scene, room=self.room, status=RoundStatus.BETWEEN_ROUNDS
        )

        # Participant (victim) — place in the room so ensure_round can find them.
        self.victim_sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(
            character_sheet=self.victim_sheet, health=100, max_health=100
        )
        self.victim_sheet.character.db_location = self.room
        self.victim_sheet.character.save(update_fields=["db_location"])
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.victim_sheet,
            status=ParticipantStatus.ACTIVE,
        )

        # A conscious bystander in the room who can drive resolution.
        self.bystander_sheet = CharacterSheetFactory()
        self.bystander_sheet.character.db_location = self.room
        self.bystander_sheet.character.save(update_fields=["db_location"])

        # Give the victim a ROUNDS-duration Bleeding-Out that the end-tick will decrement.
        template = ConditionTemplateFactory(
            name=BLEED_OUT_CONDITION_NAME,
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=2,
        )
        self.bleed_instance = ConditionInstanceFactory(
            target=self.victim_sheet.character, condition=template, rounds_remaining=2
        )

    def test_combat_end_hands_off_bleed_out_to_scene_round(self):
        """Task 6 RED→GREEN gate.

        An encounter completes while a participant is Bleeding-Out:
        1. A STRICT ``SceneRound(start_reason=DANGER)`` must exist in the room afterward.
        2. The victim is enrolled in that round.
        3. A present bystander declaring + ``maybe_resolve_scene_round`` advances the bleed-out
           (rounds_remaining decrements), confirming the peril is being driven by the round.
        """
        from world.combat.constants import EncounterOutcome
        from world.combat.services import complete_encounter

        complete_encounter(self.encounter, outcome=EncounterOutcome.ABANDONED)

        # --- Assertion 1: a STRICT DANGER scene round now exists in the room. ---
        rnd = SceneRound.objects.filter(room=self.room, status=RoundStatus.DECLARING).first()
        assert rnd is not None, "Expected a DECLARING scene round after combat end, found none."
        assert rnd.mode == SceneRoundMode.STRICT, f"Expected STRICT mode, got {rnd.mode!r}"
        assert rnd.start_reason == SceneRoundStartReason.DANGER, (
            f"Expected DANGER start_reason, got {rnd.start_reason!r}"
        )

        # --- Assertion 2: the victim is enrolled. ---
        enrolled = SceneRoundParticipant.objects.filter(
            scene_round=rnd, character_sheet=self.victim_sheet
        ).exists()
        assert enrolled, "Expected victim to be enrolled in the scene round."

        # --- Assertion 3: driving the round advances the bleed-out. ---
        # All present participants (victim + bystander) declare passes so the
        # presence-gated completion rule is met and the round resolves.
        victim_participant = SceneRoundParticipant.objects.get(
            scene_round=rnd, character_sheet=self.victim_sheet
        )
        bystander_participant = SceneRoundParticipant.objects.get(
            scene_round=rnd, character_sheet=self.bystander_sheet
        )
        for p in (victim_participant, bystander_participant):
            SceneActionDeclaration.objects.create(
                scene_round=rnd,
                round_number=rnd.round_number,
                participant=p,
                is_pass=True,
                is_immediate=False,
            )
        maybe_resolve_scene_round(rnd)

        self.bleed_instance.refresh_from_db()
        assert self.bleed_instance.rounds_remaining == 1, (
            f"Expected bleed-out rounds_remaining to decrement to 1, "
            f"got {self.bleed_instance.rounds_remaining}"
        )
