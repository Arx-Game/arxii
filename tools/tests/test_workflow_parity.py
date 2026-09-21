"""Keep Claude and Polytoken orchestration contracts aligned."""

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
RECIPES = [
    ROOT / "tools/skills/issue-to-merged-pr/SKILL.md",
    ROOT / "tools/skills/issue-to-merged-pr-polytoken/SKILL.md",
]


class WorkflowParityTests(unittest.TestCase):
    def test_both_recipes_name_the_same_discovery_states_and_gate(self) -> None:
        texts = [path.read_text() for path in RECIPES]
        required = {
            "discovery:lane=lightweight;state=complete",
            "state=awaiting-stakeholder",
            "spec:approved",
            "validate-discovery.sh",
            "product brief/PRD",
            "demo directions or screenshot variants",
            "implementation-quality-reviewer",
            "intent-ambiguity-critic",
            "scope-simplicity-critic",
            "selected/skipped",
        }
        for path, text in zip(RECIPES, texts, strict=True):
            missing = sorted(token for token in required if token not in text)
            self.assertEqual(missing, [], f"{path} is missing parity tokens: {missing}")

    def test_both_recipes_dispatch_the_same_narrow_reviewer_catalog(self) -> None:
        texts = [path.read_text() for path in RECIPES]
        reviewers = {
            "schema-shape-reviewer",
            "migration-reviewer",
            "blast-radius-reviewer",
            "mock-fidelity-reviewer",
            "outcome-delivery-reviewer",
            "typeclass-creation-reviewer",
            "derived-classifier-reviewer",
            "enumerated-set-reviewer",
            "portal-code-deploy-reviewer",
            "demo-fidelity-reviewer",
        }
        for reviewer in reviewers:
            self.assertTrue(all(reviewer in text for text in texts), reviewer)


if __name__ == "__main__":
    unittest.main()
