"""One-off introspection script for generating MODEL_MAP.md content.
Run via: uv run python tools/introspect_models.py > docs/systems/MODEL_MAP.md

Also importable: call write_model_map() to write directly to file.

#2906 collapsed 66 ``world.*`` Django apps (+ 27 models folded in from
``actions``/``flows``/``behaviors``/``evennia_extensions``/``web.admin`` via an
explicit ``Meta.app_label``) into a single app: package ``world``, label
``arxii``. Model introspection below therefore queries that ONE app config
once, then groups the result by authoring *domain*
(``core.app_domains.domain_of``) for the doc's section headers — there is no
longer a one-Django-app-per-domain list to loop over. Service-function
discovery still walks real importable packages (a domain has no "services"
of its own; a package does), so that part keeps a package list — but it is
auto-discovered for everything under ``world/`` rather than hand-maintained,
since a hand-maintained 66-entry list is exactly what silently rotted into a
no-op the moment the collapse landed (every entry raised ``LookupError``
against the single surviving app, and a bare ``except`` swallowed it).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "src"
_DEFAULT_OUTPUT = _REPO_ROOT / "docs" / "systems" / "MODEL_MAP.md"

# The single Django app label every first-party model shares since #2906.
MODEL_APP_LABEL = "arxii"

# Packages outside ``world/`` whose models fold into ``arxii`` too (#2906)
# and/or carry their own ``services`` module. Unlike ``world/*``, these are
# not siblings under one directory, so they can't be auto-discovered the
# same way and stay a short, hand-owned list.
EXTRA_SERVICE_PACKAGES = ["actions", "flows", "behaviors", "evennia_extensions", "web.admin"]


def _discover_world_packages() -> list[str]:
    """Return ``world.<name>`` for every real sub-package under ``world/``.

    Auto-discovered, not hand-maintained: walks the actual directory tree so
    a new ``world/<name>/`` package is picked up automatically and this list
    can't silently rot the way the old hand-written ``TARGET_APPS`` did.
    """
    world_dir = _SRC_ROOT / "world"
    return sorted(
        f"world.{child.name}"
        for child in world_dir.iterdir()
        if child.is_dir() and (child / "__init__.py").is_file()
    )


def _domain_for_package(package: str) -> str:
    """Forward mapping: dotted package path -> authoring domain.

    Mirrors ``core.app_domains.domain_of``'s own convention deliberately
    (rather than importing it) because that function maps a *model class* to
    a domain string, and this needs the same transform applied to a *package
    path* instead.
    """
    if package.startswith("world."):
        return package.split(".")[1]
    return "web_admin" if package == "web.admin" else package


def _package_for_domain(domain: str) -> str:
    """Inverse of ``_domain_for_package``, for domains with no matching package."""
    if domain == "web_admin":
        return "web.admin"
    if (_SRC_ROOT / "world" / domain).is_dir():
        return f"world.{domain}"
    return domain


def _ensure_django_setup() -> None:
    import django  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    if settings.configured:
        return

    src_dir = str(_SRC_ROOT)
    os.chdir(src_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    django.setup()


def _domain_of(model: object) -> str:
    from core.app_domains import domain_of  # noqa: PLC0415

    return domain_of(model)  # type: ignore[arg-type]


def get_fk_info(field: object) -> str:
    related_model = field.related_model  # type: ignore[attr-defined]
    return f"{_domain_of(related_model)}.{related_model.__name__}"


def get_field_info(field: object) -> tuple[str | None, str | None]:
    if not (hasattr(field, "related_model") and field.related_model):
        if not field.auto_created and hasattr(field, "get_internal_type"):  # type: ignore[attr-defined]
            return "field", field.name  # type: ignore[attr-defined]
        return None, None

    # Reverse relations (ManyToOneRel / OneToOneRel / ManyToManyRel) are auto-created by
    # Django on the *target* side and are non-concrete; they expose ``get_accessor_name()``.
    # Classify ALL of them as reverse pointers — crucially including reverse OneToOne, which
    # has ``one_to_one=True`` and so was previously mis-read as a forward FK on the target
    # model (#1204). ``auto_created and not concrete`` excludes auto-created *forward*
    # fields (the ``id`` PK, multi-table-inheritance parent-link OneToOnes), which are
    # concrete columns and must stay on the forward side.
    if field.auto_created and not field.concrete:  # type: ignore[attr-defined]
        source = f"{_domain_of(field.related_model)}.{field.related_model.__name__}"  # type: ignore[attr-defined]
        accessor = field.get_accessor_name()  # type: ignore[attr-defined]
        return "reverse", f"{accessor} <- {source}"

    # Forward relations.
    if field.many_to_one or field.one_to_one:  # type: ignore[attr-defined]
        target = get_fk_info(field)
        fk_type = "OneToOne" if field.one_to_one else "FK"  # type: ignore[attr-defined]
        null = " (nullable)" if field.null else ""  # type: ignore[attr-defined]
        return "fk", f"{field.name} -> {target} [{fk_type}]{null}"  # type: ignore[attr-defined]
    if field.many_to_many:  # type: ignore[attr-defined]
        # Forward ManyToManyField was silently dropped before: ``many_to_many`` was caught
        # by the reverse branch first, then failed its inner guard and fell through to
        # ``return None``. The map emitted zero forward M2M edges despite many in code (#1204).
        target = get_fk_info(field)
        return "fk", f"{field.name} -> {target} [M2M]"  # type: ignore[attr-defined]

    return None, None


def _gather_models_by_domain() -> dict[str, list[dict]]:
    """Introspect the single ``arxii`` app ONCE, grouped by authoring domain."""
    from django.apps import apps  # noqa: PLC0415

    app_config = apps.get_app_config(MODEL_APP_LABEL)
    by_domain: dict[str, list[dict]] = {}

    for model in app_config.get_models():
        model_info: dict = {"name": model.__name__, "fks": [], "reverse_relations": []}
        for field in model._meta.get_fields():  # noqa: SLF001
            kind, info = get_field_info(field)
            if kind == "fk":
                model_info["fks"].append(info)
            elif kind == "reverse":
                model_info["reverse_relations"].append(info)
        by_domain.setdefault(_domain_of(model), []).append(model_info)

    for models_list in by_domain.values():
        models_list.sort(key=lambda m: m["name"])
    return by_domain


def _gather_service_functions(package: str) -> list[str]:
    import importlib  # noqa: PLC0415
    import inspect  # noqa: PLC0415

    module_path = f"{package}.services"
    try:
        services_mod = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # Tolerate ONLY "this package has no services module at all". A genuine
        # import failure inside an existing services.py (bad import, syntax
        # error, missing dependency) must surface loudly instead of vanishing
        # the way the old bare ``except (ImportError, ModuleNotFoundError)``
        # let every dead TARGET_APPS entry vanish into a silent no-op (#2906).
        if exc.name != module_path:
            raise
        return []

    functions = []
    for name, obj in inspect.getmembers(services_mod, inspect.isfunction):
        if name.startswith("_"):
            continue
        # Skip helpers imported into the services module (e.g. dataclasses.field,
        # typing.cast) — document only functions defined in project source, not
        # stdlib/third-party callables that happen to be importable here.
        func_mod = sys.modules.get(obj.__module__)
        # getattr-with-default: func_mod may be None or a module without __file__.
        func_file = getattr(func_mod, "__file__", "") or ""  # noqa: GETATTR_LITERAL
        if "site-packages" in func_file or "/lib/python" in func_file:
            continue
        # Render the signature deterministically: repr() of a sentinel-object
        # default (``object()`` / ``dataclasses._MISSING_TYPE``) embeds a
        # per-process memory address; strip it so regeneration is reproducible.
        sig = re.sub(r" at 0x[0-9a-fA-F]+", "", str(inspect.signature(obj)))
        doc = (inspect.getdoc(obj) or "").split("\n")[0]
        functions.append(f"{name}{sig}" + (f" - {doc}" if doc else ""))
    return functions


def format_output(header: str, models_list: list[dict], service_functions: list[str]) -> str:
    if not models_list and not service_functions:
        return ""

    lines = [f"\n## {header}\n"]

    for model in models_list:
        lines.append(f"### {model['name']}")
        if model["fks"]:
            lines.append("**Foreign Keys:**")
            lines.extend(f"  - {fk}" for fk in model["fks"])
        if model["reverse_relations"]:
            lines.append("**Pointed to by:**")
            lines.extend(f"  - {rev}" for rev in model["reverse_relations"])
        lines.append("")

    if service_functions:
        lines.append("### Service Functions")
        lines.extend(f"- `{fn}`" for fn in service_functions)
        lines.append("")

    return "\n".join(lines)


def _generate_content() -> str:
    lines = [
        "# Arx II Model Introspection Report",
        "# Generated for CLAUDE.md enrichment\n",
    ]
    models_by_domain = _gather_models_by_domain()
    packages = sorted(set(_discover_world_packages()) | set(EXTRA_SERVICE_PACKAGES))

    covered_domains: set[str] = set()
    for package in packages:
        domain = _domain_for_package(package)
        covered_domains.add(domain)
        models_list = models_by_domain.get(domain, [])
        service_functions = _gather_service_functions(package)
        lines.append(format_output(package, models_list, service_functions))

    # A domain with models but no package above would mean the earlier
    # discovery missed something real -- render it rather than drop it, since
    # a silent drop here is exactly the #2906 task 6 bug this rewrite fixes.
    lines.extend(
        format_output(_package_for_domain(domain), models_by_domain[domain], [])
        for domain in sorted(set(models_by_domain) - covered_domains)
    )

    return "\n".join(lines)


def write_model_map(output_path: Path | None = None) -> None:
    _ensure_django_setup()
    content = _generate_content()
    target = output_path or _DEFAULT_OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    _ensure_django_setup()
    # Content already ends with a single newline; use end="" so the `> file`
    # redirect doesn't append a second one (which end-of-file-fixer would strip,
    # churning the committed doc on every regeneration).
    print(_generate_content(), end="")
