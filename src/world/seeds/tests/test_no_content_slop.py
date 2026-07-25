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

The ratified rule (TehomCD, 2026-07-25): **if it has a name, it is content.**
Config is the mechanical spine and nothing else.

This test is the standing guard. It seeds against a stub content root and fails
naming any model outside :data:`SEEDER_CONFIG_MODELS` that gained rows — so a
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
from world.seeds.database import seed_dev_database
from world.seeds.tests.content_stub import stub_content_root

#: **A ratchet, not an allowlist. This set may only ever shrink.**
#:
#: Snapshot of every ``CONTENT_MODELS`` entry the seeders populated as of #2698 —
#: 78 models, far more than "a few sample rows". The seeders currently build a
#: parallel content set: 33 techniques, 48 condition templates, 19 rituals, 12
#: mission templates, 9 gifts, 3 codex entries. Untangling that is a large piece
#: of work and is deliberately NOT a launch blocker.
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
        "achievements.statdefinition",
        "character_creation.beginnings",
        "character_creation.beginningtradition",
        "character_creation.cgexplanation",
        "character_creation.startingarea",
        "character_sheets.gender",
        "checks.checkcategory",
        "checks.checktype",
        "checks.checktypetrait",
        "classes.aspect",
        "classes.path",
        "classes.pathaspect",
        "codex.codexcategory",
        "codex.codexentry",
        "codex.codexsubject",
        "conditions.capabilitytype",
        "conditions.conditioncapabilityeffect",
        "conditions.conditioncategory",
        "conditions.conditioncheckmodifier",
        "conditions.conditiondamageinteraction",
        "conditions.conditiondamageovertime",
        "conditions.conditionmodifiereffect",
        "conditions.conditionstage",
        "conditions.conditiontemplate",
        "conditions.damagetype",
        "covenants.covenantrite",
        "covenants.covenantriterolepackage",
        "covenants.covenantrole",
        "covenants.mentorbondconfig",
        "distinctions.distinction",
        "distinctions.distinctioncategory",
        "distinctions.distinctioneffect",
        "flows.flowdefinition",
        "flows.flowstepdefinition",
        "flows.triggerdefinition",
        "forms.build",
        "forms.formtrait",
        "forms.formtraitoption",
        "forms.heightband",
        "forms.speciesformtrait",
        "magic.affinity",
        "magic.compromiseacttype",
        "magic.dramaticmomenttype",
        "magic.effecttype",
        "magic.fallredemptionconfig",
        "magic.gift",
        "magic.intensitytier",
        "magic.pathgiftgrant",
        "magic.portalanchorkind",
        "magic.resonance",
        "magic.resonanceconversion",
        "magic.ritual",
        "magic.technique",
        "magic.techniqueappliedcondition",
        "magic.techniquestyle",
        "magic.threadweavingunlock",
        "magic.tradition",
        "magic.traditiongiftgrant",
        "mechanics.application",
        "mechanics.challengeapproach",
        "mechanics.challengecategory",
        "mechanics.challengetemplate",
        "mechanics.modifiercategory",
        "mechanics.modifiertarget",
        "mechanics.property",
        "mechanics.propertycategory",
        "missions.missioncategory",
        "missions.missionnode",
        "missions.missionoption",
        "missions.missionoptionroute",
        "missions.missionoptionroutereward",
        "missions.missiontemplate",
        "realms.realm",
        "relationships.relationshiptrack",
        "skills.skill",
        "species.species",
        "tarot.tarotcard",
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

        before = {label: model.objects.count() for label, model in content_models.items()}
        seed_dev_database()
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
