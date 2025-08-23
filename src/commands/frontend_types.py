"""Typed definitions for frontend command metadata."""

from typing import Dict, TypedDict


class ParamSchema(TypedDict, total=False):
    """Schema definition for a single command parameter."""

    type: str
    required: bool
    match: str
    widget: str
    options_endpoint: str


class UsageEntry(TypedDict, total=False):
    """Declarative usage entry for legacy Evennia commands."""

    prompt: str
    params_schema: Dict[str, ParamSchema]
    icon: str


class FrontendDescriptor(TypedDict):
    """Serialized usage descriptor consumed by the frontend."""

    action: str
    prompt: str
    params_schema: Dict[str, ParamSchema]
    icon: str
