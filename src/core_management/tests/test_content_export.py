"""Tests for the content export pipeline."""

import json
from pathlib import Path
import tempfile
from unittest import mock

from django.test import TestCase

from core_management.content_export import (
    CONTENT_MODELS,
    ContentExportError,
    export_to_content_repo,
)


class ContentExportTests(TestCase):
    """End-to-end: export models to a temp dir, verify format."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_export_writes_one_file_per_model_with_rows(self) -> None:
        """Models with rows get a JSON file; models with 0 rows are skipped."""
        # Create a simple content model row so export has something to write
        from world.magic.models import EffectType

        EffectType.objects.get_or_create(
            name="Test Export Effect",
            defaults={"description": "Test effect for export."},
        )

        result = export_to_content_repo(self.root)
        # At least some files should be written
        assert len(result.written) > 0
        assert result.total_records > 0
        # Each written file should be valid JSON
        for path in result.written:
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, list)
            assert len(data) > 0
        # The EffectType file should exist and contain our test record
        et_path = self.root / "fixtures" / "magic" / "effecttype.json"
        assert et_path.exists()
        et_data = json.loads(et_path.read_text(encoding="utf-8"))
        names = [r["fields"]["name"] for r in et_data]
        assert "Test Export Effect" in names

    def test_exported_files_have_no_pks(self) -> None:
        """Exported fixtures must not have pk fields (natural-key only)."""
        result = export_to_content_repo(self.root)
        for path in result.written:
            data = json.loads(path.read_text(encoding="utf-8"))
            for record in data:
                assert "pk" not in record, f"{path} has pk field: {record.get('pk')}"

    def test_exported_files_use_natural_key_fk_references(self) -> None:
        """FK values should be natural-key lists, not integer pks."""
        result = export_to_content_repo(self.root)
        for path in result.written:
            data = json.loads(path.read_text(encoding="utf-8"))
            for record in data:
                fields = record.get("fields", {})
                for key, value in fields.items():
                    # A natural-key FK reference is a list (e.g. ["Category", "name"])
                    # A pk-based reference would be an integer — we should never see those
                    # (use_natural_foreign_keys=True ensures this)
                    if isinstance(value, list):
                        assert all(not isinstance(v, int) or v is None for v in value), (
                            f"{path} field {key} has integer in FK list: {value}"
                        )

    def test_export_creates_subdirectory_structure(self) -> None:
        """Files are written to fixtures/<app_label>/<model_name>.json."""
        result = export_to_content_repo(self.root)
        app_labels = {m.split(".")[0] for m in CONTENT_MODELS}
        for path in result.written:
            rel = path.relative_to(self.root / "fixtures")
            parts = rel.parts
            assert len(parts) == 2, f"Expected 2 path parts, got {parts}"
            assert parts[0] in app_labels, f"Unexpected app_label dir: {parts[0]}"

    def test_export_round_trips_through_load_entries(self) -> None:
        """Export then import = no-op (all updates, no creates)."""
        from world.magic.models import EffectType

        EffectType.objects.get_or_create(
            name="Round Trip Effect",
            defaults={"description": "Round-trip test."},
        )

        from core_management.content_fixtures import build_all, load_entries

        result = export_to_content_repo(self.root)
        assert result.errors == []

        # Now load the exported files back
        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        # All records should already exist — 0 created, N updated
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

    def test_export_raises_on_missing_content_root(self) -> None:
        """When CONTENT_REPO_PATH is not set and no arg given, raises."""
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("CONTENT_REPO_PATH", None)
            with self.assertRaises(ContentExportError):
                export_to_content_repo(None)

    def test_glimpse_catalog_round_trips(self) -> None:
        """GlimpseTag + suggestion export then import = updates, no creates (#2427)."""
        from world.distinctions.factories import DistinctionFactory
        from world.magic.factories import (
            GlimpseTagDistinctionSuggestionFactory,
            GlimpseTagFactory,
        )

        tag = GlimpseTagFactory(slug="round-trip-tag")
        GlimpseTagDistinctionSuggestionFactory(
            tag=tag, distinction=DistinctionFactory(slug="round-trip-distinction")
        )

        from core_management.content_fixtures import build_all, load_entries

        result = export_to_content_repo(self.root)
        assert result.errors == []
        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0

    def test_media_export_excludes_player_uploaded_rows(self) -> None:
        """Player-uploaded Media (slug=None) must never export toward the lore repo.

        #2408: without the ``slug__isnull=False`` filter in the export loop,
        every player-uploaded row would serialize with the identical,
        unresolvable natural key ``(None,)`` and leak player content into the
        content-repo fixtures — the exact thing ADR-0142's content boundary
        exists to prevent.
        """
        from evennia_extensions.factories import MediaFactory

        MediaFactory(player_data=None, slug="staff-art")  # should export
        MediaFactory()  # player upload, slug=None — must NOT export

        result = export_to_content_repo(self.root)
        assert result.errors == []

        exported = (self.root / "fixtures" / "evennia_extensions" / "media.json").read_text(
            encoding="utf-8"
        )
        assert "staff-art" in exported
        assert '"slug": null' not in exported

    def test_clue_is_a_content_model(self) -> None:
        """Clue became exportable content once it carried a natural key (#2451)."""
        assert "clues.clue" in CONTENT_MODELS

    def test_mission_graph_round_trips(self) -> None:
        """A small authored mission graph exports and reloads as a no-op (#2470).

        Exercises 2+ MissionOptionRouteReward rows and 2+ MissionRenownAward
        rows sharing the same parent route, plus a MissionOptionRouteCandidate,
        so all three natural keys round-trip.

        NOTE (re-review, #2470): this test verifies pipeline SHAPE only — rows
        here are created before export and never deleted before reimport, so
        ``load_entries``'s ``update_or_create(**lookup, defaults=fields)``
        always matches an existing row and takes the UPDATE branch.
        ``save()``'s ``if self.pk is None:`` guard (the actual sequence
        auto-assign fix in models.py) is a no-op on updates, so this test does
        NOT exercise it and would pass identically against the pre-fix
        formula. The real proof that save() auto-assigns correctly under the
        adversarial explicit-then-auto-assign ordering lives in
        ``world/missions/tests/test_sequence_auto_assign.py``, which calls
        save() directly and does not go through this pipeline. This test is
        kept as legitimate (if narrower) coverage that multiple rows per
        parent survive an export/import round trip unchanged.
        """
        from world.missions.factories import (
            MissionNodeFactory,
            MissionOptionFactory,
            MissionOptionRouteCandidateFactory,
            MissionOptionRouteFactory,
            MissionOptionRouteRewardFactory,
            MissionTemplateFactory,
        )
        from world.missions.models import MissionRenownAward
        from world.societies.constants import RenownMagnitude, RenownRisk

        template = MissionTemplateFactory(name="Round Trip Prelude Template")
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(node=node, key="entry-option")
        route = MissionOptionRouteFactory(
            option=option, outcome_tier=None, target_node=None, is_random_set=True
        )
        MissionOptionRouteRewardFactory(route=route, amount=50)
        MissionOptionRouteRewardFactory(route=route, amount=75)
        MissionOptionRouteCandidateFactory(route=route)
        MissionRenownAward.objects.create(
            route=route, magnitude=RenownMagnitude.MODERATE, risk=RenownRisk.NONE
        )
        MissionRenownAward.objects.create(
            route=route, magnitude=RenownMagnitude.HIGH, risk=RenownRisk.LOW
        )

        from core_management.content_fixtures import build_all, load_entries

        result = export_to_content_repo(self.root)
        assert result.errors == []
        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        # Re-run to prove idempotency isn't order-dependent luck: a second
        # import of the same export must also create nothing.
        load_result_again = build_all(self.root)
        created_again, _updated_again, _ = load_entries(load_result_again)
        assert created_again == 0, (
            f"Second round-trip created {created_again} new records (expected 0)"
        )

    def test_content_models_all_have_natural_key(self) -> None:
        """Every model in the allowlist must have NaturalKeyMixin."""
        from django.apps import apps

        from core.natural_keys import NaturalKeyMixin

        for model_label in CONTENT_MODELS:
            app_label, model_name = model_label.split(".")
            model = apps.get_model(app_label, model_name)
            assert issubclass(model, NaturalKeyMixin), f"{model_label} lacks NaturalKeyMixin"

    def test_magic_catalog_round_trips_with_payload(self) -> None:
        """A payload-bearing Technique + all three grant tables export → load = no-op."""
        from world.classes.factories import PathFactory
        from world.conditions.factories import (
            CapabilityTypeFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.magic.factories import (
            GiftFactory,
            ResonanceFactory,
            RestrictionFactory,
            TechniqueAppliedConditionFactory,
            TechniqueCapabilityGrantFactory,
            TechniqueCapabilityRequirementFactory,
            TechniqueFactory,
            TechniqueRemovedConditionFactory,
            TraditionFactory,
        )
        from world.magic.models import (
            PathGiftGrant,
            PortalAnchorKind,
            TechniqueDamageProfile,
            TechniqueOutcomeModifier,
            TraditionGiftGrant,
        )
        from world.species.factories import SpeciesGiftGrantFactory
        from world.traits.factories import CheckOutcomeFactory

        anchor = PortalAnchorKind.objects.create(name="Mirror RT")
        # damage_profile=False: TechniqueFactory's post_generation hook auto-seeds an
        # untyped damage profile from EffectType.base_power (default 10), which would
        # collide with the explicit untyped TechniqueDamageProfile.objects.create(...)
        # below (unique_untyped_damage_profile_per_technique is one-per-technique).
        technique = TechniqueFactory(
            name="Round Trip Bolt", travel_anchor_kind=anchor, damage_profile=False
        )
        technique.restrictions.add(RestrictionFactory(name="RT Touch"))
        TechniqueDamageProfile.objects.create(
            technique=technique, damage_type=DamageTypeFactory(), base_damage=3
        )
        TechniqueDamageProfile.objects.create(technique=technique, damage_type=None)
        TechniqueAppliedConditionFactory(technique=technique, condition=ConditionTemplateFactory())
        TechniqueRemovedConditionFactory(technique=technique, condition=ConditionTemplateFactory())
        TechniqueCapabilityGrantFactory(technique=technique, capability=CapabilityTypeFactory())
        TechniqueCapabilityRequirementFactory(
            technique=technique, capability=CapabilityTypeFactory()
        )
        TechniqueOutcomeModifier.objects.create(outcome=CheckOutcomeFactory(), modifier_value=-2)
        technique.gift.resonances.add(ResonanceFactory())

        tradition_grant = TraditionGiftGrant.objects.create(
            tradition=TraditionFactory(), gift=technique.gift
        )
        tradition_grant.signature_techniques.set([technique])
        path_grant = PathGiftGrant.objects.create(path=PathFactory(), gift=technique.gift)
        path_grant.starter_techniques.set([technique])
        SpeciesGiftGrantFactory(gift=GiftFactory(name="RT Minor Gift"))

        from core_management.content_fixtures import build_all, load_entries

        result = export_to_content_repo(self.root)
        assert result.errors == [], result.errors

        load_result = build_all(self.root)
        created, _updated, deferred = load_entries(load_result, defer_unresolved=True)
        assert created == 0, f"Round-trip created {created} records: {load_result.skipped}"
        assert deferred == [], f"Round-trip deferred {len(deferred)} records"
        # M2M survived the trip:
        technique.refresh_from_db()
        assert technique.restrictions.count() == 1
        assert list(path_grant.starter_techniques.all()) == [technique]
        technique.gift.refresh_from_db()
        assert technique.gift.resonances.count() == 1


class MagicCatalogContentExportTests(TestCase):
    """Round-trip coverage for the five magic catalog models (#2474).

    Uses ``load_world_content`` rather than the bare ``build_all`` +
    ``load_entries`` pair the other tests in this file use: within the
    ``fixtures/magic/`` directory, ``gift.json`` sorts alphabetically before
    ``resonance.json`` and ``technique.json`` sorts before ``techniquestyle.json``
    (file processing order is plain alphabetical — ``NaturalKeyConfig.dependencies``
    is metadata only, not consulted for load ordering anywhere in this pipeline),
    so a straight one-pass ``load_entries`` would skip ``Gift``/``Technique``
    on a fresh load (their FK/M2M targets don't exist yet at the moment their own
    file is processed). ``load_world_content``'s defer-then-retry-to-fixed-point
    pass (built for the content-vs-grid circular dependency, #2448; retried to a
    fixed point rather than once, #2474 review fix) closes this content-internal
    ordering gap too — see ``test_populated_grant_m2m_resolves_across_multiple_retry_passes``
    below for the deeper (3-hop) case that needs more than a single retry.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_magic_catalog_round_trips_through_load_world_content(self) -> None:
        """Resonance/Gift/Technique/PathGiftGrant/TraditionGiftGrant survive a wipe."""
        from core_management.content_fixtures import load_world_content
        from world.classes.factories import PathFactory
        from world.magic.factories import (
            GiftFactory,
            PathGiftGrantFactory,
            ResonanceFactory,
            TechniqueFactory,
            TraditionFactory,
            TraditionGiftGrantFactory,
        )
        from world.magic.models import (
            Gift,
            PathGiftGrant,
            Resonance,
            Technique,
            TraditionGiftGrant,
        )

        resonance = ResonanceFactory(name="Round Trip Resonance")
        gift = GiftFactory(name="Round Trip Gift")
        # Exercises the many-to-many natural-key fix (#2474) — an untouched
        # (empty-list) m2m field already broke the load before that fix, so a
        # populated one proves the fix resolves real related rows, not just
        # tolerates an empty list.
        gift.resonances.add(resonance)
        technique = TechniqueFactory(
            name="Round Trip Technique",
            gift=gift,
            damage_profile=False,
        )
        path = PathFactory()
        path_grant = PathGiftGrantFactory(path=path, gift=gift)
        tradition = TraditionFactory(name="Round Trip Tradition")
        tradition_grant = TraditionGiftGrantFactory(tradition=tradition, gift=gift)

        result = export_to_content_repo(self.root)
        assert result.errors == []

        # Wipe every row the export just captured. Grants first (both PROTECT
        # their `gift` FK), then technique/gift/resonance. Path/Tradition are
        # left standing — they aren't part of this issue's five models.
        TraditionGiftGrant.objects.filter(pk=tradition_grant.pk).delete()
        PathGiftGrant.objects.filter(pk=path_grant.pk).delete()
        Technique.objects.filter(pk=technique.pk).delete()
        Gift.objects.filter(pk=gift.pk).delete()
        Resonance.objects.filter(pk=resonance.pk).delete()

        world_result = load_world_content(self.root)

        assert world_result.skipped == []

        reloaded_resonance = Resonance.objects.get(name="Round Trip Resonance")
        reloaded_gift = Gift.objects.get(name="Round Trip Gift")
        assert list(reloaded_gift.resonances.all()) == [reloaded_resonance]

        reloaded_technique = Technique.objects.get(gift=reloaded_gift, name="Round Trip Technique")
        # DiscoverableContent's own field (discovery_achievement) survives the
        # trip at its default null value — Achievement itself lacks a natural
        # key, so a populated FK there isn't exportable by this pipeline yet;
        # out of scope for this task (see task-2-report.md).
        assert reloaded_technique.discovery_achievement is None
        # TechniqueStyle/EffectType were never wiped — same underlying rows.
        assert reloaded_technique.style_id == technique.style_id
        assert reloaded_technique.effect_type_id == technique.effect_type_id

        reloaded_path_grant = PathGiftGrant.objects.get(path=path, gift=reloaded_gift)
        assert reloaded_path_grant.path_id == path.pk

        reloaded_tradition_grant = TraditionGiftGrant.objects.get(
            tradition=tradition, gift=reloaded_gift
        )
        assert reloaded_tradition_grant.tradition_id == tradition.pk

    def test_populated_grant_m2m_resolves_across_multiple_retry_passes(self) -> None:
        """#2474 review fix: a 3-hop chain (grant -> gift -> technique) needs >1 retry.

        ``PathGiftGrant.starter_techniques``/``TraditionGiftGrant.signature_techniques``
        name ``Technique`` rows. On a fresh load, alphabetical file order puts
        ``pathgiftgrant.json``/``traditiongiftgrant.json`` BEFORE ``technique.json`` —
        so even after the single retry pass resolves ``gift`` (technique.json's own
        prerequisite), the grant's m2m still can't resolve, because Technique itself
        hasn't been created yet within that same retry pass. A single-pass retry
        lands the grants in ``skipped``; a fixed-point retry (this fix) keeps
        looping until nothing new resolves, so the grants get another chance once
        Technique exists.
        """
        from core_management.content_fixtures import load_world_content
        from world.classes.factories import PathFactory
        from world.magic.factories import (
            GiftFactory,
            PathGiftGrantFactory,
            ResonanceFactory,
            TechniqueFactory,
            TraditionFactory,
            TraditionGiftGrantFactory,
        )
        from world.magic.models import (
            Gift,
            PathGiftGrant,
            Resonance,
            Technique,
            TraditionGiftGrant,
        )

        resonance = ResonanceFactory(name="Chain Resonance")
        gift = GiftFactory(name="Chain Gift")
        gift.resonances.add(resonance)
        technique = TechniqueFactory(name="Chain Technique", gift=gift, damage_profile=False)
        path = PathFactory()
        path_grant = PathGiftGrantFactory(path=path, gift=gift)
        path_grant.starter_techniques.add(technique)
        tradition = TraditionFactory(name="Chain Tradition")
        tradition_grant = TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        tradition_grant.signature_techniques.add(technique)

        result = export_to_content_repo(self.root)
        assert result.errors == []

        TraditionGiftGrant.objects.filter(pk=tradition_grant.pk).delete()
        PathGiftGrant.objects.filter(pk=path_grant.pk).delete()
        Technique.objects.filter(pk=technique.pk).delete()
        Gift.objects.filter(pk=gift.pk).delete()
        Resonance.objects.filter(pk=resonance.pk).delete()

        world_result = load_world_content(self.root)

        assert world_result.skipped == [], (
            f"Expected every deferred object to resolve, got skips: {world_result.skipped}"
        )

        reloaded_gift = Gift.objects.get(name="Chain Gift")
        reloaded_technique = Technique.objects.get(gift=reloaded_gift, name="Chain Technique")

        reloaded_path_grant = PathGiftGrant.objects.get(path=path, gift=reloaded_gift)
        assert list(reloaded_path_grant.starter_techniques.all()) == [reloaded_technique]

        reloaded_tradition_grant = TraditionGiftGrant.objects.get(
            tradition=tradition, gift=reloaded_gift
        )
        assert list(reloaded_tradition_grant.signature_techniques.all()) == [reloaded_technique]


class SpeciesFormTraitContentExportTests(TestCase):
    """Round-trip coverage for Species/FormTrait/FormTraitOption/SpeciesFormTrait.

    These four models are the CG Appearance stage's data source (#2463): a
    species with zero ``SpeciesFormTrait`` rows renders an empty Appearance
    stage. The round-trip below proves the content pipeline carries a species'
    full form-trait set (trait + options + the species↔trait link, including
    the ``allowed_options`` M2M) through an export → wipe → reload — the exact
    shape that broke when the elf subspecies shipped without form-trait rows.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_species_form_traits_round_trip_through_load_world_content(self) -> None:
        """A species' form traits + options survive a content wipe and reload."""
        from core_management.content_fixtures import load_world_content
        from world.forms.factories import (
            FormTraitFactory,
            FormTraitOptionFactory,
            SpeciesFormTraitFactory,
        )
        from world.forms.models import FormTrait, FormTraitOption, SpeciesFormTrait
        from world.species.factories import SpeciesFactory
        from world.species.models import Species

        species = SpeciesFactory(name="Round Trip Species")
        hair_trait = FormTraitFactory(name="rt_hair_color", display_name="Hair Color")
        eye_trait = FormTraitFactory(name="rt_eye_color", display_name="Eye Color")
        # Two options on hair, one on eye — hair exercises the multi-option path.
        hair_opt_a = FormTraitOptionFactory(trait=hair_trait, name="black", display_name="Black")
        hair_opt_b = FormTraitOptionFactory(trait=hair_trait, name="silver", display_name="Silver")
        eye_opt = FormTraitOptionFactory(trait=eye_trait, name="violet", display_name="Violet")

        hair_link = SpeciesFormTraitFactory(species=species, trait=hair_trait)
        eye_link = SpeciesFormTraitFactory(species=species, trait=eye_trait)
        # Restrict hair to a subset of options — exercises the allowed_options M2M
        # round-trip (the path that breaks silently when the M2M isn't carried).
        hair_link.allowed_options.add(hair_opt_a, hair_opt_b)

        result = export_to_content_repo(self.root)
        assert result.errors == []

        # Wipe every row the export captured. SpeciesFormTrait first (FK→species,
        # FK→trait), then options (FK→trait), then traits, then species.
        SpeciesFormTrait.objects.filter(pk__in=[hair_link.pk, eye_link.pk]).delete()
        FormTraitOption.objects.filter(pk__in=[hair_opt_a.pk, hair_opt_b.pk, eye_opt.pk]).delete()
        FormTrait.objects.filter(pk__in=[hair_trait.pk, eye_trait.pk]).delete()
        Species.objects.filter(pk=species.pk).delete()

        world_result = load_world_content(self.root)
        assert world_result.skipped == []

        reloaded_species = Species.objects.get(name="Round Trip Species")
        reloaded_hair = FormTrait.objects.get(name="rt_hair_color")
        reloaded_eye = FormTrait.objects.get(name="rt_eye_color")

        # Both traits link back to the species, available in CG.
        links = SpeciesFormTrait.objects.filter(
            species=reloaded_species, is_available_in_cg=True
        ).select_related("trait")
        assert {link.trait.name for link in links} == {"rt_hair_color", "rt_eye_color"}

        # The allowed_options M2M survived the trip for hair; eye (empty) stayed empty.
        reloaded_hair_link = SpeciesFormTrait.objects.get(
            species=reloaded_species, trait=reloaded_hair
        )
        reloaded_eye_link = SpeciesFormTrait.objects.get(
            species=reloaded_species, trait=reloaded_eye
        )
        assert {opt.name for opt in reloaded_hair_link.allowed_options.all()} == {
            "black",
            "silver",
        }
        assert reloaded_eye_link.allowed_options.count() == 0

        # The options themselves round-tripped and re-attach to their traits.
        assert {opt.name for opt in reloaded_hair.options.all()} == {"black", "silver"}
        assert {opt.name for opt in reloaded_eye.options.all()} == {"violet"}


class CovenantRoleContentExportTests(TestCase):
    """Round-trip coverage for CovenantRole + CovenantRoleActionScaling (#2529).

    ``covenants.covenantrole``/``covenants.covenantroleactionscaling`` were added
    to ``CONTENT_MODELS`` with natural keys (``CovenantRole`` -> ``["slug"]``;
    ``CovenantRoleActionScaling`` -> ``["covenant_role", "action_key"]``) but no
    test round-tripped actual rows through export -> import, leaving the
    ``parent_role`` self-FK, the ``resonance`` FK (sub-roles), and the blend-weight
    Decimal fields unexercised in the pipeline.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_covenant_role_and_action_scaling_round_trip(self) -> None:
        """A blended primary role + its scaling + a sub-role survive export -> import."""
        from decimal import Decimal

        from world.covenants.factories import (
            CovenantRoleActionScalingFactory,
            CovenantRoleFactory,
            SubroleCovenantRoleFactory,
        )

        primary = CovenantRoleFactory(
            name="Round Trip Vanguard",
            slug="round-trip-vanguard",
            sword_weight=Decimal("0.3"),
            shield_weight=Decimal("0.1"),
            crown_weight=Decimal("0.6"),
        )
        primary.full_clean()  # proves the blend is a valid primary-role state
        scaling = CovenantRoleActionScalingFactory(
            covenant_role=primary,
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("0.125"),
        )
        sub_role = SubroleCovenantRoleFactory(
            parent_role=primary,
            name="Round Trip Vanguard (Ember)",
            slug="round-trip-vanguard-ember",
            unlock_thread_level=2,
        )
        sub_role.full_clean()  # proves the all-zero-weight sub-role is valid too
        original_resonance_id = sub_role.resonance_id
        assert original_resonance_id is not None

        result = export_to_content_repo(self.root)
        assert result.errors == []

        role_path = self.root / "fixtures" / "covenants" / "covenantrole.json"
        scaling_path = self.root / "fixtures" / "covenants" / "covenantroleactionscaling.json"
        assert role_path.exists()
        assert scaling_path.exists()

        role_records = {
            r["fields"]["slug"]: r for r in json.loads(role_path.read_text(encoding="utf-8"))
        }
        for record in role_records.values():
            assert "pk" not in record

        primary_record = role_records["round-trip-vanguard"]
        assert primary_record["fields"]["parent_role"] is None
        assert Decimal(str(primary_record["fields"]["sword_weight"])) == Decimal("0.3")
        assert Decimal(str(primary_record["fields"]["shield_weight"])) == Decimal("0.1")
        assert Decimal(str(primary_record["fields"]["crown_weight"])) == Decimal("0.6")

        sub_record = role_records["round-trip-vanguard-ember"]
        # Natural-key identity, not raw pks: parent_role/resonance are lists.
        assert sub_record["fields"]["parent_role"] == ["round-trip-vanguard"]
        assert isinstance(sub_record["fields"]["resonance"], list)
        assert all(not isinstance(v, int) for v in sub_record["fields"]["resonance"])
        assert sub_record["fields"]["unlock_thread_level"] == 2
        assert Decimal(str(sub_record["fields"]["sword_weight"])) == 0

        scaling_records = json.loads(scaling_path.read_text(encoding="utf-8"))
        assert len(scaling_records) == 1
        assert "pk" not in scaling_records[0]
        assert scaling_records[0]["fields"]["covenant_role"] == ["round-trip-vanguard"]
        assert Decimal(str(scaling_records[0]["fields"]["thread_level_multiplier"])) == Decimal(
            "0.125"
        )

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        primary.refresh_from_db()
        assert primary.sword_weight == Decimal("0.300")
        assert primary.shield_weight == Decimal("0.100")
        assert primary.crown_weight == Decimal("0.600")

        sub_role.refresh_from_db()
        assert sub_role.parent_role_id == primary.pk
        assert sub_role.resonance_id == original_resonance_id
        assert sub_role.unlock_thread_level == 2

        scaling.refresh_from_db()
        assert scaling.covenant_role_id == primary.pk
        assert scaling.thread_level_multiplier == Decimal("0.125")

    def test_covenant_role_defense_profile_round_trips(self) -> None:
        """CovenantRoleDefenseProfile (#2533) survives export -> import via its NK.

        NK is ``["covenant_role"]`` (the FK's own natural key, a single-element
        list holding the role's slug) — unexercised until now.
        """
        from world.covenants.constants import DefenseStyle
        from world.covenants.factories import CovenantRoleDefenseProfileFactory, CovenantRoleFactory

        role = CovenantRoleFactory(name="Defense Profile Role", slug="defense-profile-role")
        profile = CovenantRoleDefenseProfileFactory(
            covenant_role=role,
            style=DefenseStyle.EVASION,
            gear_additive_tenths=3,
        )

        result = export_to_content_repo(self.root)
        assert result.errors == []

        profile_path = self.root / "fixtures" / "covenants" / "covenantroledefenseprofile.json"
        assert profile_path.exists()

        records = json.loads(profile_path.read_text(encoding="utf-8"))
        assert len(records) == 1
        record = records[0]
        assert "pk" not in record
        assert record["fields"]["covenant_role"] == ["defense-profile-role"]
        assert record["fields"]["style"] == DefenseStyle.EVASION
        assert record["fields"]["gear_additive_tenths"] == 3

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        profile.refresh_from_db()
        assert profile.covenant_role_id == role.pk
        assert profile.style == DefenseStyle.EVASION
        assert profile.gear_additive_tenths == 3


class VowSituationalPerkContentExportTests(TestCase):
    """Round-trip coverage for the situational-perk authoring models (#2536).

    ``covenants.vowsituationalperk`` / ``vowsituationalperkrung`` /
    ``vowsituationalperksituation`` were added to ``CONTENT_MODELS`` with
    natural keys — verify the ``covenant_role``/``perk`` FKs, the nullable
    ``check_type`` FK-NK (scoped to ``checks.CheckType``, itself NK-resolvable
    per #2503), and the choice fields all survive export -> import identity-stable.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _build_rows(self):
        """Create one perk + situation + rung, keyed on a fresh role + check_type."""
        from world.checks.factories import CheckTypeFactory
        from world.covenants.factories import (
            CovenantRoleFactory,
            VowSituationalPerkFactory,
            VowSituationalPerkRungFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation

        role = CovenantRoleFactory(name="Round Trip Scout", slug="round-trip-scout", sword_weight=1)
        check_type = CheckTypeFactory(name="Round Trip Perception")
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            name="Scout's Instinct",
            beneficiary=PerkBeneficiary.WHOLE_GROUP,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=15,
            announce_template="{holder} reveals a trap!",
            check_type=check_type,
        )
        situation = VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)
        rung = VowSituationalPerkRungFactory(
            perk=perk,
            rung_number=1,
            extra_situation=Situation.ALLY_LOW_HEALTH,
            magnitude_tenths=25,
        )
        return role, check_type, perk, situation, rung

    def _assert_exported_fixtures(self) -> None:
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation

        perk_path = self.root / "fixtures" / "covenants" / "vowsituationalperk.json"
        situation_path = self.root / "fixtures" / "covenants" / "vowsituationalperksituation.json"
        rung_path = self.root / "fixtures" / "covenants" / "vowsituationalperkrung.json"
        assert perk_path.exists()
        assert situation_path.exists()
        assert rung_path.exists()

        perk_records = json.loads(perk_path.read_text(encoding="utf-8"))
        assert len(perk_records) == 1
        perk_record = perk_records[0]
        assert "pk" not in perk_record
        assert perk_record["fields"]["covenant_role"] == ["round-trip-scout"]
        assert perk_record["fields"]["name"] == "Scout's Instinct"
        assert perk_record["fields"]["beneficiary"] == PerkBeneficiary.WHOLE_GROUP
        assert perk_record["fields"]["effect_kind"] == PerkEffectKind.CHECK_BONUS
        assert perk_record["fields"]["magnitude_tenths"] == 15
        # Natural-key identity for the nullable check_type FK, not a raw pk.
        assert isinstance(perk_record["fields"]["check_type"], list)
        assert all(not isinstance(v, int) for v in perk_record["fields"]["check_type"])

        situation_records = json.loads(situation_path.read_text(encoding="utf-8"))
        assert len(situation_records) == 1
        assert "pk" not in situation_records[0]
        assert situation_records[0]["fields"]["perk"] == ["round-trip-scout", "Scout's Instinct"]
        assert situation_records[0]["fields"]["situation"] == Situation.AT_RANGE

        rung_records = json.loads(rung_path.read_text(encoding="utf-8"))
        assert len(rung_records) == 1
        assert "pk" not in rung_records[0]
        assert rung_records[0]["fields"]["perk"] == ["round-trip-scout", "Scout's Instinct"]
        assert rung_records[0]["fields"]["rung_number"] == 1
        assert rung_records[0]["fields"]["extra_situation"] == Situation.ALLY_LOW_HEALTH
        assert rung_records[0]["fields"]["magnitude_tenths"] == 25

    def test_perk_situation_and_rung_round_trip(self) -> None:
        from world.covenants.perks.constants import Situation

        role, check_type, perk, situation, rung = self._build_rows()

        result = export_to_content_repo(self.root)
        assert result.errors == []
        self._assert_exported_fixtures()

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        perk.refresh_from_db()
        assert perk.covenant_role_id == role.pk
        assert perk.check_type_id == check_type.pk
        assert perk.magnitude_tenths == 15

        situation.refresh_from_db()
        assert situation.perk_id == perk.pk
        assert situation.situation == Situation.AT_RANGE

        rung.refresh_from_db()
        assert rung.perk_id == perk.pk
        assert rung.rung_number == 1
        assert rung.magnitude_tenths == 25

    def test_perk_with_null_check_type_round_trips(self) -> None:
        """A POWER_BONUS perk (no check_type) also round-trips cleanly."""
        from world.covenants.factories import CovenantRoleFactory, VowSituationalPerkFactory
        from world.covenants.perks.constants import PerkEffectKind

        role = CovenantRoleFactory(
            name="Round Trip Vanguard 2536",
            slug="round-trip-vanguard-2536",
            sword_weight=1,
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            name="Backline Bulwark",
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        assert perk.check_type is None

        result = export_to_content_repo(self.root)
        assert result.errors == []

        perk_path = self.root / "fixtures" / "covenants" / "vowsituationalperk.json"
        records = {
            r["fields"]["name"]: r for r in json.loads(perk_path.read_text(encoding="utf-8"))
        }
        record = records["Backline Bulwark"]
        assert record["fields"]["check_type"] is None

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0

        perk.refresh_from_db()
        assert perk.check_type is None


class TechniqueFunctionTagContentExportTests(TestCase):
    """Round-trip coverage for TechniqueFunctionTag (#2443).

    ``magic.techniquefunctiontag`` was added to ``CONTENT_MODELS`` with natural
    key ``["technique", "function"]`` — verify a technique carrying two function
    tags survives export -> import identity-stable.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_technique_function_tags_round_trip(self) -> None:
        from world.magic.constants import TechniqueFunction
        from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory

        technique = TechniqueFactory(name="Round Trip Cinder Lash")
        weaken_tag = TechniqueFunctionTagFactory(
            technique=technique, function=TechniqueFunction.WEAKEN
        )
        buff_tag = TechniqueFunctionTagFactory(
            technique=technique, function=TechniqueFunction.DAMAGE_BUFF_SELF
        )

        result = export_to_content_repo(self.root)
        assert result.errors == []

        tag_path = self.root / "fixtures" / "magic" / "techniquefunctiontag.json"
        assert tag_path.exists()

        records = json.loads(tag_path.read_text(encoding="utf-8"))
        assert len(records) == 2
        for record in records:
            assert "pk" not in record
            # Natural-key identity, not a raw pk: technique serializes as
            # [gift_name, technique_name], not an integer FK id.
            technique_key = record["fields"]["technique"]
            assert isinstance(technique_key, list)
            assert technique_key[-1] == "Round Trip Cinder Lash"
            assert all(not isinstance(v, int) for v in technique_key)
            assert not isinstance(record["fields"]["function"], int)

        functions = {r["fields"]["function"] for r in records}
        assert functions == {TechniqueFunction.WEAKEN, TechniqueFunction.DAMAGE_BUFF_SELF}

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        weaken_tag.refresh_from_db()
        assert weaken_tag.technique_id == technique.pk
        assert weaken_tag.function == TechniqueFunction.WEAKEN

        buff_tag.refresh_from_db()
        assert buff_tag.technique_id == technique.pk
        assert buff_tag.function == TechniqueFunction.DAMAGE_BUFF_SELF


class CovenantRoleTechniqueSpecialtyContentExportTests(TestCase):
    """Round-trip coverage for CovenantRoleTechniqueSpecialty (#2443).

    ``covenants.covenantroletechniquespecialty`` was added to ``CONTENT_MODELS`` with
    natural key ``["covenant_role", "function"]`` — verify a specialty row attached to
    a PRIMARY role AND one attached to a SUB-role both survive export -> import
    identity-stable (specialty rows are valid on both, unlike the blend weights).
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_technique_specialty_round_trip(self) -> None:
        from world.covenants.factories import (
            CovenantRoleFactory,
            CovenantRoleTechniqueSpecialtyFactory,
            SubroleCovenantRoleFactory,
        )
        from world.magic.constants import TechniqueFunction

        primary = CovenantRoleFactory(
            name="Round Trip Specialist",
            slug="round-trip-specialist",
            sword_weight=1,
            crown_weight=0,
        )
        primary.full_clean()
        primary_specialty = CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=primary,
            function=TechniqueFunction.WEAKEN,
            multiplier_tenths=15,
        )

        sub_role = SubroleCovenantRoleFactory(
            parent_role=primary,
            name="Round Trip Specialist (Ember)",
            slug="round-trip-specialist-ember",
            unlock_thread_level=2,
        )
        sub_role.full_clean()  # sanity: the all-zero-weight sub-role is valid
        sub_specialty = CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=sub_role,
            function=TechniqueFunction.PERCEPTION,
            multiplier_tenths=20,
        )
        sub_specialty.full_clean()  # sanity: specialty rows are valid on sub-roles too

        result = export_to_content_repo(self.root)
        assert result.errors == []

        specialty_path = (
            self.root / "fixtures" / "covenants" / "covenantroletechniquespecialty.json"
        )
        assert specialty_path.exists()

        records = json.loads(specialty_path.read_text(encoding="utf-8"))
        assert len(records) == 2
        for record in records:
            assert "pk" not in record
            # Natural-key identity, not a raw pk.
            role_key = record["fields"]["covenant_role"]
            assert isinstance(role_key, list)
            assert all(not isinstance(v, int) for v in role_key)
            assert not isinstance(record["fields"]["function"], int)

        by_function = {r["fields"]["function"]: r for r in records}
        primary_record = by_function[TechniqueFunction.WEAKEN]
        assert primary_record["fields"]["covenant_role"] == ["round-trip-specialist"]
        assert primary_record["fields"]["multiplier_tenths"] == 15

        sub_record = by_function[TechniqueFunction.PERCEPTION]
        assert sub_record["fields"]["covenant_role"] == ["round-trip-specialist-ember"]
        assert sub_record["fields"]["multiplier_tenths"] == 20

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        primary_specialty.refresh_from_db()
        assert primary_specialty.covenant_role_id == primary.pk
        assert primary_specialty.multiplier_tenths == 15

        sub_specialty.refresh_from_db()
        assert sub_specialty.covenant_role_id == sub_role.pk
        assert sub_specialty.multiplier_tenths == 20


class VowStatScalingContentExportTests(TestCase):
    """Round-trip coverage for VowStatScaling (#2533).

    ``covenants.vowstatscaling`` was added to ``CONTENT_MODELS`` with natural key
    ``["covenant_role", "modifier_target"]`` — verify a row survives export -> import
    identity-stable, including the FK-in-NK resolution of ``modifier_target`` (itself
    keyed on ``["category", "name"]`` via ``mechanics.ModifierTarget``).
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_vow_stat_scaling_round_trip(self) -> None:
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.models import VowStatScaling
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        role = CovenantRoleFactory(
            name="Round Trip Oathbound",
            slug="round-trip-oathbound",
            sword_weight=1,
            crown_weight=0,
        )
        role.full_clean()
        category = ModifierCategoryFactory(name="Round Trip Vow Stat Category")
        target = ModifierTargetFactory(name="Round Trip Vow Stat Target", category=category)
        scaling = VowStatScaling.objects.create(
            covenant_role=role,
            modifier_target=target,
            bonus_per_level=5,
        )

        result = export_to_content_repo(self.root)
        assert result.errors == []

        scaling_path = self.root / "fixtures" / "covenants" / "vowstatscaling.json"
        assert scaling_path.exists()

        records = json.loads(scaling_path.read_text(encoding="utf-8"))
        assert len(records) == 1
        record = records[0]
        assert "pk" not in record

        # FK-in-NK: modifier_target serializes as [category_name, target_name],
        # not a raw pk.
        target_key = record["fields"]["modifier_target"]
        assert isinstance(target_key, list)
        assert target_key == ["Round Trip Vow Stat Category", "Round Trip Vow Stat Target"]
        assert all(not isinstance(v, int) for v in target_key)

        assert record["fields"]["covenant_role"] == ["round-trip-oathbound"]
        assert record["fields"]["bonus_per_level"] == 5

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        scaling.refresh_from_db()
        assert scaling.covenant_role_id == role.pk
        assert scaling.modifier_target_id == target.pk
        assert scaling.bonus_per_level == 5


class CovenantRoleBonusContentExportTests(TestCase):
    """Round-trip coverage for CovenantRoleBonus (#2533).

    ``covenants.covenantrolebonus`` was added to ``CONTENT_MODELS`` with natural key
    ``["covenant_role", "modifier_target"]`` — mirrors ``VowStatScaling``'s FK-in-NK
    shape but scales by character level rather than thread level (#985, Spec D §5.6).
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_covenant_role_bonus_round_trip(self) -> None:
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.models import CovenantRoleBonus
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        role = CovenantRoleFactory(
            name="Round Trip Sworn Blade",
            slug="round-trip-sworn-blade",
            sword_weight=1,
            crown_weight=0,
        )
        role.full_clean()
        category = ModifierCategoryFactory(name="Round Trip Role Bonus Category")
        target = ModifierTargetFactory(name="Round Trip Role Bonus Target", category=category)
        bonus = CovenantRoleBonus.objects.create(
            covenant_role=role,
            modifier_target=target,
            bonus_per_level=3,
        )

        result = export_to_content_repo(self.root)
        assert result.errors == []

        bonus_path = self.root / "fixtures" / "covenants" / "covenantrolebonus.json"
        assert bonus_path.exists()

        records = json.loads(bonus_path.read_text(encoding="utf-8"))
        assert len(records) == 1
        record = records[0]
        assert "pk" not in record

        # FK-in-NK: modifier_target serializes as [category_name, target_name].
        target_key = record["fields"]["modifier_target"]
        assert isinstance(target_key, list)
        assert target_key == ["Round Trip Role Bonus Category", "Round Trip Role Bonus Target"]
        assert all(not isinstance(v, int) for v in target_key)

        assert record["fields"]["covenant_role"] == ["round-trip-sworn-blade"]
        assert record["fields"]["bonus_per_level"] == 3

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        bonus.refresh_from_db()
        assert bonus.covenant_role_id == role.pk
        assert bonus.modifier_target_id == target.pk
        assert bonus.bonus_per_level == 3


class GearArchetypeCompatibilityContentExportTests(TestCase):
    """Round-trip coverage for GearArchetypeCompatibility (#2533).

    ``covenants.geararchetypecompatibility`` was added to ``CONTENT_MODELS`` with
    natural key ``["covenant_role", "gear_archetype"]`` — an existence-only join
    (Spec D §4.4), so the only FK-in-NK to exercise is ``covenant_role``.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_gear_archetype_compatibility_round_trip(self) -> None:
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.models import GearArchetypeCompatibility
        from world.items.constants import GearArchetype

        role = CovenantRoleFactory(
            name="Round Trip Shieldbearer",
            slug="round-trip-shieldbearer",
            shield_weight=1,
            crown_weight=0,
        )
        role.full_clean()
        compat = GearArchetypeCompatibility.objects.create(
            covenant_role=role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )

        result = export_to_content_repo(self.root)
        assert result.errors == []

        compat_path = self.root / "fixtures" / "covenants" / "geararchetypecompatibility.json"
        assert compat_path.exists()

        records = json.loads(compat_path.read_text(encoding="utf-8"))
        assert len(records) == 1
        record = records[0]
        assert "pk" not in record

        # FK-in-NK: covenant_role serializes as a natural-key list, not a raw pk.
        role_key = record["fields"]["covenant_role"]
        assert isinstance(role_key, list)
        assert role_key == ["round-trip-shieldbearer"]

        assert record["fields"]["gear_archetype"] == GearArchetype.HEAVY_ARMOR

        from core_management.content_fixtures import build_all, load_entries

        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

        compat.refresh_from_db()
        assert compat.covenant_role_id == role.pk
        assert compat.gear_archetype == GearArchetype.HEAVY_ARMOR
