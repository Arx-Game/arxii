"""The generations module is generated, never hand-edited: prove the renderer round-trips.

``src/world/migrations/_generations.py`` is what every regenerated migration imports
``REPLACED`` from (ADR-0272). It is written by ``render_generations_module`` and read
back by ``parse_generations_source`` without importing it, so the guard and the
``squashmigrations`` command can inspect it before Django is fully set up.
"""

from __future__ import annotations

import ast

from django.test import SimpleTestCase

from core_management.migration_generations import (
    GenerationsData,
    parse_generations_source,
    render_generations_module,
)


def _exec(source: str) -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "_generations.py", "exec"), namespace)  # noqa: S102 - our own template
    return namespace


class RenderGenerationsModuleTests(SimpleTestCase):
    def test_renders_valid_python_with_replaced_from_previous_generation(self) -> None:
        source = render_generations_module(
            current=2,
            generations={1: ["0001_initial", "0002_initial_part_2"]},
            commits={1: "abc123"},
        )
        assert isinstance(ast.parse(source), ast.Module)
        namespace = _exec(source)
        assert namespace["CURRENT"] == 2
        assert namespace["GENERATIONS"] == {1: ["0001_initial", "0002_initial_part_2"]}
        assert namespace["COMMITS"] == {1: "abc123"}
        assert namespace["REPLACED"] == [
            ("arxii", "0001_initial"),
            ("arxii", "0002_initial_part_2"),
        ]

    def test_generation_one_has_nothing_to_replace(self) -> None:
        namespace = _exec(render_generations_module(current=1, generations={}, commits={}))
        assert namespace["REPLACED"] == []

    def test_round_trip_through_parse(self) -> None:
        data = GenerationsData(
            current=3,
            generations={1: ["0001_initial"], 2: ["0001_g2_initial", "0104_persona_title"]},
            commits={1: "aaa", 2: "bbb"},
        )
        source = render_generations_module(data.current, data.generations, data.commits)
        assert parse_generations_source(source) == data

    def test_previous_names_is_the_generation_before_current(self) -> None:
        data = GenerationsData(current=2, generations={1: ["0001_initial"]}, commits={})
        assert data.previous_names == ["0001_initial"]
        assert GenerationsData(current=1).previous_names == []
