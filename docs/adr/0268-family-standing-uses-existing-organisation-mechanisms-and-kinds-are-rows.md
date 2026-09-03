# ADR-0268: Family standing is expressed through existing organisation mechanisms, and family kinds are rows

**Status:** Accepted (#3617, 2026-09-03, TehomCD ruling). Related ADR-0010, ADR-0101, ADR-0238, ADR-0251.

**Context.** Designing per-beginning Upbringings raised what a family with influence *is*: its kind (noble, crime, Humble, merchant, clan), who it answers to, who backs it, and culture-specific facts (a Letter of Marque, a house quiddity). Each is a temptation to add a column or model per case.

**Decision.** No bespoke structure per case. Kind is a `FamilyKind` row (`Family.kind` FK replaces the `family_type` code list; `styles_as_house` is the one behaviour code reads). Subordination is `FealtyEdge` or `Organization.parent_org`. Patronage and alliance are `OrgPact` on an authored `PactKind`. Culture-specific facts are `OrganizationAspect` (variants) or `OrganizationFeature` (flat facts). Standing at CG is `Family.influence`, staff-set. Families that hold authority over the world are staff-authored in alpha; players may only name families with influence 0. The mapping is a directive: `docs/systems/family-authoring-recipes.md`, one test per recipe.

**Rejected.** A fourth `FamilyType` enum member per new kind (a deploy per kind). A `patron` FK or `subordinate_to` field on Family (duplicates pacts and fealty). A boolean per culture-specific fact (aspects and features already generalise it). A player path that founds influential families (a future issue, not alpha).
