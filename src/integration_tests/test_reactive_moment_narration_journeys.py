"""Journeys for the lines a reactive condition tells when it fires (#4587).

Brenna and Cassian stand against a hired brute in the Yard, as in the holding-the-line
journeys (#4584), and Dara stands by and watches without fighting. A condition that answers
the fight does five things that used to happen in silence: it strikes back, its source
steps in for her ward, it turns the brute on its source, it keeps Cassian on his feet through
a knockout, and a once-only condition is used up. Staff write one line for each moment on
the condition; a moment with no line gets a plain one.

Every expected line below is written out from the authored text and the names in the world
(the brute is "Hired Brute", the players are named for their characters), never read back
from the code under test. Each moment is told twice in one journey, round 1 with an authored
line and round 2 after staff blank it, so the same journey shows both the authored line and
the plain fallback.

The round's narration reaches the room two ways, as an OUTCOME row in the scene log and as
the row pushed live to everyone standing there; the journeys assert both carry the same line.
A moment that is hidden by design (a condition not visible to others, a concealed source) is
told only to the two people it concerns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.test import override_settings

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from integration_tests.test_holding_the_line_journeys import (
    GRACE_HEALTH,
    GRACE_SWING,
    _TheGuardedYard,
    _TheYard,
)
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import SeededLevelLadderMixin, force_check_outcome
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionCheckModifierFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
    UnconsciousConditionFactory,
)
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import apply_condition, spend_condition_use
from world.scenes.constants import InteractionMode, PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.models import Interaction
from world.scenes.services import set_active_persona
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals
from world.vitals.services import get_vitals_consequence_config

if TYPE_CHECKING:
    from world.traits.models import CheckOutcome

BRUTE = "Hired Brute"


class _TheYardWatched(_TheYard):
    """The Yard with Dara watching, and the helpers that read what the room was told."""

    def setUp(self) -> None:
        super().setUp()
        self.brute.name = BRUTE
        self.brute.save(update_fields=["name"])
        self.dara = self.make_player("Dara", room=self.yard)
        self.watch(self.brenna, self.cassian, self.dara)

    def _log(self) -> list[Interaction]:
        """Every Narrator OUTCOME row so far, oldest first."""
        return list(Interaction.objects.filter(mode=InteractionMode.OUTCOME).order_by("pk"))

    def _lines_since(self, mark: int) -> list[str]:
        """The OUTCOME lines written after ``mark`` rows of the scene log."""
        return [row.content for row in self._log()[mark:]]

    def _mark(self) -> int:
        return len(self._log())

    def _set_line(self, template: ConditionTemplate, field: str, text: str) -> None:
        setattr(template, field, text)
        template.save(update_fields=[field])

    def assertRoomHeard(self, line: str, since: int) -> None:  # noqa: N802
        """The scene log holds ``line`` once, and Dara was pushed that same line live."""
        self.assertEqual(self._lines_since(since).count(line), 1, self._lines_since(since))
        self.assertShownRow(self.dara, line)

    def assertToldInFightScene(self, line: str) -> None:  # noqa: N802
        """A private whisper of ``line`` sits in the fight's own scene, where a refetch finds it."""
        self.assertTrue(
            Interaction.objects.filter(
                content=line, mode=InteractionMode.WHISPER, scene=self.encounter.scene
            ).exists()
        )

    def assertNotInRoomFeed(self, line: str, since: int) -> None:  # noqa: N802
        """``line`` is in no OUTCOME row since ``since`` and Dara was never pushed it."""
        self.assertNotIn(line, self._lines_since(since))
        self.assertFalse(any(line in row for row in self.mailbox(self.dara).rows))


class StrikeBackIsNarrated(_TheYardWatched):
    """A thorn ward on Cassian, with Brenna as its source, strikes the brute back."""

    def setUp(self) -> None:
        super().setUp()
        self.thorn_ward = ConditionTemplateFactory(
            name="Thorn Ward",
            retaliation_damage=5,
            retaliation_damage_type=DamageTypeFactory(name="Thorn"),
            retaliation_narration=(
                "Thorns lash from {bearer} and rake {attacker}, as {source} willed."
            ),
        )
        apply_condition(self.cassian, self.thorn_ward, source_character=self.brenna)

    def test_the_room_hears_the_authored_line_and_then_the_plain_one(self) -> None:
        mark = self._mark()
        self._round()
        self.assertRoomHeard(f"Thorns lash from Cassian and rake {BRUTE}, as Brenna willed.", mark)

        self._set_line(self.thorn_ward, "retaliation_narration", "")
        self._next_round()
        mark = self._mark()
        self._round()
        self.assertRoomHeard(f"Cassian's Thorn Ward strikes {BRUTE} back.", mark)

    def test_the_line_names_the_face_a_character_presents(self) -> None:
        veil = PersonaFactory(
            character_sheet=self.brenna.sheet_data,
            name="the Veiled Warden",
            persona_type=PersonaType.ESTABLISHED,
        )
        set_active_persona(self.brenna.sheet_data, veil)

        mark = self._mark()
        self._round()

        line = f"Thorns lash from Cassian and rake {BRUTE}, as the Veiled Warden willed."
        self.assertRoomHeard(line, mark)
        self.assertNotIn("Brenna", line)

    def test_a_hidden_ward_is_told_only_to_the_bearer_and_the_source(self) -> None:
        self.thorn_ward.is_visible_to_others = False
        self.thorn_ward.save(update_fields=["is_visible_to_others"])
        line = f"Thorns lash from Cassian and rake {BRUTE}, as Brenna willed."

        mark = self._mark()
        self._round()

        self.assertNotInRoomFeed(line, mark)
        self.assertShownRow(self.cassian, line)
        self.assertShownRow(self.brenna, line)
        self.assertToldInFightScene(line)

    def test_a_concealed_source_is_told_only_to_the_bearer_and_the_source(self) -> None:
        unseen = ConditionTemplateFactory(
            name="Unseen", category=ConditionCategoryFactory(conceals_from_perception=True)
        )
        apply_condition(self.brenna, unseen)
        line = f"Thorns lash from Cassian and rake {BRUTE}, as Brenna willed."

        mark = self._mark()
        self._round()

        self.assertNotInRoomFeed(line, mark)
        self.assertShownRow(self.cassian, line)
        self.assertShownRow(self.brenna, line)
        self.assertToldInFightScene(line)


class GuardIsNarrated(_TheYardWatched, _TheGuardedYard):
    """Brenna's standing guard over Cassian steps into the brute's swing."""

    def test_the_room_hears_the_authored_line_and_then_the_plain_one(self) -> None:
        self._set_line(
            self.bodyguards_watch,
            "guard_narration",
            "{source} throws herself between {bearer} and {attacker}.",
        )
        mark = self._mark()
        self._guarded_round()
        self.assertRoomHeard(f"Brenna throws herself between Cassian and {BRUTE}.", mark)

        self._set_line(self.bodyguards_watch, "guard_narration", "")
        self._next_round()
        mark = self._mark()
        self._guarded_round()
        self.assertRoomHeard(f"Brenna steps between Cassian and {BRUTE}.", mark)


class ProvokeIsNarrated(_TheYardWatched):
    """A call-out laid on the brute by Brenna turns it from Cassian onto her."""

    def test_the_room_hears_the_authored_line_and_then_the_plain_one(self) -> None:
        self._set_line(self.called_out, "provoke_narration", "{bearer} rounds on {source}!")
        apply_condition(self.brute.objectdb, self.called_out, source_character=self.brenna)

        mark = self._mark()
        self._round()
        self.assertRoomHeard(f"{BRUTE} rounds on Brenna!", mark)
        self.assertEqual(self._swing_targets(round_number=1), [self.brenna_seat])

        self._set_line(self.called_out, "provoke_narration", "")
        self._next_round()
        mark = self._mark()
        self._round()
        self.assertRoomHeard(f"{BRUTE} turns on Brenna.", mark)


@override_settings(SEED_SAMPLE_CONTENT=True)  # the Endurance check type gates on #2698
class GraceIsNarrated(SeededLevelLadderMixin, _TheYardWatched):
    """A 3-round grace on Cassian, at 15 of 100 health, stops a knockout twice."""

    def test_the_room_hears_the_authored_line_and_then_the_plain_one(self) -> None:
        vitals = CharacterVitals.objects.get(character_sheet=self.cassian.sheet_data)
        vitals.health = GRACE_HEALTH
        vitals.save(update_fields=["health"])
        self.swing.base_damage = GRACE_SWING
        self.swing.save(update_fields=["base_damage"])
        failure = self._knockout_pool_of(UnconsciousConditionFactory())
        steady = ConditionTemplateFactory(
            name="Steady Footing",
            prevents_knockout=True,
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
            grace_narration="{bearer} refuses to fall.",
        )
        apply_condition(self.cassian, steady)

        mark = self._mark()
        with force_check_outcome(failure):
            self._round()
        self.assertRoomHeard("Cassian refuses to fall.", mark)

        self._set_line(steady, "grace_narration", "")
        self._next_round()
        mark = self._mark()
        with force_check_outcome(failure):
            self._round()
        self.assertRoomHeard("Cassian's Steady Footing keeps them on their feet.", mark)

    def _knockout_pool_of(self, unconscious: ConditionTemplate) -> CheckOutcome:
        """The knockout pool: a failed knockout roll applies Unconscious. Returns that failure."""
        failure = CheckOutcomeFactory(name="Narration-KO-Failure", success_level=-1)
        consequence = ConsequenceFactory(outcome_tier=failure, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=unconscious,
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        config = get_vitals_consequence_config()
        config.knockout_pool = pool
        config.save(update_fields=["knockout_pool"])
        return failure


class SpentIsNarrated(_TheYardWatched):
    """A once-only blessing on Brenna helps her offence roll and is used up."""

    def setUp(self) -> None:
        super().setUp()
        self.steadying_word = ConditionTemplateFactory(
            name="Steadying Word",
            default_duration_type=DurationType.UNTIL_USED,
            spent_narration="{bearer}'s resolve is used up.",
        )
        ConditionCheckModifierFactory(
            condition=self.steadying_word, check_type=self.technique_check_type, modifier_value=3
        )

    def test_the_room_hears_the_authored_line_and_then_the_plain_one(self) -> None:
        apply_condition(self.brenna, self.steadying_word)
        self._brenna_declares(self.plain)
        mark = self._mark()
        self._round()
        self.assertRoomHeard("Brenna's resolve is used up.", mark)

        self._set_line(self.steadying_word, "spent_narration", "")
        apply_condition(self.brenna, self.steadying_word)
        self._next_round()
        self._brenna_declares(self.plain)
        mark = self._mark()
        self._round()
        self.assertRoomHeard("Brenna's Steadying Word is spent.", mark)

    def test_a_once_only_ward_on_the_brute_is_told_to_the_room_by_the_brutes_name(self) -> None:
        # The brute has no character sheet, so its fight and its name come from its opponent row.
        ward = ConditionTemplateFactory(
            name="Stone Skin", default_duration_type=DurationType.UNTIL_USED
        )
        apply_condition(self.brute.objectdb, ward, source_character=self.brenna)
        instance = ConditionInstance.objects.get(target=self.brute.objectdb, condition=ward)

        mark = self._mark()
        spend_condition_use(instance)

        self.assertRoomHeard(f"{BRUTE}'s Stone Skin is spent.", mark)
