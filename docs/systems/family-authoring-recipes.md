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
(`Family.influence`), **Family Template** (`HouseTemplate` row; the type a named
family is built from), **Vacancy** (an opening on a staff family's org; see Recipes
11-12). The code keeps the `OriginTemplate*` and `HouseTemplate` names (Decision 4 on
#3617; #3648).

## Recipe 1: an Upbringing for a beginning
Admin > Societies > Family Templates > Add: kind, `org_type` (resolves against the
prerequisite anchors, which now include `commoner_family` alongside `noble_family`),
society, features, aspect definitions, and served house choices (staff houses this
family's kind may declare it served; blank = the question is not offered). Then
Admin > Character Creation > Upbringings > Add: beginning, name, frame text, CG cost
(0 = free, negative refunds), trust required, the family paths it allows, the kinds it
offers on the claim path (empty = all), and, under **Family Templates**, tick the
templates its name path offers (one auto-picks; more than one shows a picker). Add
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
Superseded by Recipes 11 and 12 (#3648): a claim-path role priced by influence is now a
kin or retainer **Vacancy** on the staff family's org, not a pick-list prompt. See
those recipes below.

## Recipe 9: a new family kind (the Humble, a merchant house, a clan)
Admin > Roster > Family Kinds > Add. Tick "styles as house" if its orgs should be named
"House <name>"; nobiliary particles come separately, from NobiliaryParticle rows
authored per realm and kind (add one if the realm should mark this kind). Then pick the
kind on the Upbringings that should offer it. Do not: edit a code list.

## Recipe 10: a Family Template on the name path
Admin > Societies > Family Templates > Add (as Recipe 1): kind, `org_type`, society,
aspect definitions and their options, features, served house choices. The template's
`name_pattern` (default `[A-Z][a-z]{2,19}`, a full-match regex) gates the family name a
player may pick; the default matches only a single title-case word, so a template
that wants a multi-word or apostrophized name (e.g. a Caretaker household name with a
particle) needs a looser pattern, such as `[A-Z][A-Za-z' -]{2,39}`, authored on that
template. A malformed pattern is a staff error, not a player one: it surfaces to the
player as "This family template's naming rule is misconfigured; tell staff" rather
than crashing. Tick the template under an Upbringing's **Family Templates**. Every
named family of that type comes out shaped the same: same kind, same org type, same
aspect questions, same served-house options.

## Recipe 11: a kin Vacancy backed by a pool
On a staff family's Organization admin page, add a Vacancy inline (or via Admin >
Societies > Vacancies > Add): name, description, link a `KinSlotPool` on that family
(`kin_pool`), set `importance` (how much the family cares) and `presumed_importance`
(what outsiders assume), price (`cg_point_cost` flat, `cost_per_influence` per point
of the family's influence), and `count_remaining` (openings left). A Vacancy with a
`kin_pool` or `kin_node` set is a **kin** Vacancy (`basis == "kin"`): claiming the
staff family on the claim path requires taking it when the family offers one, in place
of the free kin-slot picker. Cost = `cg_point_cost + cost_per_influence * family.influence`.

## Recipe 12: a standing retainer Vacancy
Same admin path as Recipe 11, but leave `kin_pool`/`kin_node` unset (a **retainer**
Vacancy, `basis == "retainer"`) and leave `count_remaining` blank: a standing Vacancy
is always open, never decremented. A retainer Vacancy is reachable from any family
path (via the Service panel) as long as it is not the draft's own claimed family's
org, the realm matches, the Upbringing is allowed, and trust is met.

## Pricing at a glance
Cost of an Upbringing = its flat cost + for each picked choice (flat + per-influence x
the claimed family's influence; influence is 0 on the name and none paths) + the
selected Vacancy's cost (flat + per-influence x the **Vacancy's** family's influence,
ADR-0269 extended by ADR-0273).

## Worked examples (illustrative names; not shipped content)

**Caretaker (Arx).** Family Template "Caretaker Household": kind Commoner, `org_type`
`commoner_family`, society Arx, no liege, no served house choices; aspect definition
"What did your family keep?" (granaries, aqueducts, watch rolls, archive, gates,
bridges). Upbringing "Raised to a Charge": name path only, offers Caretaker Household.
No Vacancies; the family's identity lives entirely on the org aspects.

**A crime family in Salvation.** Staff family "the Marrow" (Recipe 4: kind Crime,
influence 5, org type gang) with a "House Vice" `OrganizationAspect` (Recipe 7).
Vacancies: "Low thug" (retainer, importance 1/presumed 1, cost 0, standing); "Enforcer"
(retainer, 3/2, 2 + 1 per influence, count 3); "The Matriarch's niece" (kin via a
pool, 2/5, 1 + 1 per influence, count 1); "Counsel" (retainer, 5/1, 3 + 2 per
influence, count 1, `allowed_upbringings` restricted to a schooled Upbringing).

**Infernal Nobility.** The house org already carries its House Quiddity (Recipe 7).
Vacancies: "Third daughter" (kin via a pool, 1/5, 1 + 1 per influence); "Heir
presumptive" (kin via a named appable node, 5/5, 5 + 3 per influence, count 1, trust
2); "Master-at-arms" (retainer, 4/3, 2 + 1 per influence, count 1); "Household guard"
(retainer, 1/1, cost 0, standing). Founding a house behind a set-aside title is the
unchanged noble title-claim path (#1884 Phase D); Vacancies only cover joining an
existing house.

**Reavers.** Family Kind "Crew" (Recipe 9). Family Template "Reaver Crew": kind Crew,
org type gang (or an authored crew type), society Inferna, served house choices set to
the staff-authored captains' orgs; aspect definition "What does your crew take?".
Upbringing "Raised on the Deck": name path, offers Reaver Crew. A player names the
crew, answers the aspect, declares which captain it served (fealty via the served
house), and may take a standing retainer Vacancy "Deckhand" (1/1, cost 0) on that
captain's org: the served-house-plus-retainer combination.
