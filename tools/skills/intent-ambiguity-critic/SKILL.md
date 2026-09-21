---
name: intent-ambiguity-critic
description: Finds outcome-changing ambiguity in a claimed issue before technical design. Use in the standard or heavyweight discovery lane; do not use for clearly bounded lightweight work.
compatibility: project-local
---

# Intent ambiguity critic

Review the issue, its comments, relevant code context, and the root agent's
inferred outcome. Find assumptions that could change what users experience, who
can act, what success means, the priority, or the future commitment. Treat issue
labels and the reporter's wording as evidence, not as authority for product taste.

For each finding, report:

- **Ambiguity:** the two or more plausible interpretations;
- **Evidence:** issue text, comment, code, scenario, or provenance;
- **Affected outcome:** what changes under each interpretation;
- **Consequences:** cost, risk, and user impact of each option;
- **Confidence:** high, medium, or low;
- **Focused question:** one question the stakeholder can answer.

Separate observations, proposals, and ratified decisions. Identify reporter,
affected user, implementer, and product decision-maker when they differ. Do not
choose product priorities or silently resolve the question. If no outcome-changing
ambiguity remains, say so and name the evidence checked.
