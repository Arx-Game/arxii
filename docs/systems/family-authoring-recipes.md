# Family authoring recipes (staff and agents)

Directives for authoring anything family-side: an Upbringing for a beginning, a family
that holds influence, who it answers to, who backs it, and the culture-specific facts
that mark it. Every recipe maps onto rows that exist today. **If a need seems to call
for a new model, column or flag, stop: find the recipe here first** (ADR-0268). Each
recipe is proven by the test of the same number in
`src/world/character_creation/tests/test_upbringing_recipes.py`.

Vocabulary: **Upbringing** (`OriginTemplate` row; the card a player picks in Lineage),
**Prompt** (`OriginTemplateSlot`), **Choice** (`OriginTemplateSlotChoice`), **Family
Path** (claim, name, or none), **Family Kind** (`FamilyKind` row), **Influence**
(`Family.influence`). The code keeps the `OriginTemplate*` names (Decision 4 on #3617).

## Recipe 1: an Upbringing for a beginning
Admin > Character Creation > Upbringings > Add. Set beginning, name, frame text, CG cost
(0 = free, negative refunds), trust required, the family paths it allows, the kinds it
offers on the claim path (empty = all), and the kind a named family gets. Then add
Prompts (each: question, example, required, which path it applies to, whether a
write-in is allowed) and, on a pick-list prompt, its Choices with flat and
per-influence costs. Do not: add a column to Beginnings; the old family-known switch is
gone and its job is the paths.

## Recipe 2: an orphan Upbringing
Same as Recipe 1 with only the none path on, plus prompts applying to the none path
("How did you survive?"). The tarot surname ritual runs automatically on that path.
Do not: bring back an orphan flag.

## Recipe 3: an amnesiac beginning (Sleeper)
One Upbringing named "Unknown", none path, no prompts. Every active beginning must have
at least one active Upbringing or the Game Ops dashboard lists it under "Beginnings
without an Upbringing".

## Recipe 4: a staff-authored family with influence
Admin > Roster > Families > Add: name, kind, influence (0 = holds no authority; only
staff-authored families are ever above 0), playable. Then Admin > Societies >
Organizations > Add with `family` set to it (org type = a row; add one if none fits).
Do not: give players a path that creates a family with influence (Decision 3 on #3617).

## Recipe 5: a subordinate family or clan
Political fealty between houses: a `FealtyEdge` (vassal org -> liege org). A wing or
branch of the same body: the org's `parent_org`. Do not: add a "subordinate_to" field.

## Recipe 6: a patron or ally
Add a `PactKind` row if none fits (e.g. "Patronage" with the levers it carries), then an
`OrgPact` between the two organisations, ratified. Do not: add a patron FK to Family.

## Recipe 7: a culture-specific fact (quiddity, Letter of Marque)
A fact with variants: a `HouseAspectDefinition` (the question) with `HouseAspectOption`
rows, stamped on the org as `OrganizationAspect`. A flat fact: a `HouseFeature` (with a
stable slug code can check) stamped as `OrganizationFeature`. Both can be set directly
on staff-authored houses. Do not: add a boolean per fact.

## Recipe 8: servants of a powerful family
An Upbringing with the claim path, offering the kinds of the great houses, and a
pick-list prompt on the claim path ("Your place in their household?") whose choices
carry per-influence costs. The price scales with the claimed family's influence.

## Recipe 9: a new family kind (the Humble, a merchant house, a clan)
Admin > Roster > Family Kinds > Add. Tick "styles as house" if its orgs should be named
"House <name>"; nobiliary particles come separately, from NobiliaryParticle rows
authored per realm and kind (add one if the realm should mark this kind). Then pick the
kind on the Upbringings that should offer it. Do not: edit a code list.

## Pricing at a glance
Cost of an Upbringing = its flat cost + for each picked choice (flat + per-influence x
the claimed family's influence; influence is 0 on the name and none paths).
