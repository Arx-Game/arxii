"""SETTLE_OBLIGATION offer kind (#2428 whole-branch fix).

``world.societies.obligation_services.settle_obligation`` was authored in an
earlier task on this cluster with no live caller — an Unbound Prospect had no
in-game way to ever pay off their Academy entrance debt, dead-ending the
cluster's headline loop. The Academy Registrar's SETTLE_OBLIGATION offer
(``run_settle_obligation_offer``, seeded by ``ensure_academy_registrar_role``)
is that caller.
"""

from __future__ import annotations

from django.test import TestCase

from world.currency.models import FavorTokenDetails
from world.currency.services import mint_favor_token
from world.items.constants import OwnershipEventType
from world.items.models import OwnershipEvent
from world.npc_services.constants import OfferKind
from world.npc_services.effects import OFFER_EFFECT_HANDLERS, run_settle_obligation_offer
from world.npc_services.factories import NPCRoleFactory, NPCServiceOfferFactory
from world.npc_services.services import resolve_offer, start_interaction
from world.scenes.factories import PersonaFactory
from world.seeds.tests.content_stub import stub_content_root
from world.societies.constants import ObligationState
from world.societies.factories import OrganizationFactory, OrganizationObligationFactory


class SettleObligationOfferTests(TestCase):
    def setUp(self) -> None:
        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character

        self.role = NPCRoleFactory(faction_affiliation=self.academy)
        self.offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.SETTLE_OBLIGATION,
            label="Settle your Academy debt",
            is_final=True,
        )

    def test_registered(self) -> None:
        self.assertIn(OfferKind.SETTLE_OBLIGATION.value, OFFER_EFFECT_HANDLERS)

    def test_happy_path_through_resolve_offer_settles_and_redeems(self) -> None:
        """The real resolve_offer flow: obligation settled, Hare redeemed, and an
        OwnershipEvent recorded per redeem_favor_token's convention."""
        obligation = OrganizationObligationFactory(debtor=self.sheet, creditor=self.academy)
        token = mint_favor_token(self.academy, self.sheet, provenance_note="Cleared the trial")

        session = start_interaction(role=self.role, persona=self.persona, character=self.character)
        result = resolve_offer(session, self.offer)

        self.assertIsNotNone(result.object_pk)

        obligation.refresh_from_db()
        self.assertEqual(obligation.state, ObligationState.SETTLED)
        self.assertIsNotNone(obligation.settled_at)
        self.assertEqual(obligation.settled_by_token_id, token.pk)

        row = FavorTokenDetails.objects.get(pk=token.pk)
        self.assertIsNotNone(row.redeemed_at)
        self.assertTrue(
            OwnershipEvent.objects.filter(
                item_instance_id=row.item_instance_id,
                event_type=OwnershipEventType.CONSUMED,
            ).exists()
        )

    def test_refusal_without_obligation(self) -> None:
        """No OWED row against the offer's org -> typed refusal, not an error."""
        token = mint_favor_token(self.academy, self.sheet, provenance_note="Unrelated deed")

        result = run_settle_obligation_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("nothing", result.message)
        row = FavorTokenDetails.objects.get(pk=token.pk)
        self.assertIsNone(row.redeemed_at)

    def test_refusal_without_hare(self) -> None:
        """OWED, but no unredeemed Hare in hand -> typed refusal."""
        OrganizationObligationFactory(debtor=self.sheet, creditor=self.academy)

        result = run_settle_obligation_offer(self.offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("Golden Hare", result.message)

    def test_double_settle_is_a_no_op(self) -> None:
        """Settling once flips OWED -> SETTLED; a second attempt finds nothing left
        to settle and leaves a second, unrelated Hare untouched."""
        obligation = OrganizationObligationFactory(debtor=self.sheet, creditor=self.academy)
        mint_favor_token(self.academy, self.sheet, provenance_note="Cleared the trial")

        first = run_settle_obligation_offer(self.offer, self.persona)
        self.assertIsNotNone(first.object_pk)
        obligation.refresh_from_db()
        self.assertEqual(obligation.state, ObligationState.SETTLED)

        second_token = mint_favor_token(self.academy, self.sheet, provenance_note="A second deed")
        second = run_settle_obligation_offer(self.offer, self.persona)

        self.assertIsNone(second.object_pk)
        self.assertIn("nothing", second.message)
        row = FavorTokenDetails.objects.get(pk=second_token.pk)
        self.assertIsNone(row.redeemed_at)

    def test_authoring_error_no_faction_affiliation(self) -> None:
        role = NPCRoleFactory(faction_affiliation=None)
        offer = NPCServiceOfferFactory(role=role, kind=OfferKind.SETTLE_OBLIGATION, is_final=True)

        result = run_settle_obligation_offer(offer, self.persona)

        self.assertIsNone(result.object_pk)
        self.assertIn("no house", result.message)


class SettleObligationLoopEndToEndTests(TestCase):
    """The #2428 whole-branch fix headline proof: a fresh-seeded Unbound character
    can complete the entire in-play loop with no manual DB surgery — GM-award a
    Hare, settle at the Registrar, and the training door that was refused while
    OWED now opens."""

    @stub_content_root()
    def test_settle_at_registrar_unblocks_train_offer(self) -> None:  # noqa: PLR0915
        from evennia.accounts.models import AccountDB

        from world.character_creation.models import CharacterDraft
        from world.character_creation.services import finalize_character
        from world.magic.models import CharacterTechnique, Resonance, Tradition
        from world.magic.services.cg_catalog import get_gift_options, get_technique_options
        from world.npc_services.effects import run_train_offer
        from world.npc_services.models import NPCRole, NPCServiceOffer
        from world.npc_services.seeds import (
            ACADEMY_GENERALIST_TRAINER_ROLE_NAME,
            ACADEMY_REGISTRAR_ROLE_NAME,
        )
        from world.seeds.character_creation import DEFAULT_STAT_NAMES, ensure_shroudwatch_academy
        from world.seeds.database import seed_dev_database
        from world.societies.models import OrganizationObligation
        from world.societies.obligation_services import has_open_obligation
        from world.tarot.models import TarotCard
        from world.traits.models import Trait, TraitType

        seed_dev_database()
        academy = ensure_shroudwatch_academy()

        area = CharacterDraft._meta.get_field("selected_area").related_model.objects.get(
            name="Arx City"
        )
        beginnings = CharacterDraft._meta.get_field(
            "selected_beginnings"
        ).related_model.objects.get(name="Commoner")
        species = CharacterDraft._meta.get_field("selected_species").related_model.objects.get(
            name="Human"
        )
        gender = CharacterDraft._meta.get_field("selected_gender").related_model.objects.get(
            key="unspecified"
        )
        path = CharacterDraft._meta.get_field("selected_path").related_model.objects.get(
            name="Path of Steel"
        )
        height_band = CharacterDraft._meta.get_field("height_band").related_model.objects.get(
            name="average_band"
        )
        build = CharacterDraft._meta.get_field("build").related_model.objects.get(
            name="average_build"
        )
        tarot = TarotCard.objects.get(name="The Fool")

        tradition = Tradition.objects.get(name="Unbound")
        gift = get_gift_options(tradition, path)[0]
        technique_options = get_technique_options(path, gift, tradition)
        available_techniques = technique_options.pool + technique_options.signature

        trainer_role = NPCRole.objects.get(name=ACADEMY_GENERALIST_TRAINER_ROLE_NAME)
        trainer_offer = NPCServiceOffer.objects.get(
            role=trainer_role,
            kind=OfferKind.TRAIN,
            train_offer_details__technique__gift=gift,
        )
        train_technique = trainer_offer.train_offer_details.technique
        # CG picks a DIFFERENT technique from the same pool so the post-settle TRAIN
        # attempt below is a genuine "learn something new" grant, not a same-
        # technique "you already know this" refusal.
        cg_technique = next(t for t in available_techniques if t.pk != train_technique.pk)

        resonance = Resonance.objects.first()
        stat = Trait.objects.filter(trait_type=TraitType.STAT).first()
        from world.skills.models import Skill

        skill = Skill.objects.filter(is_active=True).first()

        account = AccountDB.objects.create(username="settle_loop_probe")
        draft_data = {
            "first_name": "Debtor",
            "description": "A fresh Unbound Prospect who owes the Academy a Hare.",
            "stats": dict.fromkeys(DEFAULT_STAT_NAMES, 2),
            "lineage_is_orphan": True,
            "tarot_card_name": tarot.name,
            "tarot_reversed": False,
            "traits_complete": True,
            "selected_gift_id": gift.id,
            "selected_technique_ids": [cg_technique.id],
            "selected_gift_resonance_id": resonance.id,
            "anima_check_stat_id": stat.id,
            "anima_check_skill_id": skill.id,
        }
        draft = CharacterDraft.objects.create(
            account=account,
            selected_area=area,
            selected_beginnings=beginnings,
            selected_species=species,
            selected_gender=gender,
            selected_path=path,
            selected_tradition=tradition,
            age=25,
            height_band=height_band,
            height_inches=(height_band.min_inches + height_band.max_inches) // 2,
            build=build,
            draft_data=draft_data,
        )

        character_obj = finalize_character(draft, add_to_roster=True)
        sheet = character_obj.character_sheet
        persona = sheet.primary_persona

        # Unbound -> OWED against Shroudwatch Academy, straight out of CG.
        self.assertTrue(has_open_obligation(sheet, academy))

        # TRAIN is refused while OWED.
        refused = run_train_offer(trainer_offer, persona)
        self.assertIsNone(refused.object_pk)
        self.assertIn("debt", refused.message)
        self.assertFalse(
            CharacterTechnique.objects.filter(character=sheet, technique=train_technique).exists()
        )

        # GM awards a Hare — mint_favor_token is the exact function
        # GMAwardAction(award_type="favor_token") delegates to; the action's own
        # permission gate is covered by actions.tests.test_gm_adjudication_actions.
        # A second Hare is minted too: settling the debt spends one Hare, and
        # TRAIN itself always spends its OWN separate Hare on top of that — the
        # two doors are independent Hare sinks, not one Hare unlocking both.
        mint_favor_token(academy, sheet, provenance_note="GM: cleared the entrance trial")
        mint_favor_token(academy, sheet, provenance_note="GM: reward for the training itself")

        # Settle at the Registrar via the real resolve_offer flow.
        registrar_role = NPCRole.objects.get(name=ACADEMY_REGISTRAR_ROLE_NAME)
        settle_offer = NPCServiceOffer.objects.get(
            role=registrar_role, kind=OfferKind.SETTLE_OBLIGATION
        )
        settle_session = start_interaction(
            role=registrar_role, persona=persona, character=character_obj
        )
        settle_result = resolve_offer(settle_session, settle_offer)
        self.assertIsNotNone(settle_result.object_pk)
        self.assertFalse(has_open_obligation(sheet, academy))
        self.assertEqual(
            OrganizationObligation.objects.get(debtor=sheet, creditor=academy).state,
            ObligationState.SETTLED,
        )

        # TRAIN now accepts.
        train_session = start_interaction(
            role=trainer_role, persona=persona, character=character_obj
        )
        accepted = resolve_offer(train_session, trainer_offer)
        self.assertIsNotNone(accepted.object_pk, accepted.message)
        self.assertTrue(
            CharacterTechnique.objects.filter(character=sheet, technique=train_technique).exists()
        )
