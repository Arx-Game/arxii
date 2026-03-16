"""
One-off introspection script for generating MODEL_MAP.md content.
Run via: uv run python tools/introspect_models.py > docs/systems/MODEL_MAP.md

Also importable: call write_model_map() to write directly to file.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

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

_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "systems" / "MODEL_MAP.md"


def _ensure_django_setup() -> None:
    import django  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    if settings.configured:
        return

    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    os.chdir(src_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    django.setup()


def get_fk_info(field: object) -> str:
    related_model = field.related_model  # type: ignore[attr-defined]
    app = related_model._meta.app_label  # noqa: SLF001
    return f"{app}.{related_model.__name__}"


def get_field_info(field: object) -> tuple[str | None, str | None]:
    if not (hasattr(field, "related_model") and field.related_model):
        if not field.auto_created and hasattr(field, "get_internal_type"):  # type: ignore[attr-defined]
            return "field", field.name  # type: ignore[attr-defined]
        return None, None

    if field.one_to_many or field.many_to_many:  # type: ignore[attr-defined]
        if hasattr(field, "field"):
            app = field.related_model._meta.app_label  # type: ignore[attr-defined]  # noqa: SLF001
            source = f"{app}.{field.related_model.__name__}"  # type: ignore[attr-defined]
            accessor = field.get_accessor_name()  # type: ignore[attr-defined]
            return "reverse", f"{accessor} <- {source}"
    elif field.many_to_one or field.one_to_one:  # type: ignore[attr-defined]
        target = get_fk_info(field)
        fk_type = "OneToOne" if field.one_to_one else "FK"  # type: ignore[attr-defined]
        null = " (nullable)" if field.null else ""  # type: ignore[attr-defined]
        return "fk", f"{field.name} -> {target} [{fk_type}]{null}"  # type: ignore[attr-defined]
    elif hasattr(field, "m2m_field"):
        target = get_fk_info(field)
        return "fk", f"{field.name} -> {target} [M2M]"  # type: ignore[attr-defined]

    return None, None


def introspect_app(app_label: str) -> dict | None:
    import importlib  # noqa: PLC0415
    import inspect  # noqa: PLC0415

    from django.apps import apps  # noqa: PLC0415

    try:
        app_config = apps.get_app_config(app_label.split(".")[-1])
    except LookupError:
        return None

    result: dict = {"app": app_label, "models": [], "service_functions": []}

    for model in app_config.get_models():
        model_info: dict = {
            "name": model.__name__,
            "fks": [],
            "reverse_relations": [],
        }

        for field in model._meta.get_fields():  # noqa: SLF001
            kind, info = get_field_info(field)
            if kind == "fk":  # noqa: STRING_LITERAL
                model_info["fks"].append(info)
            elif kind == "reverse":  # noqa: STRING_LITERAL
                model_info["reverse_relations"].append(info)

        result["models"].append(model_info)

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


def format_output(data: dict) -> str:
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


def _generate_content() -> str:
    lines = [
        "# Arx II Model Introspection Report",
        "# Generated for CLAUDE.md enrichment\n",
    ]
    for app_label in sorted(TARGET_APPS):
        data = introspect_app(app_label)
        if data and (data["models"] or data["service_functions"]):
            lines.append(format_output(data))
    return "\n".join(lines)


def write_model_map(output_path: Path | None = None) -> None:
    _ensure_django_setup()
    content = _generate_content()
    target = output_path or _DEFAULT_OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    _ensure_django_setup()
    print(_generate_content())
