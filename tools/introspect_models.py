# ruff: noqa: E402
"""
One-off introspection script for generating MODEL_MAP.md content.
Run via: uv run python tools/introspect_models.py > docs/systems/MODEL_MAP.md

Outputs per-app model info: fields, FKs, reverse relations, and service function signatures.
"""

import os
from pathlib import Path
import sys

# Setup Django - must run from src/ dir for .env loading
src_dir = str(Path(__file__).resolve().parent.parent / "src")
os.chdir(src_dir)
sys.path.insert(0, src_dir)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")

import django

django.setup()

import importlib
import inspect

from django.apps import apps

# Apps we care about (under src/)
TARGET_APPS = [
    "actions",
    "behaviors",
    "commands",
    "conditions",
    "evennia_extensions",
    "flows",
    "typeclasses",
    "world.attempts",
    "world.character_creation",
    "world.character_sheets",
    "world.checks",
    "world.classes",
    "world.codex",
    "world.conditions",
    "world.goals",
    "world.magic",
    "world.mechanics",
    "world.progression",
    "world.realms",
    "world.relationships",
    "world.roster",
    "world.scenes",
    "world.skills",
    "world.societies",
    "world.stories",
    "world.traits",
]


def get_fk_info(field):
    """Extract FK target info."""
    related_model = field.related_model
    app = related_model._meta.app_label  # noqa: SLF001
    return f"{app}.{related_model.__name__}"


def get_field_info(field):
    """Categorize a single field into fks, reverse_relations, or plain fields."""
    if not (hasattr(field, "related_model") and field.related_model):
        if not field.auto_created and hasattr(field, "get_internal_type"):
            return "field", field.name
        return None, None

    if field.one_to_many or field.many_to_many:
        if hasattr(field, "field"):
            app = field.related_model._meta.app_label  # noqa: SLF001
            source = f"{app}.{field.related_model.__name__}"
            accessor = field.get_accessor_name()
            return "reverse", f"{accessor} <- {source}"
    elif field.many_to_one or field.one_to_one:
        target = get_fk_info(field)
        fk_type = "OneToOne" if field.one_to_one else "FK"
        null = " (nullable)" if field.null else ""
        return "fk", f"{field.name} -> {target} [{fk_type}]{null}"
    elif hasattr(field, "m2m_field"):
        target = get_fk_info(field)
        return "fk", f"{field.name} -> {target} [M2M]"

    return None, None


def introspect_app(app_label):
    """Dump model info for an app."""
    try:
        app_config = apps.get_app_config(app_label.split(".")[-1])
    except LookupError:
        return None

    result = {"app": app_label, "models": [], "service_functions": []}

    for model in app_config.get_models():
        model_info = {"name": model.__name__, "fks": [], "reverse_relations": []}

        for field in model._meta.get_fields():  # noqa: SLF001
            kind, info = get_field_info(field)
            if kind == "fk":
                model_info["fks"].append(info)
            elif kind == "reverse":
                model_info["reverse_relations"].append(info)

        result["models"].append(model_info)

    # Try to find services.py
    module_path = app_label + ".services"
    try:
        services_mod = importlib.import_module(module_path)
        for name, obj in inspect.getmembers(services_mod, inspect.isfunction):
            if name.startswith("_"):
                continue
            sig = inspect.signature(obj)
            doc = (inspect.getdoc(obj) or "").split("\n")[0]
            result["service_functions"].append(f"{name}{sig}" + (f" — {doc}" if doc else ""))
    except (ImportError, ModuleNotFoundError):
        pass

    return result


def format_output(data):
    """Format introspection data as markdown."""
    if not data:
        return ""

    lines = [f"\n## {data['app']}\n"]

    for model in data["models"]:
        lines.append(f"### {model['name']}")
        if model["fks"]:
            lines.append("**Foreign Keys:**")
            lines.extend(f"  - {fk}" for fk in model["fks"])
        if model["reverse_relations"]:
            lines.append("**Pointed to by:**")
            lines.extend(f"  - {rev}" for rev in model["reverse_relations"])
        lines.append("")

    if data["service_functions"]:
        lines.append("### Service Functions")
        lines.extend(f"- `{fn}`" for fn in data["service_functions"])
        lines.append("")

    return "\n".join(lines)


# Main
print("# Arx II Model Introspection Report")
print("# Generated for CLAUDE.md enrichment\n")

for app_label in sorted(TARGET_APPS):
    data = introspect_app(app_label)
    if data and (data["models"] or data["service_functions"]):
        print(format_output(data))
