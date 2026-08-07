"""Seeders must not create authored content (#2698).

Pressing the Big Button is mandatory — ``seed_dev_database()`` is the only
source of the game's mechanical spine (``CheckRank``, ``ResultChart``,
``CheckOutcome``, ``ConsequencePool``, ``ActionTemplate``,
``PointConversionRange``, ``Pronouns``, ``Heritage``). None of those live in the
content repo, so a fresh database cannot resolve a single check without a press.

But the same seeders also create *named* rows a player reads as world content —
``Organization`` ("House Veyrane PLACEHOLDER"), ``NPCRole``
("Great Archive Librarian"), ``ItemTemplate``, ``Area``, ``Family``,
``MarketStall``. Those get captured by ``export_to_content_repo`` and land in the
content repo indistinguishable from authored work. That is how "Commoner",
"Noble", "Arx City" and "Luxen Port" got there.

The settled rule (TehomCD, 2026-07-25; ADR-0168) — **the registration is the
line, not the shape of the table**:

    If a model is in ``CONTENT_MODELS``, the content repo owns it and no
    seeder may create rows in it. If it is not, the seeder owns it.

An earlier draft of this guard used "if it has a name, it is content", which
argued itself into a corner — ``CheckType`` has the name "Melee Attack" and is
plainly mechanical. The audit that replaced it found all 70 content models the
seeders still populated were *already authored* in the content repo, usually
with far more rows, and that the genuine config the Big Button must provide is
never in ``CONTENT_MODELS`` at all. Hence: one registration, two consumers
(export and this guard), no per-model judgement calls, and a target of zero.

This test is the standing guard. It seeds against a stub content root and fails
naming any ``CONTENT_MODELS`` entry outside the ratchet that gained rows — so a
seeder that invents content fails CI instead of quietly polluting the corpus on
the next export.

Note the vector is the *seeder*, never the test suite: the fast tier runs on
SQLite ``:memory:`` with its own runner, so test rows can never reach the dev
database.
"""

from __future__ import annotations

from django.db.models import DateField
from django.test import TestCase

from core.app_domains import resolve_model_by_name
from core_management.content_export import CONTENT_MODELS
from world.seeds.clusters import CLUSTER_SEEDERS
from world.seeds.database import load_content_first
from world.seeds.tests.content_stub import stub_content_root

#: **This is now a plain invariant, not a ratchet being paid down.**
#:
#: Seeders never write content, full stop. Every ``CONTENT_MODELS`` entry the
#: cluster seeders used to populate directly — condition templates, rituals,
#: mission templates, distinctions, and finally the character-creation family
#: (species, gender, forms, distinctions) — has been converted via
#: ``world.seeds.sample_content.authored_or_sample()``: every call site now
#: looks content up first and invents a row only under
#: ``SEED_SAMPLE_CONTENT`` (off by default). Measured against the *stub*
#: content root, which carries almost no content, so the two tests below both
#: hold with this set empty.
#:
#: History (#2698): the ratchet started at 70 entries (the ADR-0168 audit) and
#: was paid down in passes — magic.* (15 models), conditions.* (10),
#: mechanics.*/flows.* (11), achievements/covenants/missions/realms/
#: relationships (11), checks.*/skills.skill/classes.*/traits.trait (7, which
#: also fixed a real bug: 15 call sites across 8 files were wiping and
#: recreating a CheckType's composition on every press, silently reverting
#: staff/lore edits — all 15 now converge via ``get_or_create``/
#: ``authored_or_sample`` instead of delete-then-create) — down to the final
#: 11: ``character_creation.cgexplanation``, ``character_sheets.gender``,
#: ``distinctions.distinction``/``distinctioncategory``/``distinctioneffect``,
#: ``forms.build``/``formtrait``/``formtraitoption``/``heightband``/
#: ``speciesformtrait``, and ``species.species``. Two of those were genuine
#: inventions with no authored counterpart (5 ``CGExplanation`` "_lore_intro"
#: rows; the ``forms.formtraitoption`` "court_coils" row) — both now gated
#: behind ``SEED_SAMPLE_CONTENT`` rather than authored, exactly like every
#: other missing-content case. ``world.magic.seeds_cast``'s
#: ``ensure_technique_cast_content()`` stays the one deliberate exception to
#: the rule entirely: it is a config prerequisite
#: ``world.seeds.database.load_content_first()`` runs BEFORE the content load
#: (so lore-repo ``Technique`` fixtures can resolve the "Technique Cast"
#: ``ActionTemplate`` by natural key on a database with nothing authored yet)
#: and sits outside this test's measurement window entirely — gating it would
#: permanently break content loading.
#:
#: **Never add an entry here.** An addition would mean a seeder started
#: writing content again — that is a regression, not a thing to grandfather.
#: Fix the seeder (``authored_or_sample()``) instead.
SEEDER_GRANDFATHERED_MODELS: frozenset[str] = frozenset()

#: **What this guard cannot see (#2973):** its growth check only fires for models
#: registered in ``CONTENT_MODELS``. Several rows the eight magic-seeder content
#: stand-ins touched were never registered at all — either the whole model is a
#: seeder/content mix (``items.itemtemplate``: most rows are legitimately
#: seeder-owned config, so the model can't register wholesale) or the content has
#: no lore-repo destination to register against (the "Hallowed Threshold"
#: ``stories.*`` rows, test-fixture scaffolding that never ships). Constituent
#: models this guard is blind to, by construction, not oversight: the demo
#: ``ObjectDB`` rooms + ``LocationValueModifier`` tags (stand-in 1),
#: ``stories.story``/``chapter``/``episode``/``beat``/``transition`` (stand-in 2),
#: ``ActionEnhancement`` + ``TechniqueVariant`` (stand-in 3 — the "Social Arts"
#: ``Gift``/``Technique`` rows themselves ARE registered, and ARE covered below),
#: ``MagicalAlterationTemplate`` (stand-in 4's 12 corruption twists — the 2
#: ``ConditionTemplate`` rows themselves ARE registered and covered), and
#: ``items.itemtemplate`` (stand-in 6, the touchstone/reagents). Their regression
#: coverage is entirely the name-keyed strip-absence tests in
#: ``integration_tests.game_content.tests.test_magic_seed`` — see
#: ``SeedMagicDevStripsStandInsTests``/``SeedStarterMagicStoryStripsStandInsTests``
#: for the full list.
#:
#: Stand-ins 5 (reaction conditions + achievement bridge), 7 (fall-redemption
#: examples), and 8 (the "Devotion" ``RelationshipTrack``) touch only registered
#: models, so the two tests below already assert the general invariant for them
#: directly: a fresh ``seed_magic_dev()``/``seed_starter_magic_story()`` call (one
#: of ``CLUSTER_SEEDERS``) authors zero rows in any registered content model. Of
#: those three, 7 and 8 were **already** ``authored_or_sample()``-gated before
#: #2973 (#2698/#2972) — this guard already covered them pre-branch too. #2973
#: didn't gate anything new there; it verified the gate against code and added the
#: name-keyed strip-absence tests
#: (``test_no_fall_redemption_example_rows_authored``,
#: ``test_no_devotion_track_authored``) as belt-and-suspenders regression coverage
#: alongside this pre-existing general guard.


class SeedersDoNotCreateContentTests(TestCase):
    """The Big Button yields config, never authored content.

    :data:`SEEDER_GRANDFATHERED_MODELS` is empty and stays empty — seeders
    never write content, full stop (#2698). It is not a ratchet being paid
    down anymore; do not add an entry to it to silence a failure here. A
    seeder that starts populating a ``CONTENT_MODELS`` row is a regression —
    fix the seeder with ``authored_or_sample()`` instead.
    """

    def _content_models(self) -> dict[str, type]:
        models = {}
        for label in sorted(CONTENT_MODELS):
            # label is "<domain>.<model_name>", not a real Django app_label
            # post-collapse (#2906) — resolve by model name.
            try:
                models[label] = resolve_model_by_name(label)
            except LookupError:
                continue
        return models

    @stub_content_root()
    def test_seeding_creates_no_content_model_rows(self) -> None:
        content_models = self._content_models()

        # Snapshot BETWEEN the content load and the cluster loop. Measuring
        # across a whole seed_dev_database() call would score the stub content
        # root's own rows as seeder growth — the loader is the content repo, so
        # its writes are the one thing this guard must not count.
        load_content_first()
        before = {label: model.objects.count() for label, model in content_models.items()}
        for seeder in CLUSTER_SEEDERS.values():
            seeder()
        after = {label: model.objects.count() for label, model in content_models.items()}

        grew = {
            label: (before[label], after[label])
            for label in content_models
            if after[label] > before[label] and label not in SEEDER_GRANDFATHERED_MODELS
        }

        assert not grew, (
            "Seeding created rows in content models. Authored content belongs in "
            "the content repo, not a seeder — see #2698.\n"
            + "\n".join(f"  {label}: {lo} -> {hi}" for label, (lo, hi) in sorted(grew.items()))
            + "\n\nDo NOT add these to SEEDER_GRANDFATHERED_MODELS to silence this — "
            "that set is a ratchet and may only shrink. Fix the seeder instead: "
            "authored content belongs in the content repo."
        )

    @stub_content_root()
    def test_seeding_does_not_delete_or_overwrite_authored_rows(self) -> None:
        """Counting rows is not enough: a wipe-and-rebuild nets to zero.

        The row-count guard above is blind to a seeder that deletes an authored
        row and writes its own copy back — the count is identical either side.
        That is not hypothetical. Eight check seeders ran
        ``CheckTypeTrait.objects.filter(check_type=...).delete()`` and recreated
        the rows from hardcoded values, and because seeders run *after* the
        content load, every Big Button press silently reverted 62 authored trait
        weights. ``combat_checks.py``'s own docstring advertised it as a feature
        ("the composition is rewritten on each run"), which it was — until the
        content repo started supplying those rows first. The count guard never
        saw it (#2698).

        So this asserts the stronger property: after the cluster seeders run,
        every row the content load produced is still there, unchanged.
        """
        content_models = self._content_models()

        load_content_first()
        before = {
            label: self._snapshot(model)
            for label, model in content_models.items()
            if label not in SEEDER_GRANDFATHERED_MODELS
        }
        for seeder in CLUSTER_SEEDERS.values():
            seeder()

        deleted: list[str] = []
        changed: list[str] = []
        for label, rows in before.items():
            after_rows = self._snapshot(content_models[label])
            for pk, values in rows.items():
                if pk not in after_rows:
                    deleted.append(f"  {label} pk={pk}")
                elif after_rows[pk] != values:
                    diff = {
                        field: (old, after_rows[pk][field])
                        for field, old in values.items()
                        if after_rows[pk][field] != old
                    }
                    changed.append(f"  {label} pk={pk}: {diff}")

        damage = deleted + changed
        assert not damage, (
            "Seeding destroyed or rewrote authored content rows. Seeders run "
            "AFTER the content load, so a delete-and-recreate silently reverts "
            "whatever the content repo authored — see #2698.\n"
            + ("\nDELETED:\n" + "\n".join(sorted(deleted)) if deleted else "")
            + ("\nOVERWRITTEN:\n" + "\n".join(sorted(changed)) if changed else "")
            + "\n\nUse get_or_create keyed on the identifying fields (never "
            "filter().delete() then create(), never update_or_create) so a "
            "re-seed converges instead of clobbering."
        )

    @staticmethod
    def _snapshot(model: type) -> dict[object, dict[str, object]]:
        """pk -> {field: value} for every row, skipping auto-timestamp columns.

        ``auto_now`` fields move on every save by design, so including them
        would report a spurious change for any row a seeder merely re-saved
        without altering.
        """
        # Only DateField (and its DateTimeField subclass) carry auto_now /
        # auto_now_add, so the isinstance narrowing is what makes the attribute
        # access safe across every other field type.
        fields = [
            f
            for f in model._meta.concrete_fields
            if not (isinstance(f, DateField) and (f.auto_now or f.auto_now_add))
        ]
        names = [f.attname for f in fields]
        return {
            row[0]: dict(zip(names[1:], row[1:], strict=True))
            for row in model.objects.values_list("pk", *names[1:])
        }
