"""Journeys for the commands ledger (#3657, tranche 17): the things a character keeps. A
beastlord binds, poses as, rides and releases a companion; a shifter takes another shape
and comes back; a captain commissions, upgrades and repairs a ship; a tenant keeps the
lab station in her workshop. Each types what the person types through the real command
handler and asserts what they were told and what the rows now hold."""

from __future__ import annotations

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import CombatAllegiance, OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.companions.content import ensure_companion_content
from world.companions.models import Companion, CompanionArchetype
from world.companions.mount_content import MOUNTED_CONDITION_NAME, ensure_mount_conditions
from world.conditions.capability_content import AT_WILL_SHIFTING
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCategoryFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition
from world.covenants.factories import CovenantFactory
from world.currency.services import get_or_create_purse, transfer
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import ActiveAlternateSelf, CharacterFormState, FormType
from world.items.crafting.models import LabStationDetails
from world.locations.constants import LocationRole
from world.locations.factories import LocationTenancyFactory
from world.magic.factories import CharacterGiftFactory
from world.magic.models.affinity import Resonance
from world.magic.specialization.services import provision_latent_gift_thread
from world.mechanics.factories import ModifierCategoryFactory, ModifierSourceFactory
from world.mechanics.models import CharacterModifier, ModifierTarget
from world.projects.constants import ProjectKind
from world.projects.models import Project
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import RoomFeatureProgressionDetails
from world.room_features.seeds import ensure_lab_kind
from world.scenes.models import Interaction
from world.ships.factories import ShipDetailsFactory, ShipTypeFactory
from world.ships.models import (
    ShipConstructionDetails,
    ShipDetails,
    ShipRepairDetails,
    ShipUpgradeDetails,
)
from world.traits.factories import CheckOutcomeFactory


def fund(character, coppers: int) -> None:
    """Put ``coppers`` in ``character``'s purse."""
    transfer(
        amount=coppers,
        reason="a purse for the journey",
        to_purse=get_or_create_purse(character.sheet_data),
    )


def purse_of(character) -> int:
    return get_or_create_purse(character.sheet_data).balance


def condition_names(character) -> list[str]:
    character.conditions.invalidate()
    return [instance.condition.name for instance in character.conditions.active()]


class KeepingACompanion(JourneyCase):
    """Ysmay holds the Beastlord gift with a little capacity; Hobb holds no gift. She binds
    a hawk and a wolf, poses as one, rides the other, and lets the hawk go."""

    def setUp(self) -> None:
        super().setUp()
        self.kennels = self.make_room("The Kennels")
        self.yard = self.make_room("The Yard")
        self.ysmay = self.make_player("Ysmay", room=self.kennels)
        self.hobb = self.make_player("Hobb", room=self.kennels)
        self.sheet = self.ysmay.sheet_data
        self.gift = ensure_companion_content()
        ensure_mount_conditions()
        wolf = CompanionArchetype.objects.get(name="Wolf")
        wolf.is_mount = True
        wolf.save(update_fields=["is_mount"])
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        wild_bond = Resonance.objects.get(name="Wild Bond")
        self.thread = provision_latent_gift_thread(self.sheet, self.gift, resonance=wild_bond)
        self.thread.level = 10
        self.thread.save(update_fields=["level"])
        self.watch(self.hobb)

    def _bind(self, line: str, *, success_level: int) -> str:
        outcome = CheckOutcomeFactory(name=f"Bind {success_level}", success_level=success_level)
        with force_check_outcome(outcome) as capture:
            told = self.telnet(self.ysmay, line)
        self.assertEqual(capture.check_type.name, "Bind Attempt")
        return told

    def test_binding_a_hawk_and_a_wolf(self) -> None:  # noqa: PLR0915 - one bond, read top to bottom
        hub = self.telnet(self.ysmay, "companion")
        self.assertIn("Companion actions", hub)
        self.assertIn("You have no active companions.", hub)
        self.assertIn("  Beastlord: 0/10 capacity (10 remaining)", hub)
        hobbs_hub = self.telnet(self.hobb, "companion status")
        self.assertIn("You have no active companions.", hobbs_hub)
        self.assertNotIn("capacity", hobbs_hub)
        self.assertIn(
            "Unknown companion action 'frobnicate'. Try: bind, fight, deploy, release, order, "
            "mount, dismount, emote, promote.",
            self.telnet(self.ysmay, "companion frobnicate"),
        )
        self.assertIn(
            "Specify an archetype: archetype=<name or id>.",
            self.telnet(self.ysmay, "companion bind"),
        )
        self.assertIn(
            "No companion archetype found for 'Dragon'.",
            self.telnet(self.ysmay, "companion bind archetype=Dragon gift=Beastlord name=Smoke"),
        )
        self.assertIn(
            "You do not own a gift matching 'Necromancy'.",
            self.telnet(self.ysmay, "companion bind archetype=Hawk gift=Necromancy name=Skree"),
        )
        self.assertIn(
            "Specify a name: name=<text> (must be the final token).",
            self.telnet(self.ysmay, "companion bind archetype=Hawk gift=Beastlord"),
        )
        self.assertIn(
            "You do not own a gift matching 'Beastlord'.",
            self.telnet(self.hobb, "companion bind archetype=Hawk gift=Beastlord name=Skree"),
        )
        self.assertIn(
            "You don't have enough Companion Capacity to bind a Direwolf.",
            self.telnet(self.ysmay, "companion bind archetype=Direwolf gift=Beastlord name=Grim"),
        )
        self.assertFalse(Companion.objects.exists())

        self.assertIn(
            "The Hawk resists your attempt to bind it.",
            self._bind("companion bind archetype=Hawk gift=Beastlord name=Skree", success_level=-1),
        )
        self.assertFalse(Companion.objects.exists())
        self.assertIn(
            "Skree the Hawk is now bonded to you.",
            self._bind("companion bind archetype=hawk gift=beastlord name=Skree", success_level=1),
        )
        skree = Companion.objects.get()
        self.assertEqual(skree.owner_id, self.sheet.pk)
        self.assertEqual(skree.archetype.name, "Hawk")
        self.assertEqual(skree.granting_gift_id, self.gift.pk)
        self.assertEqual(skree.objectdb.key, "Skree")
        self.assertEqual(skree.objectdb.location, self.kennels)
        hub = self.telnet(self.ysmay, "companion list")
        self.assertIn(f"  #{skree.pk} — Skree (Hawk, cost 5)", hub)
        self.assertIn("  Beastlord: 5/10 capacity (5 remaining)", hub)

        # A wolf costs 10; the thread grows and the name runs to the end of the line.
        self.assertIn(
            "You don't have enough Companion Capacity to bind a Wolf.",
            self.telnet(self.ysmay, "companion bind archetype=Wolf gift=Beastlord name=Old Grey"),
        )
        self.thread.level = 20
        self.thread.save(update_fields=["level"])
        self.assertIn(
            "Old Grey the Wolf is now bonded to you.",
            self._bind(
                "companion bind archetype=Wolf gift=Beastlord name=Old Grey", success_level=2
            ),
        )
        old_grey = Companion.objects.get(name="Old Grey")
        self.assertEqual(old_grey.objectdb.key, "Old Grey")
        self.assertIn(
            "  Beastlord: 15/30 capacity (15 remaining)", self.telnet(self.ysmay, "companion")
        )

        # Posing as a present companion; an absent one cannot be posed.
        usage = "Usage: companion emote <name or id> <text>"
        self.assertIn(usage, self.telnet(self.ysmay, "companion emote"))
        self.assertIn(usage, self.telnet(self.ysmay, "companion emote Skree"))
        self.assertIn(
            "No active companion found for 'Ghost'.",
            self.telnet(self.ysmay, "companion emote Ghost ruffles its feathers."),
        )
        self.telnet(self.ysmay, "companion emote Skree ruffles its feathers.")
        self.assertTold(self.hobb, "Skree ruffles its feathers.")
        row = Interaction.objects.get(attributed_companion=skree)
        self.assertEqual(row.content, "ruffles its feathers.")
        self.assertEqual(row.persona_id, self.sheet.primary_persona.pk)
        skree.objectdb.location = self.yard
        self.assertIn(
            "Skree is not here.",
            self.telnet(self.ysmay, "companion emote Skree ruffles its feathers."),
        )
        # Hobb's line resolves among his own companions and names nothing of hers; the
        # web's emote, which takes a pk straight, is refused by the prerequisite.
        self.assertIn(
            f"No active companion found for '{skree.pk}'.",
            self.telnet(self.hobb, f"companion emote {skree.pk} ruffles its feathers."),
        )
        self.assertEqual(
            self.web(
                self.hobb, "companion_emote", companion_id=skree.pk, text="ruffles its feathers."
            ).detail.message,
            "That is not your companion.",
        )

        # Riding the wolf; the hawk cannot be ridden.
        self.assertIn("You are not mounted.", self.telnet(self.ysmay, "companion dismount"))
        self.assertIn("Skree cannot be ridden.", self.telnet(self.ysmay, "companion mount Skree"))
        self.assertIn(
            "Specify a companion: companion mount <name or id>.",
            self.telnet(self.ysmay, "companion mount"),
        )
        self.assertIn("You mount Old Grey.", self.telnet(self.ysmay, "companion mount Old Grey"))
        self.assertEqual(Companion.objects.get(pk=old_grey.pk).ridden_by_id, self.sheet.pk)
        self.assertIn(MOUNTED_CONDITION_NAME, condition_names(self.ysmay))
        self.assertIn(
            "Old Grey is already being ridden.",
            self.telnet(self.ysmay, f"companion mount {old_grey.pk}"),
        )
        self.assertIn("You dismount Old Grey.", self.telnet(self.ysmay, "companion dismount"))
        self.assertIsNone(Companion.objects.get(pk=old_grey.pk).ridden_by_id)
        self.assertNotIn(MOUNTED_CONDITION_NAME, condition_names(self.ysmay))

        # The fighting verbs answer themselves outside any fight.
        self.assertIn(
            "You are not in active combat.", self.telnet(self.ysmay, "companion fight Old Grey")
        )
        self.assertIn(
            "You are not in a battle.", self.telnet(self.ysmay, "companion deploy Old Grey")
        )
        self.assertIn(
            "Usage: companion order <name> <attack | hold | defend> [target]",
            self.telnet(self.ysmay, "companion order Old Grey"),
        )
        self.assertIn(
            "Usage: companion order <name> attack <target> [with <ability>]",
            self.telnet(self.ysmay, "companion order Old Grey attack"),
        )
        self.assertIn(
            "Usage: companion order <name> defend <ally>",
            self.telnet(self.ysmay, "companion order Old Grey defend"),
        )
        self.assertIn(
            "Unknown order verb 'dance'. Try: attack, hold, defend.",
            self.telnet(self.ysmay, "companion order Old Grey dance"),
        )
        self.assertIn(
            "No target found for 'Nobody'.",
            self.telnet(self.ysmay, "companion order Old Grey attack Nobody"),
        )
        self.assertIn(
            "No ally found for 'Nobody'.",
            self.telnet(self.ysmay, "companion order Old Grey defend Nobody"),
        )
        self.assertIn(
            "You are not in active combat or a battle.",
            self.telnet(self.ysmay, "companion order Old Grey hold"),
        )
        self.assertIn(
            "Usage: companion promote <npc> archetype=<name or id> gift=<name or id> name=<text>",
            self.telnet(self.ysmay, "companion promote archetype=Hawk gift=Beastlord name=Pell"),
        )
        self.assertIn(
            "They are not someone you can bind.",
            self.telnet(
                self.ysmay, "companion promote Hobb archetype=Hawk gift=Beastlord name=Pell"
            ),
        )

        # A summon of her own, standing here, is promoted into a lasting companion
        # through the same line (the charmed-enemy path is combat ground).
        pell = CombatOpponentFactory(
            encounter=CombatEncounterFactory(room=self.kennels), name="Pell"
        )
        pell.allegiance = CombatAllegiance.ALLY
        pell.summoned_by = self.sheet
        pell.status = OpponentStatus.ACTIVE
        pell.save(update_fields=["allegiance", "summoned_by", "status"])
        with force_check_outcome(CheckOutcomeFactory(name="Promote 2", success_level=2)):
            told = self.telnet(
                self.ysmay, "companion promote Pell archetype=Hawk gift=Beastlord name=Pell"
            )
        self.assertIn("Pell the Hawk is now bonded to you.", told)
        self.assertEqual(Companion.objects.get(name="Pell").owner_id, self.sheet.pk)
        self.assertIn(
            "  Beastlord: 20/30 capacity (10 remaining)", self.telnet(self.ysmay, "companion")
        )

        # Releasing the hawk destroys its body and keeps the row.
        self.assertIn(
            "Specify a companion: companion release <name or id>.",
            self.telnet(self.ysmay, "companion release"),
        )
        self.assertIn(
            "No active companion found for 'Ghost'.",
            self.telnet(self.ysmay, "companion release Ghost"),
        )
        self.assertIn(
            "No active companion found for 'Skree'.",
            self.telnet(self.hobb, "companion release Skree"),
        )
        self.assertIn(
            "Skree is released from your bond.",
            self.telnet(self.ysmay, f"companion release {skree.pk}"),
        )
        skree = Companion.objects.get(pk=skree.pk)
        self.assertIsNotNone(skree.released_at)
        self.assertIsNone(skree.objectdb)
        self.assertFalse(self.yard.contents)
        self.assertIn(
            "No active companion found for 'Skree'.",
            self.telnet(self.ysmay, "companion release Skree"),
        )
        hub = self.telnet(self.ysmay, "companion")
        self.assertNotIn("Skree", hub)
        self.assertIn("Old Grey (Wolf, cost 10)", hub)
        self.assertIn("  Beastlord: 15/30 capacity (15 remaining)", hub)
        self.assertIn(
            "Pell is released from your bond.", self.telnet(self.ysmay, "companion release Pell")
        )

        # The web releases the wolf through the same action.
        result = self.web(self.ysmay, "release_companion", companion_id=old_grey.pk)
        self.assertEqual(result.detail.message, "Old Grey is released from your bond.")
        self.assertFalse(Companion.objects.filter(released_at__isnull=True).exists())


class TakingAnotherShape(JourneyCase):
    """Ysmay can shift at will between her true self and the Beast; Hobb cannot shift."""

    def setUp(self) -> None:
        super().setUp()
        self.glade = self.make_room("The Glade")
        self.ysmay = self.make_player("Ysmay", room=self.glade)
        self.hobb = self.make_player("Hobb", room=self.glade)
        self.sheet = self.ysmay.sheet_data
        true_form = CharacterFormFactory(character=self.sheet, name="True", form_type=FormType.TRUE)
        CharacterFormStateFactory(character=self.sheet, active_form=true_form)
        self.beast_form = CharacterFormFactory(
            character=self.sheet, name="Beast", form_type=FormType.ALTERNATE
        )
        self.beast = AlternateSelfFactory(
            character=self.sheet, form=self.beast_form, display_name="the Beast"
        )
        self.owl = AlternateSelfFactory(character=self.sheet, display_name="the Owl")
        capability = CapabilityTypeFactory(name=AT_WILL_SHIFTING, innate_baseline=0)
        target = ModifierTarget.objects.create(
            name=f"capability_{capability.pk}",
            category=ModifierCategoryFactory(name="capability"),
            target_capability=capability,
        )
        CharacterModifier.objects.create(
            character=self.sheet, target=target, source=ModifierSourceFactory(), value=1
        )

    def _active(self) -> ActiveAlternateSelf | None:
        return ActiveAlternateSelf.objects.filter(character=self.sheet).first()

    def _form_state(self) -> CharacterFormState:
        return CharacterFormState.objects.get(character=self.sheet)

    def test_shifting_and_reverting(self) -> None:
        hub = self.telnet(self.ysmay, "form")
        self.assertIn("You are in your true self.", hub)
        self.assertIn("Available alternate selves:", hub)
        self.assertIn("  the Beast (form)", hub)
        self.assertIn("  the Owl", hub)
        self.assertNotIn("not in control", hub)
        self.assertIn("Available alternate selves:", self.telnet(self.ysmay, "form list"))
        hobbs_hub = self.telnet(self.hobb, "form")
        self.assertIn("You are in your true self.", hobbs_hub)
        self.assertIn("You have no alternate selves.", hobbs_hub)
        self.assertIn(
            "Usage: form [list | shift <name or id> | revert].",
            self.telnet(self.ysmay, "form dance"),
        )
        self.assertIn(
            "Shift into which alternate self? Usage: form shift <name or id>.",
            self.telnet(self.ysmay, "form shift"),
        )
        self.assertIn(
            "No alternate self named 'Nobody'. Available: the Beast, the Owl.",
            self.telnet(self.ysmay, "form shift Nobody"),
        )
        # Hobb owns no alternate self, so her pk means nothing to him; and the web's
        # shift, which takes a pk straight, is refused for want of the capability.
        self.assertIn(
            "You have no alternate selves.", self.telnet(self.hobb, f"form shift {self.beast.pk}")
        )
        self.assertEqual(
            self.web(self.hobb, "shift_form", alternate_self_id=self.beast.pk).detail.message,
            "You cannot shift forms at will.",
        )
        self.assertIn(
            "You have no alternate self to revert.", self.telnet(self.ysmay, "form revert")
        )
        self.assertIsNone(self._active())

        self.assertIn("You assume the Beast.", self.telnet(self.ysmay, "form shift the beast"))
        active = self._active()
        self.assertEqual(active.alternate_self_id, self.beast.pk)
        self.assertEqual(self._form_state().active_form_id, self.beast_form.pk)
        self.assertIn("You are in the Beast.", self.telnet(self.ysmay, "form"))
        self.assertIn(
            "You are already wearing another alternate self. Revert first.",
            self.telnet(self.ysmay, "form shift the Owl"),
        )
        self.assertIn("You revert to your true self.", self.telnet(self.ysmay, "form revert"))
        self.assertIsNone(self._active().alternate_self_id)
        self.assertEqual(self._form_state().active_form.form_type, FormType.TRUE)
        self.assertIn("You are in your true self.", self.telnet(self.ysmay, "form"))

        # By id, and the same shift from the web.
        self.assertIn("You assume the Owl.", self.telnet(self.ysmay, f"form shift {self.owl.pk}"))
        self.assertIn("You revert to your true self.", self.telnet(self.ysmay, "form revert"))
        result = self.web(self.ysmay, "shift_form", alternate_self_id=self.beast.pk)
        self.assertEqual(result.detail.message, "You assume the Beast.")
        self.assertEqual(self._active().alternate_self_id, self.beast.pk)

        # Not in control: the hub says so and the revert is refused.
        rage = ConditionTemplateFactory(
            name="Rage", category=ConditionCategoryFactory(name="Fury", alters_behavior=True)
        )
        apply_condition(self.ysmay, rage)
        self.assertIn("You are not in control; revert is blocked.", self.telnet(self.ysmay, "form"))
        self.assertIn(
            "You can't revert while not in control of yourself.",
            self.telnet(self.ysmay, "form revert"),
        )
        self.assertEqual(self._active().alternate_self_id, self.beast.pk)

    def test_two_selves_of_one_name_are_told_apart(self) -> None:
        AlternateSelfFactory(character=self.sheet, display_name="The Beast")
        told = self.telnet(self.ysmay, "form shift the beast")
        self.assertIn("Multiple alternate selves match 'the beast':", told)
        self.assertIn("Be more specific.", told)
        self.assertIsNone(self._active())


class CommissioningAShip(JourneyCase):
    """Ysmay commissions a sloop from the quay and keeps the Wavecutter, whose deck she
    owns; Hobb stands on her deck and owns nothing."""

    def setUp(self) -> None:
        super().setUp()
        self.quay = self.make_room("The Quay")
        self.deck = self.make_room("Main Deck")
        deck_profile = RoomProfileFactory(objectdb=self.deck)
        self.ysmay = self.make_player("Ysmay", room=self.quay)
        self.hobb = self.make_player("Hobb", room=self.deck)
        self.persona = self.ysmay.sheet_data.primary_persona
        self.sloop = ShipTypeFactory(name="Sloop", base_hull=8, base_handling=15, base_armament=5)
        self.wavecutter = ShipDetailsFactory(
            ship_type=self.sloop,
            building__area__name="Sloop 'Wavecutter'",
            building__owner_persona=self.persona,
            building__entry_room=deck_profile,
            building__fortification_level=2,
        )
        self.tide = CovenantFactory(name="The Tide")

    def test_commissioning_from_the_quay(self) -> None:
        hub = self.telnet(self.ysmay, "ship")
        self.assertIn("Ship actions", hub)
        self.assertIn("There is no ship here.", hub)
        self.assertIn("There is no ship here.", self.telnet(self.ysmay, "ship status"))
        self.assertIn(
            "Unknown ship action 'frobnicate'. Try: commission, upgrade, repair, status.",
            self.telnet(self.ysmay, "ship frobnicate"),
        )
        usage = "Usage: ship commission ship_type=<name> [covenant=<name>] name=<ship name>."
        self.assertIn(usage, self.telnet(self.ysmay, "ship commission"))
        self.assertIn(usage, self.telnet(self.ysmay, "ship commission ship_type=Sloop"))
        self.assertIn(usage, self.telnet(self.ysmay, "ship commission name=Wavecutter"))
        self.assertIn(
            "There is no ship type called 'Galleon'.",
            self.telnet(self.ysmay, "ship commission ship_type=Galleon name=Leviathan"),
        )
        self.assertIn(
            "There is no covenant called 'Nobody'.",
            self.telnet(
                self.ysmay, "ship commission ship_type=Sloop covenant=Nobody name=Tidesong"
            ),
        )
        self.assertFalse(Project.objects.exists())

        told = self.telnet(self.ysmay, "ship commission ship_type=sloop name=The Black Pearl")
        project = Project.objects.get(kind=ProjectKind.SHIP_CONSTRUCTION)
        self.assertIn(
            f"Construction of 'The Black Pearl' commissioned (project #{project.pk}).", told
        )
        self.assertEqual(project.owner_persona_id, self.persona.pk)
        details = ShipConstructionDetails.objects.get(project=project)
        self.assertEqual(details.name, "The Black Pearl")
        self.assertEqual(details.ship_type_id, self.sloop.pk)
        self.assertIsNone(details.owner_covenant)

        self.telnet(self.ysmay, "ship commission ship_type=Sloop covenant=the tide name=Tidesong")
        self.assertEqual(
            ShipConstructionDetails.objects.get(name="Tidesong").owner_covenant_id, self.tide.pk
        )

        # Away from any ship, the owner's verbs find nothing.
        self.assertIn(
            "No such ship.", self.telnet(self.ysmay, "ship upgrade stat=handling level=1")
        )
        self.assertIn("No such ship.", self.telnet(self.ysmay, "ship repair"))
        self.assertIn("No such ship.", self.telnet(self.ysmay, "ship status ship_id=999999"))

    def test_keeping_the_wavecutter(self) -> None:
        self.ysmay.move_to(self.deck, quiet=True)
        hub = self.telnet(self.ysmay, "ship")
        self.assertIn("Sloop 'Wavecutter': hull 2, handling 15, armament 5.", hub)
        self.assertNotIn("needs repair", hub)
        self.assertIn(
            "Sloop 'Wavecutter': hull 2, handling 15, armament 5.",
            self.telnet(self.hobb, f"ship status ship_id={self.wavecutter.pk}"),
        )
        self.assertIn(
            "Usage: ship upgrade stat=<handling | armament | hull> level=<n>.",
            self.telnet(self.ysmay, "ship upgrade"),
        )
        self.assertIn(
            "Usage: ship upgrade stat=<handling | armament | hull> level=<n>.",
            self.telnet(self.ysmay, "ship upgrade stat=handling level=two"),
        )
        self.assertIn(
            "You don't own this ship.", self.telnet(self.hobb, "ship upgrade stat=handling level=1")
        )
        self.assertIn("You don't own this ship.", self.telnet(self.hobb, "ship repair"))
        self.assertIn(
            "'speed' is not a valid stat.",
            self.telnet(self.ysmay, "ship upgrade stat=speed level=2"),
        )
        self.assertIn(
            "That upgrade must target a higher handling level than the ship currently has.",
            self.telnet(self.ysmay, "ship upgrade stat=handling level=0"),
        )
        self.assertFalse(Project.objects.exists())

        told = self.telnet(self.ysmay, "ship upgrade stat=handling level=2")
        upgrade = ShipUpgradeDetails.objects.get()
        self.assertIn(f"Handling upgrade to level 2 begins (project #{upgrade.project_id}).", told)
        self.assertEqual(upgrade.ship_id, self.wavecutter.pk)
        self.assertEqual(upgrade.stat, "handling")
        self.assertEqual(upgrade.target_level, 2)
        self.assertEqual(upgrade.project.owner_persona_id, self.persona.pk)
        self.assertEqual(
            upgrade.project.description, "Raise Sloop 'Wavecutter''s handling level to 2"
        )

        # The hull is the building's fortification: raised through the ceiling's rules.
        told = self.telnet(self.ysmay, "ship upgrade stat=hull level=3")
        hull = Project.objects.get(kind=ProjectKind.FORTIFICATION_UPGRADE)
        self.assertIn(f"Hull upgrade to level 3 begins (project #{hull.pk}).", told)
        self.assertEqual(hull.owner_persona_id, self.persona.pk)
        self.assertIn(
            "That upgrade is not valid.", self.telnet(self.ysmay, "ship upgrade stat=hull level=1")
        )
        self.assertIn(
            "That upgrade is not valid.", self.telnet(self.ysmay, "ship upgrade stat=hull level=9")
        )
        self.assertEqual(Project.objects.filter(kind=ProjectKind.FORTIFICATION_UPGRADE).count(), 1)

        # Breached: nothing is upgraded until the repair project opens.
        self.wavecutter.needs_repair = True
        self.wavecutter.save(update_fields=["needs_repair"])
        self.assertIn("(needs repair)", self.telnet(self.ysmay, "ship"))
        self.assertIn(
            "This ship needs repair before it can be upgraded.",
            self.telnet(self.ysmay, "ship upgrade stat=armament level=1"),
        )
        self.assertIn(
            "This ship needs repair before it can be upgraded.",
            self.telnet(self.ysmay, "ship upgrade stat=hull level=10"),
        )
        told = self.telnet(self.ysmay, "ship repair")
        repair = ShipRepairDetails.objects.get()
        self.assertIn(f"Repairs begin (project #{repair.project_id}).", told)
        self.assertEqual(repair.ship_id, self.wavecutter.pk)
        self.assertEqual(repair.project.description, "Repair Sloop 'Wavecutter'")

        # From the quay, by id.
        self.ysmay.move_to(self.quay, quiet=True)
        told = self.telnet(self.ysmay, f"ship repair ship_id={self.wavecutter.pk}")
        self.assertIn("Repairs begin (project #", told)
        self.assertEqual(ShipRepairDetails.objects.count(), 2)
        self.assertEqual(ShipDetails.objects.get(pk=self.wavecutter.pk).needs_repair, True)


class KeepingALabStation(JourneyCase):
    """Ysmay is the tenant of the Workshop; Hobb is a guest in it. She raises a Lab
    station there and pays to keep it in repair."""

    def setUp(self) -> None:
        super().setUp()
        self.workshop = self.make_room("The Workshop")
        self.profile = RoomProfileFactory(objectdb=self.workshop)
        self.ysmay = self.make_player("Ysmay", room=self.workshop)
        self.hobb = self.make_player("Hobb", room=self.workshop)
        LocationTenancyFactory(
            room_profile=self.profile,
            tenant_persona=self.ysmay.sheet_data.primary_persona,
            kind=LocationRole.TENANT,
        )
        self.lab = ensure_lab_kind()

    def test_raising_and_repairing_the_station(self) -> None:
        hub = self.telnet(self.ysmay, "station")
        self.assertIn("Station actions", hub)
        self.assertIn("There is no Lab station here.", hub)
        self.assertIn(
            "Unknown station action 'frobnicate'. Try: install, repair, upgrade.",
            self.telnet(self.ysmay, "station frobnicate"),
        )
        self.assertIn(
            "You don't have standing to build here.", self.telnet(self.hobb, "station install")
        )
        self.assertIn(
            "Usage: station install level=<n>.",
            self.telnet(self.ysmay, "station install level=two"),
        )
        self.assertIn(
            "Usage: station upgrade level=<n>.", self.telnet(self.ysmay, "station upgrade")
        )
        self.assertIn(
            "Level 9 exceeds this feature kind's maximum of 5.",
            self.telnet(self.ysmay, "station install level=9"),
        )
        self.assertFalse(Project.objects.exists())

        self.assertIn(
            "A project to raise the Lab to level 1 begins.",
            self.telnet(self.ysmay, "station install"),
        )
        project = Project.objects.get(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
        self.assertEqual(project.owner_persona_id, self.ysmay.sheet_data.primary_persona.pk)
        self.assertEqual(project.threshold_target, 500)
        progression = RoomFeatureProgressionDetails.objects.get(project=project)
        self.assertEqual(progression.target_room_profile_id, self.profile.pk)
        self.assertEqual(progression.target_feature_kind_id, self.lab.pk)
        self.assertEqual(progression.target_level, 1)

        # The project completes (off-stage) and the station stands here, worn.
        instance = RoomFeatureInstanceFactory(room_profile=self.profile, feature_kind=self.lab)
        station = LabStationDetails.objects.create(
            feature_instance=instance, durability=3, max_durability=10
        )
        self.assertIn("A Lab station stands here: L1, 3/10", self.telnet(self.ysmay, "station"))
        self.assertIn("That would not be an upgrade.", self.telnet(self.ysmay, "station install"))
        self.assertIn(
            "That would not be an upgrade.", self.telnet(self.ysmay, "station upgrade level=1")
        )
        self.assertIn(
            "A project to raise the Lab to level 3 begins.",
            self.telnet(self.ysmay, "station upgrade level=3"),
        )
        self.assertEqual(
            RoomFeatureProgressionDetails.objects.get(target_level=3).target_feature_kind_id,
            self.lab.pk,
        )

        # Repairs cost 15 coppers a point at level 1.
        self.assertIn(
            "Usage: station repair points=<n>.", self.telnet(self.ysmay, "station repair")
        )
        self.assertIn(
            "You don't have standing to build here.",
            self.telnet(self.hobb, "station repair points=2"),
        )
        self.assertIn(
            "Insufficient funds: 0c on hand.", self.telnet(self.ysmay, "station repair points=2")
        )
        self.assertEqual(LabStationDetails.objects.get(pk=station.pk).durability, 3)
        fund(self.ysmay, 100)
        self.assertIn(
            "You repair the Lab station: 7/10.", self.telnet(self.ysmay, "station repair points=4")
        )
        self.assertEqual(purse_of(self.ysmay), 40)
        self.assertIn("A Lab station stands here: L1, 7/10", self.telnet(self.ysmay, "station"))
        # The deficit is three points, 45 coppers; the purse holds 40.
        self.assertIn(
            "Insufficient funds: 4s on hand.", self.telnet(self.ysmay, "station repair points=50")
        )
        fund(self.ysmay, 5)
        self.assertIn(
            "You repair the Lab station: 10/10.",
            self.telnet(self.ysmay, "station repair points=50"),
        )
        self.assertEqual(purse_of(self.ysmay), 0)
        self.assertIn(
            "You repair the Lab station: 10/10.", self.telnet(self.ysmay, "station repair points=5")
        )

        # Broken; and next door, where she holds no standing, she may build nothing.
        station.durability = 0
        station.save(update_fields=["durability"])
        self.assertIn(
            "A Lab station stands here: L1, 0/10 (BROKEN)", self.telnet(self.ysmay, "station")
        )
        self.ysmay.move_to(self.make_room("The Cellar"), quiet=True)
        self.assertIn(
            "You don't have standing to build here.", self.telnet(self.ysmay, "station install")
        )
        self.assertIn("There is no Lab station here.", self.telnet(self.ysmay, "station"))

    def test_one_feature_to_a_room(self) -> None:
        RoomFeatureInstanceFactory(room_profile=self.profile, feature_kind=RoomFeatureKindFactory())
        self.assertIn(
            "This room already has a feature installed.", self.telnet(self.ysmay, "station install")
        )
        self.assertIn("There is no Lab station here.", self.telnet(self.ysmay, "station"))
        self.assertIn(
            "There is no Lab station here.", self.telnet(self.ysmay, "station repair points=1")
        )
