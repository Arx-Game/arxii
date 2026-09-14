"""The prefetch-to_attr linter sanctions ``to_attr`` only onto a same-file
``PrunedCachedProperty``-backed attribute (#3816); every other target still fails."""

from lint_prefetch_to_attr import check_source


def test_to_attr_onto_pruned_cached_property_passes():
    source = """
from evennia_extensions.cached_property import PrunedCachedProperty

class Foo(models.Model):
    @PrunedCachedProperty
    def cached_bar(self):
        return list(Bar.objects.filter(foo=self))

def get_queryset():
    return Foo.objects.prefetch_related(
        Prefetch("bar_set", to_attr="cached_bar")
    )
"""
    assert check_source(source) == []


def test_to_attr_onto_plain_property_still_fails():
    source = """
class Foo(models.Model):
    @property
    def cached_bar(self):
        return list(Bar.objects.filter(foo=self))

def get_queryset():
    return Foo.objects.prefetch_related(Prefetch("bar_set", to_attr="cached_bar"))
"""
    assert len(check_source(source)) == 1


def test_to_attr_onto_plain_cached_property_still_fails():
    source = """
from django.utils.functional import cached_property

class Foo(models.Model):
    @cached_property
    def cached_bar(self):
        return list(Bar.objects.filter(foo=self))

def get_queryset():
    return Foo.objects.prefetch_related(Prefetch("bar_set", to_attr="cached_bar"))
"""
    assert len(check_source(source)) == 1


def test_to_attr_onto_bare_attribute_still_fails():
    source = (
        "def get_queryset():\n"
        "    return Foo.objects.prefetch_related(\n"
        '        Prefetch("bar_set", to_attr="cached_bar")\n'
        "    )\n"
    )
    assert len(check_source(source)) == 1


def test_to_attr_name_mismatch_still_fails():
    """A ``PrunedCachedProperty`` exists in the file, but under a different name."""
    source = """
from evennia_extensions.cached_property import PrunedCachedProperty

class Foo(models.Model):
    @PrunedCachedProperty
    def cached_other(self):
        return list(Bar.objects.filter(foo=self))

def get_queryset():
    return Foo.objects.prefetch_related(Prefetch("bar_set", to_attr="cached_bar"))
"""
    assert len(check_source(source)) == 1


def test_pruned_cached_property_without_the_import_still_fails():
    """A locally-defined/aliased ``PrunedCachedProperty`` name is not enough - the
    heuristic requires the genuine import from ``evennia_extensions.cached_property``."""
    source = """
class PrunedCachedProperty:
    pass

class Foo(models.Model):
    @PrunedCachedProperty
    def cached_bar(self):
        return list(Bar.objects.filter(foo=self))

def get_queryset():
    return Foo.objects.prefetch_related(Prefetch("bar_set", to_attr="cached_bar"))
"""
    assert len(check_source(source)) == 1


def test_suppressed_line_passes():
    source = (
        "def get_queryset():\n"
        "    return Foo.objects.prefetch_related(\n"
        '        Prefetch("bar_set", to_attr="cached_bar")  # noqa: PREFETCH_TO_ATTR - reason\n'
        "    )\n"
    )
    assert check_source(source) == []


def test_prefetch_without_to_attr_passes():
    assert check_source('Foo.objects.prefetch_related(Prefetch("bar_set"))\n') == []
