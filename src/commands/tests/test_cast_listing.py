"""Bare ``cast`` is the telnet cast list (#2898, #2901).

Telnet had no way to find out what a technique does. ``sheet/magic`` printed name
and level; bare ``cast`` raised a usage error. This is the telnet face of the web
castable-techniques list — both read ``castable_technique_links_for_sheet``.

#2901 adds the compact forms line: enough to reveal that ``base`` and
``variant=<resonance>`` exist and what they are called, without turning an
already-dense list into a catalogue.
"""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from commands.combat import CmdDeclareTechnique
from world.character_sheets.factories import CharacterFactory, CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models import Thread
from world.magic.models.techniques import ConditionTargetKind
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import provision_latent_gift_thread


class _RecordingCmd(CmdDeclareTechnique):
    """CmdDeclareTechnique with ``msg`` captured instead of sent to a session."""

    def __init__(self, caller, args: str = "") -> None:
        super().__init__()
        self.caller = caller
        self.args = args
        self.sent: list[str] = []

    def msg(self, text="", **kwargs) -> None:
        self.sent.append(str(text))


class CastListingTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _technique(self, name: str):
        # An action_template is what makes a technique castable standalone.
        technique = TechniqueFactory(
            name=name,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            anima_cost=5,
            action_template=ActionTemplateFactory(),
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        return technique

    def test_bare_cast_lists_techniques_with_what_they_do(self) -> None:
        technique = self._technique("Ward of Ash")

        cmd = _RecordingCmd(self.character)
        cmd.func()
        text = "\n".join(cmd.sent)

        self.assertIn("Ward of Ash", text)
        self.assertIn("Cast on an ally", text)
        self.assertIn("Costs 5 anima.", text)
        self.assertIn("Applies Guarded.", text)
        self.assertIn(technique.description, text)

    def test_bare_cast_with_no_techniques_says_so(self) -> None:
        cmd = _RecordingCmd(self.character)
        cmd.func()

        self.assertEqual(cmd.sent, ["You know no techniques you can cast."])

    def test_listing_does_not_scale_queries_with_technique_count(self) -> None:
        """The payload tables prefetch onto the cached_property names the summary
        reads, so N techniques cost a fixed handful of queries, not 4N.

        7 queries: the CharacterTechnique rows, the four #2898 payload prefetches,
        the #2901 variants prefetch (the caster's alternate forms), and one read
        of the cached threads handler (which of those variants they have
        unlocked). Every one is fixed; none is per technique.
        """
        for name in ("Ward of Ash", "Ember Lash", "Cinder Step", "Ash Veil"):
            self._technique(name)

        cmd = _RecordingCmd(self.character)
        with self.assertNumQueries(7):
            lines = cmd._castable_listing()

        self.assertIn("Ash Veil", "\n".join(lines))


class CastListingFormsTests(TestCase):
    """The forms affordance on the bare-``cast`` listing (#2901)."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.gift = GiftFactory()
        self.resonance = ResonanceFactory(name="Cinder")
        self.gift.resonances.add(self.resonance)
        self.technique = TechniqueFactory(
            name="Ember Lash",
            gift=self.gift,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

    def _unlock_variant(self, level: int) -> TechniqueVariant:
        variant = TechniqueVariant.objects.create(
            parent_technique=self.technique,
            resonance=self.resonance,
            unlock_thread_level=3,
            name_override="Ashfall Lash",
        )
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        thread.level = level
        thread.save(update_fields=["level"])
        self.character.threads.invalidate()
        return variant

    def test_no_forms_line_when_only_the_base_form_is_reachable(self) -> None:
        """Naming a single option is no help, so the dense list stays quiet."""
        cmd = _RecordingCmd(self.character)
        cmd.func()

        self.assertNotIn("Forms:", "\n".join(cmd.sent))

    def test_forms_line_names_the_variant_and_marks_the_default(self) -> None:
        """This is what makes `base` and `variant=<resonance>` discoverable."""
        self._unlock_variant(level=3)

        cmd = _RecordingCmd(self.character)
        cmd.func()
        text = "\n".join(cmd.sent)

        self.assertIn("Forms: base | Cinder (Ashfall Lash) (default)", text)

    def test_locked_forms_stay_off_the_cast_list(self) -> None:
        """The scene shows what you can do; the sheet shows what you are becoming."""
        self._unlock_variant(level=1)

        cmd = _RecordingCmd(self.character)
        cmd.func()
        text = "\n".join(cmd.sent)

        self.assertNotIn("Forms:", text)
        self.assertNotIn("Ashfall Lash", text)
