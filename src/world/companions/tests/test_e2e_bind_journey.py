"""E2E journey: grant Beastlord gift, bind, follow, capacity limit, release (#672)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.content import ensure_companion_content
from world.magic.specialization.services import grant_gift_to_character


class CompanionBindJourneyTests(EvenniaTestCase):
    def setUp(self) -> None:
        from evennia import create_object

        self.room_a = create_object("typeclasses.rooms.Room", key="Journey Room A")
        self.room_b = create_object("typeclasses.rooms.Room", key="Journey Room B")
        self.sheet = CharacterSheetFactory()
        self.owner = self.sheet.character
        self.owner.location = self.room_a
        self.owner.save()
        self.gift = ensure_companion_content()
        self.resonance = self.gift.resonances.first()
        grant_gift_to_character(self.sheet, self.gift, resonance=self.resonance)

        from world.magic.constants import TargetKind
        from world.magic.models.threads import Thread

        self.thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        # min_thread_level 10 and 20 tiers both apply at level 20 (flat_bonus 10 + 20 = 30
        # total Companion Capacity) — see world/companions/content.py's _CAPACITY_TIERS.
        self.thread.level = 20
        self.thread.save(update_fields=["level"])

    def test_full_bind_follow_capacity_release_journey(self) -> None:
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.companions.models import Companion, CompanionArchetype
        from world.traits.factories import CheckOutcomeFactory

        hawk = CompanionArchetype.objects.get(name="Hawk")
        wolf = CompanionArchetype.objects.get(name="Wolf")
        direwolf = CompanionArchetype.objects.get(name="Direwolf")
        success = CheckOutcomeFactory(name="Forced Journey Success", success_level=5)

        # Bind a Hawk (capacity cost 5) — succeeds.
        with force_check_outcome(success):
            result = BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        self.assertTrue(result.success, result.message)
        companion = Companion.objects.get(name="Skree")
        self.assertEqual(companion.objectdb.location, self.room_a)

        # It appears in the room and can be looked at (default Evennia behavior).
        self.assertIn(companion.objectdb, self.room_a.contents)

        # Move the owner — the companion follows.
        self.owner.__dict__.pop("companions", None)  # clear cached_property so it re-queries
        self.owner.move_to(self.room_b, quiet=True)
        companion.objectdb.refresh_from_db()
        self.assertEqual(companion.objectdb.location, self.room_b)

        # Bind a Wolf (capacity cost 10) — still within capacity (30 - 5 = 25 remaining).
        with force_check_outcome(success):
            result = BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=wolf.pk, name="Fang"
            )
        self.assertTrue(result.success, result.message)

        # A Direwolf (capacity cost 20) would exceed capacity (5 + 10 + 20 = 35 > 30) —
        # rejected by the prerequisite before any roll is attempted.
        result = BindCompanionAction().run(
            actor=self.owner, gift_id=self.gift.pk, archetype_id=direwolf.pk, name="Ghost"
        )
        self.assertFalse(result.success)
        self.assertIn("enough Companion Capacity", result.message)
        self.assertFalse(Companion.objects.filter(name="Ghost").exists())

        # Release the Wolf — object gone, row persists with released_at set.
        # Uses ReleaseCompanionAction (the Action seam), not the service directly (#1918).
        from evennia.objects.models import ObjectDB

        from actions.definitions.companions import ReleaseCompanionAction

        fang = Companion.objects.get(name="Fang")
        object_id = fang.objectdb_id
        release_result = ReleaseCompanionAction().run(actor=self.owner, companion_id=fang.pk)
        self.assertTrue(release_result.success, release_result.message)

        self.assertFalse(ObjectDB.objects.filter(pk=object_id).exists())
        self.assertTrue(Companion.objects.filter(pk=fang.pk, released_at__isnull=False).exists())

    def test_bind_deploy_release_journey(self) -> None:
        """Full bind → deploy → release loop through the Action seam (#1918).

        Proves the three Actions compose end-to-end: bind creates the
        companion, deploy bridges it into a battle vehicle, release tears
        down the live object while keeping the row.
        """
        from actions.definitions.companions import (
            BindCompanionAction,
            DeployCompanionAction,
            ReleaseCompanionAction,
        )
        from world.battles.factories import BattleFactory, BattleSideFactory
        from world.battles.models import BattleParticipant, BattleParticipantStatus
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype
        from world.traits.factories import CheckOutcomeFactory

        # 1. Bind a companion.
        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="Journey Deploy Success", success_level=5)
        with force_check_outcome(success):
            result = BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        self.assertTrue(result.success, result.message)
        companion = Companion.objects.get(name="Skree")

        # 2. Deploy into a battle (mirrors test_combat_bridge_e2e.py's fixture pattern).
        battle = BattleFactory(risk_level=RiskLevel.LOW)
        side = BattleSideFactory(battle=battle)
        BattleParticipant.objects.create(
            battle=battle,
            character_sheet=self.sheet,
            side=side,
            status=BattleParticipantStatus.ACTIVE,
        )
        deploy_result = DeployCompanionAction().run(actor=self.owner, companion_id=companion.pk)
        self.assertTrue(deploy_result.success, deploy_result.message)
        self.assertIn("vehicle_id", deploy_result.data)

        # 3. Release the companion via the Action seam.
        object_id = companion.objectdb_id
        release_result = ReleaseCompanionAction().run(actor=self.owner, companion_id=companion.pk)
        self.assertTrue(release_result.success, release_result.message)
        self.assertIn("released from your bond", release_result.message)

        from evennia.objects.models import ObjectDB

        companion.refresh_from_db()
        self.assertIsNotNone(companion.released_at)
        self.assertFalse(companion.is_active)
        self.assertFalse(ObjectDB.objects.filter(pk=object_id).exists())
