"""Journeys for Cover reading the maneuver effect catalog, once per coverer (#4783).

Hobb is pinned in a fight at the Steading and declares flight; Mara and Perrin each declare
Cover for him through the web dispatch. The round resolves with Hobb's flee check forced to
Success, and what is read back is the contribution each coverer added to his roll, taken from
the modifiers the roll was really built from. Expected values are the catalog default (10 per
coverer) and the spec: a coverer's own Cover escape bonus counts for that coverer only, and
the contribution is labelled "Covered by <the coverer's name>".
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.services import collect_check_modifiers
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatParticipant, FleeConfig
from world.combat.services import resolve_round
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, engage_vow_with_thread
from world.covenants.models import VowStatScaling
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    ManeuverEffectKey,
)
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from collections.abc import Iterator

    from world.checks.types import ModifierContribution

COVER_ESCAPE = 10


class CoverReadsTheCatalog(JourneyCase):
    """Hobb flees; Mara and Perrin both cover him."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        ensure_maneuver_effects()
        self.steading = self.make_room("The Steading")
        self.hobb = self.make_player("Hobb", room=self.steading)
        self.mara = self.make_player("Mara", room=self.steading)
        self.perrin = self.make_player("Perrin", room=self.steading)
        self.flee_check = CheckTypeFactory()
        FleeConfig.objects.filter(pk=1).delete()
        FleeConfig.objects.create(pk=1, check_type=self.flee_check, base_difficulty=50)

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.steading
        )
        CombatOpponentFactory(encounter=self.encounter)
        self.participants: dict[str, CombatParticipant] = {}
        for character in (self.hobb, self.mara, self.perrin):
            sheet = character.sheet_data
            CharacterVitals.objects.create(
                character_sheet=sheet, health=100, max_health=100, base_max_health=100
            )
            self.participants[character.key] = CombatParticipantFactory(
                encounter=self.encounter,
                character_sheet=sheet,
                status=ParticipantStatus.ACTIVE,
            )

    def cover(self, coverer, ally) -> None:
        result = self.web(
            coverer, "combat_cover", ally_participant_id=self.participants[ally.key].pk
        )
        self.assertTrue(result.detail.success, result.detail.message)

    def flee_and_resolve(self) -> list[ModifierContribution]:
        """Hobb flees; return the contributions his flee roll was built from."""
        result = self.web(self.hobb, "combat_flee")
        self.assertTrue(result.detail.success, result.detail.message)
        with self.success_recording_contributions() as rolled:
            resolve_round(self.encounter)
        self.assertEqual(len(rolled), 1)
        return rolled[0]

    @contextmanager
    def success_recording_contributions(self) -> Iterator[list[list[ModifierContribution]]]:
        """Hobb's flee check lands at Success; the list gets each flee roll's contributions."""
        outcome = CheckOutcome.objects.get(name="Success")
        rolled: list[list[ModifierContribution]] = []

        def recording(sheet, check_type, *args, **kwargs):
            breakdown = collect_check_modifiers(sheet, check_type, *args, **kwargs)
            if check_type == self.flee_check:
                rolled.append(list(breakdown.contributions))
            return breakdown

        with (
            patch("world.combat.services.collect_check_modifiers", side_effect=recording),
            force_check_outcome(outcome),
        ):
            yield rolled

    @staticmethod
    def covers(contributions: list[ModifierContribution]) -> dict[str, int]:
        return {
            c.source_label: c.value for c in contributions if c.source_label.startswith("Covered")
        }

    def give_cover_bonus(self, character, bonus: int) -> None:
        """The character's vow adds ``bonus`` to Cover escape bonus (thread level 1)."""
        category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        target = ModifierTargetFactory(
            category=category,
            name=f"Cover escape vow {character.key}",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.COVER_ESCAPE_BONUS),
        )
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            character.sheet_data,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=1,
        )
        VowStatScaling.objects.create(
            covenant_role=role, modifier_target=target, bonus_per_level=bonus
        )

    def test_two_coverers_add_ten_each(self) -> None:
        self.cover(self.mara, self.hobb)
        self.cover(self.perrin, self.hobb)

        contributions = self.flee_and_resolve()

        self.assertEqual(
            self.covers(contributions),
            {"Covered by Mara": COVER_ESCAPE, "Covered by Perrin": COVER_ESCAPE},
        )

    def test_coverers_own_modifier_counts_only_for_them(self) -> None:
        self.give_cover_bonus(self.mara, 2)
        self.cover(self.mara, self.hobb)
        self.cover(self.perrin, self.hobb)

        contributions = self.flee_and_resolve()

        self.assertEqual(
            self.covers(contributions),
            {"Covered by Mara": COVER_ESCAPE + 2, "Covered by Perrin": COVER_ESCAPE},
        )

    def test_edited_base_value_is_used_per_coverer(self) -> None:
        row = get_maneuver_effect(ManeuverEffectKey.COVER_ESCAPE_BONUS)
        row.base_value = 4
        row.save()
        self.cover(self.mara, self.hobb)

        contributions = self.flee_and_resolve()

        self.assertEqual(self.covers(contributions), {"Covered by Mara": 4})

    def test_no_coverer_adds_nothing(self) -> None:
        contributions = self.flee_and_resolve()

        self.assertEqual(self.covers(contributions), {})
