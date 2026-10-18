"""The SENIOR ad-hoc check through the extracted catalog core (#2118, #3295).

Every player path of the scene checks (``check``, ``check find``, ``callcheck``,
``check answer``/``decline``, ``check propose``, their web dispatches, the band and
invention-kwarg firewalls, a synthesized check resolving for its owner alone) is typed
in ``integration_tests/test_playing_a_scene_journeys.py`` (``RollingAtTheTable``). What
stays here is the regression for ``InvokeCatalogCheckAction`` (``gm check``), which
belongs to the GM adjudication group of the actions ledger and keeps its fixture until
that group's journeys take it.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from actions.definitions.gm_adjudication import InvokeCatalogCheckAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import DifficultyChoice
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.constants import TraitType
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
)


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object]:
    """Return (Character, Account) -- a PC with a live roster tenure, in *room*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account


class SeniorAdHocRegressionThroughExtractedCoreTests(TestCase):
    """#2118's SENIOR ad-hoc action must behave identically after its catalog
    resolve/find/band-validation core moved to ``world.checks.catalog_invocation``."""

    def setUp(self) -> None:
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for rank_val, min_pts, name in [
            (0, 0, "SceneCheckNone"),
            (1, 10, "SceneCheckNovice"),
            (2, 25, "SceneCheckCompetent"),
            (3, 50, "SceneCheckExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )

        self.room = ObjectDBFactory(
            db_key="SceneCheckRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.scene = SceneFactory(room=self.room)
        self.gm_actor, self.gm_account = _pc_in_room(self.room, db_key="CallingGM")
        GMProfileFactory(account=self.gm_account, level=GMLevel.SENIOR)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        self.target_actor, self.target_account = _pc_in_room(self.room, db_key="CalledTarget")
        SceneParticipationFactory(scene=self.scene, account=self.target_account, is_gm=False)

        check_trait, _ = Trait.objects.get_or_create(
            name="scene_check_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        self.check_type = CheckTypeFactory(
            name="Riverside Tracking", category=CheckCategoryFactory(name="scene_check_combat")
        )
        CheckTypeTraitFactory(check_type=self.check_type, trait=check_trait, weight=Decimal("1.0"))
        CharacterTraitValue.objects.get_or_create(
            character=self.target_actor.sheet_data, trait=check_trait, defaults={"value": 30}
        )

    def test_senior_gm_can_still_invoke_via_the_extracted_core(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
        )
        self.assertTrue(result.success, result.message)

    def test_senior_find_mode_still_lists_the_catalog(self) -> None:
        result = InvokeCatalogCheckAction().run(actor=self.gm_actor, query="Riverside")
        self.assertTrue(result.success)
        self.assertIn(self.check_type.name, result.message)

    def test_senior_unresolvable_ref_still_hints_gm_find(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target_actor,
            check_type_ref="Nonexistent Check",
            difficulty=DifficultyChoice.HARD,
        )
        self.assertFalse(result.success)
        self.assertIn("gm check find", result.message)
