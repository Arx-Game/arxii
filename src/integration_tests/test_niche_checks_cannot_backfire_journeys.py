"""Journeys for niche checks that cannot backfire (#4386).

A character whose distinction says a kind of check is her niche cannot botch at it: a
roll that comes up a Critical Failure lands on a plain Failure instead. Everyone else,
and she herself at any check outside the niche, keeps the full range of results.

Hobb's distinction, Eye for Faces, covers the Identification check's whole category, so
``identify`` forced to a botch tells him only that he can't place the face. Maud's
distinction covers only the Search check, so her botched ``identify`` still names the
wrong person. Ysmay's Born to the Rock covers her climbing; her botched climb lands on
Failure, so the roll she reads back over REST shows her slip, not her fall, with a
"Cannot botch" line that Maren, who shares the scene, never sees.

Staff author the immunity the way the spec says: a ``botch_immunity`` modifier target
scoped to a check category or a check type, and a distinction effect on it, granted
through ``grant_distinction``.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import override_settings

from actions.constants import ActionBackend
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.models import CheckType
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import CapabilityTypeFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.forms.constants import IDENTIFICATION_CHECK_TYPE_NAME
from world.magic.factories import TechniqueCapabilityGrantFactory, TechniqueFactory
from world.mechanics.constants import BOTCH_IMMUNITY_CATEGORY_NAME
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
    PropertyFactory,
    SituationInstanceFactory,
)
from world.mechanics.models import ChallengeInstance, ModifierTarget
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.interaction_services import get_active_scene
from world.scenes.models import PersonaDiscovery
from world.scenes.tests.cast_test_helpers import grant_technique
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.investigation_checks import ensure_identification_check
from world.traits.models import CheckOutcome, ResultChart

SLIPPED = "Your hands slip and you catch the ledge."
FELL = "You fall to the quarry floor."
CANT_PLACE = "You can't place who's really underneath"
FAKE_ID = "You'd swear that's Old Marta... but you're wrong."


class _NicheCase(JourneyCase):
    """Staff have authored the botch_immunity category; each test authors its niches."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        ResultChart.clear_cache()
        ModifierTarget.clear_trait_cache()
        self.botch_immunity = ModifierCategoryFactory(name=BOTCH_IMMUNITY_CATEGORY_NAME)
        self.botch = CheckOutcome.objects.get(name="Critical Failure")

    def tearDown(self) -> None:
        ModifierTarget.clear_trait_cache()
        super().tearDown()

    def niche(self, character, distinction_name: str, **scope: object) -> None:
        """A botch_immunity target on ``scope`` and a distinction granting it, held by
        ``character`` through the real grant service."""
        target = ModifierTargetFactory(
            category=self.botch_immunity, name=f"{distinction_name} scope", **scope
        )
        distinction = DistinctionFactory(name=distinction_name)
        DistinctionEffectFactory(distinction=distinction, target=target, value_per_rank=1)
        grant_distinction(character.sheet_data, distinction, origin=DistinctionOrigin.GM_AWARD)


@override_settings(SEED_SAMPLE_CONTENT=True)
class AMaskReaderCannotBotchAtHisNiche(_NicheCase):
    """Ysmay wears a stag mask; Hobb reads faces for a living, Maud searches rooms."""

    def setUp(self) -> None:
        super().setUp()
        ensure_identification_check()
        self.identification = CheckType.objects.get(name=IDENTIFICATION_CHECK_TYPE_NAME)
        self.search = CheckTypeFactory(name="Search", category=self.identification.category)
        self.lantern = self.make_room("The Lantern")
        profile = RoomProfileFactory(objectdb=self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.maud = self.make_player("Maud", room=self.lantern)
        FunctionaryFactory(
            role=NPCRoleFactory(name="Barkeep"), room=profile, name_override="Old Marta"
        )
        self.niche(self.hobb, "Eye for Faces", target_check_category=self.identification.category)
        self.niche(self.maud, "Nose for Hiding Places", target_scope_check_type=self.search)
        self.telnet(self.ysmay, "persona mask Stag Mask")

    def test_his_botch_is_only_a_miss(self) -> None:
        with force_check_outcome(self.botch):
            told = self.telnet(self.hobb, "identify Ysmay")

        self.assertIn(CANT_PLACE, told)
        self.assertNotIn("Old Marta", told)
        self.assertEqual(PersonaDiscovery.objects.count(), 0)

    def test_outside_her_niche_a_botch_still_names_the_wrong_person(self) -> None:
        # Maud cannot botch at Search; Identification is a different check type.
        with force_check_outcome(self.botch):
            told = self.telnet(self.maud, "identify Ysmay")

        self.assertIn(FAKE_ID, told)
        self.assertEqual(PersonaDiscovery.objects.count(), 0)


class AClimberSeesWhyHerFallWasOnlyAFailure(_NicheCase):
    """Ysmay climbs the quarry face in Ravenna's scene; Maren watches."""

    def setUp(self) -> None:
        super().setUp()
        self.climbing = CheckTypeFactory(name="Climbing")
        self.room = self.make_room("The Old Quarry")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.maren = self.make_player("Maren", room=self.room)
        self.ravenna = self.make_player("Ravenna", room=self.room)
        self.telnet(self.ravenna, "scene start")
        self.telnet(self.maren, "pose settles in to watch.")
        scaling = CapabilityTypeFactory(name="Scaling")
        prop = PropertyFactory(name="sheer")
        template = ChallengeTemplateFactory(
            name="The Quarry Face", severity=DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL]
        )
        template.properties.add(prop)
        for tier, label in (("Failure", SLIPPED), ("Critical Failure", FELL)):
            ChallengeTemplateConsequenceFactory(
                challenge_template=template,
                consequence=ConsequenceFactory(
                    outcome_tier=CheckOutcome.objects.get(name=tier), label=label
                ),
            )
        self.approach = ChallengeApproachFactory(
            challenge_template=template,
            application=ApplicationFactory(
                name="Scale It", capability=scaling, target_property=prop
            ),
            check_type=self.climbing,
            display_name="Climb the face",
            action_template=None,
        )
        self.face = ChallengeInstance.objects.create(
            template=template,
            location=self.room,
            target_object=ObjectDBFactory(db_key="the quarry face", location=self.room),
            situation_instance=SituationInstanceFactory(
                location=self.room, scene=get_active_scene(self.room)
            ),
            is_active=True,
            is_revealed=True,
        )
        climber = TechniqueFactory(name="Spider Step", damage_profile=False)
        TechniqueCapabilityGrantFactory(
            technique=climber,
            capability=scaling,
            base_value=5,
            intensity_multiplier=Decimal(0),
        )
        grant_technique(self.ysmay.sheet_data.primary_persona, climber)
        self.niche(self.ysmay, "Born to the Rock", target_check_category=self.climbing.category)

    def stored_for(self, character) -> dict:
        """The climb's stored outcome, as ``character``'s player reads it over REST."""
        response = self.api(self.account_of(character)).get("/api/checks/consequence-outcomes/")
        self.assertEqual(response.status_code, 200, response.content)
        (outcome,) = response.json()["results"]
        return outcome

    def climb(self) -> None:
        """Ysmay climbs the face from the browser's dispatch endpoint.

        ``web()`` drives registry keys only, so the challenge ref is posted to the
        dispatch endpoint the browser's action calls go through.
        """
        response = self.api(self.account_of(self.ysmay)).post(
            f"/api/actions/characters/{self.ysmay.pk}/dispatch/",
            {
                "ref": {
                    "backend": ActionBackend.CHALLENGE,
                    "challenge_instance_id": self.face.pk,
                    "approach_id": self.approach.pk,
                },
                "kwargs": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_her_botch_lands_on_failure_and_only_she_reads_why(self) -> None:
        with force_check_outcome(self.botch):
            self.climb()

        stored = self.stored_for(self.ysmay)
        (shown,) = [row for row in stored["outcome_display"] if row["is_selected"]]
        self.assertEqual((shown["label"], shown["tier_name"]), (SLIPPED, "Failure"))
        hers = [(m["source_kind"], m["source_label"], m["value"]) for m in stored["modifiers"]]
        self.assertIn(("botch_immunity", "Cannot botch: Born to the Rock", 0), hers)
        self.assertEqual(sum(value for _, _, value in hers), stored["modifier_total"])
        theirs = self.stored_for(self.maren)
        self.assertNotIn(
            "Born to the Rock", " ".join(m["source_label"] for m in theirs["modifiers"])
        )
        self.assertNotIn("botch_immunity", [m["source_kind"] for m in theirs["modifiers"]])
