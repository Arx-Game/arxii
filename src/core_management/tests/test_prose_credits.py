"""Prose-field classification and credit coverage (#2980)."""

from datetime import date

from django.db import models
from django.test import SimpleTestCase, TestCase

from core.app_domains import resolve_model_by_name
from core_management.content_export import CONTENT_MODELS
from core_management.prose_fields import (
    NON_PROSE_TEXT_FIELDS,
    PROSE_FIELD_NAMES,
    prose_fields_for,
)
from world.codex.models import CodexEntry
from world.contributors.factories import ContentContributorFactory
from world.contributors.models import CreditedContent
from world.traits.models import Trait, TraitCategory, TraitType


def _content_models() -> list[tuple[str, type[models.Model]]]:
    resolved = []
    for label in sorted(CONTENT_MODELS):
        try:
            resolved.append((label, resolve_model_by_name(label)))
        except LookupError:
            continue
    return resolved


class ProseFieldClassificationTests(SimpleTestCase):
    def test_every_text_field_on_a_content_model_is_classified(self):
        # Deliberately NOT prose_fields_for: that function already filters to
        # PROSE_FIELD_NAMES, so it cannot surface a field that belongs in
        # neither set. This test needs every free-text field, classified or
        # not, which is exactly what it is checking for completeness.
        unclassified = {
            f"{label}.{field.name}"
            for label, model in _content_models()
            for field in model._meta.get_fields()
            if isinstance(field, (models.TextField, models.CharField))
            and not field.choices
            and field.name not in PROSE_FIELD_NAMES
            and field.name not in NON_PROSE_TEXT_FIELDS
        }
        self.assertEqual(
            unclassified,
            set(),
            "Add each of these to PROSE_FIELD_NAMES or NON_PROSE_TEXT_FIELDS in "
            "core_management/prose_fields.py. Prose means a person writes it for "
            "players (or a GM) to read; anything else is not prose.",
        )

    def test_no_field_is_in_both_sets(self):
        self.assertEqual(PROSE_FIELD_NAMES & NON_PROSE_TEXT_FIELDS, frozenset())


class ProseCreditCoverageTests(SimpleTestCase):
    def test_every_prose_content_model_is_credited(self):
        missing = [
            label
            for label, model in _content_models()
            if prose_fields_for(model) and not issubclass(model, CreditedContent)
        ]
        self.assertEqual(
            missing,
            [],
            "These content models carry prose but cannot record who wrote it. "
            "Add CreditedContent to each (world.contributors.models).",
        )

    def test_the_guard_is_not_passing_vacuously(self):
        credited = [label for label, model in _content_models() if prose_fields_for(model)]
        self.assertGreater(len(credited), 75)


class ProseFieldDeclarationOrderTests(SimpleTestCase):
    """`prose_fields_for` returns field-declaration order, not alphabetical (#3019).

    CodexEntry is the multi-prose-field case the Task 1 review flagged as
    untested: `summary`, `lore_content`, `mechanics_content` are declared in
    that order on the model (`world/codex/models.py`) but sort
    alphabetically as `lore_content`, `mechanics_content`, `summary` - a
    regression that silently reordered fields would pass every other guard
    in this module while still breaking the authoring workbench's editor,
    which renders one textarea per name in exactly this order (see
    `web.admin.tests.test_authoring_editor
    .TestAuthoringEditorGet.test_textareas_render_in_declaration_order`).
    """

    def test_codex_entry_prose_fields_are_in_declaration_order(self):
        self.assertEqual(
            prose_fields_for(CodexEntry),
            ["summary", "lore_content", "mechanics_content"],
        )


class CreditedRowTests(TestCase):
    """The columns actually reach a real content row and persist (#2980)."""

    def test_a_content_row_stores_writer_and_reviewer(self):
        writer = ContentContributorFactory(name="Writer")
        reviewer = ContentContributorFactory(name="Reviewer")
        trait = Trait.objects.create(
            name="Credited Trait",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
            description="Prose.",
            written_by=writer,
            written_on=date(2026, 8, 4),
            reviewed_by=reviewer,
            reviewed_on=date(2026, 8, 5),
        )
        trait.refresh_from_db()
        self.assertEqual(trait.written_by, writer)
        self.assertEqual(trait.reviewed_on, date(2026, 8, 5))

    def test_no_reverse_accessor_is_created_on_the_contributor(self):
        # This is the assertion Task 1 could not make: with CreditedContent
        # abstract and attached to nothing, there was no candidate reverse
        # accessor to collide, so the check passed whether or not
        # related_name="+" was set. Trait inherits it now, so `trait_set`
        # would exist here if the related_name were ever dropped.
        contributor = ContentContributorFactory(name="Reverse Check")
        for accessor in ("trait_set", "trait_written_set", "trait_reviewed_set"):
            with self.subTest(accessor=accessor):
                self.assertFalse(hasattr(contributor, accessor))

    def test_a_row_with_no_writer_is_still_a_placeholder(self):
        trait = Trait.objects.create(
            name="Uncredited Trait",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
            description="PLACEHOLDER.",
        )
        self.assertIsNone(trait.written_by)
        self.assertIsNone(trait.written_on)
