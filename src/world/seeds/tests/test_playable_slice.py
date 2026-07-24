"""Bounded playable-slice proof for the Phase A seed loader (#651).

Seeds the full dev database (now including the check-resolution spine) and
proves that a freshly seeded DB resolves a real check to a real CheckOutcome.
Scope is deliberately narrow: resolution tables + combat content + a single
factory-built character's check resolving. The full character-creation
pipeline and a live multi-round encounter are Phase 2, out of scope here.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.seeds.database import seed_dev_database
from world.seeds.tests.content_stub import stub_content_root


class TestPlayableSlice(TestCase):
    @stub_content_root()
    def test_resolution_tables_seeded(self) -> None:
        from world.traits.models import CheckRank, ResultChart

        seed_dev_database()
        self.assertGreater(CheckRank.objects.count(), 0)
        self.assertGreater(ResultChart.objects.count(), 0)

    @stub_content_root()
    def test_combat_resolution_content_present(self) -> None:
        from world.checks.models import CheckType

        seed_dev_database()
        # penetration + flee CheckTypes seeded by the combat cluster
        self.assertTrue(CheckType.objects.filter(name__in=["penetration", "flee"]).exists())

    @stub_content_root()
    def test_a_factory_character_check_resolves_to_a_real_outcome(self) -> None:
        """A factory character's check resolves to a real CheckOutcome.

        Mirrors world/checks/tests/test_services.py PerformCheckTests: seed the
        DB, build a character with an existing factory, give it a trait value
        for a trait the seeded ``flee`` CheckType weights, then call the live
        ``perform_check`` and assert a real (non-null) CheckOutcome comes back.
        """
        from world.checks.models import CheckType, CheckTypeTrait
        from world.checks.services import perform_check
        from world.checks.types import CheckResult
        from world.traits.models import (
            CharacterTraitValue,
            CheckOutcome,
            ResultChart,
            Trait,
        )

        seed_dev_database()
        ResultChart.clear_cache()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

        # The seeded "flee" CheckType weights real STAT traits (agility/wits).
        flee = CheckType.objects.get(name="flee")
        weighted_trait = (
            CheckTypeTrait.objects.filter(check_type=flee).select_related("trait").first()
        )
        self.assertIsNotNone(weighted_trait)
        trait = weighted_trait.trait

        sheet = CharacterSheetFactory()
        character = sheet.character
        CharacterTraitValue.objects.create(character=sheet, trait=trait, value=30)

        result = perform_check(character, flee, target_difficulty=0)

        self.assertIsInstance(result, CheckResult)
        self.assertGreater(result.trait_points, 0)
        self.assertIsNotNone(result.outcome)
        self.assertIsInstance(result.outcome, CheckOutcome)


class TestSeededCharacterCreation(TestCase):
    """The #1333 proof: a clean DB seeded via the Big Button can run CG.

    Builds a CharacterDraft against the SEEDED CG-world content (not test-only
    rows) and asserts ``finalize_character`` produces a CharacterSheet + primary
    Persona without raising. This is the test that closes the "fresh DB cannot
    run character creation" gap.
    """

    @stub_content_root()
    def test_finalize_character_works_on_seeded_only_db(self) -> None:
        from evennia.accounts.models import AccountDB

        from world.character_creation.models import CharacterDraft
        from world.character_creation.services import finalize_character
        from world.character_sheets.models import CharacterSheet
        from world.magic.models import Resonance, Tradition
        from world.magic.services.cg_catalog import get_gift_options, get_technique_options
        from world.seeds.character_creation import DEFAULT_STAT_NAMES
        from world.skills.models import Skill
        from world.tarot.models import TarotCard
        from world.traits.models import Trait, TraitType

        seed_dev_database()

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
        # "The Wanderer" (the generic fallback path) has no starter Gift options —
        # the CG-selectable magic pipeline lives on the 5 style-linked PROSPECT
        # paths — real lore-repo content, loaded via load_world_content()
        # (the stub content root carries an equivalent-shaped stand-in, #2474).
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

        # The seeded magic cluster / loaded catalog provides the Unbound
        # tradition + a Gift/technique pool for every PROSPECT path (#2426/#2474).
        tradition = Tradition.objects.get(name="Unbound")
        gift_options = get_gift_options(tradition, path)
        self.assertTrue(gift_options, "Unbound must have a gift option for Path of Steel")
        gift = gift_options[0]
        technique_options = get_technique_options(path, gift, tradition)
        available_techniques = technique_options.pool + technique_options.signature
        self.assertTrue(available_techniques, "the picked gift must have >=1 available technique")
        technique = available_techniques[0]
        resonance = Resonance.objects.first()
        self.assertIsNotNone(resonance, "magic cluster must seed a resonance")
        stat = Trait.objects.filter(trait_type=TraitType.STAT).first()
        self.assertIsNotNone(stat, "character-creation cluster must seed STAT traits")
        skill = Skill.objects.filter(is_active=True).first()
        self.assertIsNotNone(skill, "checks cluster must seed an active skill")

        account = AccountDB.objects.create(username="seeded_cg_player")
        draft_data = {
            "first_name": "Seeded",
            "description": "A character finalized against seeded-only content.",
            "stats": dict.fromkeys(DEFAULT_STAT_NAMES, 2),
            "lineage_is_orphan": True,
            "tarot_card_name": tarot.name,
            "tarot_reversed": False,
            "traits_complete": True,
            "selected_gift_id": gift.id,
            "selected_technique_ids": [technique.id],
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

        character = finalize_character(draft, add_to_roster=True)

        self.assertIsNotNone(character)
        self.assertTrue(CharacterSheet.objects.filter(character=character).exists())
        # #2121 — the seeded "Arx City" StartingArea now carries a wired
        # default_starting_room; finalize_character() never produces
        # location=None on a Big-Button-seeded DB.
        self.assertIsNotNone(character.location)

    @stub_content_root()
    def test_tradition_step_completable_for_every_seeded_beginning(self) -> None:
        """The CG Tradition step is completable, via the real endpoints, for every
        seeded Beginning (#2426 whole-branch-review finding).

        Without ``seed_beginning_traditions()``,
        ``TraditionViewSet.get_queryset()`` returns nothing (empty
        ``cached_beginning_traditions``) and ``select-tradition`` independently
        400s for every Beginning on a fresh Big-Button-only DB — CG is
        uncompletable, even the tradition-agnostic Unbound path. This drives the
        real gates end-to-end (the API endpoint) instead of assigning
        ``draft.selected_tradition`` directly, which is what let the original gap
        slip past this test file.
        """
        from evennia.accounts.models import AccountDB
        from rest_framework import status
        from rest_framework.test import APIClient

        from world.character_creation.models import Beginnings, CharacterDraft

        seed_dev_database()

        beginnings = list(Beginnings.objects.filter(is_active=True))
        self.assertTrue(
            beginnings, "character_creation cluster must seed at least one active Beginning"
        )

        account = AccountDB.objects.create(username="tradition_step_probe")
        client = APIClient()
        client.force_authenticate(user=account)

        for beginning in beginnings:
            # Same list TraditionViewSet.get_queryset() reads (#2426).
            bts = beginning.cached_beginning_traditions
            self.assertTrue(
                bts,
                f"{beginning.name!r} must have >=1 seeded BeginningTradition (#2426)",
            )
            unbound_bt = next((bt for bt in bts if bt.tradition.name == "Unbound"), None)
            self.assertIsNotNone(
                unbound_bt, f"{beginning.name!r} must offer the Unbound tradition (#2426)"
            )

            draft = CharacterDraft.objects.create(account=account, selected_beginnings=beginning)

            response = client.post(
                f"/api/character-creation/drafts/{draft.id}/select-tradition/",
                {"tradition_id": unbound_bt.tradition_id},
                format="json",
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                f"select-tradition failed for {beginning.name!r}: {response.data}",
            )
            draft.refresh_from_db()
            self.assertEqual(draft.selected_tradition_id, unbound_bt.tradition_id)


class TestAcademyTrainingLoopReachable(TestCase):
    """#2428 whole-branch fix (Important finding): a fresh-seeded DB must not
    dead-end a Prospect's training loop before any lore-repo trainer content
    exists. The ungated Academy generalist trainer (``ensure_academy_
    generalist_trainer_role``) is the dev-minimum guarantee — every PROSPECT
    Path must have >=1 TRAIN offer that is genuinely GRANTABLE (not merely
    listed by ``available_offers`` — TRAIN offers carry no path/gift-specific
    ``eligibility_rule``; availability is enforced at grant time inside
    ``run_train_offer`` via ``_technique_available_to_learner``)."""

    @stub_content_root()
    def test_every_prospect_path_has_a_reachable_train_offer(self) -> None:
        from world.action_points.models import ActionPointPool
        from world.currency.services import get_or_create_purse, mint_favor_token
        from world.magic.factories import ResonanceFactory
        from world.magic.models.grants import PathGiftGrant
        from world.magic.specialization.services import grant_gift_to_character
        from world.npc_services.constants import OfferKind
        from world.npc_services.effects import run_train_offer
        from world.npc_services.models import NPCRole, NPCServiceOffer
        from world.npc_services.seeds import ACADEMY_GENERALIST_TRAINER_ROLE_NAME
        from world.progression.factories import CharacterPathHistoryFactory
        from world.scenes.factories import PersonaFactory
        from world.seeds.character_creation import ensure_shroudwatch_academy

        # The starter Gift/Technique/PathGiftGrant/Tradition catalog is real
        # lore-repo content, loaded via load_world_content() — the stub content
        # root carries an equivalent-shaped stand-in (#2474), so
        # ensure_academy_generalist_trainer_role() (invoked inside
        # seed_dev_database(), via the npc_services cluster) has real Technique
        # rows to author TRAIN offers against.
        seed_dev_database()
        academy = ensure_shroudwatch_academy()
        role = NPCRole.objects.get(name=ACADEMY_GENERALIST_TRAINER_ROLE_NAME)

        path_gift_grants = list(PathGiftGrant.objects.select_related("path", "gift"))
        self.assertGreaterEqual(len(path_gift_grants), 5)

        for grant in path_gift_grants:
            path = grant.path
            gift = grant.gift

            offer = NPCServiceOffer.objects.filter(
                role=role,
                kind=OfferKind.TRAIN,
                train_offer_details__technique__gift=gift,
            ).first()
            self.assertIsNotNone(
                offer, f"generalist trainer has no TRAIN offer for {path.name}'s pool"
            )
            technique = offer.train_offer_details.technique
            self.assertIn(
                technique,
                grant.starter_techniques.all(),
                f"{path.name}'s offered technique isn't in its own starter pool",
            )

            persona = PersonaFactory()
            sheet = persona.character_sheet
            character = sheet.character
            CharacterPathHistoryFactory(character=sheet, path=path)
            # Mirrors CG's own `_finalize_magic_data` call shape: a real Prospect
            # always already owns their one Path-matched major Gift (with a
            # provisioned, resonance-anchored GIFT thread) by the time they can
            # ever see an Academy trainer — starter-catalog MAJOR gifts carry no
            # `resonances` M2M of their own, so leaving this ungranted would hit
            # charge_and_learn's implicit-acquisition path, which cannot resolve
            # a resonance and never provisions a thread —
            # not a real player state, just a test-only bare persona artifact.
            grant_gift_to_character(sheet, gift, resonance=ResonanceFactory())
            pool = ActionPointPool.get_or_create_for_character(character)
            pool.current = 200
            pool.save()
            purse = get_or_create_purse(sheet)
            purse.balance = 1000
            purse.save()
            # TRAIN always spends a Hare regardless of the obligation gate (which
            # this bare factory persona has no row for at all, so it's already
            # open) — mint one so the acquisition itself can complete.
            mint_favor_token(academy, sheet, provenance_note="test rig: Hare for TRAIN")

            result = run_train_offer(offer, persona)

            self.assertIsNotNone(
                result.object_pk,
                f"{path.name}'s generalist TRAIN offer was not grantable: {result.message}",
            )
