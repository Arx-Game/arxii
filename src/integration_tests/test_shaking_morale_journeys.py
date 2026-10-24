"""Journeys for techniques that shake enemy morale (#4619).

- Staff author a technique's morale effect inline on the Technique admin page, and the
  technique's effect summary then says it shakes morale.
- A morale row that removes no morale is refused on the page.
- In a fight, Ilse casts Dread and it shakes each enemy it lands on by its own authored
  amount; a mindless guard takes half, and a guard that breaks flees the next round.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.combat.constants import (
    PENETRATION_CHECK_TYPE_NAME,
    ActionCategory,
    CombatAllegiance,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    OpponentTierTemplateFactory,
    SpectacleConfigFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import (
    DamageSuccessLevelMultiplierFactory,
    PenetrationOutcomeFactorFactory,
)
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
    TechniqueMoraleEffectFactory,
)
from world.magic.models import Technique, TechniqueMoraleEffect
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneParticipationFactory
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals


def _filled(bound_fields) -> dict[str, str | list[str]]:
    """What a browser posts for these bound fields untouched; unchecked boxes are left out."""
    data: dict[str, str | list[str]] = {}
    for bound in bound_fields:
        value = bound.value()
        if isinstance(value, bool):
            if value:
                data[bound.html_name] = "on"
        elif isinstance(value, (list, tuple)):
            data[bound.html_name] = [str(item) for item in value]
        else:
            data[bound.html_name] = "" if value is None else str(value)
    return data


class AuthoringAMoraleEffect(JourneyCase):
    """Staff set a technique's morale effect on its own admin page."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.technique = TechniqueFactory(damage_profile=False)
        self.url = reverse("admin:arxii_technique_change", args=[self.technique.pk])

    def change_post(self, row: dict[str, object]) -> dict[str, str | list[str]]:
        """The change form's post with the morale inline filled in from *row*."""
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "morale_effect-TOTAL_FORMS")
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            formset = inline.formset
            data.update(_filled(formset.management_form))
            for form in formset.forms:
                data.update(_filled(form))
            if formset.prefix == "morale_effect":
                for name, value in row.items():
                    data[f"morale_effect-0-{name}"] = str(value)
        return data

    def test_staff_add_a_morale_effect_on_the_technique_page(self) -> None:
        data = self.change_post({"base_morale": 30, "morale_per_extra_sl": 10})

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        row = TechniqueMoraleEffect.objects.get(technique=self.technique)
        self.assertEqual(
            (row.base_morale, row.morale_per_extra_sl, row.minimum_success_level), (30, 10, 1)
        )
        refreshed = Technique.objects.get(pk=self.technique.pk)
        self.assertIn("Shakes morale.", refreshed.cached_effect_summary["summary"])

    def test_a_row_that_removes_no_morale_is_refused_on_the_page(self) -> None:
        data = self.change_post(
            {
                "minimum_success_level": 2,
                "base_morale": 0,
                "morale_intensity_multiplier": 0,
                "morale_per_extra_sl": 0,
            }
        )

        response = self.client.post(self.url, data)

        self.assertContains(response, "This row removes no morale.")
        self.assertFalse(TechniqueMoraleEffect.objects.filter(technique=self.technique).exists())

    def test_a_refused_save_leaves_the_game_reading_the_stored_row(self) -> None:
        """A refused save must not leave the posted values on the cached rows.

        Validating the admin form writes the posted values onto the identity-mapped
        Technique and morale row. The database read alone cannot see that, so this
        reads both rows back the way the game does, through the identity map.
        """
        stored = TechniqueMoraleEffectFactory(technique=self.technique, base_morale=30)
        stored_description = self.technique.description
        data = self.change_post(
            {"base_morale": 0, "morale_intensity_multiplier": 0, "morale_per_extra_sl": 0}
        )
        data["description"] = "A description nobody saved."

        response = self.client.post(self.url, data)

        self.assertContains(response, "This row removes no morale.")
        self.assertEqual(TechniqueMoraleEffect.objects.get(pk=stored.pk).base_morale, 30)
        technique = Technique.objects.get(pk=self.technique.pk)
        self.assertEqual(technique.description, stored_description)
        self.assertEqual(technique.cached_morale_effect.base_morale, 30)
        page = self.client.get(self.url)
        self.assertContains(page, 'name="morale_effect-0-base_morale" value="30"')


@contextmanager
def every_check_at(outcome_name: str) -> Iterator[None]:
    """Every combat check in the block lands at the named ``CheckOutcome``."""
    outcome = CheckOutcome.objects.get(name=outcome_name)

    def forced(*args: object, **kwargs: object) -> CheckResult:
        with force_check_outcome(outcome):
            return perform_check(*args, **kwargs)

    with patch("world.combat.services.perform_check", side_effect=forced):
        yield


def by_id(rows: list[dict], pk: int) -> dict:
    return next(row for row in rows if row["id"] == pk)


class ShakingMorale(JourneyCase):
    """Ilse casts Dread on the guards; each one loses the morale the technique says."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        SpectacleConfigFactory()
        self.yard = self.make_room("The Gatehouse")
        self.check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=self.check_type, trait=StatTraitFactory(), weight=1)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.dread = self.technique(ActionTargetType.AREA)
        self.dread_row = TechniqueMoraleEffectFactory(
            technique=self.dread,
            base_morale=30,
            morale_per_extra_sl=10,
            minimum_success_level=1,
            morale_intensity_multiplier=Decimal(0),
        )
        self.ilse = self.fighter("Ilse", self.dread)
        OpponentTierTemplateFactory(tier=OpponentTier.ELITE, has_morale=False)
        self.hale = CombatOpponentFactory(
            encounter=self.encounter, name="Guard Hale", tier=OpponentTier.MOOK, morale=70
        )
        self.rook = CombatOpponentFactory(
            encounter=self.encounter, name="Guard Rook", tier=OpponentTier.ELITE, morale=40
        )
        self.hound = CombatOpponentFactory(
            encounter=self.encounter,
            name="Brindle",
            allegiance=CombatAllegiance.ALLY,
            morale=70,
        )
        self.cutpurse = CombatOpponentFactory(
            encounter=self.encounter, name="Cutpurse", status=OpponentStatus.FLED, morale=70
        )

    # -- setup helpers ----------------------------------------------------------

    def technique(self, target_type: str) -> Technique:
        """A castable technique with no damage of its own."""
        return TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            target_type=target_type,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )

    def single_target_technique(self) -> Technique:
        """A SINGLE technique with the same morale row as Dread, known to Ilse."""
        technique = self.technique(ActionTargetType.SINGLE)
        TechniqueMoraleEffectFactory(
            technique=technique,
            base_morale=30,
            morale_per_extra_sl=10,
            minimum_success_level=1,
            morale_intensity_multiplier=Decimal(0),
        )
        CharacterTechniqueFactory(character=self.ilse.sheet_data, technique=technique)
        return technique

    def fighter(self, name: str, technique: Technique) -> ObjectDB:
        character = self.make_player(name, room=self.yard)
        sheet = character.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=technique)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=500, max_health=500, base_max_health=500
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        return character

    # -- the fight ----------------------------------------------------------------

    def declare(self, character: ObjectDB, technique: Technique, target: CombatOpponent) -> None:
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            character,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": target.pk},
        )
        self.assertTrue(declared.deferred, declared)

    def resolve_at(self, outcome_name: str) -> None:
        with every_check_at(outcome_name):
            resolve_round(self.encounter)

    def morale(self, opponent: CombatOpponent) -> int:
        opponent.refresh_from_db()
        return opponent.morale

    def status(self, opponent: CombatOpponent) -> str:
        opponent.refresh_from_db()
        return opponent.status

    # -- journeys -----------------------------------------------------------------

    def test_dread_shakes_both_guards_and_the_mindless_one_takes_half(self) -> None:
        self.declare(self.ilse, self.dread, self.hale)
        self.resolve_at("Critical Success")

        self.assertEqual(self.morale(self.hale), 30)  # 70 - 40: falters
        self.assertEqual(self.morale(self.rook), 20)  # 40 - 40 * 50%: breaks
        self.assertEqual(self.morale(self.hound), 70)
        self.assertEqual(self.morale(self.cutpurse), 70)

    def test_the_broken_guard_flees_next_round_and_the_faltering_one_stays(self) -> None:
        self.declare(self.ilse, self.dread, self.hale)
        self.resolve_at("Critical Success")
        self.assertEqual(self.status(self.rook), OpponentStatus.ACTIVE)

        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        self.resolve_at("Success")

        self.assertEqual(self.status(self.rook), OpponentStatus.FLED)
        self.assertEqual(self.status(self.hale), OpponentStatus.ACTIVE)

    def test_players_see_the_state_and_the_gm_sees_the_numbers(self) -> None:
        self.declare(self.ilse, self.dread, self.hale)
        self.resolve_at("Critical Success")
        url = f"/api/combat/{self.encounter.pk}/"

        response = self.api(self.account_of(self.ilse)).get(url)
        self.assertEqual(response.status_code, 200)
        hale = by_id(response.json()["opponents"], self.hale.pk)
        self.assertIsNone(hale["morale"])
        self.assertEqual(hale["morale_state"], "falter")
        rook = by_id(response.json()["opponents"], self.rook.pk)
        self.assertEqual(rook["morale_state"], "break")

        gm_account = AccountFactory()
        SceneParticipationFactory(scene=self.encounter.scene, account=gm_account, is_gm=True)
        response = self.api(gm_account).get(url)
        self.assertEqual(response.status_code, 200)
        opponents = response.json()["opponents"]
        self.assertEqual(by_id(opponents, self.hale.pk)["morale"], 30)
        self.assertEqual(by_id(opponents, self.rook.pk)["morale"], 20)

    def test_below_the_minimum_success_level_nobody_is_shaken(self) -> None:
        self.dread_row.minimum_success_level = 2
        self.dread_row.save(update_fields=["minimum_success_level"])

        self.declare(self.ilse, self.dread, self.hale)
        self.resolve_at("Success")

        self.assertEqual(self.morale(self.hale), 70)
        self.assertEqual(self.morale(self.rook), 40)

    def test_a_single_target_cast_shakes_only_its_target(self) -> None:
        glare = self.single_target_technique()

        self.declare(self.ilse, glare, self.hale)
        self.resolve_at("Critical Success")

        self.assertEqual(self.morale(self.hale), 30)
        self.assertEqual(self.morale(self.rook), 40)

    def test_a_cast_that_bounces_off_a_ward_shakes_nothing(self) -> None:
        penetration = CheckTypeFactory(name=PENETRATION_CHECK_TYPE_NAME)
        CheckTypeTraitFactory(check_type=penetration, trait=StatTraitFactory(), weight=1)
        # The only authored rung: every penetration roll, however good, bounces.
        PenetrationOutcomeFactorFactory(min_success_level=-10, factor=0, label="Bounced")
        self.hale.barrier_strength = 5
        self.hale.save(update_fields=["barrier_strength"])

        self.declare(self.ilse, self.dread, self.hale)
        self.resolve_at("Critical Success")

        self.assertEqual(self.morale(self.hale), 70)
        self.assertEqual(self.morale(self.rook), 40)

    def test_a_guard_the_cast_kills_is_not_shaken(self) -> None:
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)
        spear = self.single_target_technique()
        TechniqueDamageProfileFactory(technique=spear, base_damage=500)
        self.hale.health = 10
        self.hale.max_health = 10
        self.hale.save(update_fields=["health", "max_health"])

        self.declare(self.ilse, spear, self.hale)
        self.resolve_at("Critical Success")

        self.assertEqual(self.status(self.hale), OpponentStatus.DEFEATED)
        self.assertEqual(self.morale(self.hale), 70)
