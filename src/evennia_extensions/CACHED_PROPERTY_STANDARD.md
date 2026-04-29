# Cached Property Usage Standard

## Rule

**Always use `from django.utils.functional import cached_property`** in `src/`. Never use `from functools import cached_property`.

A custom pre-commit linter (`tools/lint_cached_property_import.py`, token `CACHED_PROPERTY_IMPORT`) enforces this.

## Why

`functools.cached_property` and `django.utils.functional.cached_property` expose the same Python-level interface (lazy-computed attribute, `__set_name__`, set-on-instance-dict semantics). They are interface-equivalent.

But Django's `prefetch_related(Prefetch(..., to_attr="cached_X"))` machinery only recognizes its own class via `isinstance`. With `functools.cached_property`, Django's `is_to_attr_fetched()` decides "this isn't my cached_property, assume the attr is already populated" and **silently skips the batched prefetch**. Subsequent attribute access fires the cached_property's fallback query — once per row. Classic N+1, no warning, no exception, correct data, slow performance.

Because the project's documented prefetch pattern (CLAUDE.md: "to_attr should point to a cached_property on the model for cache-safe access") relies on Django recognizing the descriptor, we must use Django's version everywhere. Even on classes that aren't currently a `Prefetch(to_attr=...)` target — making the choice once project-wide eliminates the footgun.

## Suppression

If a non-Django context genuinely needs `functools.cached_property` (e.g., a defensive `isinstance` target, a script outside `src/`, or a pure utility class that will never be a Prefetch target and where stdlib alignment matters), suppress with:

```python
from functools import cached_property  # noqa: CACHED_PROPERTY_IMPORT — <reason>
```

The canonical example is `src/evennia_extensions/mixins.py`, which `isinstance`-checks against both classes to clear caches defensively. Suppressions in `src/` should be rare and accompanied by a clear reason. The default answer is "use Django's."

## History

The original standard (commit history) recommended `functools.cached_property` for stdlib alignment. That advice predated discovery of the silent Prefetch+to_attr breakage; commit `dd6a5ca1` documents the bug, and the project-wide sweep that followed inverted the recommendation.
