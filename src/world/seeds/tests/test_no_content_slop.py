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

The settled rule (TehomCD, 2026-07-25; ADR-0164) — **the registration is the
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

from django.apps import apps
from django.test import TestCase

from core_management.content_export import CONTENT_MODELS
from world.seeds.clusters import CLUSTER_SEEDERS
from world.seeds.database import load_content_first
from world.seeds.tests.content_stub import stub_content_root

#: **A ratchet, not an allowlist. This set may only ever shrink.**
#:
#: Every ``CONTENT_MODELS`` entry the cluster seeders still populate. The
#: seeders build a parallel content set — condition templates, rituals,
#: mission templates, distinctions — that the content repo already authors,
#: usually with far more rows (48 condition templates against 183). The
#: entire ``magic.*`` slice (15 models: affinity, gift, technique, ritual,
#: resonance, etc.) was cleared in #2698 via ``authored_or_sample()`` — every
#: magic seeder call site now looks content up and invents only under
#: ``SEED_SAMPLE_CONTENT``. The entire ``conditions.*`` slice (10 models:
#: capabilitytype, conditioncategory, conditiontemplate, conditionstage,
#: damagetype, etc.) was cleared the same way in a follow-up #2698 pass.
#:
#: Measured against the *stub* content root, which carries almost no content.
#: Against a real content repo these seeders are near-total no-ops: their
#: ``get_or_create`` calls find the authored row and add nothing. The
#: ``mechanics.*``/``flows.*`` slice (11 models: application, challengeapproach,
#: challengecategory, challengetemplate, modifiercategory, modifiertarget,
#: property, propertycategory, flowdefinition, flowstepdefinition,
#: triggerdefinition) was cleared the same way in a follow-up #2698 pass —
#: including the "menace" ``mechanics.modifiertarget`` row that was one of the
#: genuine stub-relative inventions. A further #2698 pass cleared 11 more
#: (``achievements.statdefinition``; ``covenants.covenantrite``/
#: ``covenantriterolepackage``/``covenantrole`` — ``covenants.mentorbondconfig``
#: stays, a pk=1 tuning singleton under separate review; the entire
#: ``missions.*`` demo/tutorial-chain quintet — missiontemplate/missionnode/
#: missionoption/missionoptionroute/missionoptionroutereward, including the "A
#: Simple Job" demo mission called out below; ``realms.realm``;
#: ``relationships.relationshiptrack``, which also dropped an ``update_or_create``
#: that silently re-applied PLACEHOLDER names over a staff edit on every reseed).
#: What remains is genuine invention (62 ``checks.checktypetrait``, 5
#: ``character_creation.cgexplanation``, ``forms.formtraitoption`` "court_coils",
#: and two singleton configs). The stub-relative number is the stricter,
#: hermetic one, and it is what this ratchet drives to zero.
#:
#: So this freezes today's state and guards the margin: a seeder that starts
#: populating a *new* content model fails immediately, while the existing overlap
#: is paid down over time. Same shape as the grandfathered-noqa ratchet in
#: ``.pre-commit-config.yaml``.
#:
#: **Never add an entry to make a failing test pass.** A new entry means a seeder
#: began inventing content that belongs in the content repo — fix the seeder. The
#: only legitimate edits are deletions, as each model stops being seeded.
SEEDER_GRANDFATHERED_MODELS: frozenset[str] = frozenset(
    {
        "character_creation.cgexplanation",
        "character_sheets.gender",
        "checks.checkcategory",
        "checks.checktype",
        "checks.checktypetrait",
        "classes.aspect",
        "classes.pathaspect",
        "distinctions.distinction",
        "distinctions.distinctioncategory",
        "distinctions.distinctioneffect",
        "forms.build",
        "forms.formtrait",
        "forms.formtraitoption",
        "forms.heightband",
        "forms.speciesformtrait",
        "skills.skill",
        "species.species",
        "traits.trait",
    }
)


class SeedersDoNotCreateContentTests(TestCase):
    """The Big Button yields config, never authored content.

    The ratchet in :data:`SEEDER_GRANDFATHERED_MODELS` may only shrink. When a
    seeder stops populating a model, delete its entry so the guard tightens.
    """

    @stub_content_root()
    def test_seeding_creates_no_content_model_rows(self) -> None:
        content_models = {}
        for label in sorted(CONTENT_MODELS):
            try:
                content_models[label] = apps.get_model(*label.split("."))
            except LookupError:
                continue

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
