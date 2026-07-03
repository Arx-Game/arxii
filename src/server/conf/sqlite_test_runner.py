"""
SQLite inner-loop test runner.

Used by :mod:`server.conf.sqlite_test_settings` (via ``TEST_RUNNER``) so
production code stays free of test-database awareness. Specifically: the
``refresh_*_view()`` helpers (``world.societies.models.refresh_legend_views``,
``world.codex.models.refresh_codex_breadcrumbs``,
``world.areas.models.refresh_area_closure``) execute raw
``REFRESH MATERIALIZED VIEW`` which is PG-only syntax. On the SQLite tier
the views don't exist (their migrations don't run; see ``sqlite_test_settings``
for the ``DisableMigrations`` sentinel). Production code calls these helpers
unconditionally; this runner patches them to no-op before tests start so
SQLite doesn't choke on the unsupported SQL.

**Patching strategy:** ``__code__`` replacement, not module-attribute
re-binding. Several consumer modules (``world.societies.services``,
multiple test modules) imported the functions by name — they hold their
own references that a module-attribute monkey-patch wouldn't reach. By
replacing ``__code__`` directly on the function object, *all* references
(wherever imported from) now execute the no-op body.

Pre-conditions for ``__code__`` replacement: source and target functions
must have compatible signatures (same positional/keyword arg counts, no
closure variables). All three refresh helpers take zero arguments and
have no closures; ``_noop`` matches.

The PG parity tier (``arx test`` without ``--sqlite``, plus CI shards) uses
the default ``DiscoverRunner`` and runs the real refresh implementations
against actual materialized views.

**Schema-template cache:** building the in-memory test schema from model
state (``migrate --run-syncdb`` over 90+ apps / ~700 models) costs ~15-20s
of every invocation despite creating an identical schema each time. This
runner therefore caches the fully-built test DB (schema + the
``post_migrate``-seeded rows: content types, permissions, sites) as a
SQLite file under ``src/.test_schema_cache/``, keyed by a fingerprint of
current model state. On a fingerprint match the file is restored into the
in-memory test DB via the SQLite backup API instead of running ``migrate``
— sub-second instead of ~20s. Any model/field/Meta change (or a
Django/Evennia upgrade) changes the fingerprint and rebuilds the template.
Set ``ARX_SCHEMA_CACHE=0`` to bypass the cache entirely.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import types
from typing import Any
from urllib.parse import quote

from django.db import DEFAULT_DB_ALIAS

from server.conf.test_runner import TimedEvenniaTestRunner

# src/.test_schema_cache/ — gitignored; one file per model-state fingerprint.
SCHEMA_CACHE_DIR = Path(__file__).resolve().parents[2] / ".test_schema_cache"

# How many fingerprint files to keep before pruning the oldest (branch
# switching produces a handful of live fingerprints; more than this is
# churn). A fingerprint mismatch is always safe — it just rebuilds and
# re-caches (~15s) — so occasional spurious misses cost time, not
# correctness; keeping a few extra templates absorbs them.
_SCHEMA_CACHE_KEEP = 5

# CPython object reprs embed memory addresses ("<function now at 0x7f...>");
# strip them so field kwargs containing callables hash stably across runs.
_MEMORY_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")


def _stable_repr(value: Any) -> str:
    """Deterministic repr for fingerprinting model state.

    Two per-process repr instabilities need canonicalizing: memory
    addresses inside object reprs, and iteration order of sets (Django
    stores e.g. ``unique_together`` as a set, and set order follows hash
    randomization). Containers are walked recursively; sets are emitted in
    sorted-element order.
    """
    if isinstance(value, set | frozenset):
        return "{" + ",".join(sorted(_stable_repr(item) for item in value)) + "}"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: repr(kv[0]))
        return "{" + ",".join(f"{_stable_repr(k)}:{_stable_repr(v)}" for k, v in items) + "}"
    if isinstance(value, list | tuple):
        return "[" + ",".join(_stable_repr(item) for item in value) + "]"
    if isinstance(value, types.FunctionType):
        # Function repr omits the module, so same-named functions (and all
        # lambdas) from different modules would collapse to one string once
        # the address is stripped; hash by module-qualified name instead.
        return f"<function {value.__module__}.{value.__qualname__}>"
    return _MEMORY_ADDRESS_RE.sub("0x", repr(value))


def _schema_fingerprint() -> str:
    """Hash the schema-relevant model state of every installed app.

    Covers each concrete model's fields (via ``Field.deconstruct()``),
    ``Meta`` options (indexes, constraints, unique_together, ordering, ...)
    and bases, plus the Django and Evennia versions and the installed-app
    labels. Auto-created M2M through-tables are excluded — their schema is
    fully determined by the owning ``ManyToManyField``, which is hashed. A
    false mismatch merely rebuilds the template; a false match would need
    two genuinely different schemas to hash equal. The known residual
    collapses in ``_stable_repr`` (``functools.partial``/bound-method/
    same-scope-lambda kwargs) can't get there: callable field kwargs are
    Python-side and never influence the emitted DDL.
    """
    import django  # noqa: PLC0415
    from django.apps import apps  # noqa: PLC0415
    from django.db.migrations.state import ModelState  # noqa: PLC0415
    import evennia  # noqa: PLC0415

    hasher = hashlib.sha256()
    hasher.update(django.get_version().encode())
    hasher.update(evennia.__version__.encode())
    # Include the installed-app list itself: a model-less app being added or
    # removed can still change what migrate would have produced (post_migrate
    # receivers seeding rows) without altering any model's state.
    hasher.update(repr(sorted(app.label for app in apps.get_app_configs())).encode())
    # Proxy models (every Evennia typeclass) have no schema of their own and
    # get registered lazily on first import — including them would make the
    # fingerprint depend on which test modules discovery happened to import.
    states = sorted(
        (
            ModelState.from_model(model)
            for model in apps.get_models()
            if not model._meta.proxy  # noqa: SLF001
        ),
        key=lambda state: (state.app_label, state.name),
    )
    for state in states:
        for field_name, field in sorted(state.fields.items()):
            _, path, args, kwargs = field.deconstruct()
            raw = (
                f"{state.app_label}.{state.name}.{field_name}"
                f"|{path}|{_stable_repr(args)}|{_stable_repr(kwargs)}"
            )
            hasher.update(raw.encode())
        hasher.update(_stable_repr(state.options).encode())
        hasher.update(_stable_repr(state.bases).encode())
    return hasher.hexdigest()[:16]


def _restore_sqlite_from_template(alias: str, template: Path) -> None:
    """Copy the cached template DB into the (fresh, empty) in-memory test DB.

    The source opens in read-only URI mode: a template deleted between the
    existence check and this call (concurrent prune or corrupt-fallback in
    another process) must raise — a plain ``sqlite3.connect(path)`` would
    silently create an empty DB at the path, and a backup from an empty
    source "succeeds" while leaving the target with zero tables. For the
    empty-but-present case, the restored DB is verified to contain tables.
    Both failures raise ``sqlite3.Error`` subclasses, which the caller's
    fallback turns into a real ``migrate``.
    """
    from django.db import connections  # noqa: PLC0415

    connection = connections[alias]
    connection.ensure_connection()
    # Percent-encode the path: SQLite parses the URI form, so a raw '#' in a
    # worktree path would truncate it (dropping mode=ro) and '%HH' sequences
    # would be decoded, both silently defeating the read-only guard.
    source = sqlite3.connect(f"file:{quote(str(template))}?mode=ro", uri=True)
    try:
        source.backup(connection.connection)
    finally:
        source.close()
    tables = connection.connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    if tables == 0:
        message = f"schema template {template.name} restored zero tables"
        raise sqlite3.DatabaseError(message)


def _dump_sqlite_to_template(alias: str, template: Path) -> None:
    """Save the just-built in-memory test DB as the cached template (atomic)."""
    from django.db import connections  # noqa: PLC0415

    connection = connections[alias]
    connection.ensure_connection()
    template.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=template.parent, suffix=".sqlite3.tmp")
    os.close(fd)
    try:
        target = sqlite3.connect(tmp_name)
        try:
            connection.connection.backup(target)
        finally:
            target.close()
        Path(tmp_name).replace(template)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _prune_schema_cache() -> None:
    """Drop all but the newest ``_SCHEMA_CACHE_KEEP`` cached templates.

    Also sweeps ``*.sqlite3.tmp`` files older than an hour — a hard-killed
    dump (the ``except BaseException`` cleanup never ran) orphans its tmp
    file, and nothing else would ever remove it.
    """

    def snapshot(pattern: str) -> list[tuple[Path, float]]:
        # A concurrent run's prune can unlink an entry between glob and
        # stat; skip those instead of crashing a run whose schema already
        # built fine.
        entries = []
        for path in SCHEMA_CACHE_DIR.glob(pattern):
            try:
                entries.append((path, path.stat().st_mtime))
            except FileNotFoundError:
                continue
        return entries

    templates = sorted(snapshot("schema-*.sqlite3"), key=lambda entry: entry[1], reverse=True)
    for stale, _mtime in templates[_SCHEMA_CACHE_KEEP:]:
        stale.unlink(missing_ok=True)
    cutoff = time.time() - 3600
    for orphan, mtime in snapshot("*.sqlite3.tmp"):
        if mtime < cutoff:
            orphan.unlink(missing_ok=True)


@contextmanager
def _migrate_replaced_by_restore(template: Path) -> Iterator[None]:
    """Swap ``call_command("migrate", ...)`` for a template restore.

    ``create_test_db`` imports ``call_command`` from
    ``django.core.management`` at call time, so rebinding the module
    attribute is the reliable seam. Every other command (e.g.
    ``createcachetable``) passes through untouched.

    If the template turns out unreadable, concurrently deleted, or empty,
    the target in-memory DB is discarded (closing an in-memory SQLite DB
    destroys it), the template is deleted, and the real ``migrate`` runs —
    the next run rebuilds the cache.
    """
    from django.core import management  # noqa: PLC0415

    real_call_command = management.call_command

    def call_command_with_cached_schema(name: Any, *args: Any, **kwargs: Any) -> Any:
        # Django management-command name, not a domain identifier. Only the
        # default alias's template is ever dumped, so only its migrate call
        # is intercepted — a hypothetical second test DB alias falls through
        # to a real migrate rather than silently receiving default's schema.
        if name == "migrate" and kwargs.get("database", DEFAULT_DB_ALIAS) == DEFAULT_DB_ALIAS:  # noqa: STRING_LITERAL
            try:
                _restore_sqlite_from_template(DEFAULT_DB_ALIAS, template)
                return None
            except sqlite3.Error:
                from django.db import connections  # noqa: PLC0415

                connections[DEFAULT_DB_ALIAS].close()
                template.unlink(missing_ok=True)
        return real_call_command(name, *args, **kwargs)

    management.call_command = call_command_with_cached_schema
    try:
        yield
    finally:
        management.call_command = real_call_command


def _noop() -> None:
    """No-op stub used as a ``__code__`` donor for PG-only refresh helpers."""


class SqliteTestRunner(TimedEvenniaTestRunner):
    """Test runner for the SQLite inner-loop tier.

    Extends the project's :class:`TimedEvenniaTestRunner` (which handles
    Evennia's ``_init()``, worker initialization, optional timing wrapper)
    and additionally replaces PG-only ``REFRESH MATERIALIZED VIEW``
    helpers with no-ops at ``setup_test_environment`` time. The patches
    persist for the lifetime of the test run.
    """

    def setup_test_environment(self, **kwargs: Any) -> None:
        """Install the SQLite-tier monkey-patches after Evennia/Django setup."""
        super().setup_test_environment(**kwargs)
        self._install_sqlite_noops()

    def setup_databases(self, **kwargs: Any) -> Any:
        """Create the test DB from the schema-template cache when possible.

        Cache hit: ``migrate`` (the ~20s schema build) is replaced by a
        sub-second SQLite backup-API restore of the cached template. Cache
        miss: the schema builds normally, then the result is saved as the
        new template. ``ARX_SCHEMA_CACHE=0`` bypasses the cache.
        """
        if os.environ.get("ARX_SCHEMA_CACHE") == "0":
            return super().setup_databases(**kwargs)
        template = SCHEMA_CACHE_DIR / f"schema-{_schema_fingerprint()}.sqlite3"
        if template.exists():
            if self.verbosity >= 1:
                print(f"Restoring cached test schema ({template.name}).")
            with _migrate_replaced_by_restore(template):
                return super().setup_databases(**kwargs)
        old_config = super().setup_databases(**kwargs)
        _dump_sqlite_to_template(DEFAULT_DB_ALIAS, template)
        _prune_schema_cache()
        if self.verbosity >= 1:
            print(f"Cached test schema for reuse ({template.name}).")
        return old_config

    @staticmethod
    def _install_sqlite_noops() -> None:
        """Replace the three refresh helpers' ``__code__`` with the no-op body.

        Imported lazily inside the method so this module can be imported
        before Django's app registry is ready (settings load earlier than
        models).
        """
        from world.areas.models import refresh_area_closure  # noqa: PLC0415
        from world.codex.models import refresh_codex_breadcrumbs  # noqa: PLC0415
        from world.societies.models import refresh_legend_views  # noqa: PLC0415

        refresh_legend_views.__code__ = _noop.__code__
        refresh_codex_breadcrumbs.__code__ = _noop.__code__
        refresh_area_closure.__code__ = _noop.__code__
