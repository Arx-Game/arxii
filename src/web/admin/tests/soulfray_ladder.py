"""Shared Soulfray ladder fixtures for the Soulfray Stage Builder tests (#4089).

Call ``build_ladder``/``stock``/``shared_pool`` only from ``setUpTestData``:
``stock`` re-points a stage's pool, and a row re-pointed inside a test method
is an identity-mapped instance whose Python attribute outlives the rollback.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from django.test import TestCase
from evennia.accounts.models import AccountDB

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.models import ConsequencePool
from world.checks.factories import ConsequenceFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.models import ConditionStage, ConditionTemplate
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import CheckOutcome

STAGE_SPECS = (
    ("Fraying", 1),
    ("Tearing", 6),
    ("Ripping", 16),
    ("Sundering", 36),
    ("Unravelling", 66),
)
OUTCOME_SPECS = (
    ("Critical Failure", -3),
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 3),
)


@dataclass
class Ladder:
    template: ConditionTemplate
    stages: list[ConditionStage]
    outcomes: dict[str, CheckOutcome]

    def stage(self, name: str) -> ConditionStage:
        return next(stage for stage in self.stages if stage.name == name)

    @property
    def outcome_list(self) -> list[CheckOutcome]:
        return sorted(self.outcomes.values(), key=lambda outcome: outcome.success_level)


def build_ladder() -> Ladder:
    template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
    stages = [
        ConditionStageFactory(
            condition=template,
            stage_order=order,
            name=name,
            severity_threshold=threshold,
            rounds_to_next=None,
            description="PLACEHOLDER stage warning",
        )
        for order, (name, threshold) in enumerate(STAGE_SPECS, start=1)
    ]
    outcomes = {
        name: CheckOutcomeFactory(name=name, success_level=level) for name, level in OUTCOME_SPECS
    }
    return Ladder(template=template, stages=stages, outcomes=outcomes)


def stock(  # noqa: PLR0913 - every knob is a scenario the tests name explicitly
    stage: ConditionStage,
    ladder: Ladder,
    *,
    tiers: tuple[str, ...] | None = None,
    weight: int = 3,
    lethal_tier: str | None = None,
    lethal_weight: int = 1,
    parent: ConsequencePool | None = None,
) -> ConsequencePool:
    """Give ``stage`` its own pool: one row per tier labelled "<stage> <tier>", plus a lethal
    row."""
    pool = ConsequencePoolFactory(name=f"Soulfray - {stage.name}", parent=parent)
    for name in tiers if tiers is not None else tuple(ladder.outcomes):
        ConsequencePoolEntryFactory(
            pool=pool,
            consequence=ConsequenceFactory(
                outcome_tier=ladder.outcomes[name], label=f"{stage.name} {name}", weight=weight
            ),
        )
    if lethal_tier is not None:
        ConsequencePoolEntryFactory(
            pool=pool,
            consequence=ConsequenceFactory(
                outcome_tier=ladder.outcomes[lethal_tier],
                label=f"{stage.name} death",
                weight=lethal_weight,
                character_loss=True,
            ),
        )
    stage.consequence_pool = pool
    stage.save(update_fields=["consequence_pool"])
    return pool


def shared_pool(
    ladder: Ladder, tiers: tuple[str, ...], name: str = "Soulfray - common"
) -> ConsequencePool:
    """A parentless pool no stage uses, with one row per tier labelled "common <tier>"."""
    pool = ConsequencePoolFactory(name=name)
    for tier in tiers:
        ConsequencePoolEntryFactory(
            pool=pool,
            consequence=ConsequenceFactory(
                outcome_tier=ladder.outcomes[tier], label=f"common {tier}", weight=1
            ),
        )
    return pool


def make_superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class SoulfrayBuilderTestCase(TestCase):
    """Shared base for the builder's authoring test modules (#4089, Tasks 4-5).

    Gives every subclass a logged-in-able superuser and a built ladder; a
    subclass's own ``setUpTestData`` (calling ``super().setUpTestData()``)
    adds whatever pools, rows and credit fixtures its own tests need.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.author = make_superuser("sfauthor")
        cls.ladder = build_ladder()


class _FormValues(HTMLParser):
    """Collect what a browser would post from one ``<form id=...>``, skipping ``<template>``."""

    def __init__(self, form_id: str) -> None:
        super().__init__()
        self.form_id = form_id
        self.in_form = False
        self.template_depth = 0
        self.values: dict[str, list[str]] = {}
        self._select: str | None = None
        self._select_multiple = False
        self._textarea: str | None = None
        self._text: list[str] = []

    def handle_starttag(  # noqa: C901 - test-only HTML parsing, one branch per tag/attr kind
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attr = dict(attrs)
        if tag == "form" and attr.get("id") == self.form_id:
            self.in_form = True
            return
        if not self.in_form:
            return
        if tag == "template":
            self.template_depth += 1
            return
        if self.template_depth:
            return
        name = attr.get("name")
        if tag == "input" and name:
            kind = attr.get("type", "text")
            if kind in {"submit", "button"}:
                return
            if kind == "checkbox":
                if "checked" in attr:
                    self.values.setdefault(name, []).append(attr.get("value") or "on")
                return
            self.values.setdefault(name, []).append(attr.get("value") or "")
        elif tag == "select" and name:
            self._select = name
            self._select_multiple = "multiple" in attr
            self.values.setdefault(name, [])
        elif tag == "option" and self._select and "selected" in attr:
            self.values[self._select].append(attr.get("value") or "")
        elif tag == "textarea" and name:
            self._textarea = name
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "template" and self.template_depth:
            self.template_depth -= 1
        elif self.template_depth:
            return
        elif tag == "form" and self.in_form:
            self.in_form = False
        elif tag == "select" and self._select:
            if not self._select_multiple and not self.values[self._select]:
                self.values[self._select] = [""]
            self._select = None
        elif tag == "textarea" and self._textarea:
            self.values[self._textarea] = ["".join(self._text)]
            self._textarea = None

    def handle_data(self, data: str) -> None:
        if self._textarea and not self.template_depth:
            self._text.append(data)


def form_values(html: str, form_id: str = "soulfray-stage-form") -> dict[str, list[str]]:
    """The POST a browser would send for ``form_id`` as rendered, ready to edit and post."""
    parser = _FormValues(form_id)
    parser.feed(html)
    return parser.values
