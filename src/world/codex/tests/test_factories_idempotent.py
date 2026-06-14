from django.test import TestCase

from world.classes.factories import PathFactory
from world.codex.factories import (
    CodexCategoryFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
    PathCodexGrantFactory,
)


class CodexFactoryIdempotencyTests(TestCase):
    def test_subject_factory_get_or_create(self):
        cat = CodexCategoryFactory(name="Magic")
        s1 = CodexSubjectFactory(category=cat, parent=None, name="The Mage's Journey")
        s2 = CodexSubjectFactory(category=cat, parent=None, name="The Mage's Journey")
        assert s1.pk == s2.pk

    def test_path_grant_factory_get_or_create(self):
        path = PathFactory()
        entry = CodexEntryFactory()
        g1 = PathCodexGrantFactory(path=path, entry=entry)
        g2 = PathCodexGrantFactory(path=path, entry=entry)
        assert g1.pk == g2.pk
